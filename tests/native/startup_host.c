#include "frida-gumjs.h"
#include <windows.h>
#include <bcrypt.h>
#include <stdio.h>
#include <wchar.h>
#include <assert.h>
#pragma comment(lib,"bcrypt.lib")
#include "../../src/native/startup.h"

int wmain(int argc, wchar_t **argv) {
    if(argc!=2)return 2;
    gum_init_embedded(); configured_features=2;
    StartupInstall(argv[1]);
    assert(!strcmp(StartupState(),"armed"));
    wchar_t path[32768];
    swprintf_s(path,32768,L"%ls..\\..\\preload\\paks\\client\\gfx.pak",argv[1]);
    HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    assert(file!=INVALID_HANDLE_VALUE);
    for(unsigned i=0;i<STARTUP_EDIT_COUNT;i++) {
        const StartupEdit *e=&startup_edits[i];
        LARGE_INTEGER pos;pos.QuadPart=e->offset;
        assert(SetFilePointerEx(file,pos,NULL,FILE_BEGIN));
        unsigned char data[64];DWORD count;
        assert(ReadFile(file,data,e->size,&count,NULL) && count==e->size);
        assert(!memcmp(data,e->after,e->size));
        for(unsigned j=0;j<e->size;j++) {
            pos.QuadPart=e->offset+j;
            assert(SetFilePointerEx(file,pos,NULL,FILE_BEGIN));
            assert(ReadFile(file,data,1,&count,NULL) && count==1 && data[0]==e->after[j]);
        }
        // The underlying syscall trampoline still reads the original bytes.
        ULONG_PTR iosb[2]={0};pos.QuadPart=e->offset;
        assert(startup_read(file,NULL,NULL,NULL,iosb,data,e->size,&pos,NULL)==0);
        assert(!memcmp(data,e->before,e->size));
    }
    assert(!strcmp(StartupState(),"active"));
    HANDLE asyncFile=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OVERLAPPED,NULL);
    assert(asyncFile!=INVALID_HANDLE_VALUE);
    startup_seen=0; memset((void *)startup_coverage,0,sizeof(startup_coverage));
    unsigned pendingCount=0;
    for(unsigned i=0;i<STARTUP_EDIT_COUNT;i++) {
        const StartupEdit *e=&startup_edits[i];
        OVERLAPPED ov={0};ov.Offset=(DWORD)e->offset;ov.OffsetHigh=(DWORD)(e->offset>>32);
        ov.hEvent=CreateEventW(NULL,TRUE,FALSE,NULL);assert(ov.hEvent);
        unsigned char data[64];DWORD count=0;
        BOOL ready=ReadFile(asyncFile,data,e->size,&count,&ov);
        if(!ready){assert(GetLastError()==ERROR_IO_PENDING);pendingCount++;}
        assert(GetOverlappedResult(asyncFile,&ov,&count,TRUE));
        assert(count==e->size && !memcmp(data,e->after,e->size));
        CloseHandle(ov.hEvent);
    }
    assert(!strcmp(StartupState(),"active"));
    CloseHandle(asyncFile);
    printf("Asynchronous reads passed (%u pending completions).\n",pendingCount);
    CloseHandle(file);
    puts("Startup interception: full and single-byte reads pass; original archive bytes preserved.");
    return 0;
}
