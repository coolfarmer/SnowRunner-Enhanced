"""Execute the actual map fix against guarded VM descriptors in a disposable host."""
import json
from pathlib import Path
import sys
import unittest
import frida

ROOT=Path(__file__).resolve().parents[1]
WORDS=[0x80000101,0x80000007,0x8000550a,0x80000004,0x80001a0d,0x80000002,
       0x80000101,0x80000007,0x8000540a,0x80000004,0x80001a0d,0x80000002,0x80000113]
FIXTURE=r'''
rpc.exports.run=()=>{
 const pool=Memory.alloc(256),slot=Memory.alloc(8),cls=Memory.alloc(64),sig=Memory.alloc(16),fn=Memory.alloc(128);
 pool.writeUtf8String('MinimapUiSidepanelView');pool.add(64).writeUtf8String('HideContractBtn');
 slot.writePointer(pool);cls.add(0x18).writeU32(0);sig.writeU32(64);
 fn.writeByteArray(new Uint8Array(128));fn.add(0x48).writePointer(cls);fn.add(0x40).writePointer(sig);
 const code=Memory.alloc(WORDS.length*4);WORDS.forEach((w,i)=>code.add(i*4).writeU32(w));
 fn.add(0x60).writePointer(code);fn.add(0x68).writeU32(WORDS.length);
 const read=()=>Array.from({length:fn.add(0x68).readU32()},(_,i)=>fn.add(0x60).readPointer().add(i*4).readU32());
 // Small interpreter for the real straight-line method's stack operations.
 function execute(words){
  const contract={visible:true},reset={visible:true},notify={visible:true},other={visible:true};
  const ui={149:notify,148:other},self={6:ui,85:contract,84:reset},stack=[];
  let calls=0;
  for(const w of words){const op=w&255,arg=(w>>>8)-0x800000;
   if(op===1)continue;
   if(op===7){if(arg!==0)throw Error('Unexpected receiver');stack.push(self);}
   else if(op===0xa)stack.push(stack.pop()[arg]);
   else if(op===4)stack.push(arg);
   else if(op===5)stack.push(!!arg);
   else if(op===0xd){if(arg!==26||stack.pop()!==0)throw Error('Unexpected call');stack.pop().visible=false;calls++;stack.push(undefined);}
   else if(op===0x3c){if(arg!==24)throw Error('Unexpected setter');const object=stack.pop();object.visible=stack.pop();stack.push(undefined);}
   else if(op===2)stack.pop();
   else if(op===0x13){if(stack.length)throw Error('Unbalanced stack');break;}
   else throw Error('Unknown opcode');
  }
  return{contract:contract.visible,reset:reset.visible,notify:notify.visible,other:other.visible,calls};
 }
 const fix=makeMapNotificationHitAreaFix(slot),before=execute(read()),applied=fix.apply(fn),after=execute(read());
 const originalUntouched=WORDS.every((w,i)=>code.add(i*4).readU32()===w);
 const repeat=fix.apply(fn),restored=fix.restore(),afterRestore=execute(read());
 const rejected=[];
 for(const kind of ['name','method','length','constants','body','tail']){
  if(kind==='name')pool.writeUtf8String('Other');
  if(kind==='method')sig.writeU32(0);
  if(kind==='length')fn.add(0x68).writeU32(12);
  if(kind==='constants')fn.add(0x58).writeU32(1);
  if(kind==='body')code.add(8).writeU32(0x8000540a);
  if(kind==='tail')code.add(48).writeU32(0x80000213);
  rejected.push(!fix.apply(fn)&&fn.add(0x60).readPointer().equals(code));
  pool.writeUtf8String('MinimapUiSidepanelView');sig.writeU32(64);fn.add(0x68).writeU32(13);fn.add(0x58).writeU32(0);
  WORDS.forEach((w,i)=>code.add(i*4).writeU32(w));
 }
 const reapplied=fix.apply(fn),replacement=fn.add(0x60).readPointer();
 replacement.add(48).writeU32(0x80000105);
 const rejectsForeignRestore=!fix.restore()&&fn.add(0x60).readPointer().equals(replacement);
 replacement.add(48).writeU32(0x80000005);
 const finalRestore=fix.restore();
 return{before,applied,after,originalUntouched,repeat,restored,afterRestore,rejected,reapplied,rejectsForeignRestore,finalRestore};
};
'''

class MapHoverVmTests(unittest.TestCase):
 def test_preserves_original_actions_and_restores_without_overwriting_foreign_code(self):
  device=frida.get_local_device()
  pid=device.spawn([sys.executable,'-c','import time; time.sleep(60)'])
  session=None
  try:
   session=device.attach(pid);device.resume(pid)
   script=session.create_script('const WORDS='+json.dumps(WORDS)+';\n'+(ROOT/'src/vm_scope.js').read_text()+FIXTURE)
   script.load();result=script.exports_sync.run();script.unload()
   self.assertEqual(result['before'],dict(contract=False,reset=False,notify=True,other=True,calls=2))
   self.assertEqual(result['after'],dict(contract=False,reset=False,notify=False,other=True,calls=2))
   self.assertEqual(result['afterRestore'],result['before'])
   self.assertFalse(result['repeat'])
   self.assertTrue(all(result['rejected']))
   for key in ['applied','originalUntouched','restored','reapplied','rejectsForeignRestore','finalRestore']:
    self.assertTrue(result[key],key)
  finally:
   if session:session.detach()
   device.kill(pid)

if __name__=='__main__':unittest.main()
