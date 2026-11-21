#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>
#include "proxy_names.h"

static HMODULE self, system_version;
static INIT_ONCE once = INIT_ONCE_STATIC_INIT;
static volatile LONG launched;
static FARPROC exports[17];

static DWORD WINAPI StartEnhanced(void *unused) {
    (void)unused;
    wchar_t path[32768];
    DWORD n = GetModuleFileNameW(NULL, path, 32768);
    if (!n || n >= 32768) return 0;
    wchar_t *name = wcsrchr(path, L'\\');
    if (!name || _wcsicmp(name + 1, L"SnowRunner.exe")) return 0;
    n = GetModuleFileNameW(self, path, 32768);
    if (!n || n >= 32000) return 0;
    name = wcsrchr(path, L'\\');
    if (!name) return 0;
    wcscpy_s(name + 1, 32768 - (size_t)(name + 1 - path), L"SnowRunnerEnhanced.dll");
    HMODULE plugin = LoadLibraryExW(path, NULL, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if (plugin) {
        void (*start)(void) = (void (*)(void))GetProcAddress(plugin, "EnhancedStart");
        if (start) start();
        // The process owns the private runtime for its lifetime. Never unload
        // a DLL whose interceptors may still be executing on another thread.
    }
    return 0;
}

static BOOL CALLBACK LoadSystem(PINIT_ONCE init, PVOID parameter, PVOID *context) {
    (void)init; (void)parameter; (void)context;
    wchar_t path[MAX_PATH];
    UINT n = GetSystemDirectoryW(path, MAX_PATH);
    if (!n || n + 13 >= MAX_PATH) return FALSE;
    wcscat_s(path, MAX_PATH, L"\\version.dll");
    system_version = LoadLibraryExW(path, NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!system_version || system_version == self) return FALSE;
    for (int i = 0; i < 17; ++i) exports[i] = GetProcAddress(system_version, proxy_names[i]);
    return TRUE;
}

static ULONG_PTR WINAPI MissingExport(void) { SetLastError(ERROR_PROC_NOT_FOUND); return 0; }

FARPROC ResolveVersion(unsigned index) {
    DWORD error = GetLastError();
    InitOnceExecuteOnce(&once, LoadSystem, NULL, NULL);
    if (InterlockedCompareExchange(&launched, 1, 0) == 0) {
        // This is an exported API call, not DllMain; never wait for the worker.
        HMODULE pinned;
        if (GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
                              (LPCWSTR)(uintptr_t)&ResolveVersion, &pinned)) {
            HANDLE worker = CreateThread(NULL, 0, StartEnhanced, NULL, 0, NULL);
            if (worker) CloseHandle(worker);
        }
    }
    FARPROC target = index < 17 && exports[index] ? exports[index] : (FARPROC)MissingExport;
    SetLastError(error);
    return target;
}

BOOL WINAPI DllMain(HINSTANCE module, DWORD why, LPVOID reserved) {
    (void)reserved;
    if (why == DLL_PROCESS_ATTACH) { self = module; DisableThreadLibraryCalls(module); }
    return TRUE;
}
