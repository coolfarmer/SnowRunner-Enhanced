'use strict';

// Diagnostic-only replacement for menu startup. The normal bootstrap still
// resolves and validates the same VM entry before calling start(). The callback
// deliberately performs no reads, filtering, counting or JavaScript calls.
function makeEmptyMenuProbe() {
    const discoveryOnly = typeof ENHANCED_DISCOVERY_ONLY !== 'undefined' && ENHANCED_DISCOVERY_ONLY;
    let initialized = false;
    let hook = null, module = null;
    return {
        start(framePush) {
            if (initialized) throw Error('Empty menu probe already started');
            module = new CModule(`
#include <gum/guminterceptor.h>
void on_enter(GumInvocationContext *ic) { (void)ic; }
`);
            // Keep CModule compilation identical in the control; omit only attachment.
            if (!discoveryOnly) hook = Interceptor.attach(framePush, {onEnter: module.on_enter});
            initialized = true;
        },
        status() {
            return {enabled: false, running: false, status: 'disabled', fault: null,
                probeInitialized: initialized,
                interception: {mode: discoveryOnly ? 'discovery-only' : 'empty', nativeHooks: hook ? 1 : 0, filters: 0}};
        },
        stop() {
            if (hook) { hook.detach(); hook = null; Interceptor.flush(); }
            initialized = false;
            // Retain the CModule until after detach/flush and this probe's lifetime.
        }
    };
}
