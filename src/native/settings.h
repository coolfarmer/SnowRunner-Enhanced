// User preferences live separately from the installer's feature configuration
// and receipt hash. They survive an upgrade or uninstall/reinstall.
static wchar_t settings_path[32768], settings_temp[32768];
static const char *settings_state = "default";

typedef struct { int zoom, panning; BOOL keep_north_up, automatic_reverse, truck_storage_search; } SettingsPreferences;

static int SettingsNumber(JsonNode *node) {
    if (!node || json_node_get_value_type(node)!=G_TYPE_INT64) return -1;
    gint64 n=json_node_get_int(node);
    return n>=0 && n<=100 ? (int)n : -1;
}

static BOOL SettingsValue(JsonNode *node, SettingsPreferences *result) {
    if (!node || !JSON_NODE_HOLDS_OBJECT(node)) return FALSE;
    JsonObject *root=json_node_get_object(node);
    JsonNode *schema=json_object_get_member(root,"schemaVersion");
    if (!schema || json_node_get_value_type(schema)!=G_TYPE_INT64) return FALSE;
    gint64 version=json_node_get_int(schema);
    if (version<1 || version>5 || json_object_get_size(root)!=(guint)(version+1)) return FALSE;
    int zoom=SettingsNumber(json_object_get_member(root,"zoomSensitivity"));
    // Upgrade preview.18 preferences without changing the existing zoom value.
    int panning=version==1?50:SettingsNumber(json_object_get_member(root,"panningSensitivity"));
    JsonNode *north=json_object_get_member(root,"keepNorthUp");
    if (zoom<0 || panning<0 || (version>=3 && (!north || json_node_get_value_type(north)!=G_TYPE_BOOLEAN))) return FALSE;
    JsonNode *reverse=json_object_get_member(root,"automaticReverse");
    if(version>=4 && (!reverse || json_node_get_value_type(reverse)!=G_TYPE_BOOLEAN))return FALSE;
    JsonNode *search=json_object_get_member(root,"truckStorageSearch");
    if(version>=5 && (!search || json_node_get_value_type(search)!=G_TYPE_BOOLEAN))return FALSE;
    result->truck_storage_search=version<5 || json_node_get_boolean(search);
    result->automatic_reverse=version<4 || json_node_get_boolean(reverse);
    result->zoom=zoom;result->panning=panning;result->keep_north_up=version>=3 && json_node_get_boolean(north);
    return TRUE;
}

static SettingsPreferences SettingsLoad(const wchar_t *folder) {
    SettingsPreferences values={50,50,FALSE,TRUE,TRUE};
    swprintf_s(settings_path,32768,L"%lsSnowRunnerEnhanced.settings.json",folder);
    swprintf_s(settings_temp,32768,L"%lsSnowRunnerEnhanced.settings.tmp",folder);
    HANDLE file=CreateFileW(settings_path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);
    if(file==INVALID_HANDLE_VALUE){settings_state=GetLastError()==ERROR_FILE_NOT_FOUND?"default":"read-error";return values;}
    char text[1025];DWORD size=GetFileSize(file,NULL),read=0;
    BOOL ok=size>0&&size<=1024&&ReadFile(file,text,size,&read,NULL)&&read==size;
    CloseHandle(file);
    BOOL valid=FALSE;
    if(ok){
        text[size]=0;JsonParser *parser=json_parser_new();
        if(json_parser_load_from_data(parser,text,size,NULL))valid=SettingsValue(json_parser_get_root(parser),&values);
        g_object_unref(parser);
    }
    settings_state=valid?"loaded":"invalid-file";
    return values;
}

static BOOL SettingsSave(JsonNode *node) {
    SettingsPreferences values;if(!SettingsValue(node,&values))return FALSE;
    char text[256];int count=snprintf(text,sizeof(text),"{\"schemaVersion\":5,\"zoomSensitivity\":%d,\"panningSensitivity\":%d,\"keepNorthUp\":%s,\"automaticReverse\":%s,\"truckStorageSearch\":%s}\n",values.zoom,values.panning,values.keep_north_up?"true":"false",values.automatic_reverse?"true":"false",values.truck_storage_search?"true":"false");
    if(count<0 || count>=(int)sizeof(text)){settings_state="write-error";return FALSE;}
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
