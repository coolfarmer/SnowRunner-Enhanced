"""Exercise permanent map rotation sensitivity in the embedded runtime."""
import json
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
from native_host import NativeDevice
HERE = ROOT/'src'

FIXTURE=r'''
rpc.exports.run=(scenario)=>{
 const keep=[],alloc=n=>{const p=Memory.alloc(n);p.writeByteArray(new Uint8Array(n));keep.push(p);return p;};
 const props=new Map(),owned=new Set(),tag=p=>p.or('0x20000000000000'),untag=p=>p.and('0xffffffffffff');
 function object(own=false){const p=alloc(64);props.set(p.toString(),{});if(own)owned.add(p.toString());return p;}
 function prop(p,n){const d=props.get(p.toString());if(!d[n])d[n]=alloc(8);return d[n];}
 const view=object(),controller=object(true),other=object();prop(controller,'view').writePointer(tag(view));
 function vm(p,value){const v=alloc(32),a=alloc(16);v.add(0x18).writePointer(a);a.writePointer(tag(p));a.add(8).writePointer(ptr('0x3000000000000'));a.add(8).writeFloat(value??0);return v;}
 const access={prop,get:(p,n)=>untag(prop(p,n).readPointer()),owns:p=>owned.has(p.toString()),receiver:v=>untag(v.add(0x18).readPointer().readPointer())};
 const callbacks={},saved=[];let detached=0;
 const zoom=makeMapPanningSensitivity(PROFILE,access,{mapEnabled:scenario!=='disabled',panningSensitivity:75,onPanningChange:v=>saved.push(v)},
 (_f,_s,cb,c,m)=>{if(scenario==='attach-failure'&&m==='HandleChange')throw Error('Synthetic attach failure');callbacks[m]=cb;return {detach(){detached++;}};});
 zoom.start(ptr(0),ptr(0));
 if(scenario==='disabled')return {status:zoom.status(),hooks:Object.keys(callbacks)};
 if(scenario==='attach-failure')return {status:zoom.status(),detached};
 function method(words,count=0){const fn=alloc(128),code=alloc(words.length*4),constants=alloc(64);words.forEach((w,i)=>code.add(i*4).writeU32(w));fn.add(0x60).writePointer(code);fn.add(0x68).writeU32(words.length);fn.add(0x50).writePointer(constants);fn.add(0x58).writeU32(count);return {fn,code,constants};}

 const z=method(PROFILE.mouseRotateWords),s=method(PROFILE.getterWords);
 const read=m=>Array.from({length:m.fn.add(0x68).readU32()},(_,i)=>m.fn.add(0x60).readPointer().add(i*4).readU32());
 const original=m=>m.fn.add(0x60).readPointer().equals(m.code)&&m.fn.add(0x50).readPointer().equals(m.constants);
 if(scenario==='mismatch'){z.code.writeU32(0);callbacks.MouseRotate(null,z.fn);return {status:zoom.status(),untouched:original(z)};}
 callbacks.GetCurrentValue(vm(controller),s.fn);
 const initial=prop(controller,'hackCurrent').readFloat();
 const getter=read(s),delta=getter.length-PROFILE.getterWords.length;
 const text={24:false},container={24:false,143:text},tree={5:{6:{144:{95:container}}}},stack=[];
 for(const w of getter.slice(0,delta)){
  const op=w&255,arg=(w>>>8)-0x800000;
  if(op===5)stack.push(!!arg);else if(op===7)stack.push(tree);else if(op===10)stack.push(stack.pop()[arg]);
  else if(op===60){const p=stack.pop();p[arg]=stack.pop();stack.push(undefined);}else if(op===2)stack.pop();else throw Error('Unexpected getter prefix');
 }
 callbacks.GetCurrentValue(vm(other),s.fn);callbacks.HandleChange(vm(other,0));
 const unrelated=original(s)&&zoom.status().value===75;
 const cases=[];
 for(const value of [0,25,50,75,100,50]){
  callbacks.HandleChange(vm(controller,value));callbacks.MouseRotate(null,z.fn);
  const words=read(z);
  if(!PROFILE.mouseRotateWords.slice(0,10).every((w,i)=>words[i]===w))throw Error('Native input refresh changed');
  if(value===50&&!original(z))throw Error('Midpoint must restore exact body');
  for(const input of [-.5,0,.5]){
   const self={6:5000},vector={5:input},stack=[];let result;
   for(const w of words.slice(10)){
    const op=w&255,arg=(w>>>8)-0x800000;
    if(op===1)continue;
    if(op===7)stack.push(arg===0?self:vector);
    else if(op===10)stack.push(stack.pop()[arg]);
    else if(op===30)stack.push(-stack.pop());
    else if(op===40){const b=stack.pop();stack.push(Math.fround(stack.pop()*b));}
    else if(op===6)stack.push(z.fn.add(0x50).readPointer().add(arg*8).readFloat());
    else if(op===4)stack.push(arg);
    else if(op===13){if(arg!==90||stack.pop()!==1||stack.pop()!==self)throw Error('Wrong native rotation call');result=stack.pop();stack.push(undefined);}
    else if(op===2)stack.pop();else if(op===19)break;else throw Error('Unknown rotation opcode '+op);
   }
   if(stack.length||vector[5]!==input)throw Error('Input or stack changed');cases.push({value,input,result});
  }
 }
 callbacks.HandleChange(vm(controller,100));callbacks.MouseRotate(null,z.fn);
 if(scenario==='foreign'){
  z.fn.add(0x58).writeU32(2);let rejected=false;try{zoom.stop();}catch(_){rejected=true;}
  return {rejected,preserved:z.fn.add(0x58).readU32()===2};
 }
 if(scenario==='invalid')callbacks.HandleChange(vm(controller,NaN));
 const status=zoom.status();zoom.stop();
 return {status,initial,unrelated,visible:container[24]&&text[24],cases,restored:original(z)&&original(s),detached};
};
'''

class PanningTests(unittest.TestCase):
    def run_case(self, scenario='normal'):
        device=NativeDevice(); pid=device.spawn(None)
        try:
            source='const PROFILE='+ (HERE/'settings-profile.json').read_text()+';\n'
            script=device.create_script(source+(HERE/'map_panning.js').read_text()+FIXTURE)
            script.load(); result=script.exports_sync.run(scenario); script.unload(); return result
        finally: device.kill(pid)
    def test_rotation_slider_and_restore(self):
        r=self.run_case()
        self.assertIsNone(r['status']['fault'])
        self.assertEqual(r['initial'],75)
        for key in ['unrelated','visible','restored']: self.assertTrue(r[key],key)
        self.assertEqual(r['detached'],3)
        for c in r['cases']:
            factor=(50 if c['value']<50 else 4)**((c['value']-50)/50)
            self.assertAlmostEqual(c['result'],-c['input']*5000*factor,places=3)
        minimum=next(c for c in r['cases'] if c['value']==0 and c['input']==.5)
        self.assertAlmostEqual(minimum['result'],-2500/50,places=4)
    def test_mismatch_rejected(self):
        r=self.run_case('mismatch'); self.assertTrue(r['untouched']); self.assertIsNotNone(r['status']['fault'])
    def test_foreign_change_preserved(self):
        r=self.run_case('foreign'); self.assertTrue(r['rejected']); self.assertTrue(r['preserved'])
    def test_invalid_value_restores(self):
        r=self.run_case('invalid'); self.assertTrue(r['restored']); self.assertIsNotNone(r['status']['fault'])
    def test_disabled(self):
        r=self.run_case('disabled'); self.assertEqual(r['hooks'],[])
    def test_attach_failure(self):
        r=self.run_case('attach-failure'); self.assertEqual(r['detached'],1); self.assertFalse(r['status']['running'])
if __name__=='__main__': unittest.main()
