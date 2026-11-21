/* Synthetic second ASI: Enhanced must not block the loader scan. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
__declspec(dllexport) void InitializeASI(void) {
    HANDLE file = CreateFileW(L"companion.started", GENERIC_WRITE, 0, NULL,
                              CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
}
BOOL WINAPI DllMain(HINSTANCE module, DWORD why, LPVOID reserved) {
    (void)module; (void)why; (void)reserved;
    return TRUE;
}
