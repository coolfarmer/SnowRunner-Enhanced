rpc.exports.lifecycle=scenario=>{
    const keep=[],alloc=n=>{const p=Memory.alloc(n);p.writeByteArray(new Uint8Array(n));keep.push(p);return p;};
    const types=new Map(),fields=new Map(),methods=new Map(),arrays=new Map(),texts=new Map(),receivers=new Map();
    const object=n=>{const p=alloc(256);p.writeU32(1);types.set(String(p),n);return p;};
    const key=(p,n)=>p+':'+n,tag=p=>p.or('0x20000000000000'),untag=p=>p.and('0xffffffffffff');
    const text=s=>{const p=alloc(8);texts.set(String(p),s);return p.or('0x10000000000000');};
    const field=(p,n)=>{const k=key(p,n);if(!fields.has(k))fields.set(k,alloc(8));return fields.get(k);};
    const put=(p,n,x)=>field(p,n).writePointer(x);
    const float=x=>{const p=alloc(8);p.writeFloat(x);p.add(6).writeU16(3);return p.readPointer();};
    const boolean=x=>ptr(x?'0x2000000000001':'0x2000000000000');
    const array=items=>{const p=object('array');arrays.set(String(p),items);return p;};
    function method(p,n,words,k=0){
        const fn=alloc(128),code=alloc(Math.max(4,words.length*4)),constants=alloc(Math.max(8,k*8));
        words.forEach((w,i)=>code.add(i*4).writeU32(w));fn.add(0x60).writePointer(code);fn.add(0x68).writeU32(words.length);
        fn.add(0x50).writePointer(constants);fn.add(0x58).writeU32(k);methods.set(key(p,n),{fn,code,constants});return fn;
    }
    const global=object('__global');
    const view=object('UiTruckWarehouseView'),controller=object('UiTruckWarehouseController'),input=object('UiTextInput');
    const ui=object('UiObject'),panel=object('UiObject'),content=object('UiObject'),list=object('UiObject'),adapter=object('UiListAdapter');
    const screen=object('SslUiInputScreen'),listScreen=object('SslUiInputScreen'),otherAdapter=object('UiListAdapter'),otherScreen=object('SslUiInputScreen');
    const data=object('UiTruckWarehouseViewData'),images=object('dictionary'),holder=object('Holder'),row=object('UiTruckWarehouseViewLir');
    put(view,'uiObject',tag(ui));put(view,'trucksList',tag(adapter));put(view,'viewData',tag(data));put(view,'truckImages',tag(images));
    put(view,'currentTruckType',ptr(1));put(view,'isEnabled',boolean(true));put(adapter,'uiInputScreen',tag(listScreen));put(adapter,'list',tag(list));
    put(controller,'inputScreen',tag(screen));put(controller,'currentLocale',text('fr'));put(holder,'owner',tag(row));
    put(list,'y',float(213));put(list,'height',float(610));put(input,'text',text(''));put(input,'defaultText',text(''));
    put(input,'visible',boolean(true));put(input,'focus',boolean(false));
    const trucks=[['Azov 64131','azov_64131',4],['Aramatsu Forester 1910','mod_forester',4],['UI_OPAQUE_NAME','tuz_420',2]].map(([label,id,kind])=>{
        const p=object('Truck');put(p,'truckUiName',text(label));put(p,'truckName',text(id));put(p,'truckType',ptr(kind));return tag(p);
    });
    put(data,'truckDataList',tag(array(trucks)));const imageKeys=array([text('a')]),imageValues=array([tag(holder)]);
    const update=method(view,'UpdateTruckList',PROFILE.warehouseWords.UpdateTruckList,2);
    const filter=method(view,'GetTruckListByType',PROFILE.warehouseWords.GetTruckListByType,1);
    const terminate=method(view,'TerminateContent',PROFILE.warehouseWords.TerminateContent,8);
    method(view,'SubscribeMouseScheme',[],2);
    const activate=method(view,'ActivateTruckList',PROFILE.warehouseWords.ActivateTruckList,1);
    const device=method(adapter,'SetForDevice',PROFILE.deviceWords),hover=method(adapter,'HandleOnItemHovered',PROFILE.hoverWords);
    const press=method(screen,'Press',PROFILE.pressWords);
    methods.set(key(listScreen,'Press'),methods.get(key(screen,'Press')));
    const ids={GetLocalizationString:788,viewData:53,trucksList:51,UpdateTruckList:84,ActivateTruckList:87,list:13,OnFocusIn:7,isEnabled:56,focus:29,visible:24,text:86,defaultText:85,Release:8};
    let dropped=0,cleared=0;
    const v={untag,tag,receiver:vm=>receivers.get(String(vm)),className:p=>types.get(String(p)),
        member:(p,n,kind)=>({id:ids[n],kind,desc:methods.get(key(p,n))?.fn}),prop:field,get:(p,n)=>untag(field(p,n).readPointer()),
        read:(p,n)=>field(p,n).readPointer(),write:(p,n,x)=>put(p,n,x),str:x=>texts.get(String(untag(x)))||'',text,float,bool:boolean,
        integer:x=>ptr(x).or('0x1000000000000'),array:p=>arrays.get(String(p)),native:(_p,n,_vm,args)=>n==='GetLocalizationString'?
            (v.str(args[0])==='UI_OPAQUE_NAME'?text('TUZ 420 Tatarin'):args[0]):tag(n==='Keys'?imageKeys:imageValues),
        child:(_p,n)=>({panel,content,list})[n],scoped:cb=>cb(),drop:()=>dropped++};
    const native=alloc(256);native.add(0x58+24).writeU32(10);
    const gfx=alloc(48);gfx.add(32).writeDouble(1);
    const g={object:()=>native,get:()=>gfx,set:()=>{},invoke:()=>gfx,clear:()=>cleared++};
    const callbacks={},nativeHooks={},base=alloc(64),interceptor={attach:(p,cb)=>{nativeHooks[p.sub(base).toInt32()]=cb;return {detach(){}};},flush(){}};
    const create=(function(makeTruckSearchVm,makeTruckSearchGfx,Process,Interceptor){
        PRODUCTION_SOURCE
        return makeVehicleTruckSearch;
    })(()=>v,()=>g,{mainModule:{base}},interceptor);
    const p={...PROFILE,setNameRva:16,focusInRva:32,focusOutRva:48};
    const component=create(p,ptr(0),ptr(0),true,(_e,_s,cb,c,n,interior)=>{
        if(interior!==true)throw Error('Search needs the initialized callee argument stack');
        callbacks[c+'.'+n]=cb;return {detach(){}};
    });
    const vm=self=>{const p=alloc(96);p.add(0x48).writePointer(global);receivers.set(String(p),self);return p;};
    const fire=(c,n,self,fn)=>callbacks[c+'.'+n](vm(self),fn);
    const words=fn=>Array.from({length:fn.add(0x68).readU32()},(_,i)=>fn.add(0x60).readPointer().add(i*4).readU32());
    // Execute the emitted guard prefix with changing receivers/focus. Reaching
    // the original first word means normal game handling is still available.
    let guardDisplayReads=0;
    function blocked(fn,self,original){
        const program=words(fn),end=program.length-original.length,stack=[];
        for(let pc=0;pc<end;){
            const word=program[pc++],op=word&255,arg=(word>>>8)-0x800000;
            if(op===7)stack.push(tag(self));
            else if(op===6)stack.push(fn.add(0x50).readPointer().add(arg*8).readPointer());
            else if(op===48){const b=stack.pop(),a=stack.pop();stack.push(boolean(a.equals(b)));}
            else if(op===10){guardDisplayReads++;stack.push(field(untag(stack.pop()),Object.keys(ids).find(n=>ids[n]===arg)).readPointer());}
            else if(op===22){if(stack.pop().and('0xffffffffffff').isNull())pc=arg;}
            else if(op===5)stack.push(boolean(true));
            else if(op===18||op===19)return true;
            else throw Error('Unexpected guard opcode '+op);
        }
        return false;
    }
    if(scenario==='changed')update.add(0x60).readPointer().writeU32(0);
    fire('UiTruckWarehouseController','CreateData',controller);
    fire('UiTruckWarehouseView','UpdateTruckList',view,update);
    if(scenario==='changed')return component.status();
    // Interpret the added event binding with actual constant and receiver
    // resolution. Native focus can reach the list after the slot lost focus.
    const listFocusHandlers=[];
    function applyListFocusEvent(fn,remove=false){
        const program=words(fn),constants=fn.add(0x50).readPointer();
        const at=program.findIndex(w=>(w&255)===(remove?17:16)&&constants.add(((w>>>8)-0x800000)*8).readPointer().and('0xffffffffffff').toInt32()===7);
        if(at<0)return;
        const start=at-(remove?4:9),stack=[];
        for(let pc=start;pc<=at;pc++){
            const w=program[pc],op=w&255,arg=(w>>>8)-0x800000;
            if(op===7)stack.push(view);
            else if(op===10)stack.push(v.get(stack.pop(),Object.keys(ids).find(n=>ids[n]===arg)));
            else if(op===4)stack.push(arg);
            else if(op===6)stack.push(constants.add(arg*8).readPointer());
            else if(op===20){
                const owner=stack.pop(),methodId=stack.pop(),argc=stack.pop();
                stack.pop();const bound=stack.pop();
                if(argc!==0||bound!==0||!owner.equals(view)||methodId!==87)throw Error('Invalid focus delegate');
                stack.push({owner,methodId});
            }else if(op===16){
                const handler=stack.pop(),target=stack.pop();
                if(!target.equals(list))throw Error('Wrong focus target');
                listFocusHandlers.push(handler);
            }else if(op===17){
                const target=stack.pop(),owner=stack.pop();
                if(!target.equals(list)||!owner.equals(view))throw Error('Wrong unsubscribe target');
                listFocusHandlers.length=0;
            }else throw Error('Unexpected focus event opcode '+op);
        }
    }
    applyListFocusEvent(update);
    nativeHooks[16].onEnter([ptr(0),input]);
    put(input,'text',text(scenario==='localized'?'Tatarin':'forester'));
    fire('UiTruckWarehouseView','GetTruckListByType',view,filter);
    const selected=words(filter).flatMap((w,i,a)=>(w&255)===4&&a[i+1]===0x80000007&&a[i+2]===0x8000350a?[(w>>>8)-0x800000]:[]);
    const releaseBeforeArray=(words(filter)[3]&255)===13;
    // The first CLIK focus event can precede the SSL getter's visible state.
    // The guard must protect text entry even while that getter is still false.
    const focusOwner=alloc(128);focusOwner.add(0x58).writePointer(native);
    const focusContext={};nativeHooks[32].onEnter.call(focusContext,[focusOwner]);
    nativeHooks[32].onLeave.call(focusContext);
    const firstHoverBlocked=blocked(activate,view,PROFILE.warehouseWords.ActivateTruckList);
    const unrelatedActivation=!blocked(activate,otherAdapter,PROFILE.warehouseWords.ActivateTruckList);
    const hoverBlocked=blocked(hover,adapter,PROFILE.hoverWords);
    const unrelatedHover=!blocked(hover,otherAdapter,PROFILE.hoverWords);
    const deviceBlocked=blocked(device,adapter,PROFILE.deviceWords);
    const keysBlocked=blocked(press,screen,PROFILE.pressWords)&&blocked(press,listScreen,PROFILE.pressWords);
    const unrelatedKeys=!blocked(press,otherScreen,PROFILE.pressWords);
    const outContext={};nativeHooks[48].onEnter.call(outContext,[focusOwner]);nativeHooks[48].onLeave.call(outContext);
    const idleGuards={};
    for(const [name,fn,self,original] of [
        ['activation',activate,view,PROFILE.warehouseWords.ActivateTruckList],
        ['device',device,adapter,PROFILE.deviceWords],
        ['hover',hover,adapter,PROFILE.hoverWords],
        ['controllerPress',press,screen,PROFILE.pressWords],
        ['listPress',press,listScreen,PROFILE.pressWords]]){
        guardDisplayReads=0;
        const allowed=!blocked(fn,self,original);
        idleGuards[name]={allowed,displayReads:guardDisplayReads};
    }
    const unfocusedActivation=idleGuards.activation.allowed;
    const controllerReentries=Array.from({length:3},()=>listFocusHandlers.some(h=>
        !blocked(activate,h.owner,PROFILE.warehouseWords.ActivateTruckList)));
    fire('UiTruckWarehouseView','Hide',view);const queryCleared=v.str(v.read(input,'text'))==='';
    const unfocusedHover=!blocked(hover,adapter,PROFILE.hoverWords);
    component.set(false);fire('UiTruckWarehouseView','UpdateTruckList',view,update);
    const off=field(input,'visible').readU8()===0&&field(list,'y').readFloat()===213&&field(list,'height').readFloat()===610;
    component.set(true);fire('UiTruckWarehouseView','UpdateTruckList',view,update);
    const on=field(input,'visible').readU8()===1&&field(list,'y').readFloat()===269&&component.status().installations===1;
    fire('UiTruckWarehouseView','TerminateContent',view,terminate);
    applyListFocusEvent(terminate,true);
    const focusListenerRemoved=listFocusHandlers.length===0;
    fire('NavigationPanelController','Update',controller);
    return {selected,firstHoverBlocked,unrelatedActivation,unfocusedActivation,idleGuards,controllerReentries,focusListenerRemoved,releaseBeforeArray,hoverBlocked,unrelatedHover,unfocusedHover,deviceBlocked,keysBlocked,unrelatedKeys,queryCleared,off,on,dropped,cleared,
        originalListIntact:trucks.length===3,retainedListeners:component.keepAlive.length,status:component.status()};
};
