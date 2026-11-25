'use strict';

// ShiftGear semantics and transmission layout: github.com/dazza-bo/SR-NoAutoReverse.
// The complete function body is pinned to the build validated in the driving trial.
function makeVehicleReverse() {
    const shift = Process.mainModule.base.add(0xd73cf0);
    const guard = '488974241048897c241841564883ec20488b8148010000488bf148b9ffffffffffff00ff8bfa4823c1745c0fb64010c0e802a8017551488d8e48010000e88e24d0ff837804007e3f488d8e4801000048895c2430e87724d0ff488d8e48010000488bd8e86824d0ff8b4b04488b5c24303908751332c0488b742438488b7c24404883c420415ec3488b46684883c07485ff7907bfffffffffeb04750233ff8938488bce488b46688b5074e8f153dbff488b742438b001488b7c24404883c420415ec3';
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
    let enabled = true;
    return {
        set(value) {
            if (enabled === value) return;
            if (value) Interceptor.revert(shift);
            else {
                verify();
                Interceptor.replace(shift, filter);
            }
            Interceptor.flush();
            enabled = value;
        },
        status() { return {automaticReverse:enabled, ...counts}; }
    };
}
