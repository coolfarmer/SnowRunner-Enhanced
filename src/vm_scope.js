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
                    return {caller: qualified, role: callerRoles[qualified] || callerRoles[caller] || 'original'};
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
