'use strict';

// Both discovery and the click-time ID lookup must see the same vehicle pool.
// Keep the native socket-distance/eligibility and cable-creation checks: vehicle
// origins are not a conservative spatial bound for long trailers or addons.
function makeVehicleWinchRange(profile) {
    const base = Process.mainModule.base;
    for (const guard of profile.guards) {
        const bytes = new Uint8Array(base.add(guard.rva).readByteArray(guard.hex.length / 2));
        if (!bytes.every((value, i) => value === parseInt(guard.hex.slice(i * 2, i * 2 + 2), 16)))
            throw Error('Unsupported winch code: ' + guard.name);
    }
    const registry = base.add(profile.vehicleRegistryRva);
    const selectionCaller = base.add(profile.selectionCallerRva);
    const attachmentCaller = base.add(profile.attachmentCallerRva);
    // Separate buffers protect overlapping/reentrant calls. Native code borrows
    // this vector until return; it neither mutates nor retains it.
    const limit = 512;
    const buffers = Array.from({length: 4}, () => ({busy: false,
        vector: Memory.alloc(24), data: Memory.alloc(limit * 8)}));
    const hooks = [];
    const counts = {selectionCalls: 0, attachmentCalls: 0, acceptedAttachments: 0, vehicles: 0};
    let running = false, fault = null;
    function stop() {
        running = false;
        while (hooks.length) hooks.pop().detach();
        Interceptor.flush();
    }
    function fail(error) {
        fault = String(error);
        running = false;
        // Do not tear down invocation callbacks while one owns a buffer.
        setImmediate(stop);
    }
    function substitute(args, index, invocation) {
        const begin = registry.readPointer(), end = registry.add(8).readPointer();
        if (end.compare(begin) < 0) throw Error('Invalid winch vehicle registry');
        const size = Number(end.sub(begin).toString());
        if (!Number.isSafeInteger(size) || size % 8 || size > limit * 8 || (size && begin.isNull()))
            throw Error('Unsupported winch vehicle registry size');
        if (!size) return;
        const buffer = buffers.find(item => !item.busy);
        if (!buffer) throw Error('Overlapping winch calls exceed buffer limit');
        buffer.data.writeByteArray(begin.readByteArray(size));
        buffer.vector.writePointer(buffer.data);
        buffer.vector.add(8).writePointer(buffer.data.add(size));
        buffer.vector.add(16).writePointer(buffer.data.add(limit * 8));
        buffer.busy = true;
        invocation.winchBuffer = buffer;
        args[index] = buffer.vector;
        counts.vehicles = size / 8;
    }
    function release(invocation) {
        if (invocation.winchBuffer) invocation.winchBuffer.busy = false;
    }
    try {
        hooks.push(Interceptor.attach(base.add(profile.selectionRva), {
            onEnter(args) {
                const savedError = this.lastError;
                try {
                    if (!running || !this.returnAddress.equals(selectionCaller) || args[3].isNull()) return;
                    substitute(args, 1, this);
                    if (this.winchBuffer) counts.selectionCalls++;
                } catch (error) { fail(error); }
                finally { this.lastError = savedError; }
            },
            onLeave() { release(this); }
        }));
        hooks.push(Interceptor.attach(base.add(profile.attachmentRva), {
            onEnter(args) {
                const savedError = this.lastError;
                try {
                    if (!running || !this.returnAddress.equals(attachmentCaller)) return;
                    substitute(args, 2, this);
                    if (this.winchBuffer) counts.attachmentCalls++;
                } catch (error) { fail(error); }
                finally { this.lastError = savedError; }
            },
            onLeave(result) {
                if (this.winchBuffer && (result.toUInt32() & 255)) counts.acceptedAttachments++;
                release(this);
            }
        }));
        Interceptor.flush();
        running = true;
    } catch (error) { stop(); throw error; }
    return {stop, status() { return {status: fault ? 'error' : running ? 'active' : 'stopped', fault, ...counts}; }};
}
