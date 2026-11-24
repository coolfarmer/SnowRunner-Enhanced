"""Execute the shipped zoom patch in GumJS, including the actual VM arithmetic."""
import json
from pathlib import Path
import unittest
from native_host import NativeDevice

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''
rpc.exports.run=(scenario)=>{
 const keep=[],alloc=n=>{const p=Memory.alloc(n);p.writeByteArray(new Uint8Array(n));keep.push(p);return p;};
 const props=new Map(),owned=new Set(),tag=p=>p.or('0x20000000000000'),untag=p=>p.and('0xffffffffffff');
 function object(own=false){const p=alloc(64);props.set(p.toString(),{});if(own)owned.add(p.toString());return p;}
 function prop(p,n){const d=props.get(p.toString());if(!d[n])d[n]=alloc(8);return d[n];}
 const view=object(),controller=object(true),other=object();prop(controller,'view').writePointer(tag(view));
 function vm(p,value){const v=alloc(32),a=alloc(16);v.add(0x18).writePointer(a);a.writePointer(tag(p));a.add(8).writePointer(ptr('0x3000000000000'));a.add(8).writeFloat(value??0);return v;}
 const access={prop,get:(p,n)=>untag(prop(p,n).readPointer()),owns:p=>owned.has(p.toString()),receiver:v=>untag(v.add(0x18).readPointer().readPointer())};
 const callbacks={},saved=[];let detached=0;
 const zoom=makeMapZoomSensitivity(PROFILE,access,{mapEnabled:scenario!=='disabled',zoomSensitivity:75,onZoomChange:v=>saved.push(v)},
 (_f,_s,cb,c,m)=>{if(scenario==='attach-failure'&&m==='HandleChange')throw Error('Synthetic attach failure');callbacks[m]=cb;return {detach(){detached++;}};});
 zoom.start(ptr(0),ptr(0));
 if(scenario==='disabled')return {status:zoom.status(),hooks:Object.keys(callbacks)};
 if(scenario==='attach-failure')return {status:zoom.status(),detached};
 function method(words,count=0){const fn=alloc(128),code=alloc(words.length*4),constants=alloc(64);words.forEach((w,i)=>code.add(i*4).writeU32(w));fn.add(0x60).writePointer(code);fn.add(0x68).writeU32(words.length);fn.add(0x50).writePointer(constants);fn.add(0x58).writeU32(count);return {fn,code,constants};}
 const z=method(PROFILE.zoomWords),s=method(PROFILE.sliderCurrentWords,5);
 const read=m=>Array.from({length:m.fn.add(0x68).readU32()},(_,i)=>m.fn.add(0x60).readPointer().add(i*4).readU32());
 const original=m=>m.fn.add(0x60).readPointer().equals(m.code)&&m.fn.add(0x50).readPointer().equals(m.constants);
 if(['body','length','constants'].includes(scenario)){
  if(scenario==='body')z.code.add(8).writeU32(0);
  if(scenario==='length')z.fn.add(0x68).writeU32(1);
  if(scenario==='constants')z.fn.add(0x58).writeU32(1);
  callbacks.Zoom(null,z.fn);return {status:zoom.status(),untouched:original(z)};
 }
 callbacks.GetCurrentValue(vm(controller));
 const initial=prop(controller,'hackCurrent').readFloat(),format=prop(view,'textFormat').readPointer().toString();
 callbacks.GetCurrentValue(vm(other));callbacks.HandleChange(vm(other,0));
 const unrelated=zoom.status().value===75&&prop(other,'hackCurrent').readPointer().isNull();
 callbacks.UpdateSliderCurrent(vm(view),s.fn);
 const patchedView=read(s),delta=patchedView.length-PROFILE.sliderCurrentWords.length;
 const branches=PROFILE.sliderCurrentWords.every((w,i)=>patchedView[i+delta]===([22,23,24,25,26].includes(w&255)?(w+delta*256)>>>0:w));
 const tf={24:false},container={24:false,143:tf},tree={6:{144:{95:container}}},stack=[];
 for(const w of patchedView.slice(0,delta)){
  const op=w&255,arg=(w>>>8)-0x800000;
  if(op===5)stack.push(!!arg);else if(op===7)stack.push(tree);else if(op===10)stack.push(stack.pop()[arg]);
  else if(op===60){const p=stack.pop();p[arg]=stack.pop();stack.push(undefined);}else if(op===2)stack.pop();else throw Error('Unexpected display opcode');
 }
 callbacks.UpdateSliderCurrent(vm(other),s.fn);const otherViewUntouched=original(s);
 function execute(input,dt){
  const self={30:10,39:{}},vector={4:input},stack=[];
  for(const w of read(z)){
   const op=w&255,arg=(w>>>8)-0x800000;
   if(op===1)continue;
   if(op===7)stack.push(arg===0?self:vector);
   else if(op===10)stack.push(stack.pop()[arg]);
   else if(op===4)stack.push(arg);
   else if(op===6)stack.push(z.fn.add(0x50).readPointer().add(arg*8).readFloat());
   else if(op===13){if(arg!==181||stack.pop()!==0||stack.pop()!==self[39])throw Error('Unexpected game call');stack.push(dt);}
   else if(op===40){const b=stack.pop();stack.push(Math.fround(stack.pop()*b));}
   else if(op===37){const b=stack.pop();stack.push(Math.fround(stack.pop()-b));}
   else if(op===60){const p=stack.pop();p[arg]=stack.pop();stack.push(undefined);}
   else if(op===2)stack.pop();else if(op===19)break;else throw Error('Unexpected zoom opcode');
  }
  if(stack.length||vector[4]!==input)throw Error('Stack/input changed');return self[30];
 }
 const cases=[];
 for(const value of [0,25,50,75,100,50]){
  callbacks.HandleChange(vm(controller,value));callbacks.Zoom(null,z.fn);
  for(const input of [-30,0,30])for(const dt of [0,Math.fround(1/60),Math.fround(1/144)])cases.push({value,input,dt,height:execute(input,dt)});
  if(value===50&&!original(z))throw Error('Midpoint did not restore native code');
 }
 // Recreated controller retrieves the current preference, while SetDefault's
 // ordinary HandleChange(50) follows the same saved-value path.
 callbacks.HandleChange(vm(controller,100));
 const recreated=object(true);prop(recreated,'view').writePointer(tag(view));callbacks.GetCurrentValue(vm(recreated));
 const retained=prop(recreated,'hackCurrent').readFloat();
 callbacks.HandleChange(vm(recreated,50));callbacks.GetCurrentValue(vm(recreated));const reset=prop(recreated,'hackCurrent').readFloat();
 callbacks.HandleChange(vm(controller,1000));const clamped=zoom.status().value;
 callbacks.Zoom(null,z.fn);
 if(scenario.startsWith('foreign')){
  const code=z.fn.add(0x60).readPointer();
  if(scenario==='foreign-body')code.writeU32(0);
  if(scenario==='foreign-constants')z.fn.add(0x50).writePointer(alloc(8));
  if(scenario==='foreign-count')z.fn.add(0x58).writeU32(2);
  const before=z.fn.readByteArray(128);let rejected=false;try{zoom.stop();}catch(_){rejected=true;}
  return {rejected,preserved:JSON.stringify(Array.from(new Uint8Array(before)))===JSON.stringify(Array.from(new Uint8Array(z.fn.readByteArray(128))))};
 }
 if(scenario==='invalid')callbacks.HandleChange(vm(controller,NaN));
 const status=zoom.status();zoom.stop();
 return {initial,format,unrelated,branches,visible:container[24]&&tf[24],otherViewUntouched,cases,retained,reset,clamped,saved,status,restored:original(z)&&original(s),detached};
};
'''


class MapZoomTests(unittest.TestCase):
    def run_case(self, scenario='normal'):
        device = NativeDevice()
        pid = device.spawn(None)
        try:
            source = 'const PROFILE=' + (ROOT/'src/settings-profile.json').read_text() + ';\n'
            script = device.create_script(source + (ROOT/'src/map_zoom.js').read_text() + FIXTURE)
            script.load()
            result = script.exports_sync.run(scenario)
            script.unload()
            return result
        finally:
            device.kill(pid)

    def test_arithmetic_display_lifecycle_and_restore(self):
        r = self.run_case()
        self.assertIsNone(r['status']['fault'])
        self.assertEqual(r['initial'], 75)
        self.assertEqual(r['format'], '0x1000000000002')
        for key in ['unrelated','branches','visible','otherViewUntouched','restored']:
            self.assertTrue(r[key], key)
        for case in r['cases']:
            expected = 10 - case['input'] * case['dt'] * 4 ** ((case['value']-50)/50)
            self.assertAlmostEqual(case['height'], expected, places=5, msg=str(case))
        self.assertEqual((r['retained'], r['reset'], r['clamped']), (100, 50, 100))
        self.assertIn(50, r['saved'])
        self.assertEqual(r['detached'], 4)

    def test_disabled_map_installs_no_zoom_or_slider_hooks(self):
        r = self.run_case('disabled')
        self.assertEqual(r['hooks'], [])
        self.assertEqual(r['status']['status'], 'disabled')

    def test_hook_failure_is_contained_for_the_core_menu(self):
        r = self.run_case('attach-failure')
        self.assertIn('Synthetic attach failure', r['status']['fault'])
        self.assertFalse(r['status']['running'])
        self.assertEqual(r['detached'], 1)

    def test_changed_game_methods_are_not_patched(self):
        for kind in ['body','length','constants']:
            with self.subTest(kind=kind):
                r = self.run_case(kind)
                self.assertTrue(r['untouched'])
                self.assertIsNotNone(r['status']['fault'])

    def test_foreign_changes_are_not_overwritten_on_stop(self):
        for kind in ['body','constants','count']:
            with self.subTest(kind=kind):
                r = self.run_case('foreign-'+kind)
                self.assertTrue(r['rejected'])
                self.assertTrue(r['preserved'])

    def test_nonfinite_slider_value_stops_and_restores_patch(self):
        r = self.run_case('invalid')
        self.assertIn('Invalid zoom slider', r['status']['fault'])
        self.assertTrue(r['restored'])


if __name__ == '__main__':
    unittest.main()
