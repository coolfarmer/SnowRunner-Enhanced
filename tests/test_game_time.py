"""Run the real clock gate in GumJS/C; exercise session and world replacement."""
import json
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from native_host import NativeDevice

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / 'src/game-time-profile.json').read_text())
sys.path.insert(0, str(ROOT / 'src'))
from compatibility import compile_signatures, find_matches, resolve_profile, IncompatibleError

PRELUDE = r'''
const base=Memory.alloc(4096),pool=Memory.alloc(512),slot=Memory.alloc(8),callbacks={};
slot.writePointer(pool);let names=0;
function name(text){const id=names;pool.add(id).writeUtf8String(text);names+=text.length+1;return id;}
const clock1=Memory.alloc(512),clock2=Memory.alloc(512);
const p={...REFERENCE,clockStepRva:128,clockSlotRva:1024,guards:[{name:'test',rva:128,hex:'9090909090909090'}]};
base.add(128).writeByteArray(new Uint8Array(8).fill(0x90));base.add(1024).writePointer(clock1);
const vmProfile={stringPoolSlotRva:1032,guards:[{name:'vm_frame_push_entry',rva:1040}]};
base.add(1032).writePointer(pool);
const cls=Memory.alloc(128),signature=Memory.alloc(8),fn=Memory.alloc(128),code=Memory.alloc(REFERENCE.singlePlayerWords.length*4);
cls.add(0x18).writeU32(name('GameSession'));signature.writeU32(name('CreateSinglePlayer'));
fn.add(0x48).writePointer(cls);fn.add(0x40).writePointer(signature);
fn.add(0x60).writePointer(code);fn.add(0x68).writeU32(REFERENCE.singlePlayerWords.length);
REFERENCE.singlePlayerWords.forEach((w,i)=>code.add(i*4).writeU32(w));
const constants=Memory.alloc(16),type=Memory.alloc(48);type.add(8).writeU32(name('GameModeSingle'));
constants.writePointer(type.or('0x30000000000000'));fn.add(0x50).writePointer(constants);fn.add(0x58).writeU32(2);
const vm=Memory.alloc(64),args=Memory.alloc(8),session=Memory.alloc(64);args.writePointer(session.or('0x20000000000000'));vm.add(0x18).writePointer(args);
let callback=null;
const interceptor={attach(address,cb){callback=cb;return {detach(){callback=null;}};},flush(){}};
(function(Process,Interceptor){
'''
POSTLUDE = r'''
const clock=makeGameTimeFreeze(p,vmProfile,(_entry,_pool,cb,_cls,method)=>{
 callbacks[method]=cb;return {detach(){delete callbacks[method];}};
});
const harness=new CModule(`
#include <gum/guminterceptor.h>
extern void step(GumInvocationContext *);
guint32 run(void *clock, guint32 mode) {
 GumInvocationContext ic={0}; GumCpuContext cpu={0};
 cpu.r13=(guint64)(guintptr)clock;cpu.rcx=mode;ic.cpu_context=&cpu;step(&ic);return cpu.rcx;
}`, {step:callback});
const run=new NativeFunction(harness.run,'uint32',['pointer','uint32']);
rpc.exports={
 set:value=>clock.set(value),
 event:method=>callbacks[method]?.(vm,fn),
 tick:mode=>run(base.add(1024).readPointer(),mode??0),
 mismatch:()=>run(ptr(1),0),
 travel:()=>{base.add(1024).writePointer(clock2);},
 state:()=>{harness.run;return clock.status();},
 mutate:()=>code.writeU32(0),
 foreigntype:()=>type.add(8).writeU32(name('GameModeCoopMaster')),
 stop:()=>clock.stop()
};
})({mainModule:{base}},interceptor);
'''


class GameTimeTests(unittest.TestCase):
    def setUp(self):
        self.device = NativeDevice()
        self.pid = self.device.spawn(None)
        self.script = self.device.create_script('const REFERENCE=' + json.dumps(PROFILE) + ';\n' +
            PRELUDE + (ROOT / 'src/game_time.js').read_text() + POSTLUDE)
        self.script.load()
        self.api = self.script.exports_sync

    def tearDown(self):
        self.script.unload()
        self.device.kill(self.pid)

    def test_default_off_unknown_session_and_single_player_toggle(self):
        self.assertEqual(self.api.tick(), 0)
        self.api.set(True)
        self.assertEqual(self.api.tick(), 0)
        self.api.event('CreateSinglePlayer')
        self.assertEqual(self.api.tick(), 3)
        self.api.set(False)
        self.assertEqual(self.api.tick(), 0)
        self.assertEqual(self.api.state()['frozenUpdates'], 1)

    def test_map_transition_uses_new_clock_without_stale_pointer(self):
        self.api.event('CreateSinglePlayer')
        self.api.set(True)
        self.assertEqual(self.api.tick(), 3)
        self.api.travel()
        self.assertEqual(self.api.tick(), 3)
        self.assertEqual(self.api.state()['clockChanges'], 2)
        self.api.set(False)
        self.assertEqual(self.api.tick(), 0)

    def test_coop_creation_and_session_end_disarm_before_next_frame(self):
        for event in ('Init', 'Terminate', 'CreateMultiplayer', 'CreateCoopMaster', 'CreateCoopClient'):
            with self.subTest(event=event):
                self.api.event('CreateSinglePlayer')
                self.api.set(True)
                self.assertEqual(self.api.tick(), 3)
                self.api.event(event)
                self.api.travel()
                self.assertEqual(self.api.tick(), 0)
                self.assertTrue(self.api.state()['enabled'])

    def test_foreign_time_modes_are_preserved_and_stop_disarms(self):
        self.api.event('CreateSinglePlayer')
        self.api.set(True)
        for mode in (1, 2, 3, 99):
            self.assertEqual(self.api.tick(mode), mode)
        self.assertEqual(self.api.tick(), 3)
        self.api.stop()
        self.assertEqual(self.api.tick(), 0)

    def test_changed_session_bytecode_fails_closed(self):
        self.api.set(True)
        self.api.mutate()
        self.api.event('CreateSinglePlayer')
        self.assertEqual(self.api.tick(), 0)
        self.assertEqual(self.api.state()['status'], 'error')

    def test_changed_constructor_cannot_admit_coop(self):
        self.api.set(True)
        self.api.foreigntype()
        self.api.event('CreateSinglePlayer')
        self.assertEqual(self.api.tick(), 0)
        self.assertIn('constructor', self.api.state()['fault'])

    def test_clock_mismatch_fails_closed_until_reload(self):
        self.api.event('CreateSinglePlayer')
        self.api.set(True)
        self.assertEqual(self.api.mismatch(), 0)
        self.assertEqual(self.api.tick(), 0)
        self.assertEqual(self.api.state()['status'], 'error')


class ClockSignatureTests(unittest.TestCase):
    def test_native_scanner_finds_clock_getter_among_adjacent_getters(self):
        # Memory.scanSync returns non-overlapping matches. A signature spanning
        # several identical getter bodies can skip the required middle getter.
        # The call in clock_factors disambiguates the individual getter safely.
        signatures = compile_signatures(PROFILE)
        sections = [dict(rva=0x1000, size=0x3fff000, readable=True, executable=True)]
        setup = 'const fixtureBase=Memory.alloc(0x4000000);\n'
        for guard in PROFILE['guards']:
            setup += f'fixtureBase.add({guard["rva"]}).writeByteArray({list(bytes.fromhex(guard["hex"]))});\n'
        getter = next(g for g in PROFILE['guards'] if g['name'] == 'clock_singleton')
        neighbor = list(bytes.fromhex('488d0521550b02c3cccccccccccccccc'))
        for offset in (-16, 16, 32, 48):
            setup += f'fixtureBase.add({getter["rva"]+offset}).writeByteArray({neighbor});\n'
        setup += '(function(Process){' + (ROOT / 'src/compatibility_probe.js').read_text()
        setup += '})({mainModule:{base:fixtureBase,size:0x4000000}});const probe=rpc.exports;\n'
        setup += (ROOT / 'src/native/resolve.js').read_text()
        setup += '\nrpc.exports={check:(p,s,sections)=>{const matches=probe.scan(s,sections);return resolveNativeProfile(p,s,matches,sections);}};'
        device = NativeDevice()
        pid = device.spawn(None)
        try:
            script = device.create_script(setup)
            script.load()
            result = script.exports_sync.check(PROFILE, signatures, sections)
            self.assertEqual(result['profile'], PROFILE)
            self.assertEqual(result['details']['candidateCounts']['clock_singleton'], 1)
            script.unload()
        finally:
            device.kill(pid)

    def test_code_and_data_relocate_independently_and_unknown_code_is_rejected(self):
        signatures = compile_signatures(PROFILE)
        def move(rva): return rva + (0x100000 if rva < 0x21c0000 else 0x400000)
        sections = [dict(rva=0x1000, size=0x4000000, readable=True, executable=True)]
        matches = {}
        for sig in signatures:
            raw = bytearray.fromhex(sig['hex'])
            rva = move(sig['rva'])
            for ref in sig['refs']:
                raw[ref['offset']:ref['offset']+ref['size']] = (move(ref['target'])-rva-ref['next']).to_bytes(ref['size'], 'little', signed=True)
            matches[sig['name']] = find_matches(sig, [(rva, raw)], None)
        resolved, _ = resolve_profile(PROFILE, signatures, matches, sections)
        for key in ('clockStepRva', 'clockSlotRva'):
            self.assertEqual(resolved[key], move(PROFILE[key]))
        for scenario in ('missing', 'changed', 'ambiguous'):
            bad = deepcopy(matches)
            if scenario == 'missing': bad['clock_step'] = []
            elif scenario == 'changed': bad['clock_step'][0]['hex'] = '90' + bad['clock_step'][0]['hex'][2:]
            else: bad['clock_step'].append(deepcopy(bad['clock_step'][0]))
            with self.assertRaises(IncompatibleError):
                resolve_profile(PROFILE, signatures, bad, sections)


if __name__ == '__main__':
    unittest.main()
