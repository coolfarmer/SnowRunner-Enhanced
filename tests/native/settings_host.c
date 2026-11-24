#include "frida-gumjs.h"
#include <windows.h>
#include <stdio.h>
#include <wchar.h>
#include "../../src/native/settings.h"

int wmain(int argc,wchar_t **argv) {
    if(argc<2||argc>3)return 2;
    gum_init_embedded();
    int before=SettingsLoad(argv[1]),saved=-1;
    if(argc==3){
        char *text=g_utf16_to_utf8((const gunichar2 *)argv[2],-1,NULL,NULL,NULL);
        JsonParser *parser=json_parser_new();
        saved=json_parser_load_from_data(parser,text,-1,NULL)&&SettingsSave(json_parser_get_root(parser));
        g_free(text);g_object_unref(parser);
    }
    printf("{\"value\":%d,\"saved\":%d,\"state\":\"%s\"}\n",before,saved,settings_state);
    return 0;
}
