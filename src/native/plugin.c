#include "frida-gumjs.h"
#include <windows.h>
#include <bcrypt.h>
#include <stdio.h>
#include <wchar.h>
#include "bundle.h"
#pragma comment(lib, "bcrypt.lib")

#include "startup.h"
#include "settings.h"
#include "steering.h"

static HMODULE self;
static volatile LONG started;
static wchar_t status_path[32768], temp_path[32768];

static void WriteReport(const char *text, GumScript *script) {
    JsonParser *parser = json_parser_new();
    char *enriched = NULL;
    if (json_parser_load_from_data(parser, text, -1, NULL)) {
        JsonObject *root = json_node_get_object(json_parser_get_root(parser));
        json_object_set_string_member(root,"settingsPersistence",settings_state);
        JsonObject *features = json_object_get_object_member(root, "features");
        if (features) {
            json_object_set_object_member(features,"steering_wheel_improvements",SteeringStatus(configured_features >= 0 && (configured_features & 32) != 0));
            JsonObject *startup = json_object_new();
            json_object_set_boolean_member(startup,"enabled",configured_features >= 0 && (configured_features & 2) != 0);
            json_object_set_string_member(startup,"status",StartupState());
            json_object_set_object_member(features,"skip_startup_logos",startup);
            JsonObject *general = json_object_new();
            json_object_set_boolean_member(general,"enabled",configured_features >= 0 && (configured_features & 8) != 0);
            json_object_set_string_member(general,"status",FunctionsMenuState());
            json_object_set_object_member(features,"general_improvements",general);
            if (!json_object_has_member(features,"vehicle")) {
                JsonObject *vehicle=json_object_new();
                BOOL selected=configured_features>=0 && (configured_features & 16);
                json_object_set_boolean_member(vehicle,"enabled",selected);
                json_object_set_string_member(vehicle,"status",configured_features<0?"configuration-error":selected?"error":"disabled");
                json_object_set_object_member(features,"vehicle",vehicle);
            }
            if (!json_object_has_member(features,"map")) {
                JsonObject *map = json_object_new();
                json_object_set_boolean_member(map,"enabled",configured_features >= 0 && (configured_features & 4) != 0);
                json_object_set_string_member(map,"status",configured_features < 0 ? "configuration-error" : (configured_features & 4) ? "error" : "disabled");
                json_object_set_object_member(features,"map",map);
            }
            enriched=json_to_string(json_parser_get_root(parser),TRUE);
        }
    }
    if (enriched) text=enriched;
    // Return this session's live native diagnostics to the menu. Never read a
    // status file left behind by a previous game process.
    if (script && enriched) {
        char *reply = g_strdup_printf("{\"type\":\"enhanced-runtime\",\"payload\":%s}", enriched);
        gum_script_post(script, reply, NULL);
        g_free(reply);
    }

    HANDLE file = CreateFileW(temp_path, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_DELETE,
                             NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) { g_free(enriched); g_object_unref(parser); return; }
    DWORD written, count = (DWORD)strlen(text);
    BOOL ok = count < 65536 && WriteFile(file, text, count, &written, NULL) && count == written;
    CloseHandle(file);
    if (ok) MoveFileExW(temp_path, status_path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
    g_free(enriched); g_object_unref(parser);
}

static void SimpleStatus(const char *status, const char *reason) {
    char out[1024];
    SYSTEMTIME now; GetSystemTime(&now);
    snprintf(out, sizeof(out), "{\"schemaVersion\":1,\"version\":\"0.1.0-preview.33\","
        "\"processId\":%lu,\"timeUtc\":\"%04u-%02u-%02uT%02u:%02u:%02uZ\","
        "\"features\":{\"wheel_mouse\":{\"status\":\"%s\",\"reason\":\"%s\"}}}",
        (unsigned long)GetCurrentProcessId(), now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute, now.wSecond, status, reason);
    WriteReport(out, NULL);
}

static BOOL HashGame(char hex[65]) {
    wchar_t path[32768];
    if (!GetModuleFileNameW(NULL, path, 32768)) return FALSE;
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE, NULL,
                             OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return FALSE;
    BCRYPT_ALG_HANDLE alg = NULL; BCRYPT_HASH_HANDLE hash = NULL;
    BOOL ok = BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA256_ALGORITHM, NULL, 0) == 0 &&
              BCryptCreateHash(alg, &hash, NULL, 0, NULL, 0, 0) == 0;
    unsigned char buffer[65536], digest[32]; DWORD count;
    while (ok) {
        if (!ReadFile(file, buffer, sizeof(buffer), &count, NULL)) { ok = FALSE; break; }
        if (!count) break;
        if (BCryptHashData(hash, buffer, count, 0) != 0) ok = FALSE;
    }
    if (ok) ok = BCryptFinishHash(hash, digest, sizeof(digest), 0) == 0;
    if (hash) BCryptDestroyHash(hash);
    if (alg) BCryptCloseAlgorithmProvider(alg, 0);
    CloseHandle(file);
    if (ok) for (int i = 0; i < 32; i++) sprintf_s(hex + 2 * i, 3, "%02x", digest[i]);
    return ok;
}

// These installer keys also identify sections in the Enhanced settings menu.
static const struct { const char *key; int bit; } modules[] = {
    {"wheel_mouse", 1}, {"skip_startup_logos", 2}, {"map", 4},
    {"general_improvements", 8}, {"vehicle", 16}, {"steering_wheel_improvements", 32}
};

static char *MenuModuleFlags(int enabled) {
    GString *flags = g_string_new("{");
    for (size_t i = 0; i < G_N_ELEMENTS(modules); i++)
        g_string_append_printf(flags, "%s\"%s\":%s", i ? "," : "", modules[i].key,
            (enabled & modules[i].bit) ? "true" : "false");
    g_string_append_c(flags, '}');
    return g_string_free(flags, FALSE);
}

static int ReadConfiguration(const wchar_t *folder) {
    wchar_t path[32768]; swprintf_s(path, 32768, L"%lsSnowRunnerEnhanced.json", folder);
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (file == INVALID_HANDLE_VALUE) return -1;
    DWORD size = GetFileSize(file, NULL), read = 0;
    if (!size || size > 65536) { CloseHandle(file); return -1; }
    char *text = g_malloc(size + 1);
    BOOL ok = ReadFile(file, text, size, &read, NULL) && read == size;
    CloseHandle(file); text[size] = 0;
    JsonParser *parser = json_parser_new(); GError *error = NULL;
    int enabled = -1;
    char *json = size >= 3 && (unsigned char)text[0] == 0xef &&
        (unsigned char)text[1] == 0xbb && (unsigned char)text[2] == 0xbf ? text + 3 : text;
    if (ok && json_parser_load_from_data(parser, json, -1, &error)) {
        JsonNode *node = json_parser_get_root(parser);
        if (JSON_NODE_HOLDS_OBJECT(node)) {
            JsonObject *root = json_node_get_object(node);
            JsonNode *schema = json_object_get_member(root, "schemaVersion");
            JsonNode *features = json_object_get_member(root, "features");
            if (json_object_get_size(root) == 2 && schema && json_node_get_value_type(schema) == G_TYPE_INT64 &&
                    json_node_get_int(schema) == 1 && features && JSON_NODE_HOLDS_OBJECT(features)) {
                JsonObject *entries = json_node_get_object(features);
                enabled = json_object_has_member(entries,"vehicle") ? 0 : 16;
                GList *members = json_object_get_members(entries);
                for (GList *m = members; m; m = m->next) {
                    const char *key = m->data;
                    int bit = 0;
                    for (size_t i = 0; i < G_N_ELEMENTS(modules); i++) {
                        if (!strcmp(key, modules[i].key)) { bit = modules[i].bit; break; }
                    }
                    JsonNode *entryNode = json_object_get_member(entries, key);
                    if (!bit || !JSON_NODE_HOLDS_OBJECT(entryNode)) { enabled = -1; break; }
                    JsonObject *entry = json_node_get_object(entryNode);
                    JsonNode *flag = json_object_get_member(entry, "enabled");
                    if (json_object_get_size(entry) != 1 || !flag || json_node_get_value_type(flag) != G_TYPE_BOOLEAN) { enabled = -1; break; }
                    if (json_node_get_boolean(flag)) enabled |= bit;
                }
                g_list_free(members);
            }
        }
    }
    if (error) g_error_free(error);
    g_object_unref(parser); g_free(text);
    return enabled;
}

static void OnMessage(const gchar *message, GBytes *data, gpointer context) {
    (void)data;
    JsonParser *parser = json_parser_new();
    if (json_parser_load_from_data(parser, message, -1, NULL)) {
        JsonObject *root = json_node_get_object(json_parser_get_root(parser));
        const char *type = json_object_get_string_member(root, "type");
        if (!strcmp(type, "send")) {
            JsonNode *payload = json_object_get_member(root, "payload");
            if (payload && JSON_NODE_HOLDS_OBJECT(payload)) {
                JsonNode *status = json_object_get_member(json_node_get_object(payload), "enhancedStatus");
                if (status) { char *text = json_to_string(status, TRUE); WriteReport(text, (GumScript *)context); g_free(text); }
                JsonNode *settings = json_object_get_member(json_node_get_object(payload), "enhancedSettings");
                if (settings) SettingsSave(settings);
            }
        } else if (!strcmp(type, "error")) SimpleStatus("error", "Embedded script error; see development tests");
    }
    g_object_unref(parser);
}

static void EnhancedStart(void) {
    wchar_t folder[32768], game[32768];
    DWORD n = GetModuleFileNameW(self, folder, 32768);
    if (!n || n >= 32000 || !GetModuleFileNameW(NULL, game, 32768)) return;
    wchar_t *slash = wcsrchr(folder, L'\\'), *name = wcsrchr(game, L'\\');
    if (!slash || !name || _wcsicmp(name + 1, L"SnowRunner.exe")) return;
    slash[1] = 0;
    swprintf_s(status_path, 32768, L"%lsSnowRunnerEnhanced.status.json", folder);
    swprintf_s(temp_path, 32768, L"%lsSnowRunnerEnhanced.status.tmp", folder);
    // The static devkit needs GLib/GObject initialization before its JSON
    // parser can be used. This does not create any feature/game hooks.
    int enabled = configured_features;
    if (enabled < 0) { SimpleStatus("configuration-error", "Missing or invalid configuration"); return; }
    // Core UI is always loaded, including when every optional enhancement is off.
    HMODULE pinned;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
                          (LPCWSTR)(uintptr_t)&EnhancedStart, &pinned)) return;
    char hash[65] = "unavailable"; HashGame(hash);
    GMainContext *context = g_main_context_new();
    g_main_context_push_thread_default(context);
    SettingsPreferences preferences=SettingsLoad(folder);
    char *module_flags = MenuModuleFlags(enabled);
    char *source = g_strdup_printf("const ENHANCED_HOST={modules:%s,gameSha256:'%s',general:%s,wheelMouse:%s,map:%s,zoomSensitivity:%d,panningSensitivity:%d,keepNorthUp:%s,vehicle:%s,automaticReverse:%s};\n%s", module_flags, hash, (enabled & 8) ? "true" : "false", (enabled & 1) ? "true" : "false", (enabled & 4) ? "true" : "false", preferences.zoom, preferences.panning, preferences.keep_north_up?"true":"false", (enabled & 16)?"true":"false", preferences.automatic_reverse?"true":"false", enhanced_bundle);
    GError *error = NULL;
    g_free(module_flags);
    GumScript *script = gum_script_backend_create_sync(gum_script_backend_obtain_qjs(), "Enhanced", source, NULL, NULL, &error);
    g_free(source);
    if (!script) { SimpleStatus("error", "Embedded runtime initialization failed"); if (error) g_error_free(error); return; }
    gum_script_set_message_handler(script, OnMessage, script, NULL);
    gum_script_load_sync(script, NULL);
    // This is Enhanced's dedicated worker. The ASI loader never waits here.
    // Keep the context and script alive; uninstall only with the game closed.
    GMainLoop *loop = g_main_loop_new(context, FALSE);
    g_main_loop_run(loop);
}

static DWORD WINAPI EnhancedWorker(void *unused) {
    (void)unused;
    EnhancedStart();
    return 0;
}

__declspec(dllexport) void InitializeASI(void) {
    DWORD error = GetLastError();
    wchar_t gamePath[32768];
    if (!GetModuleFileNameW(NULL,gamePath,32768)) { SetLastError(error); return; }
    wchar_t *gameName=wcsrchr(gamePath,L'\\');
    if (!gameName || _wcsicmp(gameName+1,L"SnowRunner.exe")) { SetLastError(error); return; }
    if (InterlockedCompareExchange(&started, 1, 0) == 0) {
        // Startup interception must be ready before returning to the game.
        // Wheel discovery remains asynchronous; archive validation is opt-in.
        // Pin before starting the worker, including disabled/error paths.
        HMODULE pinned;
        if (GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
                              (LPCWSTR)(uintptr_t)&InitializeASI, &pinned)) {
            gum_init_embedded();
            wchar_t folder[32768];
            DWORD n = GetModuleFileNameW(self, folder, 32768);
            wchar_t *slash = n && n < 32768 ? wcsrchr(folder, L'\\') : NULL;
            if (slash) {
                slash[1] = 0;
                configured_features = ReadConfiguration(folder);
                if (configured_features >= 0) {
                    if (configured_features & 32) SteeringInstall();
                    StartupInstall(folder);
                }
            }
            HANDLE thread = CreateThread(NULL, 0, EnhancedWorker, NULL, 0, NULL);
            if (thread) CloseHandle(thread);
            else InterlockedExchange(&started, 0);
        } else InterlockedExchange(&started, 0);
    }
    SetLastError(error);
}

BOOL WINAPI DllMain(HINSTANCE module, DWORD why, LPVOID reserved) {
    (void)reserved;
    if (why == DLL_PROCESS_ATTACH) { self = module; DisableThreadLibraryCalls(module); }
    return TRUE;
}
