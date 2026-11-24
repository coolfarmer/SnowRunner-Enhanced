"""Native startup state transitions with a deterministic timer and agent seam."""
from pathlib import Path
import unittest
from native_host import NativeDevice

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / 'build/native/native-harness.exe').exists(), 'Build native host first')
class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.device = NativeDevice()
        self.pid = self.device.spawn(None)
        source = '''
const data=Memory.alloc(16);
for(let i=0;i<4;i++) data.add(4*i).writeU32(11*(i+1));
const CONFIG={profile:{ids:{a:0,b:4,c:8,d:12},guards:[{name:'vm_frame_push_entry',rva:0}],stringPoolSlotRva:8}};
const SETTINGS_PROFILE={},NATIVE_SIGNATURES=[],ENHANCED_HOST={gameSha256:'test'};
let menuStarts=0,menuError=false,settingsSaves=[],reports=[],order=[],menuOptions;
const hookHudHintUpdates=()=>{};
const makeEnhancedSettingsMenu=(_profile,_attach,options)=>{menuOptions=options;return {start:()=>{order.push('menu');menuStarts++;if(menuError)throw Error('menu');},
status:()=>({enabled:true,running:true,status:'waiting-for-settings'})};};
let queued=[],interval=null,states=[],starts=0,stops=0,scanError=false,startError=false,faults=0,active=false;
const nativeProbe={describe:()=>({name:'SnowRunner.exe',sections:[]}),scan:()=>{if(scanError)throw Error('scan');return {};}};
const resolveNativeProfile=()=>({profile:CONFIG.profile,details:{relocatedGuards:30}});
const nativeAgent={start:()=>{order.push('agent');starts++;if(startError)throw Error('install');active=true;},
mode:()=>{},status:()=>({active,faults}),drain:()=>{},stop:()=>{stops++;active=false;}};
(function(Process,setTimeout,setInterval,clearInterval,send){
''' + (ROOT / 'src/native/bootstrap.js').read_text() + '''
})({mainModule:{base:data},id:123},fn=>queued.push(fn),fn=>{interval=fn;return 1;},()=>{interval=null;},m=>{if(m.enhancedSettings){settingsSaves.push(m.enhancedSettings);return;}reports.push(m.enhancedStatus);states.push(m.enhancedStatus.features.wheel_mouse.status);});
rpc.exports={
 set:(key,value)=>{if(key==='menu')menuError=value;if(key==='features')CONFIG.features=value;if(key==='scan')scanError=value;if(key==='start')startError=value;if(key==='faults')faults=value;if(key==='ids')data.writeU32(value);},
 tick:()=>{if(queued.length)queued.shift()();},
 monitor:()=>{if(interval)interval();},
 change:(key,value)=>menuOptions[{zoom:'onZoomChange',panning:'onPanningChange',north:'onNorthChange'}[key]](value),
 state:()=>({settingsSaves,states,starts,stops,active,menuStarts,order,mapEnabled:menuOptions?.mapEnabled,report:reports.at(-1),pending:queued.length,interval:interval!==null})};
'''
        self.script = self.device.create_script(source)
        self.script.load()
        self.api = self.script.exports_sync

    def tearDown(self):
        self.script.unload()
        self.device.kill(self.pid)

    def test_slider_saves_preserve_the_other_preference(self):
        self.api.tick()
        self.api.change('panning', 0)
        self.api.change('zoom', 75)
        self.api.change('north', True)
        self.api.change('panning', 50)
        self.assertEqual(self.api.state()['settingsSaves'], [
            dict(schemaVersion=3, zoomSensitivity=50, panningSensitivity=0, keepNorthUp=False),
            dict(schemaVersion=3, zoomSensitivity=75, panningSensitivity=0, keepNorthUp=False),
            dict(schemaVersion=3, zoomSensitivity=75, panningSensitivity=0, keepNorthUp=True),
            dict(schemaVersion=3, zoomSensitivity=75, panningSensitivity=50, keepNorthUp=True)])

    def test_discovery_retries_without_hooks_and_stops(self):
        self.api.set('scan', True)
        for _ in range(30): self.api.tick()
        state = self.api.state()
        self.assertEqual(state['states'][-1], 'incompatible')
        self.assertEqual(state['starts'], 0)
        self.assertEqual(state['pending'], 0)

    def test_initializing_categories_wait_without_installing(self):
        self.api.set('ids', 0); self.api.tick()
        self.assertEqual(self.api.state()['starts'], 0)
        self.api.set('ids', 11); self.api.tick()
        self.assertTrue(self.api.state()['active'])
        self.assertEqual(self.api.state()['starts'], 1)

    def test_installation_failure_does_not_retry(self):
        self.api.set('start', True); self.api.tick()
        state = self.api.state()
        self.assertEqual(state['states'][-1], 'error')
        self.assertEqual(state['starts'], 1)
        self.assertEqual(state['pending'], 0)

    def test_runtime_fault_stops_correction(self):
        self.api.tick(); self.api.set('faults', 1); self.api.monitor()
        state = self.api.state()
        self.assertEqual(state['states'][-1], 'faulted')
        self.assertFalse(state['active'])
        self.assertTrue(state['interval'])
        self.assertEqual(state['stops'], 1)
        self.assertTrue(state['report']['components']['settings_menu']['running'])

    def test_core_menu_runs_with_every_enhancement_disabled(self):
        self.api.set('features', {'wheel_mouse': False, 'map': False})
        self.api.set('ids', 0)
        self.api.tick()
        state = self.api.state()
        self.assertEqual(state['starts'], 0)
        self.assertEqual(state['menuStarts'], 1)
        self.assertFalse(state['mapEnabled'])
        self.assertEqual(set(state['report']['features']), {'wheel_mouse', 'map'})
        self.assertTrue(all(f['status'] == 'disabled' for f in state['report']['features'].values()))
        self.assertTrue(state['report']['components']['settings_menu']['running'])

    def test_optional_hooks_validate_before_shared_entry_is_hooked(self):
        self.api.tick()
        self.assertEqual(self.api.state()['order'], ['agent', 'menu'])

    def test_menu_failure_does_not_stop_optional_corrections(self):
        self.api.set('menu', True); self.api.tick()
        state = self.api.state()
        self.assertTrue(state['active'])
        self.assertEqual(state['report']['components']['settings_menu']['status'], 'error')

    def test_optional_install_failure_does_not_stop_menu(self):
        self.api.set('start', True); self.api.tick()
        self.assertTrue(self.api.state()['report']['components']['settings_menu']['running'])


if __name__ == '__main__': unittest.main(verbosity=2)
