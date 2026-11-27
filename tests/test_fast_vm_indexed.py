"""Differential filtering and native benchmarks for the opt-in positive index."""
import json
import os
from pathlib import Path
import unittest
from native_host import NativeDevice

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path(os.environ.get('ENHANCED_FAST_TEST_BUILD', ROOT / 'build/native'))

SETUP = r'''
const keep=[],alloc=n=>{const p=Memory.alloc(n);keep.push(p);return p;};
const pool=alloc(65536),slot=alloc(8);slot.writePointer(pool);let used=0;
function name(text){const id=used;pool.add(id).writeUtf8String(text);used+=text.length+1;return id;}
function descriptor(c,m){
    const fn=alloc(128),cls=alloc(64),sig=alloc(8);
    cls.add(0x18).writeU32(name(c));sig.writeU32(name(m));
    fn.add(0x48).writePointer(cls);fn.add(0x40).writePointer(sig);return fn;
}
const vm=alloc(256),frame=alloc(64);vm.add(0x50).writePointer(frame);
const entry=alloc(Process.pageSize);Memory.protect(entry,Process.pageSize,'rwx');
const host=Process.mainModule;
'''

SEMANTICS = r'''
rpc.exports.run=scenario=>{
SETUP
    entry.writeByteArray([...Array(16).fill(0x90),0xb8,0x34,0x12,0,0,0xc3]);
    const call=new NativeFunction(entry,'uint32',['pointer','pointer']);
    const fn=descriptor('Unknown','Unknown'),cls=fn.add(0x48).readPointer(),sig=fn.add(0x40).readPointer();
    function exercise(indexed){
        const batch=makeFastMenuHooks({address:entry,hex:'90'.repeat(16),indexed},host),events=[];
        const handles=Array.from({length:32},(_,i)=>batch(entry,slot,()=>events.push(i),
            i===31?'Class':'Class'+i,i===31?'Method':'Method'+i));
        batch.commit();
        try{
            const set=(c,m)=>{cls.add(0x18).writeU32(name(c));sig.writeU32(name(m));};
            set('Unknown','Unknown');call(vm,fn);
            set('Clas','Method');call(vm,fn);
            set('ClassExtra','Method');call(vm,fn);
            set('Class','MethodExtra');call(vm,fn);
            set('Class','Metho');call(vm,fn);
            const rejected=events.length;
            set('Class','Method');
            pool.add(cls.add(0x18).readU32()+5).writeU8(255);
            pool.add(sig.readU32()+6).writeU8(255);
            call(vm,fn); // Previously rejected identity is now valid, including bit 31.
            cls.add(0x18).writeU32(0x10000001);sig.writeU32(0x10000001);
            call(vm,fn); // Positive identity stays valid after its metadata changes.
            call(vm,descriptor('Class','Method')); // Cached registration ignores replacement identity.
            const replacement=descriptor('Class0','Method0');
            if(scenario==='overflow'){
                const state=fastMenuResources[fastMenuResources.length-1].state;
                if(indexed)state.add(16+16*32+520).writeU64(1);
            }
            call(vm,replacement);
            handles[31].detach();call(vm,fn);
            return {rejected,events};
        }finally{handles.forEach(h=>h.detach());batch.releaseForTest();}
    }
    return {before:exercise(false),after:exercise(true)};
};
'''.replace('SETUP', SETUP)

TABLE = r'''
rpc.exports.run=()=>{
    const table=Memory.alloc(512),host=Process.mainModule;
    const remember=new NativeFunction(host.getExportByName('EnhancedRememberVmTarget'),'int',['pointer','pointer']);
    const keys=[];
    for(let n=16;keys.length<65;n+=16)if((((n>>>4)^(n>>>13))&63)===0)keys.push(ptr(n));
    const inserted=keys.slice(0,64).map(key=>remember(table,key));
    const duplicate=remember(table,keys[0]),overflow=remember(table,keys[64]);
    const actual=Array.from({length:64},(_,i)=>table.add(8*i).readPointer().toString());
    const mask=Memory.alloc(4);mask.writeU32(0xffffffff);
    const resolve=new NativeFunction(host.getExportByName('EnhancedResolveVmRegistration'),'void',['pointer','uint32']);
    resolve(mask,0x80000000);resolve(mask,1);
    return {inserted,duplicate,overflow,actual,expected:keys.slice(0,64).map(p=>p.toString()),mask:mask.readU32()};
};
'''

PAGE_BOUNDARY = r'''
rpc.exports.run=()=>{
SETUP
    const pages=alloc(Process.pageSize*2),end=pages.add(Process.pageSize-2);
    end.writeByteArray([65,255]);Memory.protect(pages.add(Process.pageSize),Process.pageSize,'---');
    const fn=descriptor('A','A');slot.writePointer(end);
    fn.add(0x48).readPointer().add(0x18).writeU32(0);fn.add(0x40).readPointer().writeU32(0);
    entry.writeByteArray([...Array(16).fill(0x90),0xc3]);
    let calls=0;
    const batch=makeFastMenuHooks({address:entry,hex:'90'.repeat(16),indexed:true},host);
    batch(entry,slot,()=>calls++,'A','A');batch(entry,slot,()=>calls+=100,'AB','AB');batch.commit();
    try{
        const call=new NativeFunction(entry,'void',['pointer','pointer']);
        call(vm,fn);
        // The remaining unresolved 'AB' cannot start with Z. The byte after
        // Z is inaccessible and the filter must decide on the first byte.
        const other=descriptor('Z','A');
        end.add(1).writeU8(90);
        other.add(0x48).readPointer().add(0x18).writeU32(1);
        call(vm,other);
        return {calls};
    }
    finally{batch.releaseForTest();Memory.protect(pages.add(Process.pageSize),Process.pageSize,'rw-');}
};
'''.replace('SETUP', SETUP)

BENCHMARK = r'''
rpc.exports.run=inside=>{
SETUP
    const prefix=inside?[0x48,0x8b,0x49,0x50,0x48,0x8b,0x41,0x18,...Array(8).fill(0x90)]:Array(16).fill(0x90);
    entry.writeByteArray([...prefix,0xb8,0x34,0x12,0,0,0xc3]);
    const hex=prefix.map(n=>n.toString(16).padStart(2,'0')).join('');
    const count=inside?12:20;
    const classes=['UiSettingsController','ComponentUiControllerBase','MinimapCameraController','NavigationPanelController'];
    const targets=Array.from({length:count},(_,i)=>descriptor(classes[i%4],'Method'+i));
    const ignored=Array.from({length:64},(_,i)=>descriptor(i%3===0?classes[i%4]:'VehicleController','Unrelated'+i));
    const pointers=alloc(ignored.length*8);ignored.forEach((fn,i)=>pointers.add(i*8).writePointer(fn));
    const kernel=Process.getModuleByName('kernel32.dll'),checksum=alloc(8);
    const native=new CModule(`
        #include <stdint.h>
        extern unsigned entry(void *,void *,void *);
        extern int counter(int64_t *);extern int frequency(int64_t *);
        extern uint64_t checksum;
        double measure(void *vm,void **fns,unsigned n){
            int64_t start,end,freq;unsigned i,total=0;frequency(&freq);counter(&start);
            for(i=0;i<n;i++)total+=entry(vm,fns[i&63],vm);
            counter(&end);checksum=total;
            return 1000000000.0*(double)(end-start)/(double)freq/n;
        }
    `,{entry,checksum,counter:kernel.getExportByName('QueryPerformanceCounter'),frequency:kernel.getExportByName('QueryPerformanceFrequency')});
    const measure=new NativeFunction(native.measure,'double',['pointer','pointer','uint32']);
    const call=new NativeFunction(entry,'uint32',['pointer','pointer','pointer']);
    const timings={},callbacks={};
    const sample=key=>{measure(vm,pointers,20000);timings[key]=Array.from({length:5},()=>measure(vm,pointers,500000));};
    sample('baseline');
    // Repeat in reversed order to make drift visible.
    const modes=ENHANCED_VM_PREFIXES ? [[0,true,false],[0,true,true],[1,true,true],[1,true,false]] :
        [[0,false,false],[0,true,false],[1,true,false],[1,false,false]];
    for(const [round,indexed,prefixes] of modes){
        const tag=(prefixes?'prefix':indexed?'indexed':'previous')+round;let calls=0;
        const batch=makeFastMenuHooks({address:entry,hex,indexed,prefixes,interior:inside,splitOffset:inside?8:0},host);
        targets.forEach((fn,i)=>batch(entry,slot,()=>calls++,classes[i%4],'Method'+i,inside,inside&&i>=6?1:0));
        batch.commit();
        try{
            sample(tag+'Cold');targets.forEach(fn=>call(vm,fn,vm));sample(tag+'Warm');
            callbacks[tag]=calls;
        }finally{batch.releaseForTest();}
    }
    return {timings,callbacks,registrations:count,checksum:checksum.readU64().toString(),inside};
};
'''.replace('SETUP', SETUP)


class FastVmIndexedTests(unittest.TestCase):
    def run_fixture(self, fixture, *args):
        device=NativeDevice(BUILD/'native-harness.exe');pid=device.spawn(None)
        prefix_mode = str(os.environ.get('ENHANCED_TEST_VM_PREFIXES','1') == '1').lower()
        source=f'const CONFIG={{test:true}};\nconst ENHANCED_VM_PREFIXES={prefix_mode};\n'+(ROOT/'src/native/fast_menu_hooks.js').read_text()
        script=device.create_script(source+'\n'+fixture);script.load()
        try:return script.exports_sync.run(*args)
        finally:script.unload();device.kill(pid)

    def test_rejected_descriptor_can_change_and_positive_identity_keeps_original_semantics(self):
        result=self.run_fixture(SEMANTICS,'normal')
        self.assertEqual(result['before'],result['after'])
        self.assertEqual(result['after'],dict(rejected=0,events=[31,31,0]))

    def test_overflow_uses_complete_filter(self):
        result=self.run_fixture(SEMANTICS,'overflow')
        self.assertEqual(result['before'],result['after'])
        self.assertEqual(result['after']['events'],[31,31,0])

    def test_collisions_full_table_duplicates_and_high_registration_bit(self):
        result=self.run_fixture(TABLE)
        self.assertEqual(result['inserted'],[1]*64)
        self.assertEqual(result['duplicate'],1);self.assertEqual(result['overflow'],0)
        self.assertEqual(result['actual'],result['expected'])
        self.assertEqual(result['mask'],0x7ffffffe)

    def test_exact_name_prefixes_do_not_read_past_page_boundary(self):
        self.assertEqual(self.run_fixture(PAGE_BOUNDARY),dict(calls=1))

    def test_measure_twenty_entry_and_twelve_split_interior_filters(self):
        results=[]
        for inside in (False,True):
            result=self.run_fixture(BENCHMARK,inside)
            self.assertEqual(result['checksum'],str(500000*0x1234))
            self.assertTrue(all(n==result['registrations'] for n in result['callbacks'].values()))
            results.append(result)
        (BUILD/'indexed-benchmark.json').write_text(json.dumps(results,indent=2)+'\n')
        print('\nIndexed native benchmark: '+json.dumps(results))


if __name__=='__main__':unittest.main()
