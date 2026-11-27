"""Exercise the experimental gate in real embedded GumJS, without the game."""
import json
import os
from pathlib import Path
import unittest

from native_host import NativeDevice
from test_grouped_menu_hooks import FIXTURE as GROUPED_FIXTURE

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path(os.environ.get('ENHANCED_FAST_TEST_BUILD', ROOT / 'build/native'))
HOST = BUILD / 'native-harness.exe'

# Run exactly the same differential workload as the grouped dispatcher.
FAST_FIXTURE = GROUPED_FIXTURE.replace(
    "makeGroupedMenuHooks((address, callbacks)=>{nativeAttaches++;return Interceptor.attach(address,callbacks);})",
    "makeFastMenuHooks({address:entry,hex:'90'.repeat(16)},Process.mainModule)"
).replace("makeGroupedMenuHooks()", "makeFastMenuHooks({address:entry,hex:'90'.repeat(16)},Process.mainModule)")
FAST_FIXTURE = FAST_FIXTURE.replace(
    "return {nativeAttaches, initial, afterPartial, stopped:grouped?batch.status():null,",
    "const stopped=grouped?batch.status():null; if(grouped)batch.releaseForTest();\n"
    "return {nativeAttaches, initial, afterPartial, stopped,")

ABI_FIXTURE = r'''
rpc.exports.run = scenario => {
    const keep=[],alloc=n=>{const p=Memory.alloc(n);keep.push(p);return p;};
    const pool=alloc(256),slot=alloc(8);slot.writePointer(pool);
    pool.writeUtf8String('Class');pool.add(32).writeUtf8String('Method');
    const vm=alloc(256),fn=alloc(128),cls=alloc(64),sig=alloc(8);
    cls.add(0x18).writeU32(0);sig.writeU32(32);
    fn.add(0x48).writePointer(cls);fn.add(0x40).writePointer(sig);
    const target=new CModule(`
        #include <stdint.h>
        double target(void *vm, void *fn, double c, double d, uint64_t e, double f) {
            uint64_t *out=vm; out[0]=(uint64_t)(uintptr_t)vm;out[1]=(uint64_t)(uintptr_t)fn;
            out[2]=e;return c + d * 2.0 + (double)(int64_t)e + f * 3.0;
        }
    `);
    const entry=alloc(Process.pageSize);Memory.protect(entry,Process.pageSize,'rwx');
    const writer=new X86Writer(entry,{pc:entry});writer.putBytes(Array(16).fill(0x90));
    writer.putJmpAddress(target.target);writer.flush();writer.dispose();
    const call=new NativeFunction(entry,'double',['pointer','pointer','double','double','uint64','double']);
    const before=call(vm,fn,1.25,2.5,1234567,7.75);
    let callbacks=0;
    const batch=makeFastMenuHooks({address:entry,hex:'90'.repeat(16)},Process.mainModule);
    const handle=batch(entry,slot,()=>{callbacks++;},'Class','Method');
    if(scenario==='changed-entry'){
        entry.writeU8(0x91);let rejected=false;
        try{batch.commit();}catch(_){rejected=true;}
        return {rejected,unchanged:entry.readU8()===0x91,status:batch.status()};
    }
    if(scenario==='native-guard'){
        const expected=alloc(16);expected.writeByteArray(Array(16).fill(0x91));
        const original=alloc(8);
        const install=new NativeFunction(Process.mainModule.getExportByName('EnhancedInstallFastMenu'),
            'int',['pointer','pointer','pointer','pointer','uint32']);
        const result=install(entry,target.target,original,expected,16);
        return {result,unchanged:entry.readU8()===0x90,originalNull:original.readPointer().isNull()};
    }
    batch.commit();
    try{
        const after=call(vm,fn,1.25,2.5,1234567,7.75);
        const argumentsIntact=vm.readPointer().equals(vm)&&vm.add(8).readPointer().equals(fn)&&
            vm.add(16).readU64().toString()==='1234567';
        handle.detach();
        const disabled=call(vm,fn,1.25,2.5,1234567,7.75);
        return {before,after,disabled,argumentsIntact,callbacks,status:batch.status()};
    }finally{batch.releaseForTest();}
};
'''

BENCH_FIXTURE = r'''
rpc.exports.run = () => {
    const keep=[],alloc=n=>{const p=Memory.alloc(n);keep.push(p);return p;};
    const pool=alloc(4096),slot=alloc(8);slot.writePointer(pool);let used=0;
    function descriptor(c,m){
        const fn=alloc(128),cls=alloc(64),sig=alloc(8);
        cls.add(0x18).writeU32(used);pool.add(used).writeUtf8String(c);used+=c.length+1;
        sig.writeU32(used);pool.add(used).writeUtf8String(m);used+=m.length+1;
        fn.add(0x48).writePointer(cls);fn.add(0x40).writePointer(sig);return fn;
    }
    const vm=alloc(64),unknown=descriptor('Unrelated','Work');
    const targets=Array.from({length:9},(_,i)=>descriptor('Class','Method'+i));
    const entry=alloc(Process.pageSize);Memory.protect(entry,Process.pageSize,'rwx');
    entry.writeByteArray([...Array(16).fill(0x90),0xb8,0x34,0x12,0,0,0xc3]);
    const kernel=Process.getModuleByName('kernel32.dll');
    const control=alloc(32);
    const native=new CModule(`
        #include <stdint.h>
        extern unsigned entry(void *,void *);
        extern int counter(int64_t *);
        extern int frequency(int64_t *);
        extern unsigned sleep_ms(unsigned);
        extern volatile uint64_t control[];
        double bench(void *vm,void *fn,unsigned n){
            int64_t start,end,freq;unsigned i,total=0;
            frequency(&freq);counter(&start);
            for(i=0;i<n;i++)total+=entry(vm,fn);
            counter(&end);control[3]=total;
            return 1000000000.0*(double)(end-start)/(double)freq/n;
        }
        unsigned worker(void *args){
            void **a=args;
            while(!control[0]){
                if(entry(a[0],a[1])!=0x1234)control[2]++;
                control[1]++;
            }
            return 0;
        }
        void on_enter(void *unused){}
    `,{entry,control,counter:kernel.getExportByName('QueryPerformanceCounter'),
        frequency:kernel.getExportByName('QueryPerformanceFrequency'),sleep_ms:kernel.getExportByName('Sleep')});
    const measure=new NativeFunction(native.bench,'double',['pointer','pointer','uint32']);
    const call=new NativeFunction(entry,'uint32',['pointer','pointer']);
    const results={};
    const measureMode=name=>{results[name]=Array.from({length:3},()=>measure(vm,unknown,100000));};
    measureMode('baseline');
    const empty=Interceptor.attach(entry,{onEnter:native.on_enter});Interceptor.flush();
    measureMode('empty');empty.detach();Interceptor.flush();
    const grouped=makeGroupedMenuHooks();
    const gh=targets.map((_,i)=>grouped(entry,slot,()=>{},'Class','Method'+i));grouped.commit();Interceptor.flush();
    measureMode('groupedCold');targets.forEach(fn=>call(vm,fn));measureMode('groupedCached');
    gh.forEach(h=>h.detach());Interceptor.flush();
    const fast=makeFastMenuHooks({address:entry,hex:'90'.repeat(16)},Process.mainModule);
    const fh=targets.map((_,i)=>fast(entry,slot,()=>{},'Class','Method'+i));
    const args=alloc(16);args.writePointer(vm);args.add(8).writePointer(unknown);
    const create=new NativeFunction(kernel.getExportByName('CreateThread'),'pointer',
        ['pointer','size_t','pointer','pointer','uint32','pointer']);
    const wait=new NativeFunction(kernel.getExportByName('WaitForSingleObject'),'uint32',['pointer','uint32']);
    const close=new NativeFunction(kernel.getExportByName('CloseHandle'),'int',['pointer']);
    const sleep=new NativeFunction(kernel.getExportByName('Sleep'),'void',['uint32']);
    const thread=create(ptr(0),0,native.worker,args,0,ptr(0));
    if(thread.isNull())throw Error('CreateThread failed');
    try{
        sleep(5);fast.commit();sleep(5);
    }finally{control.writeU64(1);if(wait(thread,5000)!==0)throw Error('Worker did not stop');close(thread);}
    try{
        measureMode('fastCold');targets.forEach(fn=>call(vm,fn));measureMode('fastCached');
        fh.forEach(h=>h.detach());measureMode('fastDisabled');
        return {nsPerCall:results,workerCalls:control.add(8).readU64().toString(),
            workerErrors:control.add(16).readU64().toString(),checksum:control.add(24).readU64().toString()};
    }finally{fast.releaseForTest();}
};
'''

REGISTERS_FIXTURE = r'''
rpc.exports.run=()=>{
    const keep=[],alloc=n=>{const p=Memory.alloc(n);keep.push(p);return p;};
    const pool=alloc(64),slot=alloc(8);slot.writePointer(pool);
    pool.writeUtf8String('Class');pool.add(32).writeUtf8String('Method');
    const out=alloc(160),fn=alloc(128),cls=alloc(64),sig=alloc(8);
    cls.add(0x18).writeU32(0);sig.writeU32(32);
    fn.add(0x48).writePointer(cls);fn.add(0x40).writePointer(sig);
    const entry=alloc(Process.pageSize);Memory.protect(entry,Process.pageSize,'rwx');
    const w=new X86Writer(entry,{pc:entry});w.putBytes(Array(16).fill(0x90));
    // Snapshot incoming integer registers and flags before modifying any of them.
    w.putBytes([0x48,0x89,0x01, 0x48,0x89,0x49,8, 0x48,0x89,0x51,16,
        0x4c,0x89,0x41,24, 0x4c,0x89,0x49,32, 0x4c,0x89,0x51,40, 0x4c,0x89,0x59,48,
        0x9c,0x58,0x48,0x89,0x41,56]);
    for(let i=0;i<6;i++){
        // MOVDQU [rcx+disp32], xmmN (last two slots exceed signed disp8).
        const d=64+16*i;w.putBytes([0xf3,0x0f,0x7f,0x81+(i<<3),d,0,0,0]);
    }
    w.putBytes([0xb8,0x34,0x12,0,0,0xc3]);w.flush();w.dispose();
    const caller=alloc(Process.pageSize);Memory.protect(caller,Process.pageSize,'rwx');
    const c=new X86Writer(caller,{pc:caller});c.putSubRegImm('rsp',0x28);
    for(let i=0;i<6;i++)c.putBytes([0xf3,0x41,0x0f,0x6f,0x00+(i<<3)]); // xmmN=[r8]
    c.putBytes([0xb8,0x11,0x11,0x11,0x11,
        0x41,0xb8,0x22,0x22,0x22,0x22,0x41,0xb9,0x33,0x33,0x33,0x33,
        0x41,0xba,0x44,0x44,0x44,0x44,0x41,0xbb,0x55,0x55,0x55,0x55,
        0x68,0x46,0x02,0,0,0x9d]);
    c.putCallAddress(entry);c.putAddRegImm('rsp',0x28);c.putRet();c.flush();c.dispose();
    const vector=alloc(16);vector.writeByteArray(Array.from({length:16},(_,i)=>i+1));
    const call=new NativeFunction(caller,'uint32',['pointer','pointer','pointer']);
    const beforeReturn=call(out,fn,vector),before=Array.from(new Uint8Array(out.readByteArray(160)));
    const batch=makeFastMenuHooks({address:entry,hex:'90'.repeat(16)},Process.mainModule);
    let callbacks=0;batch(entry,slot,()=>{callbacks++;},'Class','Method');batch.commit();
    try{
        const afterReturn=call(out,fn,vector),after=Array.from(new Uint8Array(out.readByteArray(160)));
        return {before,after,beforeReturn,afterReturn,callbacks};
    }finally{batch.releaseForTest();}
};
'''


class FastMenuHooksTests(unittest.TestCase):
    def run_fixture(self, fixture, *args):
        device=NativeDevice(HOST)
        pid=device.spawn(None)
        prefix_mode = str(os.environ.get('ENHANCED_TEST_VM_PREFIXES','1') == '1').lower()
        source=f'const ENHANCED_VM_PREFIXES={prefix_mode};\nconst CONFIG={{test:true}};\nconst ENHANCED_VM_INDEXED='+str(os.environ.get('ENHANCED_VM_INDEXED','1')=='1').lower()+';\n' + '\n'.join(
            (ROOT/name).read_text() for name in ('src/vm_scope.js',
                'src/native/grouped_menu_hooks.js','src/native/fast_menu_hooks.js'))
        script=device.create_script(source+'\n'+fixture)
        script.load()
        try:
            return script.exports_sync.run(*args)
        finally:
            script.unload()
            device.kill(pid)

    def compare(self, scenario):
        result=self.run_fixture(FAST_FIXTURE,scenario)
        original,fast=result['original'],result['grouped']
        for key in ('events','values','lastError','unrelatedEvents',
                    'cachedIgnoresReplacement','stoppedCallsIgnored'):
            self.assertEqual(fast[key],original[key],key)
        self.assertEqual(fast['initial']['nativeHooks'],0)
        self.assertEqual(fast['initial']['fastReplacements'],1)
        self.assertEqual(fast['initial']['registrations'],10)
        self.assertEqual(fast['stopped']['fastReplacements'],1)
        self.assertEqual(fast['stopped']['activeRegistrations'],0)
        self.assertEqual(fast['values'],[0x1234]*9)
        self.assertEqual(fast['lastError'],1234)
        self.assertEqual(fast['unrelatedEvents'],0)
        self.assertTrue(fast['cachedIgnoresReplacement'])
        self.assertTrue(fast['stoppedCallsIgnored'])
        return fast

    def test_filters_cache_arguments_order_error_and_disable_match_original(self):
        self.assertEqual(self.compare('normal')['events'][:3],[0,9,1])

    def test_reentrant_callbacks_match_original(self):
        self.compare('reentrant')

    def test_detach_before_commit(self):
        result=self.compare('detach-before')
        self.assertNotIn(4,result['events'])
        self.assertEqual(result['initial']['activeRegistrations'],9)

    def test_rejects_mixed_entry_pool_and_interior(self):
        result=self.run_fixture(FAST_FIXTURE,'invalid-registration')
        self.assertEqual(result['rejected'],3)
        self.assertEqual(result['status']['fastReplacements'],0)

    def test_preserves_float_integer_stack_arguments_and_return(self):
        result=self.run_fixture(ABI_FIXTURE,'abi')
        self.assertEqual(result['before'],1234596.5)
        self.assertEqual(result['after'],result['before'])
        self.assertEqual(result['disabled'],result['before'])
        self.assertTrue(result['argumentsIntact'])
        self.assertEqual(result['callbacks'],1)

    def test_rejects_modified_entry_before_installation(self):
        result=self.run_fixture(ABI_FIXTURE,'changed-entry')
        self.assertTrue(result['rejected'])
        self.assertTrue(result['unchanged'])
        self.assertEqual(result['status']['fastReplacements'],0)

    def test_native_transaction_rechecks_bytes(self):
        result=self.run_fixture(ABI_FIXTURE,'native-guard')
        self.assertEqual(result,dict(result=-101,unchanged=True,originalNull=True))

    def test_preserves_all_volatile_integer_sse_registers_and_flags(self):
        result=self.run_fixture(REGISTERS_FIXTURE)
        self.assertEqual(result['before'],result['after'])
        self.assertEqual(result['afterReturn'],0x1234)
        self.assertEqual(result['beforeReturn'],result['afterReturn'])
        self.assertEqual(result['callbacks'],1)

    def test_concurrent_installation_and_measure_native_dispatch(self):
        result=self.run_fixture(BENCH_FIXTURE)
        self.assertGreater(int(result['workerCalls']),0)
        self.assertEqual(result['workerErrors'],'0')
        self.assertEqual(result['checksum'],str(100000*0x1234))
        # Timings are evidence, not machine-dependent pass/fail assertions.
        (BUILD/'benchmark.json').write_text(
            json.dumps(result,indent=2)+'\n')
        print('\nNative dispatch benchmark: '+json.dumps(result))


if __name__=='__main__':
    unittest.main()
