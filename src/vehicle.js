'use strict';

// ShiftGear semantics and transmission layout: github.com/dazza-bo/SR-NoAutoReverse.
function makeVehicleReverse(profile) {
    const shift = Process.mainModule.base.add(profile.shiftGearRva);
    const guard = profile.guards[0].hex;
    function verify() {
        const bytes = new Uint8Array(shift.readByteArray(guard.length / 2));
        if (!bytes.every((value, i) => value === parseInt(guard.slice(i*2,i*2+2),16)))
            throw Error('Unsupported ShiftGear function');
    }
    verify();
    const counts = {blocked:0, manual:0, returnedToAuto:0, unknown:0};
    const original = new NativeFunction(shift, 'uint8', ['pointer','int']);

    const filter = new NativeCallback((vehicle, gear) => {
        if (gear === -1) {
            try {
                const transmission = vehicle.add(0x68).readPointer();
                if (transmission.add(0x30).readPointer().equals(vehicle)) {
                    const auto = transmission.add(0x3c).readU8();
                    if (auto === 1) {
                        if (transmission.add(0x70).readS32() !== -1) {
                            counts.blocked++;
                            return 0;
                        }
                        counts.returnedToAuto++;
                        gear = 1;
                    } else if (auto === 0) counts.manual++;
                    else counts.unknown++;
                } else counts.unknown++;
            } catch (_) { counts.unknown++; }
        }
        return original(vehicle, gear);
    }, 'uint8', ['pointer','int']);
    let enabled = true, fault = null;
    return {
        set(value) {
            if (fault) throw Error(fault);
            if (enabled === value) return;
            try {
                if (value) Interceptor.revert(shift);
                else {
                    verify();
                    Interceptor.replace(shift, filter);
                }
                Interceptor.flush();
                enabled = value;
            } catch (error) {
                fault = String(error);
                throw error;
            }
        },
        status() { return {automaticReverse:enabled, ...counts, fault}; }
    };
}
