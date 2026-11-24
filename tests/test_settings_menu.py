"""Exercise the shipped menu against disposable VM metadata in embedded GumJS."""
import json
from pathlib import Path
import unittest
from native_host import NativeDevice

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''
rpc.exports.run=(scenario)=>{
 const keep=[],alloc=n=>{const p=Memory.alloc(n);p.writeByteArray(new Uint8Array(n));keep.push(p);return p;};
 const pool=alloc(32768),slot=alloc(8);slot.writePointer(pool);let offset=0;
 const names=new Map();function name(s){if(!names.has(s)){names.set(s,offset);pool.add(offset).writeUtf8String(s);offset+=s.length+1;}return names.get(s);}
 function klass(n,members=[]){
  const c=alloc(128),table=alloc(100*32);c.add(0x18).writeU32(name(n));c.add(0x58).writePointer(table);c.add(0x60).writeU32(100);
  for(let i=0;i<100;i++)table.add(i*32).writeU32(name('_'+i));
  for(const [n,id,kind] of members){const e=table.add(id*32),d=alloc(128);e.writeU32(name(n));e.add(4).writeU8(kind);e.add(8).writePointer(d);d.add(0x50).writeU32(id);}
  return c;
 }
 const tag=p=>p.or('0x20000000000000'),untag=p=>p.and('0xffffffffffff');
 function object(c){const p=alloc(1024);p.add(0x18).writePointer(c);return p;}
 const put=(p,id,v)=>p.add(0x30+id*8).writePointer(v);
 function descriptor(c,id){return c.add(0x58).readPointer().add(id*32+8).readPointer();}
 function type(c){const p=alloc(48);p.add(8).writeU32(c.add(0x18).readU32());p.add(32).writePointer(c.or('0x3000000000000'));return p.or('0x30000000000000');}
 const props=a=>a.map(([n,id])=>[n,id,5]);
 const settingsClass=klass('UiSettingsController',[...props([['view',5],['deviceListener',8],['uiSystem',9],['localizationUpdateNotifier',11],['inputScreen',54],['settings',56],['tabBar',57],['activeTabs',63]]),['GetView',34,2],['InitContent',20,2]]);
 const gammaClass=klass('UiOneSettingSliderGammaController',[...props([['view',5],['uiSystem',9],['header',39],['desc',40],['shouldBeVisible',41],['minValue',50],['maxValue',51],['defaultValue',52],['stepInterval',53],['textfield',54]]),['Init',13,2]]);
 const sliderClass=klass('UiOneSettingSliderController',props([['header',39],['view',5],['hackCurrent',55],['textfield',54]]));
 gammaClass.add(0x20).writePointer(sliderClass);
 const viewClass=klass('SliderView',[...props([['uiObjectDesc',5],['changeSound',31],['descriptionImage',32],['textFormat',41]]),['GetUiObject',25,2]]);
 const barClass=klass('TabBar',[['items',65,5],['CreateItem',52,2],['UnsubscribeContent',29,2],['SubscribeContent',28,2],['Show',16,2]]);
 const presetClass=klass('Preset',[['name',6,5]]),arrayClass=klass('array');
 function array(n){const a=object(arrayClass);a.add(0x40).writePointer(alloc(128));a.add(0x48).writeU32(n);return a;}
 const self=object(settingsClass),gamma=object(gammaClass),bar=object(barClass),tabs=array(7),items=array(7),system=object(klass('System'));
 put(self,63,tag(tabs));put(self,57,tag(bar));put(bar,65,tag(items));put(gamma,5,tag(object(viewClass)));put(gamma,9,tag(system));put(self,9,tag(system));
 tabs.add(0x40).readPointer().writePointer(tag(object(presetClass)));
 const constants=alloc(80),code=alloc(PROFILE.createDataWords.length*4),fn=alloc(128),sig=alloc(16);
 constants.add(5*8).writePointer(type(klass('Element')));
 descriptor(settingsClass,20).add(0x50).writePointer(constants);
 PROFILE.createDataWords.forEach((w,i)=>code.add(i*4).writeU32(w));sig.writeU32(name('CreateData'));
 fn.add(0x40).writePointer(sig);fn.add(0x50).writePointer(constants);fn.add(0x58).writeU32(10);fn.add(0x60).writePointer(code);fn.add(0x68).writeU32(PROFILE.createDataWords.length);
 function vm(p){const v=alloc(32),args=alloc(8);args.writePointer(tag(p));v.add(0x18).writePointer(args);return v;}
 const callbacks={},menu=makeEnhancedSettingsMenu(PROFILE,(_f,_s,cb,c,m)=>{const key=c+'.'+m,previous=callbacks[key];callbacks[key]=(...args)=>{if(previous)previous(...args);cb(...args);};return {detach(){}};});
 menu.start(ptr(0),slot);
 const visit=()=>callbacks['UiSettingsController.CreateData'](vm(self),fn);
 const capture=()=>callbacks['UiOneSettingSliderGammaController.GetCurrentValue'](vm(gamma),fn);
 visit();const waiting=menu.status();capture();
 if(scenario==='body')code.add(8).writeU32(0);
 if(scenario==='tabs'){tabs.add(0x48).writeU32(8);items.add(0x48).writeU32(8);tabs.add(0x40).readPointer().add(56).writePointer(tag(object(presetClass)));}
 visit();const installed=menu.status(),replacement=fn.add(0x60).readPointer(),newConstants=fn.add(0x50).readPointer(),count=fn.add(0x68).readU32();
 if(scenario==='body'||scenario==='tabs')return {waiting,installed,untouched:replacement.equals(code)};
 const delta=count-PROFILE.createDataWords.length;
 const branches=PROFILE.createDataWords.slice(1).every((w,i)=>{
  const expected=[22,23,24,25,26].includes(w&255)?(w+delta*256)>>>0:w;
  return replacement.add((delta+1+i)*4).readU32()===expected;
 });
 const strings=[];let title=null,label=null,panningLabel=null;
 for(let i=10;i<fn.add(0x58).readU32();i++){const v=newConstants.add(i*8).readPointer();if(v.shr(48).toUInt32()===16){const p=untag(v),s=p.add(16).readPointer().readUtf8String(p.add(8).readU32());strings.push(s);if(s==='ENHANCED')title=v;if(s==='Zoom sensitivity')label=v;if(s==='Panning sensitivity')panningLabel=v;}}
 const slider=object(sliderClass),sliderView=object(viewClass);put(slider,39,label);put(slider,5,tag(sliderView));
 callbacks['UiOneSettingSliderController.GetCurrentValue'](vm(slider));
 const boundValue=slider.add(0x30+55*8).readFloat(),boundFormat=sliderView.add(0x30+41*8).readPointer().toString();
 const pan=object(sliderClass),panView=object(viewClass);put(pan,39,panningLabel);put(pan,5,tag(panView));
 const getter=alloc(128),getterCode=alloc(PROFILE.getterWords.length*4);
 PROFILE.getterWords.forEach((w,i)=>getterCode.add(i*4).writeU32(w));getter.add(0x60).writePointer(getterCode);getter.add(0x68).writeU32(PROFILE.getterWords.length);
 callbacks['UiOneSettingSliderController.GetCurrentValue'](vm(pan),getter);
 const panValue=pan.add(0x30+55*8).readFloat(),panStatus=menu.status().panningSensitivity;
 callbacks['UiOneSettingSliderController.GetCurrentValue'](vm(slider),getter);
 const separate=slider.add(0x30+55*8).readFloat()===50&&getter.add(0x60).readPointer().equals(getterCode)&&!panStatus.fault;

 if(scenario==='foreign'){
  replacement.writeU32(0);let rejected=false;try{menu.stop();}catch(_){rejected=true;}
  return {rejected,preserved:fn.add(0x60).readPointer().equals(replacement)};
 }
 // Model native construction completing: the VM now owns the eighth preset.
 const enhanced=object(presetClass);put(enhanced,6,title);tabs.add(0x40).readPointer().add(56).writePointer(tag(enhanced));tabs.add(0x48).writeU32(8);items.add(0x48).writeU32(8);
 visit();const repeat=menu.status(),restored=fn.add(0x60).readPointer().equals(code)&&fn.add(0x50).readPointer().equals(constants);
 // Model a recreated Settings controller using the same class method.
 callbacks['UiSettingsController.InitContent']();tabs.add(0x48).writeU32(7);items.add(0x48).writeU32(7);visit();const resetWait=menu.status();capture();visit();const recreated=menu.status();
 menu.stop();return {waiting,installed,branches,strings,boundValue,boundFormat,panValue,separate,repeat,restored,resetWait,recreated,stopped:menu.status(),finalRestore:fn.add(0x60).readPointer().equals(code)};
};
'''


class SettingsMenuTests(unittest.TestCase):
    def setUp(self):
        self.device = NativeDevice()
        self.pid = self.device.spawn(None)
        source = 'const PROFILE=' + (ROOT/'src/settings-profile.json').read_text() + ';\n'
        source += (ROOT/'src/map_zoom.js').read_text(encoding='utf-8')
        source += (ROOT/'src/map_panning.js').read_text(encoding='utf-8')
        source += (ROOT/'src/settings_menu.js').read_text(encoding='utf-8') + FIXTURE
        self.script = self.device.create_script(source)
        self.script.load()

    def tearDown(self):
        self.script.unload()
        self.device.kill(self.pid)

    def test_lifecycle_branch_relocation_and_utf8(self):
        r = self.script.exports_sync.run('normal')
        self.assertEqual(r['waiting']['status'], 'waiting-for-controls')
        self.assertIsNone(r['installed']['fault'], r)
        self.assertEqual(r['installed']['installations'], 1)
        self.assertTrue(r['branches'])
        self.assertIn('Pourquoi je vois ça?', r['strings'])
        self.assertIn('MAP', r['strings'])
        self.assertIn('Panning sensitivity', r['strings'])
        self.assertTrue(any('cinquante fois plus lent' in s and 'sauvegardés' in s for s in r['strings']))
        self.assertEqual(r['panValue'], 50)
        self.assertTrue(r['separate'])
        self.assertEqual(r['boundValue'], 50)
        self.assertEqual(r['boundFormat'], '0x1000000000002')
        self.assertTrue(any('réglage d’origine' in s and 'sauvegardés' in s for s in r['strings']))
        self.assertTrue(any('apparaît' in s and 'installé' in s for s in r['strings']))
        self.assertEqual(r['repeat']['installations'], 1)
        self.assertTrue(r['restored'])
        self.assertEqual(r['resetWait']['status'], 'waiting-for-controls')
        self.assertEqual(r['recreated']['installations'], 2)
        self.assertEqual(r['recreated']['arenaBytes'], r['installed']['arenaBytes'])
        self.assertTrue(r['finalRestore'])
        self.assertFalse(r['stopped']['running'])

    def test_changed_bytecode_is_left_untouched(self):
        r = self.script.exports_sync.run('body')
        self.assertTrue(r['untouched'])
        self.assertIn('bytecode mismatch', r['installed']['fault'])

    def test_foreign_eighth_tab_is_not_claimed(self):
        r = self.script.exports_sync.run('tabs')
        self.assertTrue(r['untouched'])
        self.assertIn('Foreign eighth', r['installed']['fault'])

    def test_foreign_bytecode_is_not_overwritten_during_restore(self):
        r = self.script.exports_sync.run('foreign')
        self.assertTrue(r['rejected'])
        self.assertTrue(r['preserved'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
