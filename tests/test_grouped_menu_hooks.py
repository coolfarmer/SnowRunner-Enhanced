"""Run both native dispatchers against real function calls in embedded GumJS."""
from pathlib import Path
import unittest

from native_host import NativeDevice

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''
rpc.exports.run = scenario => {
    const keep = [], alloc = n => { const p=Memory.alloc(n); keep.push(p); return p; };
    const pool = alloc(8192), slot = alloc(8); slot.writePointer(pool);
    let used = 0;
    const name = text => { const id=used; pool.add(id).writeUtf8String(text); used+=text.length+1; return id; };
    function descriptor(cls, method) {
        const fn=alloc(128), c=alloc(64), sig=alloc(8);
        c.add(0x18).writeU32(name(cls)); sig.writeU32(name(method));
        fn.add(0x48).writePointer(c); fn.add(0x40).writePointer(sig); return fn;
    }
    const registrations = [
        ['UiSettingsController','InitContent'], ['ComponentUiControllerBase','SetForLocale'],
        ['UiSettingsController','SetForLocale'], ['UiSettingsController','HandleInputScreenUpdate'],
        ['UiOneSettingStepperController','InitContent'], ['UiOneSettingStepperOnOff','UpdateStatus'],
        ['UiOneSettingSliderController','InitContent'], ['UiOneSettingSliderGammaController','GetCurrentValue'],
        ['UiSettingsController','CreateData']];
    const fns = registrations.map(([c,m])=>descriptor(c,m));
    const vm=alloc(64), entry=alloc(Process.pageSize);
    Memory.protect(entry, Process.pageSize, 'rwx');
    entry.writeByteArray([...Array(16).fill(0x90),0xb8,0x34,0x12,0,0,0xc3]);
    const call = new NativeFunction(entry,'uint32',['pointer','pointer']);
    const kernel=Process.getModuleByName('kernel32.dll');
    const setError=new NativeFunction(kernel.getExportByName('SetLastError'),'void',['uint32']);
    const errorProbe=new CModule(`
extern void set_error(unsigned value);
extern unsigned get_error(void);
extern unsigned entry(void *vm, void *fn);
unsigned probe(void *vm, void *fn) { set_error(1234); entry(vm, fn); return get_error(); }
`, {set_error:kernel.getExportByName('SetLastError'),get_error:kernel.getExportByName('GetLastError'),entry});
    const probe=new NativeFunction(errorProbe.probe,'uint32',['pointer','pointer']);
    const unknown=descriptor('OtherController','InitContent');
    const wrongMethod=descriptor('UiSettingsController','OtherMethod');
    const nullClass=alloc(128),nullSignature=descriptor('UiSettingsController','Other');
    nullSignature.add(0x40).writePointer(ptr(0));
    const invalidId=descriptor('Other','Other');invalidId.add(0x48).readPointer().add(0x18).writeU32(0x10000001);
    const sameNamesNewDescriptor=descriptor(...registrations[0]);
    function exercise(grouped) {
        let nativeAttaches=0;
        const batch=makeGroupedMenuHooks((address, callbacks)=>{nativeAttaches++;return Interceptor.attach(address,callbacks);});
        const attach=grouped?batch:hookHudHintUpdates, handles=[], events=[];
        registrations.forEach(([c,m],i)=>handles.push(attach(entry,slot,(actualVm,actualFn)=>{
            if(!actualVm.equals(vm)||!actualFn.equals(fns[i]))throw Error('Callback arguments changed');
            events.push(i);setError(9999);
            if(scenario==='reentrant'&&i===2)call(vm,fns[3]);
        },c,m)));
        // Duplicate subscribers must both run, in registration order.
        handles.push(attach(entry,slot,()=>events.push(9),...registrations[0]));
        if(scenario==='detach-before')handles[4].detach();
        if(grouped)batch.commit();
        Interceptor.flush();
        const initial=grouped?batch.status():null;
        for(const fn of [unknown,wrongMethod,nullClass,nullSignature,invalidId])call(vm,fn);
        const unrelatedEvents=events.length;
        const values=fns.map(fn=>call(vm,fn));
        const lastError=probe(vm,fns[1]);
        // Once cached, a different descriptor with the same spelling is ignored.
        const beforeDuplicate=events.length;call(vm,sameNamesNewDescriptor);
        const cachedIgnoresReplacement=beforeDuplicate===events.length;
        handles[0].detach();handles[0].detach();
        const afterPartial=grouped?batch.status():null;
        call(vm,fns[0]);
        handles.forEach(h=>h.detach());Interceptor.flush();
        const beforeStop=events.length;fns.forEach(fn=>call(vm,fn));
        return {nativeAttaches, initial, afterPartial, stopped:grouped?batch.status():null,
            events,values,lastError,unrelatedEvents,cachedIgnoresReplacement,
            stoppedCallsIgnored:events.length===beforeStop};
    }
    if(scenario==='invalid-registration') {
        const batch=makeGroupedMenuHooks();let rejected=0;
        batch(entry,slot,()=>{},...registrations[0]);
        for(const args of [[entry.add(1),slot,()=>{},'Class','Method'],
                [entry,slot.add(1),()=>{},'Class','Method'],
                [entry,slot,()=>{},'Class','Method',true]]) {
            try{batch(...args);}catch(_){rejected++;}
        }
        return {rejected,status:batch.status()};
    }
    return {original:exercise(false),grouped:exercise(true)};
};
'''


class GroupedMenuHooksTests(unittest.TestCase):
    def setUp(self):
        self.device = NativeDevice()
        self.pid = self.device.spawn(None)
        self.script = self.device.create_script(
            (ROOT / 'src/vm_scope.js').read_text() + '\n' +
            (ROOT / 'src/native/grouped_menu_hooks.js').read_text() + '\n' + FIXTURE)
        self.script.load()

    def tearDown(self):
        self.script.unload()
        self.device.kill(self.pid)

    def compare(self, scenario):
        result = self.script.exports_sync.run(scenario)
        original, grouped = result['original'], result['grouped']
        for key in ('events', 'values', 'lastError', 'unrelatedEvents',
                    'cachedIgnoresReplacement', 'stoppedCallsIgnored'):
            self.assertEqual(grouped[key], original[key], key)
        self.assertEqual(grouped['nativeAttaches'], 1)
        self.assertEqual(grouped['initial']['nativeHooks'], 1)
        self.assertEqual(grouped['initial']['registrations'], 10)
        self.assertEqual(grouped['afterPartial']['nativeHooks'], 1)
        self.assertEqual(grouped['stopped']['nativeHooks'], 0)
        self.assertEqual(grouped['stopped']['activeRegistrations'], 0)
        self.assertEqual(grouped['values'], [0x1234] * 9)
        self.assertEqual(grouped['lastError'], 1234)
        self.assertEqual(grouped['unrelatedEvents'], 0)
        self.assertTrue(grouped['cachedIgnoresReplacement'])
        self.assertTrue(grouped['stoppedCallsIgnored'])
        return grouped

    def test_filters_arguments_cache_order_and_detach_match_original(self):
        state = self.compare('normal')
        self.assertEqual(state['events'][:3], [0, 9, 1])

    def test_reentrant_callbacks_match_original(self):
        self.compare('reentrant')

    def test_detach_before_commit_disables_only_that_callback(self):
        state = self.compare('detach-before')
        self.assertNotIn(4, state['events'])
        self.assertEqual(state['initial']['activeRegistrations'], 9)

    def test_mixed_entry_pool_and_interior_are_rejected(self):
        state = self.script.exports_sync.run('invalid-registration')
        self.assertEqual(state['rejected'], 3)
        self.assertEqual(state['status']['nativeHooks'], 0)
        self.assertEqual(state['status']['registrations'], 1)


if __name__ == '__main__':
    unittest.main()
