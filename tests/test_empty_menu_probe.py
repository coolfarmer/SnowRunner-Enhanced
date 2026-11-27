"""Call the real empty native hook with invalid VM arguments and check passthrough."""
from pathlib import Path
import unittest
from native_host import NativeDevice

ROOT = Path(__file__).resolve().parents[1]


class EmptyMenuProbeTests(unittest.TestCase):
    def test_native_passthrough_and_detach_without_vm_access(self):
        self.run_probe(False)

    def test_discovery_control_never_attaches_and_preserves_entry_bytes(self):
        self.run_probe(True)

    def run_probe(self, discovery_only):
        device = NativeDevice()
        pid = device.spawn(None)
        try:
            source = '(() => {\nconst ENHANCED_DISCOVERY_ONLY=' + ('true' if discovery_only else 'false') + r''';
let attachRequests=0;
const Interceptor={
    attach(...args){attachRequests++;if(ENHANCED_DISCOVERY_ONLY)throw Error('Unexpected attachment');return globalThis.Interceptor.attach(...args);},
    flush(){globalThis.Interceptor.flush();}
};
''' + (ROOT / 'src/native/empty_menu_probe.js').read_text() + r'''
rpc.exports.run = () => {
    const entry = Memory.alloc(Process.pageSize);
    Memory.protect(entry, Process.pageSize, 'rwx');
    // Return arg0 XOR arg1: verify the actual argument registers and return value.
    entry.writeByteArray([...Array(16).fill(0x90),0x48,0x89,0xc8,0x48,0x31,0xd0,0xc3]);
    const original=Array.from(new Uint8Array(entry.readByteArray(23)));
    const call = new NativeFunction(entry,'pointer',['pointer','pointer']);
    const kernel=Process.getModuleByName('kernel32.dll');
    const driver = new CModule(`
extern void set_error(unsigned value);
extern unsigned get_error(void);
extern void *entry(void *vm, void *fn);
unsigned probe(void) {
    unsigned i;
    set_error(1234);
    for (i=0;i<1000;++i) if(entry((void *)1,(void *)2)!=(void *)3)return 0;
    return get_error();
}
`, {set_error:kernel.getExportByName('SetLastError'),get_error:kernel.getExportByName('GetLastError'),entry});
    const run = new NativeFunction(driver.probe,'uint32',[]);
    const baseline=run(), probe=makeEmptyMenuProbe();
    probe.start(entry);Interceptor.flush();
    const active=probe.status(), during=run(), zero=call(ptr(0),ptr(0)).toString();
    const entryUnchanged=original.every((value,i)=>entry.add(i).readU8()===value);
    let duplicateRejected=false;
    try{probe.start(entry);}catch(_){duplicateRejected=true;}
    probe.stop();probe.stop();
    return {baseline,active,during,zero,duplicateRejected,entryUnchanged,attachRequests,stopped:probe.status(),after:run()};
};
})();
'''
            script = device.create_script(source)
            script.load()
            result = script.exports_sync.run()
            self.assertEqual(result['baseline'], 1234)
            self.assertEqual(result['during'], 1234)
            self.assertEqual(result['after'], 1234)
            self.assertEqual(result['zero'], '0x0')
            self.assertTrue(result['duplicateRejected'])
            self.assertFalse(result['active']['enabled'])
            self.assertTrue(result['active']['probeInitialized'])
            self.assertEqual(result['active']['interception'], dict(
                mode='discovery-only' if discovery_only else 'empty', nativeHooks=0 if discovery_only else 1, filters=0))
            self.assertEqual(result['attachRequests'], 0 if discovery_only else 1)
            if discovery_only:
                self.assertTrue(result['entryUnchanged'])
            self.assertEqual(result['stopped']['interception']['nativeHooks'], 0)
            script.unload()
        finally:
            device.kill(pid)


if __name__ == '__main__':
    unittest.main()
