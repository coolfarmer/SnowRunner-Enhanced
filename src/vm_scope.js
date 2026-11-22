'use strict';

// Layout verified against this build's VM frame push/pop and native call code.
// Unknown callers keep the original value; only observed UI methods qualify.
function makeUiScope(stringPoolSlot, callerRoles) {
    const names = new Map();
    function name(id) {
        if (names.has(id)) return names.get(id);
        if (id > 0x10000000) throw new Error('Invalid string offset');
        const bytes = new Uint8Array(stringPoolSlot.readPointer().add(id).readByteArray(160));
        let end = 0;
        while (end < bytes.length && bytes[end] !== 0 && bytes[end] !== 255) end++;
        if (end === bytes.length) throw new Error('Unterminated VM name');
        const value = String.fromCharCode(...bytes.slice(0, end));
        if (names.size < 1024) names.set(id, value);
        return value;
    }
    const scope = context => {
        try {
            let frame = context.rsi.add(0x30).readPointer();
            let query = '';
            for (let i = 0; i < 24 && !frame.isNull(); i++) {
                const fn = frame.add(8).readPointer();
                const signature = fn.add(0x40).readPointer();
                const cls = fn.add(0x48).readPointer();
                const className = cls.isNull() ? '' : name(cls.add(0x18).readU32());
                const method = name(signature.readU32());
                if (className === 'InputFocusDeviceListener' &&
                        ['IsMouse', 'IsSteeringWheel', 'IsGamepad', 'IsDurangoGamepad'].includes(method))
                    query = method;
                if (className !== 'InputFocusDeviceListener' && className !== 'delegate') {
                    const caller = className + '.' + method;
                    const qualified = caller + (query ? '/' + query : '');
                    return {caller: qualified, role: callerRoles[qualified] || callerRoles[caller] ||
                        callerRoles[className + '.*'] || 'original'};
                }
                frame = frame.add(0x18).readPointer();
            }
        } catch (_) { /* An unreadable or unfamiliar stack is never redirected. */ }
        return {caller: '<unknown>', role: 'original'};
    };
    scope.frame = (context, expected) => {
        try {
            let frame = context.rsi.add(0x30).readPointer();
            for (let i = 0; i < 24 && !frame.isNull(); i++) {
                const fn = frame.add(8).readPointer();
                const cls = fn.add(0x48).readPointer();
                const className = cls.isNull() ? '' : name(cls.add(0x18).readU32());
                const method = name(fn.add(0x40).readPointer().readU32());
                if (className + '.' + method === expected) return frame;
                frame = frame.add(0x18).readPointer();
            }
        } catch (_) { /* Unknown stacks must not mutate list state. */ }
        return null;
    };
    scope.hasCaller = (context, expected) => scope.frame(context, expected) !== null;
    scope.receiver = (context, expected) => {
        try {
            let frame = context.rsi.add(0x30).readPointer();
            for (let i = 0; i < 24 && !frame.isNull(); i++) {
                const fn = frame.add(8).readPointer(), cls = fn.add(0x48).readPointer();
                const className = cls.isNull() ? '' : name(cls.add(0x18).readU32());
                const method = name(fn.add(0x40).readPointer().readU32());
                if (className + '.' + method === expected) {
                    // VM frame +0 points at the argument stack captured on push.
                    // The receiver is an object variant, tagged 0x20 at byte 6.
                    const value = frame.readPointer().readPointer();
                    return value.shr(48).and(255).toUInt32() === 0x20 ?
                        value.and('0xff00ffffffffffff') : null;
                }
                frame = frame.add(0x18).readPointer();
            }
        } catch (_) { /* No receiver inferred from an unreadable frame. */ }
        return null;
    };
    scope.hudHintUpdate = (vm, fn) => {
        try {
            const cls = fn.add(0x48).readPointer();
            if (cls.isNull() || name(cls.add(0x18).readU32()) !== 'NavigationPanelController' ||
                    name(fn.add(0x40).readPointer().readU32()) !== 'Update' ||
                    fn.add(0x68).readU32() !== 117) return null;
            // This exact prologue tests isForced before comparing oldState.
            // The existing forced-update path rebuilds the navigation buttons.
            const words = [0x80000301,0x80000207,0x8000001b,0x80001118,0x80000002,0x80000007,
                0x8000350a,0x80000003,0x80000830,0x80001118,0x80000002,0x80000101,
                0x80000107,0x80000007,0x8000350a,0x80000104,0x8000080d,0x80001316,
                0x80000313,0x80000101,0x80000107,0x80000004,0x8000090d,0x80000007,
                0x8000353c,0x80000002,0x80000107,0x8000040a,0x80000007,0x8000073c,
                0x80000002,0x80000038,0x7fffff3b,0x80000002,0x80000007,0x8000310a,
                0x80000048,0x80000104,0x80000730,0x80002e16,0x80000004,0x80000007,
                0x8000320a,0x8000003f,0x7fffff3b,0x80000002,0x80000101,0x80000007,
                0x80000004,0x80003d0d,0x80000002,0x80000101,0x80000107,0x80000007,
                0x80000104,0x8000400d,0x80000002,0x80000101,0x80000007,0x8000310a,
                0x80000004,0x80000f0d,0x7ffffe3b,0x80000002,0x80000101,0x7ffffe07,
                0x80000004,0x8000060d,0x8000001b,0x80005916,0x80000101,0x7ffffe07,
                0x80000004,0x8000040d,0x7ffffd3b,0x80000002,0x80000101,0x80000007,
                0x8000070a,0x7ffffd07,0x80000104,0x80000f0d,0x80000002,0x80000101,
                0x7ffffe07,0x80000004,0x8000070d,0x80000002,0x8000401a,0x80000003,
                0x7ffffe3b,0x80000002,0x80000007,0x8000310a,0x80000048,0x80000104,
                0x80000730,0x80006918,0x80000002,0x7fffff07,0x80000004,0x80000007,
                0x8000320a,0x8000003f,0x80000830,0x80006f16,0x80000101,0x80000007,
                0x80000004,0x8000010f,0x80000002,0x80000101,0x80000007,0x80000004,
                0x8000410d,0x80000002,0x80000313];
            const code = fn.add(0x60).readPointer();
            if (!words.every((w, i) => code.add(i * 4).readU32() === w)) return null;
            // The same controller updates HUD, popup and menu navigation.
            // Validate its entire method and typed arguments, independently
            // of the owning screen; every instance has its own refresh epoch.
            const argv = vm.add(0x18).readPointer();
            const receiver = argv.readU64(), state = argv.add(8).readU64();
            const forced = argv.add(16);
            if (receiver.shr(48).toNumber() !== 0x20 || receiver.and('0xffffffffffff').toNumber() === 0 ||
                    state.shr(48).toNumber() !== 0x20 || state.and('0xffffffffffff').toNumber() === 0 ||
                    forced.readU64().shr(48).toNumber() !== 2 || forced.readU8() > 1) return null;
            // Only the low byte is meaningful for a VM boolean. Its remaining
            // payload bytes may contain old stack data and must be preserved.
            return {key:receiver.toString(16), forced};
        } catch (_) { return null; }
    };
    scope.isWheelNeutralComparison = (vm, operand) => {
        try {
            // Exact live stack observed in this build. Never search past an
            // intervening call: other uses of AbsFloat/IsEqualFloat stay real.
            let frame = vm.add(0x30).readPointer();
            const frames = [];
            for (const [expectedClass, expectedMethod, pc] of [
                    ['__global', 'AbsFloat', 0], ['__global', 'IsEqualFloat', 6],
                    ['TruckInputController', 'UpdateSteeringWheelInputs', 464]]) {
                if (frame.isNull()) return false;
                const fn = frame.add(8).readPointer(), cls = fn.add(0x48).readPointer();
                if (cls.isNull() || name(cls.add(0x18).readU32()) !== expectedClass ||
                        name(fn.add(0x40).readPointer().readU32()) !== expectedMethod ||
                        frame.add(0x10).readU32() !== pc) return false;
                frames.push({frame, fn});
                frame = frame.add(0x18).readPointer();
            }
            if (!frames[0].frame.readPointer().add(8).equals(operand)) return false;
            const argv = frames[1].frame.readPointer();
            for (const offset of [8, 16, 24])
                if (argv.add(offset).readU64().shr(48).toNumber() !== 3) return false;
            if (argv.add(8).readU32() !== operand.readU32() || argv.add(16).readFloat() !== 0 ||
                    argv.add(24).readU32() !== 0x358637bd) return false; // original 1e-6 tolerance
            const equal = frames[1].fn, wheel = frames[2].fn;
            if (equal.add(0x68).readU32() !== 10 || wheel.add(0x68).readU32() !== 535) return false;
            const matches = (fn, start, words) => {
                const code = fn.add(0x60).readPointer().add(start * 4);
                return words.every((word, i) => code.add(i * 4).readU32() === word);
            };
            return matches(equal, 0, [2147483905,2147483911,2147484167,2147483685,
                2147483656,2147483908,2147584781,2147484423,2147486002,2147484690]) &&
                matches(wheel, 459, [2147485190,2147483654,2147482887,2147483656,
                    2147484420,2147592205,2147607574]);
        } catch (_) { return false; }
    };
    return scope;
}

function hookHudHintUpdates(framePush, stringPoolSlot, update) {
    // VM calls are frequent. Discover the exact method in native code, then
    // filter by its descriptor address; only that method enters JavaScript.
    const state = Memory.alloc(16);
    state.writePointer(stringPoolSlot);
    state.add(8).writePointer(ptr(0));
    const callback = new NativeCallback(update, 'void', ['pointer', 'pointer']);
    const module = new CModule(`
#include <gum/guminterceptor.h>
typedef struct { guint64 pool_slot, target; } State;
extern State state;
extern void update(void *vm, void *fn);
static guint64 word(guint64 p) { return *(guint64 *)(guintptr)p; }
static int named(guint32 id, const char *expected) {
    const unsigned char *p;
    if (id > 0x10000000) return 0;
    p=(const unsigned char *)(guintptr)(word(state.pool_slot)+id);
    while (*expected) if (*p++ != (unsigned char)*expected++) return 0;
    return *p==0 || *p==255;
}
void on_enter(GumInvocationContext *ic) {
    guint64 fn=(guint64)gum_invocation_context_get_nth_argument(ic,1),cls,signature;
    int error;
    if (state.target) { if (fn != state.target) return; }
    else {
        cls=word(fn+0x48); if (!cls) return;
        if (!named(*(guint32 *)(guintptr)(cls+0x18),"NavigationPanelController")) return;
        signature=word(fn+0x40); if (!signature) return;
        if (!named(*(guint32 *)(guintptr)signature,"Update")) return;
        state.target=fn;
    }
    error=ic->system_error;
    update(gum_invocation_context_get_nth_argument(ic,0),(void *)(guintptr)fn);
    ic->system_error=error;
}
`, {state, update:callback});
    const hook = Interceptor.attach(framePush, {onEnter:module.on_enter});
    // Retain compiled code and the callback until after detach + flush.
    return {detach:() => hook.detach(), keepAlive:[state, callback, module]};
}
