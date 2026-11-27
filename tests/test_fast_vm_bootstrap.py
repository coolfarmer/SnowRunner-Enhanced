"""Verify feature wiring and commit order, including a failed shared install."""
from pathlib import Path
import unittest
from native_host import NativeDevice

ROOT=Path(__file__).resolve().parents[1]
PRELUDE=r'''
const data=Memory.alloc(256);for(let i=0;i<4;i++)data.add(4*i).writeU32(11*(i+1));
const CONFIG={profile:{ids:{a:0,b:4,c:8,d:12},guards:[
    {name:'vm_frame_push_entry',rva:32},{name:'vm_frame_push',rva:64}],stringPoolSlotRva:96}};
const ENHANCED_HOST={wheelMouse:false,map:false,vehicle:false,general:false,modules:{}};
const GAME_TIME_PROFILE={},GAME_TIME_SIGNATURES=[];
const SETTINGS_PROFILE={},NATIVE_SIGNATURES=[],VEHICLE_PROFILE={},VEHICLE_SIGNATURES=[],
    WINCH_PROFILE={},WINCH_SIGNATURES=[],TRUCK_SEARCH_PROFILE={},TRUCK_SEARCH_SIGNATURES=[];
let order=[],registrations=[],stops=[],reports=[],queued=[],monitor=null,committed=false,failed=false,active=false;
function shared(address,pool,callback,cls,method,inside=false){
    if(committed)throw Error('Registration after commit');
    registrations.push({cls,inside,offset:address.sub(data).toInt32()});
    return {detach(){}};
}
function makeFastVmHooks(){return {attach:shared,
    commit(){order.push('commit');committed=true;if(failed)throw Error('gate failed');},
    status(){return {committed,fault:failed?'gate failed':null};}};}
const hookHudHintUpdates=()=>{throw Error('Legacy VM hook used');};
const nativeProbe={describe:()=>({name:'SnowRunner.exe',sections:[]}),scan:()=>({})};
const resolveNativeProfile=()=>({profile:CONFIG.profile,details:{}});
const nativeAgent={start(attach){order.push('agent');active=true;
    if(CONFIG.features.map||CONFIG.features.wheel_mouse)attach(data.add(32),data.add(96),()=>{},'input','Update');},
    mode(){},status:()=>({active,faults:0}),drain(){},stop(){stops.push('agent');active=false;}};
function makeEnhancedSettingsMenu(profile,attach,options){return {
    start(){order.push('menu');attach(data.add(32),data.add(96),()=>{},'menu','Update');
        if(options.modules.map)attach(data.add(32),data.add(96),()=>{},'map','Zoom');
        if(attach.commit)throw Error('Menu must not commit a shared dispatcher');},
    status:()=>({running:true}),stop(){stops.push('menu');}};}
const makeVehicleReverse=()=>({set(){},status:()=>({automaticReverse:true})});
const makeVehicleWinchRange=()=>({status:()=>({status:'ready'})});
function makeVehicleTruckSearch(profile,entry,pool,enabled,attach){
    order.push('search');attach(entry,pool,()=>{},'search','CreateData',true);
    return {keepAlive:[{detach(){stops.push('search');}}],status:()=>({status:'ready'})};
}
function makeGameTimeFreeze(profile,vmProfile,attach){order.push('clock');attach(data.add(32),data.add(96),()=>{},'clock','CreateSinglePlayer');return {set(){},status:()=>({status:'ready'}),stop(){stops.push('clock');}};}
function startFunctionsRepeat(profile,attach){order.push('repeat');
    attach(data.add(64),data.add(96),()=>{},'general','Update',true);
    return {status:()=> 'ready',stop(){stops.push('repeat');}};}
(function(Process,setTimeout,setInterval,send){
'''
POSTLUDE=r'''
rpc.exports={run(mask,fail=false){
    ENHANCED_HOST.wheelMouse=CONFIG.features.wheel_mouse=!!(mask&1);
    ENHANCED_HOST.map=CONFIG.features.map=!!(mask&4);
    ENHANCED_HOST.vehicle=CONFIG.features.vehicle=!!(mask&16);
    ENHANCED_HOST.general=!!(mask&8);
    ENHANCED_HOST.modules={wheel_mouse:!!(mask&1),map:!!(mask&4),vehicle:!!(mask&16),general_improvements:!!(mask&8)};
    failed=fail;queued.shift()();
    return {order,registrations,stops,report:reports.at(-1)};
}};
})({mainModule:{base:data},id:123},f=>queued.push(f),f=>{monitor=f;return 1;},m=>reports.push(m.enhancedStatus));
'''


class FastVmBootstrapTests(unittest.TestCase):
    def run_case(self,mask,fail=False):
        device=NativeDevice();pid=device.spawn(None)
        source=PRELUDE+(ROOT/'src/feature_status.js').read_text()+(ROOT/'src/native/bootstrap.js').read_text()+POSTLUDE
        script=device.create_script(source);script.load()
        try:return script.exports_sync.run(mask,fail)
        finally:script.unload();device.kill(pid)

    def test_optional_groups_share_dispatch_and_commit_after_all_registrations(self):
        for mask in range(64):
            with self.subTest(mask=mask):
                result=self.run_case(mask)
                self.assertEqual(result['order'][-1],'commit')
                self.assertEqual(result['order'].count('commit'),1)
                registrations={r['cls']:r for r in result['registrations']}
                self.assertIn('menu',registrations)
                for name,bit in (('map',4),('search',16),('general',8),('clock',8)):
                    self.assertEqual(name in registrations,bool(mask&bit))
                for name,offset in (('search',72),('general',64)):
                    if name in registrations:
                        self.assertTrue(registrations[name]['inside'])
                        self.assertEqual(registrations[name]['offset'],offset)
                self.assertEqual(result['stops'],[])

    def test_install_failure_stops_owners_and_reports_unavailable_search(self):
        result=self.run_case(29,True)
        self.assertEqual(set(result['stops']),{'agent','menu','repeat','search','clock'})
        report=result['report']
        self.assertEqual(report['features']['map']['status'],'error')
        self.assertEqual(report['features']['vehicle']['truckSearch']['status'],'error')
        self.assertEqual(report['components']['settings_menu']['status'],'error')
        self.assertIn('gate failed',report['components']['functions_repeat']['status'])


if __name__=='__main__':unittest.main()
