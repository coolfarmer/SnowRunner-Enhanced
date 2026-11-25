// Only completed read buffers are changed, before returning them to the game. The archive
// is opened read-only and held against writes for the lifetime of this process.
#include "startup_profile.h"
typedef LONG (NTAPI *StartupRead)(HANDLE,HANDLE,PVOID,PVOID,PVOID,PVOID,ULONG,PLARGE_INTEGER,PULONG);
static StartupRead startup_read;
static HANDLE startup_file = INVALID_HANDLE_VALUE;
static BY_HANDLE_FILE_INFORMATION startup_identity;
static volatile LONG startup_seen;
static volatile LONG64 startup_coverage[STARTUP_EDIT_COUNT];
static CRITICAL_SECTION startup_lock;
static const char *startup_state = "disabled";
static int configured_features, verified_features;

typedef BOOL (WINAPI *StartupCompleted)(HANDLE,LPOVERLAPPED,LPDWORD,BOOL);
static StartupCompleted startup_completed;
typedef struct { HANDLE file; PVOID io, buffer; ULONG size; ULONGLONG offset; } StartupPending;
static StartupPending startup_pending[32];

static void StartupPatch(PVOID buffer, ULONGLONG offset, ULONG_PTR count) {
    for (unsigned i=0; i<STARTUP_EDIT_COUNT; ++i) {
        const StartupEdit *edit=&startup_edits[i];
        if (!(configured_features & verified_features & edit->feature)) continue;
        ULONGLONG begin=max(offset,edit->offset), end=min(offset+count,edit->offset+edit->size);
        if(begin<end) {
            size_t dst=(size_t)(begin-offset), src=(size_t)(begin-edit->offset), n=(size_t)(end-begin);
            if(!memcmp((char *)buffer+dst,edit->before+src,n)) {
                memcpy((char *)buffer+dst,edit->after+src,n);
                LONG64 mask=((1LL<<n)-1)<<src;
                LONG64 seen=InterlockedOr64(&startup_coverage[i],mask)|mask;
                if(seen==(1LL<<edit->size)-1) InterlockedOr(&startup_seen,1L<<i);
            }
        }
    }
}

static LONG NTAPI StartupReadHook(HANDLE file,HANDLE event,PVOID apc,PVOID context,
        PVOID iosb,PVOID buffer,ULONG size,PLARGE_INTEGER offset,PULONG key) {
    DWORD incoming_error=GetLastError();
    LARGE_INTEGER position={0},zero={0};
    BY_HANDLE_FILE_INFORMATION identity;
    BOOL target=!apc && iosb && buffer && (!offset || offset->QuadPart>=0 || offset->QuadPart==-2) &&
        GetFileInformationByHandle(file,&identity) &&
        identity.dwVolumeSerialNumber==startup_identity.dwVolumeSerialNumber &&
        identity.nFileIndexHigh==startup_identity.nFileIndexHigh && identity.nFileIndexLow==startup_identity.nFileIndexLow;
    BOOL locked=target;
    StartupPending *pending=NULL;
    if(locked) EnterCriticalSection(&startup_lock);
    if(target) {
        if(offset && offset->QuadPart>=0) position=*offset;
        else if(!SetFilePointerEx(file,zero,&position,FILE_CURRENT))target=FALSE;
    }
    if(target) {
        BOOL overlap=FALSE;
        for(unsigned i=0;i<STARTUP_EDIT_COUNT;i++)
            if((configured_features & verified_features & startup_edits[i].feature) &&
               (ULONGLONG)position.QuadPart<startup_edits[i].offset+startup_edits[i].size &&
               (ULONGLONG)position.QuadPart+size>startup_edits[i].offset)overlap=TRUE;
        if(overlap) {
            for(unsigned i=0;i<32;i++) if(startup_pending[i].io==iosb && startup_pending[i].file==file) {pending=&startup_pending[i];break;}
            if(!pending)for(unsigned i=0;i<32;i++)if(!startup_pending[i].io){pending=&startup_pending[i];break;}
            if(pending)*pending=(StartupPending){file,iosb,buffer,size,(ULONGLONG)position.QuadPart};
        }
    }
    SetLastError(incoming_error);
    LONG result=startup_read(file,event,apc,context,iosb,buffer,size,offset,key);
    DWORD result_error=GetLastError();
    if(pending) {
        ULONG_PTR count=((ULONG_PTR *)iosb)[1];
        if(result==0 && count<=size)StartupPatch(buffer,pending->offset,count);
        // Pending buffers must not be touched before the game's completion API.
        if(result!=259)pending->io=NULL;
    }
    if(locked)LeaveCriticalSection(&startup_lock);
    SetLastError(result_error);
    return result;
}

static BOOL WINAPI StartupCompletedHook(HANDLE file,LPOVERLAPPED io,LPDWORD count,BOOL wait) {
    DWORD incoming_error=GetLastError();
    EnterCriticalSection(&startup_lock);
    StartupPending *pending=NULL;
    for(unsigned i=0;i<32;i++)if(startup_pending[i].io==io && startup_pending[i].file==file){pending=&startup_pending[i];break;}
    if(!pending)LeaveCriticalSection(&startup_lock);
    SetLastError(incoming_error);
    BOOL result=startup_completed(file,io,count,wait);
    DWORD result_error=GetLastError();
    if(pending) {
        if(result && count && *count<=pending->size)StartupPatch(pending->buffer,pending->offset,*count);
        if(result || result_error!=ERROR_IO_INCOMPLETE)pending->io=NULL;
        LeaveCriticalSection(&startup_lock);
    }
    SetLastError(result_error);
    return result;
}

// Resolve a stored ZIP member using both directory records. Reject duplicate
// names, compressed/encrypted data, ZIP64, and out-of-bounds records.
static unsigned Read16(const unsigned char *p) {
    return p[0] | ((unsigned)p[1]<<8);
}
static unsigned Read32(const unsigned char *p) {
    return Read16(p) | (Read16(p+2)<<16);
}
static BOOL BundleName(const unsigned char *name, unsigned length) {
    const char expected[]="[gfx]/gfxbundle.gfxbundle";
    if(length!=sizeof(expected)-1)return FALSE;
    for(unsigned i=0;i<length;i++)
        if((name[i]=='\\' ? '/' : name[i])!=expected[i])return FALSE;
    return TRUE;
}
static BOOL FindBundle(const unsigned char *file, size_t size, size_t *base, size_t *length) {
    if(size<22)return FALSE;
    size_t end=size-22, limit=end>65535 ? end-65535 : 0;
    while(Read32(file+end)!=0x06054b50) {
        if(end==limit)return FALSE;
        --end;
    }
    const unsigned char *footer=file+end;
    size_t pos=Read32(footer+16);
    if(Read32(footer+4) || Read16(footer+8)!=Read16(footer+10) ||
       pos>end || Read32(footer+12)!=end-pos || Read16(footer+20)>size-end-22)return FALSE;
    BOOL found=FALSE;
    for(unsigned i=0;i<Read16(footer+10);i++) {
        if(end-pos<46 || Read32(file+pos)!=0x02014b50)return FALSE;
        const unsigned char *entry=file+pos;
        unsigned namesize=Read16(entry+28);
        size_t record=46+namesize+Read16(entry+30)+Read16(entry+32);
        if(record>end-pos)return FALSE;
        if(BundleName(entry+46,namesize)) {
            size_t local=Read32(entry+42), directory=Read32(footer+16);
            if(found || Read32(entry+8)!=0 || Read16(entry+34) ||
               Read32(entry+20)!=Read32(entry+24) || local>directory || directory-local<30)return FALSE;
            const unsigned char *header=file+local;
            size_t prefix=30+Read16(header+26)+Read16(header+28);
            if(prefix>directory-local || Read32(header)!=0x04034b50 || Read32(header+6)!=0 ||
               Read32(header+18)!=Read32(entry+20) || Read32(header+22)!=Read32(entry+24) ||
               !BundleName(header+30,Read16(header+26)))return FALSE;
            *base=local+prefix; *length=Read32(entry+24);
            if(*length>directory-*base)return FALSE;
            found=TRUE;
        }
        pos+=record;
    }
    return found && pos==end;
}

static BOOL MovieMatches(const unsigned char *data, unsigned movie) {
    BCRYPT_ALG_HANDLE algorithm=NULL;
    unsigned char digest[32];
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,NULL,0)!=0)return FALSE;
    BOOL ok=BCryptHash(algorithm,NULL,0,(PUCHAR)data,movies[movie].size,digest,sizeof(digest))==0 &&
            !memcmp(digest,movies[movie].hash,sizeof(digest));
    BCryptCloseAlgorithmProvider(algorithm,0);
    return ok;
}

static int ResolveMovies(const unsigned char *file, size_t size) {
    size_t base=0,length=0;
    if(!FindBundle(file,size,&base,&length) || length<21)return 0;
    const unsigned char *bundle=file+base;
    if(memcmp(bundle,"S3DB\x01\x00\x02\x00\x01\x00\x01",11))return 0;
    unsigned count=Read32(bundle+11), indices[MOVIE_COUNT]={0};
    size_t pos=20;
    if(!count || count>length/8)return 0;
    for(unsigned i=1;i<=count;i++) {
        if(length-pos<4)return 0;
        unsigned n=Read32(bundle+pos); pos+=4;
        if(n>length-pos)return 0;
        for(unsigned m=0;m<MOVIE_COUNT;m++) {
            if(strlen(movies[m].name)==n && !memcmp(bundle+pos,movies[m].name,n))
                indices[m]=indices[m] ? UINT_MAX : i;
        }
        pos+=n;
    }
    if(pos==length || bundle[pos++]!=1 || count>(length-pos)/4)return 0;
    const unsigned char *sizes=bundle+pos;
    pos+=4ULL*count;
    size_t offsets[MOVIE_COUNT]={0};
    for(unsigned i=1;i<=count;i++) {
        unsigned n=Read32(sizes+4ULL*(i-1));
        if(n>length-pos)return 0;
        for(unsigned m=0;m<MOVIE_COUNT;m++)
            if(indices[m]==i && n==movies[m].size && MovieMatches(bundle+pos,m))
                offsets[m]=base+pos;
        pos+=n;
    }
    int verified=2|8;
    for(unsigned i=0;i<STARTUP_EDIT_COUNT;i++) {
        StartupEdit *edit=&startup_edits[i];
        size_t start=offsets[edit->movie];
        if(!start || edit->offset+edit->size>movies[edit->movie].size ||
           memcmp(file+start+edit->offset,edit->before,edit->size))verified &= ~edit->feature;
        else edit->offset+=start;
    }
    return verified;
}



static void StartupInstall(const wchar_t *folder) {
    if (!(configured_features & (2 | 8))) return;
    startup_state="incompatible";
    wchar_t path[32768];
    swprintf_s(path,32768,L"%ls..\\..\\preload\\paks\\client\\gfx.pak",folder);
    startup_file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    if(startup_file==INVALID_HANDLE_VALUE)return;
    LARGE_INTEGER size;
    HANDLE mapping=CreateFileMappingW(startup_file,NULL,PAGE_READONLY,0,0,NULL);
    if(mapping) {
        const unsigned char *view=MapViewOfFile(mapping,FILE_MAP_READ,0,0,0);
        if(view) {
            if(GetFileSizeEx(startup_file,&size) && size.QuadPart>0)
                verified_features=ResolveMovies(view,(size_t)size.QuadPart);
            UnmapViewOfFile(view);
        }
        CloseHandle(mapping);
    }
    if(!(verified_features & configured_features) || !GetFileInformationByHandle(startup_file,&startup_identity)) {
        CloseHandle(startup_file);startup_file=INVALID_HANDLE_VALUE;return;
    }
    InitializeCriticalSection(&startup_lock);
    GumInterceptor *interceptor=gum_interceptor_obtain();
    gpointer address=(gpointer)GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"NtReadFile");
    gpointer completion=(gpointer)GetProcAddress(GetModuleHandleW(L"kernel32.dll"),"GetOverlappedResult");
    GumReplaceReturn result=gum_interceptor_replace(interceptor,completion,StartupCompletedHook,(gpointer *)&startup_completed,NULL);
    if(result==GUM_REPLACE_OK) {
        result=gum_interceptor_replace(interceptor,address,StartupReadHook,(gpointer *)&startup_read,NULL);
        if(result!=GUM_REPLACE_OK)gum_interceptor_revert(interceptor,completion);
    }
    g_object_unref(interceptor);
    if(result!=GUM_REPLACE_OK){CloseHandle(startup_file);startup_file=INVALID_HANDLE_VALUE;startup_state="error";return;}
    startup_state="armed";
}

static const char *StartupState(void) {
    if (configured_features < 0 || !(configured_features & 2)) return "disabled";
    LONG seen=InterlockedCompareExchange(&startup_seen,0,0);
    if(!(verified_features & 2))return "incompatible";
    return ((seen&3)==3 || (seen&12)==12) ? "active" : startup_state;
}

static const char *FunctionsMenuState(void) {
    if (configured_features < 0) return "configuration-error";
    if (!(configured_features & 8)) return "disabled";
    LONG seen=InterlockedCompareExchange(&startup_seen,0,0);
    if(!(verified_features & 8))return "incompatible";
    for (unsigned i=0; i<STARTUP_EDIT_COUNT; ++i)
        if (startup_edits[i].feature == 8 && !(seen & (1L << i))) return startup_state;
    return "active";
}
