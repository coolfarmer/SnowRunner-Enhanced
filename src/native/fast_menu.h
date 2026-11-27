/* Install a direct native gate transactionally: publish the original trampoline
 * before any game thread can enter the replacement. No per-call Gum context. */
static __declspec(thread) unsigned fast_menu_callback_depth;

__declspec(dllexport) unsigned *EnhancedFastMenuThreadState(void) {
    return &fast_menu_callback_depth;
}

/* Only positive descriptor identities enter this table. Concurrent discovery
 * publishes the identity before marking its registration resolved. */
__declspec(dllexport) int EnhancedRememberVmTarget(void **table, void *target) {
    uintptr_t key=(uintptr_t)target;
    unsigned bucket=(unsigned)((key>>4)^(key>>13))&63;
    for(unsigned i=0;i<64;i++) {
        void *old=InterlockedCompareExchangePointer(&table[(bucket+i)&63],target,NULL);
        if(!old || old==target)return 1;
    }
    return 0; /* The caller must fall back to the complete filter. */
}

__declspec(dllexport) void EnhancedResolveVmRegistration(void *mask, unsigned bit) {
    InterlockedAnd((volatile LONG *)mask,(LONG)~bit);
}

/* Per-phase rejection table for the save-loading experiment. A class prefix
 * can rule out a callback, never select one. The existing dispatcher still
 * performs the exact name match, registration and callback. */
typedef struct {
    const unsigned char **pool;
    const volatile uintptr_t *enabled;
    const volatile uintptr_t *known;
    const volatile unsigned *unresolved;
    const volatile uintptr_t *overflow;
    void (*dispatch)(void *, void *);
    unsigned first[256];
    unsigned second[256];
} FastVmPrefixes;

__declspec(dllexport) void EnhancedDispatchVmPrefix(void *vm, unsigned char *method,
        const FastVmPrefixes *filter) {
    if (!*filter->enabled || fast_menu_callback_depth) return;
    unsigned unresolved = *filter->unresolved;
    uintptr_t key = (uintptr_t)method;
    unsigned bucket = (unsigned)((key >> 4) ^ (key >> 13)) & 63;
    if (!*filter->overflow) {
        for (unsigned i = 0; i < 64; ++i) {
            uintptr_t known = filter->known[(bucket + i) & 63];
            if (known == key) break;
            if (!known) {
                if (!unresolved) return;
                const unsigned char *cls = *(const unsigned char **)(method + 0x48);
                if (!cls) return;
                unsigned id = *(const unsigned *)(cls + 0x18);
                if (id > 0x10000000) return;
                const unsigned char *name = *filter->pool + id;
                unsigned candidates = unresolved & filter->first[name[0]];
                if (!candidates) return;
                unsigned second = name[1];
                if (second == 255) second = 0;
                if (!(candidates & filter->second[second])) return;
                break;
            }
        }
    }
    filter->dispatch(vm, method);
}

static int InstallFastVm(void *target, void *gate,
        void **original, const void *expected, unsigned size, unsigned skip) {
    if (!target || !gate || !original || !expected || size < 16 || size > 256) return -100;
    if (skip && (skip != 8 || memcmp(expected,"\x48\x8b\x49\x50\x48\x8b\x41\x18",8))) return -100;
    GumInterceptor *interceptor = gum_interceptor_obtain();
    gum_interceptor_begin_transaction(interceptor);
    int result = -101;
    void *trampoline = NULL;
    if (!memcmp(target, expected, size)) {
        result = gum_interceptor_replace_fast(interceptor, target, gate, &trampoline, NULL);
        if (result == GUM_REPLACE_OK) {
            unsigned char *resume = trampoline;
            if (skip) {
                // The gate executes these two non-relative loads between its
                // observers. Skip them in the original trampoline exactly once.
                if (!memcmp(resume,"\xf3\x0f\x1e\xfa",4)) resume += 4;
                if (memcmp(resume,expected,skip)) {
                    gum_interceptor_revert(interceptor,target);
                    result = -102;
                } else resume += skip;
            }
            if (result == GUM_REPLACE_OK) *original = resume;
        }
    }
    gum_interceptor_end_transaction(interceptor);
    g_object_unref(interceptor);
    return result;
}

__declspec(dllexport) int EnhancedInstallFastMenu(void *target, void *gate,
        void **original, const void *expected, unsigned size) {
    return InstallFastVm(target,gate,original,expected,size,0);
}

__declspec(dllexport) int EnhancedInstallFastVmSplit(void *target, void *gate,
        void **original, const void *expected, unsigned size) {
    return InstallFastVm(target,gate,original,expected,size,8);
}

#ifdef ENHANCED_FAST_MENU_TEST
/* Tests call this only once all synthetic invocations have stopped. In-game,
 * disabled gates and their memory remain alive until process termination. */
__declspec(dllexport) void EnhancedRemoveFastMenuForTest(void *target) {
    GumInterceptor *interceptor = gum_interceptor_obtain();
    gum_interceptor_revert(interceptor, target);
    gum_interceptor_flush(interceptor);
    g_object_unref(interceptor);
}
#endif
