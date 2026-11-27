'use strict';

// Stage registrations before changing any entry bytes, so each feature keeps
// its existing compatibility checks. One native gate per VM execution phase.
function makeFastVmHooks(profile, hostModule = Process.getModuleByName('SnowRunnerEnhanced.asi'), base = Process.mainModule.base) {
    const entryGuard=profile.guards.find(g=>g.name==='vm_frame_push_entry');
    const interiorGuard=profile.guards.find(g=>g.name==='vm_frame_push');
    // The +8 observer used by Truck Storage follows two loads into RCX/RAX.
    // Execute these exact loads between the two observer phases: a callback
    // may mutate the memory they read, so moving either observer is unsafe.
    if(!entryGuard || !interiorGuard || !interiorGuard.hex.startsWith('488b4950488b4118'))
        throw Error('Unsupported VM observer phases');
    const entryAddress=base.add(entryGuard.rva),interiorAddress=base.add(interiorGuard.rva);
    const entry=makeFastMenuHooks({address:entryAddress,hex:entryGuard.hex},hostModule);
    const interior=makeFastMenuHooks({address:interiorAddress,hex:interiorGuard.hex,interior:true,splitOffset:8},hostModule);
    let committed=false,fault=null;
    function attach(address,pool,callback,cls='NavigationPanelController',method='Update',inside=false){
        if(committed)throw Error('VM registration closed');
        if(!inside)return entry(address,pool,callback,cls,method,false);
        if(!address.equals(interiorAddress) && !address.equals(interiorAddress.add(8)))
            throw Error('Unknown interior VM observer');
        return interior(interiorAddress,pool,callback,cls,method,true,address.equals(interiorAddress)?0:1);
    }
    function disable(){entry.disable();interior.disable();}
    return {
        attach,disable,
        commit(){
            if(committed)throw Error('VM dispatcher already committed');
            committed=true;
            try{entry.commit();interior.commit();}
            catch(error){fault=String(error);disable();throw error;}
        },
        status(){return {mode:'fast-shared',committed,fault,entry:entry.status(),interior:interior.status()};},
        releaseForTest(){entry.releaseForTest?.();interior.releaseForTest?.();}
    };
}
