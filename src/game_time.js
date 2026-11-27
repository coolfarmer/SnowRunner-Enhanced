'use strict';

// Select the existing zero-increment branch for this clock update only. Never
// write the game's global mode, hour, speed factors, or a retained world object.
function makeGameTimeFreeze(profile, vmProfile, attach = hookHudHintUpdates) {
    const base = Process.mainModule.base, pool = base.add(vmProfile.stringPoolSlotRva);
    for (const guard of profile.guards) {
        const bytes = new Uint8Array(base.add(guard.rva).readByteArray(guard.hex.length / 2));
        if (!bytes.every((v, i) => v === parseInt(guard.hex.slice(i * 2, i * 2 + 2), 16)))
            throw Error('Unsupported game clock: ' + guard.name);
    }
    const state = Memory.alloc(64), hooks = [];
    state.writeByteArray(new Uint8Array(64));
    state.add(56).writePointer(base.add(profile.clockSlotRva));
    const module = new CModule(`
#include <gum/guminterceptor.h>
typedef struct {
    volatile guint32 enabled, session, running, fault;
    guint64 updates, last_clock, clock_changes, frozen_updates;
    guint32 foreign_mode, applied;
    guint64 clock_slot;
} State;
extern State state;
void step(GumInvocationContext *ic) {
    guint64 clock;
    state.applied=0;
    if (!state.running || state.fault) return;
    clock=*(guint64 *)(guintptr)state.clock_slot;
    if (!clock || clock != ic->cpu_context->r13) {
        state.fault=1; state.session=0; return;
    }
    state.updates++;
    if (clock != state.last_clock) { state.last_clock=clock; state.clock_changes++; }
    state.foreign_mode=(guint32)ic->cpu_context->rcx;
    if (!state.enabled || state.session != 1 || state.foreign_mode != 0) return;
    ic->cpu_context->rcx=3;
    state.applied=1;
    state.frozen_updates++;
}
`, {state});
    let fault = null, session = null, singleStarts = 0, multiplayerStarts = 0;
    function name(id) {
        if (id > 0x10000000) throw Error('Invalid session name');
        const bytes = new Uint8Array(pool.readPointer().add(id).readByteArray(128));
        let end = 0; while (end < bytes.length && bytes[end] && bytes[end] !== 255) end++;
        if (end === bytes.length) throw Error('Unterminated session name');
        return String.fromCharCode(...bytes.slice(0, end));
    }
    function disarm(kind = 0) { state.add(4).writeU32(kind); state.add(52).writeU32(0); }
    function watch(method, callback) {
        hooks.push(attach(base.add(vmProfile.guards.find(g => g.name === 'vm_frame_push_entry').rva), pool,
            (vm, fn) => {
                if (fault || state.add(12).readU32()) { disarm(); return; }
                try { callback(vm, fn); }
                catch (error) { disarm(); fault = String(error); }
            }, 'GameSession', method));
    }
    function stop() {
        state.add(8).writeU32(0); disarm();
        for (const hook of hooks.splice(0).reverse()) hook.detach();
        Interceptor.flush();
    }
    try {
        // Unknown sessions fail closed. The native callback never dereferences
        // this VM receiver; it is only an identity for the current lifecycle.
        watch('Init', () => { disarm(); session = null; });
        watch('Terminate', () => { disarm(); session = null; });
        for (const method of ['CreateMultiplayer', 'CreateCoopMaster', 'CreateCoopClient'])
            watch(method, () => { disarm(2); session = null; multiplayerStarts++; });
        watch('CreateSinglePlayer', (vm, fn) => {
            disarm();
            const words = profile.singlePlayerWords, code = fn.add(0x60).readPointer();
            const cls = fn.add(0x48).readPointer(), signature = fn.add(0x40).readPointer();
            if (name(cls.add(0x18).readU32()) !== 'GameSession' || name(signature.readU32()) !== 'CreateSinglePlayer' ||
                fn.add(0x68).readU32() !== words.length || !words.every((w, i) => code.add(i * 4).readU32() === w) ||
                fn.add(0x58).readU32() !== 2) throw Error('Unsupported single-player session');
            const type = fn.add(0x50).readPointer().readPointer();
            if (type.shr(48).toUInt32() !== 0x30 || name(type.and('0xffffffffffff').add(8).readU32()) !== 'GameModeSingle')
                throw Error('Unsupported single-player constructor');
            const value = vm.add(0x18).readPointer().readPointer();
            if (value.shr(48).toUInt32() !== 0x20) throw Error('Invalid session receiver');
            session = value.and('0xffffffffffff').toString();
            singleStarts++; state.add(4).writeU32(1);
        });
        hooks.push(Interceptor.attach(base.add(profile.clockStepRva), module.step));
        Interceptor.flush(); state.add(8).writeU32(1);
    } catch (error) { stop(); throw error; }
    return {
        set(value) { state.writeU32(value === true ? 1 : 0); if (!value) state.add(52).writeU32(0); },
        stop,
        status() {
            const nativeFault = state.add(12).readU32();
            return {status: fault || nativeFault ? 'error' : state.add(8).readU32() ? 'ready' : 'stopped',
                enabled: !!state.readU32(), active: !!state.add(52).readU32(),
                session: ['unknown', 'single-player', 'co-op'][state.add(4).readU32()] || 'unknown',
                sessionIdentity: session, singleStarts, multiplayerStarts,
                updates: state.add(16).readU64().toNumber(), clockChanges: state.add(32).readU64().toNumber(),
                frozenUpdates: state.add(40).readU64().toNumber(), foreignMode: state.add(48).readU32(),
                fault: fault || (nativeFault ? 'Clock object mismatch' : null)};
        },
        keepAlive: [state, module]
    };
}
