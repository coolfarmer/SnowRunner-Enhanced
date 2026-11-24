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
static int configured_features;

typedef BOOL (WINAPI *StartupCompleted)(HANDLE,LPOVERLAPPED,LPDWORD,BOOL);
static StartupCompleted startup_completed;
typedef struct { HANDLE file; PVOID io, buffer; ULONG size; ULONGLONG offset; } StartupPending;
static StartupPending startup_pending[32];

static void StartupPatch(PVOID buffer, ULONGLONG offset, ULONG_PTR count) {
    for (unsigned i=0; i<STARTUP_EDIT_COUNT; ++i) {
        const StartupEdit *edit=&startup_edits[i];
        if (!(configured_features & edit->feature)) continue;
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
            if((configured_features & startup_edits[i].feature) &&
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

static BOOL StartupHash(HANDLE file) {
    BCRYPT_ALG_HANDLE alg=NULL; BCRYPT_HASH_HANDLE hash=NULL;
    BOOL ok=BCryptOpenAlgorithmProvider(&alg,BCRYPT_SHA256_ALGORITHM,NULL,0)==0 &&
        BCryptCreateHash(alg,&hash,NULL,0,NULL,0,0)==0;
    unsigned char buffer[65536], digest[32]; DWORD count;
    while(ok) {
        if(!ReadFile(file,buffer,sizeof(buffer),&count,NULL)){ok=FALSE;break;}
        if(!count)break;
        ok=BCryptHashData(hash,buffer,count,0)==0;
    }
    if(ok)ok=BCryptFinishHash(hash,digest,32,0)==0 && !memcmp(digest,startup_sha256,32);
    if(hash)BCryptDestroyHash(hash);
    if(alg)BCryptCloseAlgorithmProvider(alg,0);
    return ok;
}

static void StartupInstall(const wchar_t *folder) {
    if (!(configured_features & (2 | 8))) return;
    startup_state="incompatible";
    wchar_t path[32768];
    swprintf_s(path,32768,L"%ls..\\..\\preload\\paks\\client\\gfx.pak",folder);
    startup_file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    if(startup_file==INVALID_HANDLE_VALUE)return;
    LARGE_INTEGER size;
    if(!GetFileSizeEx(startup_file,&size) || size.QuadPart!=STARTUP_ARCHIVE_SIZE ||
       !StartupHash(startup_file) || !GetFileInformationByHandle(startup_file,&startup_identity)) {
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
    return ((seen&3)==3 || (seen&12)==12) ? "active" : startup_state;
}

static const char *FunctionsMenuState(void) {
    if (configured_features < 0) return "configuration-error";
    if (!(configured_features & 8)) return "disabled";
    LONG seen=InterlockedCompareExchange(&startup_seen,0,0);
    for (unsigned i=0; i<STARTUP_EDIT_COUNT; ++i)
        if (startup_edits[i].feature == 8 && !(seen & (1L << i))) return startup_state;
    return "active";
}
