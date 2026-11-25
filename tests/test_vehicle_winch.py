"""Regression for long-trailer discovery AND click-time target lookup."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from native_host import NativeDevice

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from compatibility import compile_signatures, find_matches, resolve_profile, IncompatibleError

FIXTURE = r'''
rpc.exports.run = scenario => {
    const base = Memory.alloc(512), keep = [base], callbacks = {}, deferred = [];
    let detached = 0, installs = 0;
    const profile = {selectionRva:16, attachmentRva:32, vehicleRegistryRva:128,
        selectionCallerRva:100, attachmentCallerRva:200,
        guards:[{name:'selection',rva:16,hex:'90'},{name:'attachment',rva:32,hex:'90'}]};
    base.add(16).writeU8(0x90); base.add(32).writeU8(scenario==='guard' ? 0 : 0x90);
    const intercept = {flush(){}, attach(p, cb){
        if (++installs === 2 && scenario==='install-failure') throw Error('Rejected second hook');
        callbacks[p.sub(base).toInt32()] = cb;
        return {detach(){detached++;}};
    }};
    const construct = (function(Process, Interceptor, setImmediate) {
        PRODUCTION_SOURCE
        return makeVehicleWinchRange;
    })({mainModule:{base}}, intercept, fn=>deferred.push(fn));
    let fix;
    try { fix = construct(profile); }
    catch(e) { return {error:String(e), installs, detached}; }
    const alloc = n => {const p=Memory.alloc(n);keep.push(p);return p;};
    // The source is 40 units from the truck origin. A long target trailer has
    // its origin at 60, but a socket at 45: only 5 units from the source.
    const truck=alloc(16), target=alloc(16), distant=alloc(16), source=alloc(16);
    source.writeFloat(40); target.writeFloat(45); distant.writeFloat(70);
    const setVector = (v, items) => {
        const p=alloc(Math.max(8,items.length*8));items.forEach((x,i)=>p.add(i*8).writePointer(x));
        v.writePointer(p);v.add(8).writePointer(p.add(items.length*8));v.add(16).writePointer(p.add(items.length*8));
    };
    const registry=base.add(128), original=alloc(24);
    setVector(registry,[truck,target,distant]);setVector(original,[truck]);
    const read = v => {const p=v.readPointer(),n=v.add(8).readPointer().sub(p).toInt32()/8;
        return Array.from({length:n},(_,i)=>p.add(i*8).readPointer());};
    const ctx = caller => ({returnAddress:base.add(caller),lastError:123});
    const args = () => [ptr(0),original,truck,source];
    const find = v => read(v).filter(p=>!p.equals(truck)&&Math.abs(p.readFloat()-40)<=14);
    const attach = (v, accepted=true) => read(v).some(p=>p.equals(target)) && accepted;
    const originalBytes = Array.from(new Uint8Array(original.readByteArray(24))).join();
    if(scenario==='empty') setVector(registry,[]);
    if(scenario==='oversized') registry.add(8).writePointer(registry.readPointer().add(513*8));
    if(scenario==='reversed') registry.add(8).writePointer(registry.readPointer().sub(8));
    if(scenario==='misaligned') registry.add(8).writePointer(registry.readPointer().add(9));
    if(scenario==='overlap') {
        const active=[];
        for(let i=0;i<5;i++){const a=args(),c=ctx(100);callbacks[16].onEnter.call(c,a);active.push({a,c});}
        const distinct=new Set(active.slice(0,4).map(x=>x.a[1].toString())).size;
        const fifthUnchanged=active[4].a[1].equals(original);
        const intact=active.slice(0,4).every(x=>read(x.a[1]).length===3);
        active.forEach(x=>callbacks[16].onLeave.call(x.c));deferred.forEach(fn=>fn());
        return {distinct,fifthUnchanged,intact,status:fix.status(),detached};
    }
    const a=args(),c=ctx(scenario==='other-caller'?101:100);
    if(scenario==='no-source') a[3]=ptr(0);
    const before=find(original).length;
    callbacks[16].onEnter.call(c,a);
    const after=find(a[1]).length, replaced=!a[1].equals(original);
    callbacks[16].onLeave.call(c);
    const b=[truck,source,original,target],d=ctx(scenario==='other-caller'?201:200);
    callbacks[32].onEnter.call(d,b);
    const linked=attach(b[2],scenario!=='native-refusal');
    callbacks[32].onLeave.call(d,ptr(linked?1:0));
    const status=fix.status();deferred.forEach(fn=>fn());fix.stop();
    const z=args();callbacks[16].onEnter.call(ctx(100),z);
    return {before,after,replaced,linked,status,detached,stopped:fix.status(),
        preservedLastError:c.lastError===123&&d.lastError===123,
        afterStopUnchanged:z[1].equals(original),
        originalUnchanged:originalBytes===Array.from(new Uint8Array(original.readByteArray(24))).join()};
};
'''


class WinchHookTests(unittest.TestCase):
    def run_case(self, scenario='normal'):
        device = NativeDevice()
        pid = device.spawn(None)
        try:
            source = FIXTURE.replace('PRODUCTION_SOURCE', (ROOT / 'src/vehicle_winch.js').read_text())
            script = device.create_script(source)
            script.load()
            result = script.exports_sync.run(scenario)
            script.unload()
            return result
        finally:
            device.kill(pid)

    def test_long_trailer_discovery_and_attachment_keep_distance_limit(self):
        r = self.run_case()
        self.assertEqual((r['before'], r['after']), (0, 1))  # Far socket stays excluded.
        self.assertTrue(r['linked'])
        self.assertEqual(r['status']['acceptedAttachments'], 1)
        for key in ('preservedLastError', 'afterStopUnchanged', 'originalUnchanged'):
            self.assertTrue(r[key], key)
        self.assertEqual(r['detached'], 2)

    def test_native_attachment_rejection_is_not_overridden(self):
        r = self.run_case('native-refusal')
        self.assertFalse(r['linked'])
        self.assertEqual(r['status']['acceptedAttachments'], 0)

    def test_unrelated_callers_and_no_selected_source_are_untouched(self):
        for scenario in ('other-caller', 'no-source'):
            self.assertFalse(self.run_case(scenario)['replaced'])
        self.assertFalse(self.run_case('other-caller')['linked'])

    def test_invalid_registry_fails_closed_and_detaches_both_hooks(self):
        for scenario in ('oversized', 'reversed', 'misaligned'):
            r = self.run_case(scenario)
            self.assertFalse(r['replaced'])
            self.assertFalse(r['linked'])
            self.assertIsNotNone(r['status']['fault'])
            self.assertEqual(r['detached'], 2)
        r = self.run_case('empty')
        self.assertFalse(r['replaced'])
        self.assertIsNone(r['status']['fault'])

    def test_overlapping_calls_retain_separate_vectors(self):
        r = self.run_case('overlap')
        self.assertEqual(r['distinct'], 4)
        self.assertTrue(r['fifthUnchanged'] and r['intact'])
        self.assertIsNotNone(r['status']['fault'])
        self.assertEqual(r['detached'], 2)

    def test_guards_and_partial_install_failure_leave_no_hooks(self):
        r = self.run_case('guard')
        self.assertEqual(r['installs'], 0)
        r = self.run_case('install-failure')
        self.assertEqual(r['detached'], 1)


class WinchSignatureTests(unittest.TestCase):
    def test_relocation_missing_changed_and_ambiguous_blocks(self):
        profile = json.loads((ROOT / 'src/winch-profile.json').read_text())
        signatures = compile_signatures(profile)
        def move(rva): return rva + (0x100000 if rva < 0x21c0000 else 0x400000)
        sections = [dict(rva=0x1000, size=0x4000000, readable=True, executable=True)]
        matches = {}
        for sig in signatures:
            raw = bytearray.fromhex(sig['hex'])
            rva = move(sig['rva'])
            for ref in sig['refs']:
                raw[ref['offset']:ref['offset']+ref['size']] = (move(ref['target'])-rva-ref['next']).to_bytes(ref['size'], 'little', signed=True)
            matches[sig['name']] = find_matches(sig, [(rva, raw)], None)
        resolved, _ = resolve_profile(profile, signatures, matches, sections)
        for key, value in profile.items():
            if key.endswith('Rva'):
                self.assertEqual(resolved[key], move(value))
        for scenario in ('missing', 'changed', 'ambiguous'):
            bad = deepcopy(matches)
            name = signatures[0]['name']
            if scenario == 'missing': bad[name] = []
            elif scenario == 'changed': bad[name][0]['hex'] = '90' + bad[name][0]['hex'][2:]
            else: bad[name].append(deepcopy(bad[name][0]))
            with self.assertRaises(IncompatibleError):
                resolve_profile(profile, signatures, bad, sections)


if __name__ == '__main__':
    unittest.main()
