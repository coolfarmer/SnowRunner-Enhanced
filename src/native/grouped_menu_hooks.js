'use strict';

// Diagnostic-only, single-lifecycle batch. Preserve registration order, native
// name filtering and descriptor caches, but attach one listener to the VM entry.
function makeGroupedMenuHooks(attachNative = (address, callbacks) => Interceptor.attach(address, callbacks)) {
    const entries = [];
    let frame = null, pool = null, group = null, sealed = false;
    function attach(framePush, poolSlot, update,
            targetClass = 'NavigationPanelController', targetMethod = 'Update', interior = false) {
        if (sealed) throw Error('Grouped menu registration is closed');
        if (interior) throw Error('Grouped menu requires a function entry');
        if (entries.length >= 32 || typeof update !== 'function' ||
                !/^[A-Za-z_][A-Za-z_0-9]*$/.test(targetClass) ||
                !/^[A-Za-z_][A-Za-z_0-9]*$/.test(targetMethod)) throw Error('Invalid grouped menu registration');
        if (frame && (!frame.equals(framePush) || !pool.equals(poolSlot)))
            throw Error('Grouped menu registrations must share the VM entry and pool');
        frame = framePush; pool = poolSlot;
        const entry = {update, targetClass, targetMethod, active: true, index: entries.length};
        entries.push(entry);
        return {detach() {
            if (!entry.active) return;
            entry.active = false;
            if (group) {
                group.state.add(8 + entry.index * 16 + 8).writeU64(0);
                if (!entries.some(item => item.active) && group.attached) {
                    group.hook.detach(); group.attached = false;
                }
            }
        }};
    }
    attach.commit = () => {
        if (sealed) throw Error('Grouped menu already committed');
        sealed = true;
        if (!entries.length || !entries.some(entry => entry.active)) return;
        const state = Memory.alloc(8 + 16 * entries.length);
        state.writePointer(pool);
        entries.forEach((entry, i) => {
            state.add(8 + i * 16).writePointer(ptr(0));
            state.add(16 + i * 16).writeU64(entry.active ? 1 : 0);
        });
        const callbacks = entries.map(entry => new NativeCallback(entry.update, 'void', ['pointer', 'pointer']));
        const symbols = {state};
        callbacks.forEach((cb, i) => { symbols['update' + i] = cb; });
        const module = new CModule(`
#include <gum/guminterceptor.h>
typedef struct { guint64 target, active; } EntryState;
typedef struct { guint64 pool_slot; EntryState entries[${entries.length}]; } State;
extern State state;
${entries.map((_, i) => 'extern void update' + i + '(void *vm, void *fn);').join('\n')}
typedef void (*Update)(void *, void *);
static const struct { const char *cls, *method; Update update; } entries[] = {
${entries.map((entry, i) => `{${JSON.stringify(entry.targetClass)},${JSON.stringify(entry.targetMethod)},update${i}}`).join(',\n')}
};
static guint64 word(guint64 p) { return *(guint64 *)(guintptr)p; }
static int named(guint32 id, const char *expected) {
    const unsigned char *p;
    if (id > 0x10000000) return 0;
    p = (const unsigned char *)(guintptr)(word(state.pool_slot) + id);
    while (*expected) if (*p++ != (unsigned char)*expected++) return 0;
    return *p == 0 || *p == 255;
}
void on_enter(GumInvocationContext *ic) {
    guint64 fn = (guint64)gum_invocation_context_get_nth_argument(ic, 1);
    unsigned i;
    for (i = 0; i < ${entries.length}; ++i) {
        guint64 cls, signature;
        int error;
        if (!state.entries[i].active) continue;
        if (state.entries[i].target) {
            if (fn != state.entries[i].target) continue;
        } else {
            cls = word(fn + 0x48); if (!cls) continue;
            if (!named(*(guint32 *)(guintptr)(cls + 0x18), entries[i].cls)) continue;
            signature = word(fn + 0x40); if (!signature) continue;
            if (!named(*(guint32 *)(guintptr)signature, entries[i].method)) continue;
            state.entries[i].target = fn;
        }
        error = ic->system_error;
        entries[i].update(gum_invocation_context_get_nth_argument(ic, 0), (void *)(guintptr)fn);
        ic->system_error = error;
    }
}
`, symbols);
        const hook = attachNative(frame, {onEnter: module.on_enter});
        // Keep callbacks, native code and writable cache alive through detach/flush.
        group = {state, callbacks, module, hook, attached: true};
    };
    attach.status = () => ({mode: 'grouped', registrations: entries.length,
        activeRegistrations: entries.filter(entry => entry.active).length,
        nativeHooks: group?.attached ? 1 : 0});
    return attach;
}
