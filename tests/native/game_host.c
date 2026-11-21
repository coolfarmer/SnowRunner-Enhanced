/* Test application only. Its VERSION import exercises Windows DLL loading. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#pragma comment(lib, "version.lib")

int main(int argc, char **argv) {
    wchar_t system[MAX_PATH]; GetSystemDirectoryW(system, MAX_PATH);
    wcscat_s(system, MAX_PATH, L"\\kernel32.dll");
    DWORD handle = 0;
    DWORD size = GetFileVersionInfoSizeW(system, &handle);
    if (!size) return 2;
    void *data = malloc(size), *fixed = NULL; UINT length = 0;
    if (!GetFileVersionInfoW(system, 0, size, data) || !VerQueryValueW(data, L"\\", &fixed, &length) || !fixed) return 3;
    printf("VERSION exports work: %lu bytes\n", (unsigned long)length); fflush(stdout);
    Sleep(argc > 1 ? (DWORD)atoi(argv[1]) : 5000);
    printf("Enhanced loaded: %s\n", GetModuleHandleW(L"SnowRunnerEnhanced.dll") ? "yes" : "no");
    free(data);
    return 0;
}
