"""Real native entry/interior dispatch, sharing and failure isolation."""
import os
from pathlib import Path
import unittest
from native_host import NativeDevice

ROOT=Path(__file__).resolve().parents[1]
BUILD=Path(os.environ.get('ENHANCED_FAST_TEST_BUILD',ROOT/'build/native'))

FIXTURE=r'''
rpc.exports.run=(scenario,stackOffset=0)=>{
    const keep=[],alloc=n=>{const p=Memory.alloc(n);keep.push(p);return p;};
    const pool=alloc(256),slot=alloc(8);slot.writePointer(pool);
    pool.writeUtf8String('Class');pool.add(32).writeUtf8String('Method');
    const vm=alloc(256),fn=alloc(128),cls=alloc(64),sig=alloc(8);
    cls.add(0x18).writeU32(0);sig.writeU32(32);
    fn.add(0x48).writePointer(cls);fn.add(0x40).writePointer(sig);
    const oldArgs=alloc(8),newArgs=alloc(8),frame=alloc(64),next=alloc(64),previous=alloc(64);
    const code=alloc(Process.pageSize);Memory.protect(code,Process.pageSize,'rwx');
    const w=new X86Writer(code,{pc:code});w.putBytes(Array(16).fill(0x90));
    if(stackOffset)w.putSubRegImm('rsp',stackOffset);
    w.putBytes([0x49,0x89,0xc8,0x48,0x8b,0x41,0x68,0x48,0x89,0x41,0x18]);
    const offset=w.offset;
    const hex='488b4950488b411849894050498b401848890148895108c7411000000000498b4030488941184989483041ff4060';
    w.putBytes(Array.from(hex.match(/../g),b=>parseInt(b,16)));
    if(stackOffset)w.putAddRegImm('rsp',stackOffset);
    w.putBytes([0xb8,0x34,0x12,0,0,0xc3]);w.flush();w.dispose();
    const profile={guards:[{name:'vm_frame_push_entry',rva:0,hex:'90'.repeat(16)},
        {name:'vm_frame_push',rva:offset,hex}]};
    const call=new NativeFunction(code,'uint32',['pointer','pointer']);
    function reset(){vm.add(0x18).writePointer(oldArgs);vm.add(0x68).writePointer(newArgs);
        vm.add(0x50).writePointer(frame);frame.add(0x18).writePointer(next);
        vm.add(0x30).writePointer(previous);vm.add(0x60).writeU32(7);}
    const fast=makeFastVmHooks(profile,Process.mainModule,code);
    if(scenario==='unsupported-phase'){
        profile.guards[1].hex='90'+hex.slice(2);let rejected=false;
        try{makeFastVmHooks(profile,Process.mainModule,code);}catch(_){rejected=true;}
        return {rejected,unchanged:code.readU8()===0x90};
    }
    function exercise(useFast){
        const hooks=[],events=[],attach=useFast?fast.attach:hookHudHintUpdates;
        const watch=(site,inside,label)=>hooks.push(attach(site,slot,(actualVm,actualFn)=>{
            events.push({label,vm:actualVm.equals(vm),fn:actualFn.equals(fn),
                callee:actualVm.add(0x18).readPointer().equals(newArgs),count:actualVm.add(0x60).readU32()});
            if(scenario==='phase-mutation' && label==='search')frame.add(0x18).writePointer(ptr(0x1234));
        },'Class','Method',inside));
        watch(code,false,'entry');watch(code.add(offset),true,'general');
        // Stop the first owner without detaching the shared interior gate.
        watch(code.add(offset+8),true,'search');
        if(useFast)fast.commit();Interceptor.flush();reset();
        const value=call(vm,fn);
        const frameIntact=vm.add(0x50).readPointer().equals(next)&&vm.add(0x30).readPointer().equals(frame)&&
            frame.readPointer().equals(newArgs)&&frame.add(8).readPointer().equals(fn)&&
            frame.add(0x18).readPointer().equals(previous)&&vm.add(0x60).readU32()===8;
        hooks[1].detach();Interceptor.flush();reset();call(vm,fn);
        hooks.forEach(h=>h.detach());Interceptor.flush();reset();call(vm,fn);
        const status=useFast?fast.status():null;
        if(useFast)fast.releaseForTest();
        return {value,events,frameIntact,status};
    }
    if(scenario==='failure'){
        fast.attach(code,slot,()=>{},'Class','Method');
        fast.attach(code.add(offset),slot,()=>{},'Class','Method',true);
        code.add(offset).writeU8(0x90);let rejected=false;
        try{fast.commit();}catch(_){rejected=true;}
        const state=fast.status();fast.releaseForTest();
        return {rejected,state,foreignByte:code.add(offset).readU8()};
    }
    if(scenario==='unknown-site'){
        let rejected=false;
        try{fast.attach(code.add(offset+4),slot,()=>{},'Class','Method',true);}catch(_){rejected=true;}
        return {rejected,state:fast.status()};
    }
    return {original:exercise(false),fast:exercise(true)};
};
'''


class FastVmHooksTests(unittest.TestCase):
    def run_case(self,scenario,stack=0):
        device=NativeDevice(BUILD/'native-harness.exe');pid=device.spawn(None)
        prefix_mode = str(os.environ.get('ENHANCED_TEST_VM_PREFIXES','1') == '1').lower()
        source=f'const ENHANCED_VM_PREFIXES={prefix_mode};\nconst CONFIG={{test:true}};\nconst ENHANCED_VM_INDEXED='+str(os.environ.get('ENHANCED_VM_INDEXED','1')=='1').lower()+';\n'+'\n'.join((ROOT/name).read_text() for name in
            ('src/vm_scope.js','src/native/fast_menu_hooks.js','src/native/fast_vm_hooks.js'))
        script=device.create_script(source+'\n'+FIXTURE);script.load()
        try:return script.exports_sync.run(scenario,stack)
        finally:script.unload();device.kill(pid)

    def test_entry_and_interior_preserve_callee_phase_and_relocated_instructions(self):
        for stack in (0,8,0x28,0x30):
            with self.subTest(stack=stack):
                result=self.run_case('normal',stack)
                a,b=result['original'],result['fast']
                for key in ('value','events','frameIntact'):self.assertEqual(a[key],b[key],key)
                self.assertEqual(b['value'],0x1234);self.assertTrue(b['frameIntact'])
                self.assertEqual([event['callee'] for event in b['events']],[False,True,True,False,True])
                self.assertTrue(all(e['vm'] and e['fn'] and e['count']==7 for e in b['events']))
                self.assertEqual(b['status']['entry']['fastReplacements'],1)
                self.assertEqual(b['status']['interior']['fastReplacements'],1)
                self.assertEqual(b['status']['interior']['activeRegistrations'],0)

    def test_unknown_interior_address_is_rejected(self):
        self.assertTrue(self.run_case('unknown-site')['rejected'])

    def test_observer_mutation_does_not_change_already_loaded_registers(self):
        result=self.run_case('phase-mutation')
        self.assertEqual(result['original']['events'],result['fast']['events'])
        self.assertTrue(result['original']['frameIntact'])
        self.assertTrue(result['fast']['frameIntact'])

    def test_changed_phase_instructions_are_rejected(self):
        result=self.run_case('unsupported-phase')
        self.assertTrue(result['rejected']);self.assertTrue(result['unchanged'])

    def test_failed_second_install_disarms_first_without_overwriting_foreign_code(self):
        result=self.run_case('failure')
        self.assertTrue(result['rejected']);self.assertEqual(result['foreignByte'],0x90)
        self.assertTrue(result['state']['fault'])
        for phase in ('entry','interior'):
            self.assertEqual(result['state'][phase]['activeRegistrations'],0)


if __name__=='__main__':unittest.main()
