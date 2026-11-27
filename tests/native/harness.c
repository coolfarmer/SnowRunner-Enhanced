/* JSON-lines host for the real embedded GumJS runtime; never shipped. */
#include "frida-gumjs.h"
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef ENHANCED_FAST_MENU_TEST
#include "../../src/native/fast_menu.h"
#endif

static GumScript *scripts[32];
static JsonNode *rpc_result;
static gboolean rpc_done, rpc_error;

static void Message(const gchar *text, GBytes *data, gpointer context) {
    (void)data; (void)context;
    JsonParser *parser = json_parser_new();
    if (json_parser_load_from_data(parser, text, -1, NULL)) {
        JsonObject *root = json_node_get_object(json_parser_get_root(parser));
        const char *type = json_object_get_string_member(root, "type");
        JsonNode *payload = json_object_get_member(root, "payload");
        if (!strcmp(type, "send") && payload && JSON_NODE_HOLDS_ARRAY(payload)) {
            JsonArray *a = json_node_get_array(payload);
            if (json_array_get_length(a) >= 4 && !strcmp(json_array_get_string_element(a, 0), "frida:rpc")) {
                rpc_error = strcmp(json_array_get_string_element(a, 2), "ok") != 0;
                rpc_result = json_node_copy(json_array_get_element(a, 3));
                rpc_done = TRUE;
            }
        } else if (!strcmp(type, "error")) {
            fprintf(stderr, "%s\n", text); fflush(stderr);
        }
    }
    g_object_unref(parser);
}

static char *ReadLine(void) {
    GString *s = g_string_new(NULL); int ch;
    while ((ch = getchar()) != EOF && ch != '\n') g_string_append_c(s, (char)ch);
    if (ch == EOF && !s->len) { g_string_free(s, TRUE); return NULL; }
    return g_string_free(s, FALSE);
}

int main(void) {
    gum_init_embedded();
    GMainContext *ctx = g_main_context_default();
    char *line;
    while ((line = ReadLine()) != NULL) {
        JsonParser *parser = json_parser_new(); GError *error = NULL;
        if (!json_parser_load_from_data(parser, line, -1, &error)) return 2;
        JsonObject *root = json_node_get_object(json_parser_get_root(parser));
        const char *op = json_object_get_string_member(root, "op");
        int id = (int)json_object_get_int_member(root, "id");
        if (id < 0 || id >= 32) return 3;
        gboolean ok = TRUE;
        char *result = NULL;
        if (!strcmp(op, "create")) {
            scripts[id] = gum_script_backend_create_sync(gum_script_backend_obtain_qjs(), "test",
                json_object_get_string_member(root, "source"), NULL, NULL, &error);
            ok = scripts[id] != NULL;
            if (ok) gum_script_set_message_handler(scripts[id], Message, NULL, NULL);
        } else if (!strcmp(op, "load")) gum_script_load_sync(scripts[id], NULL);
        else if (!strcmp(op, "unload")) { gum_script_unload_sync(scripts[id], NULL); g_object_unref(scripts[id]); scripts[id] = NULL; }
        else if (!strcmp(op, "call")) {
            char *args = json_to_string(json_object_get_member(root, "args"), FALSE);
            const char *method = json_object_get_string_member(root, "method");
            char *request = g_strdup_printf("[\"frida:rpc\",1,\"call\",\"%s\",%s]", method, args);
            rpc_done = FALSE; rpc_error = FALSE; rpc_result = NULL;
            gum_script_post(scripts[id], request, NULL);
            ULONGLONG start = GetTickCount64();
            while (!rpc_done && GetTickCount64() - start < 10000) {
                while (g_main_context_pending(ctx)) g_main_context_iteration(ctx, FALSE);
                Sleep(1);
            }
            ok = rpc_done && !rpc_error;
            if (rpc_result) { result = json_to_string(rpc_result, FALSE); json_node_free(rpc_result); }
            g_free(request); g_free(args);
        } else return 4;
        if (error) { fprintf(stderr, "%s\n", error->message); g_error_free(error); }
        printf("{\"ok\":%s,\"result\":%s}\n", ok ? "true" : "false", result ? result : "null"); fflush(stdout);
        g_free(result); g_object_unref(parser); g_free(line);
    }
    for (int i = 0; i < 32; i++) if (scripts[i]) { gum_script_unload_sync(scripts[i], NULL); g_object_unref(scripts[i]); }
    gum_deinit_embedded();
    return 0;
}
