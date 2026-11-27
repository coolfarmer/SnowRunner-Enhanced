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
const CONFIG={profile:{ids:{a:0,b:4,c:8,d:12},guards:[{name:'vm_frame_push_entry',rva:0},{name:'vm_frame_push',rva:16}],stringPoolSlotRva:8}};
const SETTINGS_PROFILE={},NATIVE_SIGNATURES=[],ENHANCED_HOST={gameSha256:'test'};
const TRUCK_SEARCH_PROFILE={},TRUCK_SEARCH_SIGNATURES=[];
const VEHICLE_PROFILE={},VEHICLE_SIGNATURES=[],WINCH_PROFILE={},WINCH_SIGNATURES=[];
let searchStarts=0,searchEnabled=true,searchFailure=false;
const makeVehicleTruckSearch=(_profile,_entry,_pool,enabled)=>{searchEnabled=enabled;searchStarts++;if(searchFailure)throw Error('search failed');return {set:v=>{searchEnabled=v;},status:()=>({status:'ready',enabled:searchEnabled})};};
let reverseStarts=0,winchStarts=0,reverseFailure=false,winchFailure=false,winchFault=null;
const makeVehicleReverse=()=>{reverseStarts++;if(reverseFailure)throw Error('reverse failed');return {set:()=>{},status:()=>({unknown:0,automaticReverse:true})};};
const makeVehicleWinchRange=()=>{winchStarts++;if(winchFailure)throw Error('winch failed');return {status:()=>({status:winchFault?'error':'active',fault:winchFault})};};
let menuStarts=0,menuError=false,settingsSaves=[],reports=[],order=[],menuOptions;
const hookHudHintUpdates=()=>{};
const makeEnhancedSettingsMenu=(_profile,_attach,options)=>{menuOptions=options;return {start:()=>{order.push('menu');menuStarts++;if(menuError)throw Error('menu');},
status:()=>({enabled:true,running:true,status:'waiting-for-settings'})};};
let nativeReceiver=null;const fakeRecv=(_type,callback)=>{nativeReceiver=callback;};
let clockNow=10000;class TestDate extends Date {static now(){return clockNow;}}
let queued=[],interval=null,states=[],starts=0,stops=0,scanError=false,startError=false,faults=0,active=false;
const nativeProbe={describe:()=>({name:'SnowRunner.exe',sections:[]}),scan:()=>{if(scanError)throw Error('scan');return {};}};
const resolveNativeProfile=()=>({profile:CONFIG.profile,details:{relocatedGuards:30}});
const nativeAgent={start:()=>{order.push('agent');starts++;if(startError)throw Error('install');active=true;},
mode:()=>{},status:()=>({active,faults}),drain:()=>{},stop:()=>{stops++;active=false;}};
(function(Process,setTimeout,setInterval,clearInterval,send,Date,recv){
''' + (ROOT / 'src/feature_status.js').read_text() + (ROOT / 'src/native/bootstrap.js').read_text() + '''
})({mainModule:{base:data},id:123},fn=>queued.push(fn),fn=>{interval=fn;return 1;},()=>{interval=null;},m=>{if(m.enhancedSettings){settingsSaves.push(m.enhancedSettings);return;}reports.push(m.enhancedStatus);states.push(m.enhancedStatus.features.wheel_mouse.status);},TestDate,fakeRecv);
rpc.exports={
 vehicle:(enabled,reverseFail=false,winchFail=false)=>{ENHANCED_HOST.vehicle=enabled;CONFIG.features.vehicle=enabled;reverseFailure=reverseFail;winchFailure=winchFail;},
 winchfault:()=>{winchFault='Invalid registry';},
 vehiclecounts:()=>({reverseStarts,winchStarts}),
 searchstate:()=>({searchStarts,searchEnabled,vehicleEnabled:menuOptions.modules.vehicle}),
 searchfail:()=>{searchFailure=true;},
 health:()=>menuOptions.getFeatureStates(),
 native:(payload)=>nativeReceiver({payload}),
 select:modules=>{ENHANCED_HOST.modules=modules;},
 elapse:ms=>{clockNow+=ms;},
 set:(key,value)=>{if(key==='menu')menuError=value;if(key==='features')CONFIG.features=value;if(key==='scan')scanError=value;if(key==='start')startError=value;if(key==='faults')faults=value;if(key==='ids')data.writeU32(value);},
 tick:()=>{if(queued.length)queued.shift()();},
 monitor:()=>{if(interval)interval();},
 change:(key,value)=>menuOptions[{zoom:'onZoomChange',panning:'onPanningChange',north:'onNorthChange',search:'onSearchChange'}[key]](value),
 state:()=>({settingsSaves,states,starts,stops,active,menuStarts,order,mapEnabled:menuOptions?.modules.map,report:reports.at(-1),pending:queued.length,interval:interval!==null})};
'''
        self.script = self.device.create_script(source)
        self.script.load()
        self.api = self.script.exports_sync

    def tearDown(self):
        self.script.unload()
        self.device.kill(self.pid)

    def test_native_reply_drives_menu_and_ignores_other_processes(self):
        self.api.tick()
        self.api.select({'steering_wheel_improvements': True})
        self.assertEqual(self.api.health()['steering_wheel_improvements'], 'pending')
        self.api.native({'processId': 999, 'features': {'steering_wheel_improvements': {'status': 'active'}}})
        self.assertEqual(self.api.health()['steering_wheel_improvements'], 'pending')
        self.api.native({'processId': 123, 'features': {'steering_wheel_improvements': {'status': 'active'}}})
        self.assertEqual(self.api.health()['steering_wheel_improvements'], 'active')
        self.api.native({'processId': 123, 'features': {'steering_wheel_improvements': {'status': 'faulted'}}})
        self.assertEqual(self.api.health()['steering_wheel_improvements'], 'error')
        self.api.elapse(7000)
        self.assertEqual(self.api.health()['steering_wheel_improvements'], 'pending')

    def test_slider_saves_preserve_the_other_preference(self):
        self.api.tick()
        self.api.change('panning', 0)
        self.api.change('zoom', 75)
        self.api.change('north', True)
        self.api.change('panning', 50)
        self.assertEqual(self.api.state()['settingsSaves'], [
            dict(schemaVersion=5, truckStorageSearch=False, automaticReverse=True, zoomSensitivity=50, panningSensitivity=0, keepNorthUp=False),
            dict(schemaVersion=5, truckStorageSearch=False, automaticReverse=True, zoomSensitivity=75, panningSensitivity=0, keepNorthUp=False),
            dict(schemaVersion=5, truckStorageSearch=False, automaticReverse=True, zoomSensitivity=75, panningSensitivity=0, keepNorthUp=True),
            dict(schemaVersion=5, truckStorageSearch=False, automaticReverse=True, zoomSensitivity=75, panningSensitivity=50, keepNorthUp=True)])

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
        self.assertEqual(set(state['report']['features']), {'wheel_mouse', 'map', 'vehicle'})
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

    def test_vehicle_winch_is_owned_by_vehicle_and_ready_without_use(self):
        self.api.vehicle(True)
        self.api.tick()
        self.assertEqual(self.api.vehiclecounts(), dict(reverseStarts=1, winchStarts=1))
        self.assertEqual(self.api.health()['vehicle'], 'active')
        self.api.winchfault()
        self.api.monitor()
        self.assertEqual(self.api.health()['vehicle'], 'error')
        self.assertEqual(self.api.state()['report']['features']['vehicle']['status'], 'error')

    def test_vehicle_off_installs_neither_component(self):
        self.api.vehicle(False)
        self.api.tick()
        self.assertEqual(self.api.vehiclecounts(), dict(reverseStarts=0, winchStarts=0))

    def test_winch_install_failure_preserves_reverse_and_menu(self):
        self.api.vehicle(True, False, True)
        self.api.tick()
        report = self.api.state()['report']
        self.assertTrue(report['features']['vehicle']['automaticReverse'])
        self.assertEqual(report['features']['vehicle']['winch']['status'], 'error')
        self.assertTrue(report['components']['settings_menu']['running'])

    def test_reverse_failure_keeps_search_setting_accessible_and_persistent(self):
        self.api.vehicle(True, True, False)
        self.api.tick()
        self.assertEqual(self.api.searchstate(), dict(searchStarts=1,searchEnabled=False,vehicleEnabled=True))
        self.api.change('search', True)
        self.assertTrue(self.api.searchstate()['searchEnabled'])
        self.assertTrue(self.api.state()['settingsSaves'][-1]['truckStorageSearch'])
        self.assertTrue(self.api.state()['settingsSaves'][-1]['automaticReverse'])

    def test_search_failure_does_not_disable_reverse_or_winch(self):
        self.api.vehicle(True)
        self.api.searchfail()
        self.api.tick()
        feature = self.api.state()['report']['features']['vehicle']
        self.assertEqual(feature['truckSearch']['status'], 'error')
        self.assertEqual(feature['winch']['status'], 'active')
        self.assertTrue(feature['automaticReverse'])

    def test_reverse_failure_does_not_disable_winch(self):
        self.api.vehicle(True, True, False)
        self.api.tick()
        feature = self.api.state()['report']['features']['vehicle']
        self.assertEqual(feature['status'], 'error')
        self.assertEqual(feature['winch']['status'], 'active')


if __name__ == '__main__': unittest.main(verbosity=2)
