'use strict';

const truckSearchWord=(op,arg=0)=>(((arg+0x800000)*256)+op)>>>0;
function truckSearchMatches(query,label,internal) {
    const normalize=s=>String(s).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/_/g,' ');
    const hay=normalize(label+' '+internal);
    return normalize(query).trim().split(/\s+/).every(word=>hay.includes(word));
}
function truckSearchShift(words,offset){
    return words.map(w=>[22,23,24,25,26].includes(w&255)?truckSearchWord(w&255,(w>>>8)-0x800000+offset):w);
}

// One warehouse view owns one native CLIK TextInput. Only the game thread
// touches its objects; the settings callback merely updates a preference.
function makeVehicleTruckSearch(profile,entry,poolSlot,enabled=true,attach=hookHudHintUpdates) {
    const v=makeTruckSearchVm(profile,poolSlot),g=makeTruckSearchGfx(profile),W=truckSearchWord;
    const hooks=[],patches=new Map();let current=null,controller=null,creating=false,fault=null,refreshes=0,installations=0;
    const base=Process.mainModule.base;
    const L=i=>[W(7,i)],C=i=>[W(6,i)];
    const call=(r,id,args=[])=>[W(1,1),...args.slice().reverse().flat(),...r,W(4,args.length),W(13,id)];
    const stmt=ws=>[...ws,W(2)];
    function storage(fn,expected){
        const key=String(fn);if(patches.has(key))return patches.get(key);
        const code=fn.add(0x60).readPointer(),count=fn.add(0x68).readU32(),k=fn.add(0x58).readU32();
        if(count!==expected.length||!expected.every((w,i)=>code.add(i*4).readU32()===w)||k>128)throw Error('Unsupported Truck Storage bytecode');
        const s={fn,original:code,count,constants:fn.add(0x50).readPointer(),k,
            code:Memory.alloc(4*110000),values:Memory.alloc(8*5200),active:false};
        patches.set(key,s);return s;
    }
    function restore(s){
        if(!s.active)return;
        if(!s.fn.add(0x60).readPointer().equals(s.code)||!s.fn.add(0x50).readPointer().equals(s.values))throw Error('Foreign Truck Storage patch');
        s.fn.add(0x60).writePointer(s.original);s.fn.add(0x68).writeU32(s.count);
        s.fn.add(0x50).writePointer(s.constants);s.fn.add(0x58).writeU32(s.k);s.active=false;
    }
    function apply(s,words,extra=[]){
        if(words.length>110000||s.k+extra.length>5200)throw Error('Search program limit');
        restore(s);if(s.k)Memory.copy(s.values,s.constants,s.k*8);
        extra.forEach((x,i)=>s.values.add((s.k+i)*8).writePointer(x));
        words.forEach((w,i)=>s.code.add(i*4).writeU32(w));
        s.fn.add(0x50).writePointer(s.values);s.fn.add(0x58).writeU32(s.k+extra.length);
        s.fn.add(0x60).writePointer(s.code);s.fn.add(0x68).writeU32(words.length);s.active=true;
    }
    function method(p,n){return v.member(p,n,2).desc;}
    function check(p,n,id,kind){if(v.member(p,n,kind).id!==id)throw Error('Changed search member '+n);}
    function isCurrent(vm){return current&&v.receiver(vm).equals(current.view);}
    function placeholder(vm){
        const s=current,desired=v.str(v.read(s.input,'text',vm)).length?'':s.placeholder;
        if(v.str(v.read(s.input,'defaultText',vm))!==desired)v.write(s.input,'defaultText',v.text(desired),vm);
    }
    function layout(vm,on){
        const s=current;if(!s?.input)return;
        if(!on){v.write(s.input,'focus',v.bool(false),vm);v.write(s.input,'text',v.text(''),vm);}
        v.write(s.input,'visible',v.bool(on),vm);
        v.write(s.list,'y',v.float(s.originalY+(on?56:0)),vm);
        v.write(s.list,'height',v.float(s.originalHeight-(on?56:0)),vm);
        placeholder(vm);
    }
    function tint(active){
        const s=current;if(!s)return;
        // Use native CLIK focus events as the authority for guard state.
        s.focused=active;
        for(const slot of s.focusSlots||[])slot.writePointer(v.bool(active));
        if(!s.border||s.border.active===active)return;
        g.set(s.border.transform,'colorTransform',active?s.border.focused:s.border.normal);s.border.active=active;
    }
    function configure(vm){
        const s=current,p=s.input;if(s.configured)return;
        for(const [n,id] of [['focus',29],['visible',24],['text',86],['defaultText',85]])check(p,n,id,4);
        s.list=v.child(v.child(s.panel,'content',vm),'list',vm);
        // Preserve the installed layout rather than assuming a screen resolution.
        function number(n){const val=v.read(s.list,n,vm),tmp=Memory.alloc(8);tmp.writePointer(val);return tmp.readFloat();}
        s.originalY=number('y');s.originalHeight=number('height');
        for(const [n,x] of [['x',7],['y',442],['width',366],['height',48]])v.write(p,n,v.float(x),vm);
        v.write(p,'maxChars',v.integer(80),vm);v.write(p,'editable',v.bool(true),vm);
        const native=g.object(p),root=native.add(0x58);s.native=native;
        if((root.add(24).readU32()&0x8f)!==10)throw Error('Invalid search display object');
        g.set(root,'actAsButton',true);
        const domain=g.get(g.get(root,'loaderInfo'),'applicationDomain');
        const textEx=g.invoke(domain,'getDefinition',['scaleform.gfx.TextFieldEx']);
        for(const n of ['textField','defaultTextField'])g.invoke(textEx,'setVerticalAlign',[g.get(root,n),'center']);
        const transform=g.get(g.get(root,'bg'),'transform');
        const normal=g.get(transform,'colorTransform'),yellow=g.get(transform,'colorTransform');
        for(const [n,factor] of [['redMultiplier',210/128],['greenMultiplier',214/128],['blueMultiplier',108/128]])
            g.set(yellow,n,g.get(normal,n).add(32).readDouble()*factor);
        s.border={transform,normal,focused:yellow,active:null};tint(false);
        installFocusGuards();
        s.configured=true;layout(vm,enabled);installations++;
    }
    function open(vm){
        const view=v.receiver(vm);
        if(current&&!current.view.equals(view))throw Error('Overlapping warehouse views');
        if(current)return;
        check(view,'viewData',53,5);check(view,'trucksList',51,5);check(view,'UpdateTruckList',84,2);
        const ui=v.get(view,'uiObject'),panel=v.child(ui,'panel',vm);
        const locale=controller?v.str(v.prop(controller,'currentLocale').readPointer()):'';
        current={view,panel,ui,input:null,configured:false,locale,names:new Map(),placeholder:/^(fr|french)/i.test(locale)?'Rechercher un camion...':'Search trucks...'};
    }
    function update(vm,fn){
        retire(vm);
        const saved=storage(fn,profile.warehouseWords.UpdateTruckList);restore(saved);
        if(!enabled&&!current)return;
        open(vm);
        const s=current;
        const locale=controller?v.str(v.prop(controller,'currentLocale').readPointer()):'';
        if(locale!==s.locale){s.locale=locale;s.names.clear();s.placeholder=/^(fr|french)/i.test(locale)?'Rechercher un camion...':'Search trucks...';}
        if(!enabled){layout(vm,false);return;}
        const k=saved.k,extra=[];let prefix,inputIndex=k;
        if(!s.input){
            creating=true;
            extra.push(v.text('UiTextInput'),v.tag(s.panel),v.text('enhancedTruckSearch'),v.text('modBrowserHeaderInput'));
            prefix=[W(1,7),...call([W(8)],884,[C(k),C(k+2)]),W(59,-7),W(2)];
            prefix.push(...stmt(call(L(-7),47,[C(k+3)])),...stmt(call(L(-7),63,[C(k+2)])),...stmt(call(L(-7),45,[C(k+1)])));
            const mouse=method(s.view,'SubscribeMouseScheme').add(0x50).readPointer();
            extra.push(mouse.readPointer(),mouse.add(8).readPointer(),v.integer(80));
            inputIndex=k+7;extra.push(ptr(0));s.captureSlot=saved.values.add(inputIndex*8);
            prefix.push(...L(-7),W(4,0),W(6,k+4),W(4,0),W(4,84),W(7,0),W(20,k+5),W(16,k+6),W(2));
            // Retain the native control separately; local -7 now stores focus.
            prefix.push(...L(-7),W(10,29),W(59,-7),W(2));
        }else{
            configure(vm);layout(vm,true);placeholder(vm);extra.push(v.tag(s.input));
            prefix=[W(1,7),W(6,k),W(10,29),W(59,-7),W(2)];
        }
        const old=profile.warehouseWords.UpdateTruckList;
        // Returning before the automatic row selection preserves native input
        // selection/caret and prevents the list stealing focus after each edit.
        const tail=[W(7,-7),W(22,0),W(5,1),W(6,inputIndex),W(60,29),W(2),W(19,1)];
        const offset=i=>i+prefix.length-1+(i>=78?tail.length:0);tail[1]=W(22,offset(78));
        const words=[...prefix,...old.slice(1,78),...tail,...old.slice(78)];
        for(let i=1;i<old.length;i++)if([22,23,24,25,26].includes(old[i]&255))words[offset(i)]=W(old[i]&255,offset((old[i]>>>8)-0x800000));
        apply(saved,words,extra);
    }
    function filter(vm,fn){
        const saved=storage(fn,profile.warehouseWords.GetTruckListByType);restore(saved);
        if(!isCurrent(vm)||!enabled)return;
        creating=false;if(!current.input)throw Error('Search creation failed');configure(vm);placeholder(vm);
        const s=current,query=v.str(v.read(s.input,'text',vm));
        const global=vm.add(0x48).readPointer();
        if(v.className(global)!=='__global')throw Error('Missing localization context');
        check(global,'GetLocalizationString',788,1);
        const kind=v.prop(s.view,'currentTruckType').readU32(),indices=[];
        const data=v.array(v.get(v.get(s.view,'viewData'),'truckDataList'));
        data.forEach((value,i)=>{
            const p=v.untag(value),raw=v.prop(p,'truckUiName').readPointer(),key=v.str(raw),internal=v.str(v.prop(p,'truckName').readPointer());
            if(!s.names.has(key)){
                if(s.names.size>=5000)throw Error('Search name cache limit');
                s.names.set(key,v.str(v.native(global,'GetLocalizationString',vm,[raw]))||key);
            }
            const label=s.names.get(key);
            if((kind===1||v.prop(p,'truckType').readU32()===kind)&&truckSearchMatches(query,label,internal))indices.push(i);
        });
        // Release old row reservations before any new row acquires its image.
        const holders=[],dict=v.get(s.view,'truckImages');
        for(const key of v.array(v.untag(v.native(dict,'Keys',vm)))){
            for(const value of v.array(v.untag(v.native(dict,'Get',vm,[key])))){
                const p=v.untag(value),owner=v.get(p,'owner');
                if(!owner.isNull()&&v.className(owner)==='UiTruckWarehouseViewLir'){check(p,'Release',8,2);holders.push(p);}
            }
        }
        if(holders.length>5000)throw Error('Search image limit');
        const words=[];holders.forEach((p,i)=>words.push(...stmt(call(C(saved.k+i),8))));
        words.push(W(1,1),W(1,1),W(57,0),W(4,0),W(58,0),W(59,-1),W(2));
        for(const i of indices)words.push(W(4,i),W(7,0),W(10,53),W(10,4),W(63),W(7,-1),W(66),W(2));
        words.push(W(7,-1),W(18,2));apply(saved,words,holders.map(v.tag));refreshes++;
    }
    function installFocusGuards(){
        const s=current,list=v.get(s.view,'trucksList');
        s.focusSlots=[];
        function guard(owners,name,expected,screen=false,argumentsToPop=2){
            const saved=storage(method(owners[0],name),expected),k=saved.k;
            const prefix=[],branches=[];
            for(let i=0;i<owners.length;i++){
                const start=prefix.length;
                prefix.push(W(7,0),W(6,k+i),W(48,7),W(22),
                    W(6,k+owners.length),W(10,24),W(22),
                    W(6,k+owners.length+1),W(22),
                    ...(screen?[W(5,1),W(18,2)]:[W(19,argumentsToPop)]));
                prefix[start+3]=W(22,prefix.length);
                branches.push(start+6,start+8);
            }
            for(const i of branches)prefix[i]=W(22,prefix.length);
            // Evaluate focus in SSL, before the handler runs. A frame-push
            // callback may already be too late to replace that call's program.
            apply(saved,[...prefix,...truckSearchShift(expected,prefix.length)],
                [...owners,s.input].map(v.tag).concat(v.bool(s.focused)));
            s.focusSlots.push(saved.values.add((k+owners.length+1)*8));
        }
        guard([list],'SetForDevice',profile.deviceWords);
        guard([list],'HandleOnItemHovered',profile.hoverWords);
        // First hover also activates the whole list through OnItemMouseOver,
        // before HandleOnItemHovered. Preserve typing at that entry point too.
        guard([s.view],'ActivateTruckList',profile.warehouseWords.ActivateTruckList,false,1);
        const screens=[v.get(list,'uiInputScreen')];
        if(controller){const screen=v.get(controller,'inputScreen');if(!screens[0].equals(screen))screens.push(screen);}
        guard(screens,'Press',profile.pressWords,true);
    }
    function hide(vm){
        if(!isCurrent(vm)||!current.input)return;
        v.write(current.input,'focus',v.bool(false),vm);v.write(current.input,'text',v.text(''),vm);tint(false);
        current.names.clear();
    }
    function terminate(vm,fn){
        if(!isCurrent(vm))return;
        hide(vm);for(const p of patches.values())restore(p);
        const s=current;
        if(s.input){
            const saved=storage(fn,profile.warehouseWords.TerminateContent);
            const prefix=stmt(call(C(saved.k),53));
            apply(saved,[...prefix,...truckSearchShift(profile.warehouseWords.TerminateContent,prefix.length)],[v.tag(s.input)]);
        }
        // Terminate's bytecode still owns the reference until it returns.
        s.retiring=fn;g.clear();
    }
    function retire(vm){
        if(!current?.retiring)return;
        for(let f=vm.add(0x30).readPointer(),i=0;!f.isNull()&&i<64;f=f.add(24).readPointer(),i++)
            if(f.add(8).readPointer().equals(current.retiring))return;
        for(const p of patches.values())restore(p);
        if(current.input)v.drop(v.tag(current.input));current=null;controller=null;
    }
    function safe(cb){return (vm,fn)=>{
        if(fault)return;
        try{v.scoped(()=>cb(vm,fn));}catch(e){
            fault=String(e);creating=false;
            try{v.scoped(()=>layout(vm,false));}catch(_){}
            for(const p of patches.values())try{restore(p);}catch(_){}
        }
    };}
    // At this verified interior site the VM argument stack already belongs to
    // the callee. At function entry it can still describe the calling object.
    function watch(c,n,cb){hooks.push(attach(entry,poolSlot,safe(cb),c,n,true));}
    try {
    // Capture only the control created inside our warehouse method prefix.
    hooks.push(Interceptor.attach(base.add(profile.setNameRva),{onEnter(args){
        if(!creating||!current||current.input)return;
        try{const p=args[1];if(v.className(p)!=='UiTextInput')return;p.writeU32(p.readU32()+1);current.input=p;current.captureSlot.writePointer(v.tag(p));}catch(e){fault=String(e);}
    }}));
    for(const [rva,active] of [[profile.focusInRva,true],[profile.focusOutRva,false]])hooks.push(Interceptor.attach(base.add(rva),{
        onEnter(args){this.search=!!current?.native&&args[0].add(0x58).readPointer().equals(current.native);},
        onLeave(){if(this.search)try{tint(active);}catch(e){fault=String(e);}}
    }));
    watch('UiTruckWarehouseController','CreateData',vm=>{retire(vm);controller=v.receiver(vm);});
    watch('UiTruckWarehouseView','UpdateTruckList',update);
    watch('UiTruckWarehouseView','GetTruckListByType',filter);
    watch('UiTruckWarehouseView','Hide',hide);
    watch('UiTruckWarehouseView','TerminateContent',terminate);
    watch('NavigationPanelController','Update',retire);
    } catch(error) { for(const hook of hooks)hook.detach();Interceptor.flush();throw error; }
    // Native listeners alone do not retain their CModule/NativeCallback owners.
    // Keep every listener and its compiled callback alive with the component.
    return {keepAlive:hooks,set:value=>{enabled=value!==false;},status:()=>({status:fault?'error':'ready',enabled,fault,installations,refreshes})};
}
