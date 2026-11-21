/* Disposable host: real ASI loading without opening input devices. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <unknwn.h>
#include <stdio.h>
#include <stdlib.h>
#pragma comment(lib, "dinput8.lib")
__declspec(dllimport) HRESULT WINAPI DirectInput8Create(HINSTANCE, DWORD, REFIID, LPVOID *, LPUNKNOWN);

int main(int argc, char **argv) {
    FILETIME now; GetSystemTimeAsFileTime(&now);
    /* Invalid output deliberately prevents creating an input interface. */
    GUID iid = {0};
    HRESULT result = DirectInput8Create(GetModuleHandleW(NULL), 0x800, &iid, NULL, NULL);
    if (SUCCEEDED(result)) return 2;
    printf("DirectInput forwarding works\n"); fflush(stdout);
    Sleep(argc > 1 ? (DWORD)atoi(argv[1]) : 5000);
    HMODULE plugin = GetModuleHandleW(L"SnowRunnerEnhanced.asi");
    printf("Enhanced loaded: %s\n", plugin ? "yes" : "no");
    if (plugin) {
        void (*initialize)(void) = (void (*)(void))GetProcAddress(plugin, "InitializeASI");
        if (!initialize) return 3;
        SetLastError(1234); initialize(); initialize();
        if (GetLastError() != 1234) return 4;
    }
    return 0;
}
