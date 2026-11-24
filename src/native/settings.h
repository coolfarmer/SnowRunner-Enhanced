// User preferences live separately from the installer's feature configuration
// and receipt hash. They survive an upgrade or uninstall/reinstall.
static wchar_t settings_path[32768], settings_temp[32768];
static const char *settings_state = "default";

static int SettingsValue(JsonNode *node) {
    if (!node || !JSON_NODE_HOLDS_OBJECT(node)) return -1;
    JsonObject *root=json_node_get_object(node);
    JsonNode *schema=json_object_get_member(root,"schemaVersion"), *value=json_object_get_member(root,"zoomSensitivity");
    if (json_object_get_size(root)!=2 || !schema || json_node_get_value_type(schema)!=G_TYPE_INT64 ||
        json_node_get_int(schema)!=1 || !value || json_node_get_value_type(value)!=G_TYPE_INT64) return -1;
    gint64 n=json_node_get_int(value);
    return n>=0 && n<=100 ? (int)n : -1;
}

static int SettingsLoad(const wchar_t *folder) {
    swprintf_s(settings_path,32768,L"%lsSnowRunnerEnhanced.settings.json",folder);
    swprintf_s(settings_temp,32768,L"%lsSnowRunnerEnhanced.settings.tmp",folder);
    HANDLE file=CreateFileW(settings_path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);
    if(file==INVALID_HANDLE_VALUE){settings_state=GetLastError()==ERROR_FILE_NOT_FOUND?"default":"read-error";return 50;}
    char text[1025];DWORD size=GetFileSize(file,NULL),read=0;
    BOOL ok=size>0&&size<=1024&&ReadFile(file,text,size,&read,NULL)&&read==size;
    CloseHandle(file);
    int value=-1;
    if(ok){
        text[size]=0;JsonParser *parser=json_parser_new();
        if(json_parser_load_from_data(parser,text,size,NULL))value=SettingsValue(json_parser_get_root(parser));
        g_object_unref(parser);
    }
    settings_state=value>=0?"loaded":"invalid-file";
    return value>=0?value:50;
}

static BOOL SettingsSave(JsonNode *node) {
    int value=SettingsValue(node);if(value<0)return FALSE;
    char text[100];int count=snprintf(text,sizeof(text),"{\"schemaVersion\":1,\"zoomSensitivity\":%d}\n",value);
    HANDLE file=CreateFileW(settings_temp,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_DELETE,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    if(file==INVALID_HANDLE_VALUE){settings_state="write-error";return FALSE;}
    DWORD written=0;
    BOOL ok=WriteFile(file,text,(DWORD)count,&written,NULL)&&written==(DWORD)count&&FlushFileBuffers(file);
    CloseHandle(file);
    if(ok)ok=MoveFileExW(settings_temp,settings_path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
    if(!ok)DeleteFileW(settings_temp);
    settings_state=ok?"saved":"write-error";
    return ok;
}
