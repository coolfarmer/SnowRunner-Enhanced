#include "frida-gumjs.h"
#include <windows.h>
#include "../../src/native/steering.h"
/* Test fixtures adapted from SnowRunner FFB Fix, MIT; see Licenses/SnowRunnerFFBFix.txt. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); ExitProcess(1); } } while (0)
unsigned char abi_snapshot[176];
uintptr_t FixtureCtor(void *object, uintptr_t action, uintptr_t third, uintptr_t fourth, uintptr_t fifth);
void AbiTarget(void);
uintptr_t AbiInvoke(void *object);
static volatile LONG entered;

uintptr_t FixtureBody(void *object, uintptr_t action, uintptr_t third, uintptr_t fourth, uintptr_t fifth) {
    CHECK(GetLastError() == 0x1234);
    CHECK(third == 0x3333 && fourth == 0x4444 && fifth == 0x5555);
    for (int i = 0; i < 16; ++i) CHECK(((unsigned char *)object)[0x44+i] == 0);
    InterlockedIncrement(&entered);
    if (action == 1) {
        /* A legitimate write during the original constructor must survive. */
        memset((unsigned char *)object + 0x44, 0x37, 16);
    } else if (action == 2) {
        unsigned char *inner = VirtualAlloc(NULL, 4096, MEM_RESERVE|MEM_COMMIT, PAGE_READWRITE);
        CHECK(inner);
        memset(inner, 0x61, 4096);
        SetLastError(0x1234);
        CHECK(FixtureCtor(inner, 1, 0x3333, 0x4444, 0x5555) == (uintptr_t)inner);
        CHECK(inner[0x44] == 0x37);
        VirtualFree(inner, 0, MEM_RELEASE);
    }
    SetLastError(0x5678);
    return (uintptr_t)object;
}

static void install(void *fn) {
    /* Attach to synthetic code using the production Gum callback. */
    CHECK(SwAttach(fn));
    return;

}

static DWORD WINAPI loop(void *arg) {
    (void)arg;
    unsigned char *obj = VirtualAlloc(NULL, 4096, MEM_RESERVE|MEM_COMMIT, PAGE_READWRITE);
    CHECK(obj);
    for (int i=0; i<1000; ++i) {
        memset(obj, 0x62, 4096);
        SetLastError(0x1234);
        CHECK(FixtureCtor(obj, 0, 0x3333, 0x4444, 0x5555) == (uintptr_t)obj);
        CHECK(GetLastError() == 0x5678);
        CHECK(obj[0x43] == 0x62 && obj[0x54] == 0x62);
    }
    VirtualFree(obj, 0, MEM_RELEASE);
    return 0;
}

static int resolve_file(const char *path) {
    FILE *f=fopen(path,"rb"); CHECK(f);
    unsigned header[2]; CHECK(fread(header,sizeof(header),1,f)==1);
    unsigned size=header[0],count=header[1]; CHECK(size<100000000 && count<=96);
    SwSection sections[96]; CHECK(fread(sections,sizeof(SwSection),count,f)==count);
    unsigned char *data=g_malloc(size); CHECK(fread(data,1,size,f)==size); fclose(f);
    unsigned found[G_N_ELEMENTS(sw_signatures)],target=0;
    BOOL ok=SwResolve(data,size,sections,count,sw_signatures,G_N_ELEMENTS(sw_signatures),SW_CONSTRUCTOR_RVA,found,&target);
    printf("%s target=%u reason=%s\n",ok?"PASS":"REFUSED",target,sw_reason); g_free(data); return ok?0:3;
}

int main(int argc, char **argv) {
    gum_init_embedded();
    if (argc==3 && !strcmp(argv[1],"resolve")) return resolve_file(argv[2]);
    CHECK(argc == 2);
    unsigned char *obj = VirtualAlloc(NULL, 8192, MEM_RESERVE|MEM_COMMIT, PAGE_READWRITE);
    CHECK(obj);
    memset(obj, 0x61, 8192);
    struct { LONG armed; LONG64 applied,failed,skipped; } s;
    if (!strcmp(argv[1], "guards")) {
        SwSection sections[]={{0x1000,0x1000,1,1}};
        CHECK(SwContained(sections,1,0x1000,0x1000,TRUE));
        CHECK(!SwContained(sections,1,0x1000,0x1001,TRUE));
        CHECK(!SwContained(sections,1,0xffffffff,2,TRUE));
        CHECK(!SwLiveCode(obj,16));
        DWORD old;
        CHECK(VirtualProtect(obj,4096,PAGE_EXECUTE_READWRITE,&old));
        CHECK(SwLiveCode(obj,16));
        CHECK(!SwLiveCode(obj,8192));
        CHECK(!SwLiveCode((void *)(UINTPTR_MAX-3),16));
        CHECK(VirtualProtect(obj,4096,PAGE_READWRITE,&old));
    } else if (!strcmp(argv[1], "abi")) {
        unsigned char before[176];
        SetLastError(0x1234); CHECK(AbiInvoke(obj) == 12345);
        memcpy(before, abi_snapshot, sizeof(before));
        install(AbiTarget);
        SetLastError(0x1234); CHECK(AbiInvoke(obj) == 12345);
        CHECK(GetLastError() == 0x1234);
        CHECK(!memcmp(before,abi_snapshot,sizeof(before)));
        s.armed=sw_armed; s.applied=sw_applied; s.failed=sw_failed; s.skipped=sw_skipped; CHECK(s.applied == 1);
    } else if (!strcmp(argv[1], "semantics")) {
        install(FixtureCtor);
        SetLastError(0x1234);
        CHECK(FixtureCtor(obj,0,0x3333,0x4444,0x5555) == (uintptr_t)obj);
        CHECK(GetLastError() == 0x5678);
        for (int i=0;i<8192;++i) CHECK(obj[i] == (i>=0x44 && i<0x54 ? 0 : 0x61));
        memset(obj+0x44,0x61,16);
        SetLastError(0x1234); FixtureCtor(obj,1,0x3333,0x4444,0x5555);
        for(int i=0;i<16;++i) CHECK(obj[0x44+i] == 0x37);
        obj[0x44]=0x45; CHECK(obj[0x44]==0x45);
        SetLastError(0x1234); FixtureCtor(obj,2,0x3333,0x4444,0x5555);
        HANDLE threads[4];
        for(int i=0;i<4;++i) { threads[i]=CreateThread(NULL,0,loop,NULL,0,NULL); CHECK(threads[i]); }
        CHECK(WaitForMultipleObjects(4,threads,TRUE,30000)==WAIT_OBJECT_0);
        for(int i=0;i<4;++i) CloseHandle(threads[i]);
        s.armed=sw_armed; s.applied=sw_applied; s.failed=sw_failed; s.skipped=sw_skipped; CHECK(s.applied == 4004 && !s.failed && !s.skipped && s.armed);
        CHECK(entered == 4004);
        InterlockedExchange(&sw_armed,0); memset(obj,0x61,8192); SwInitializeFields(obj);
        CHECK(obj[0x44]==0x61);
        s.armed=sw_armed; s.applied=sw_applied; s.failed=sw_failed; s.skipped=sw_skipped; CHECK(!s.armed && s.skipped == 1);
    } else {
        install(FixtureCtor);
        DWORD old;
        void *bad = NULL;
        if (!strcmp(argv[1],"readonly")) { CHECK(VirtualProtect(obj,4096,PAGE_READONLY,&old)); bad=obj; }
        else if (!strcmp(argv[1],"boundary")) { CHECK(VirtualProtect(obj+4096,4096,PAGE_NOACCESS,&old)); bad=obj+4096-8-0x44; }
        else if (!strcmp(argv[1],"executable")) { CHECK(VirtualProtect(obj,4096,PAGE_EXECUTE_READWRITE,&old)); bad=obj; }
        else if (!strcmp(argv[1],"overflow")) bad=(void *)(UINTPTR_MAX-0x43);
        else CHECK(!strcmp(argv[1],"null"));
        SetLastError(0x98); SwInitializeFields(bad); CHECK(GetLastError()==0x98);
        s.armed=sw_armed; s.applied=sw_applied; s.failed=sw_failed; s.skipped=sw_skipped; CHECK(!s.armed && s.failed==1 && !s.applied);
        SwInitializeFields(obj+4096);
        s.armed=sw_armed; s.applied=sw_applied; s.failed=sw_failed; s.skipped=sw_skipped; CHECK(s.skipped==1 && s.failed==1);
    }
    VirtualFree(obj,0,MEM_RELEASE);
    printf("PASS %s\n",argv[1]);
    return 0;
}
