'use strict';

// All writes are to guarded VM method descriptors or our own slider instance.
// Camera limits, input vectors and the elapsed-time calculation stay native.
function makeMapZoomSensitivity(profile, access, options, attach = hookHudHintUpdates) {
    const W=(op,arg=0)=>(0x80000000+arg*256+op)>>>0;
    const enabled=options.mapEnabled!==false;
    let value=Number.isInteger(options.zoomSensitivity)&&options.zoomSensitivity>=0&&options.zoomSensitivity<=100?options.zoomSensitivity:50;
    let hooks=[],zoom=null,view=null,ourView=null,arena=null,used=0,fault=null,running=false;
    let changes=0,zoomCalls=0,displayCalls=0;
    const multiplier=()=>Math.pow(4,(value-50)/50);
    function alloc(n){
        if(!arena){
            const va=new NativeFunction(Process.getModuleByName('kernel32.dll').getExportByName('VirtualAlloc'),'pointer',['pointer','size_t','uint32','uint32']);
            arena=va(ptr(0),16384,0x3000,4);if(arena.isNull())throw Error('Zoom allocation failed');
        }
        n=(n+15)&~15;if(used+n>16384)throw Error('Zoom arena full');const p=arena.add(used);used+=n;return p;
    }
    function makePatch(fn,expected,words,constant){
        const original=fn.add(0x60).readPointer();
        if(fn.add(0x68).readU32()!==expected.length||!expected.every((w,i)=>original.add(i*4).readU32()===w))throw Error('Zoom/slider bytecode mismatch');
        const code=alloc(words.length*4);words.forEach((w,i)=>code.add(i*4).writeU32(w));
        return {fn,original,expected,code,words,constants:fn.add(0x50).readPointer(),count:fn.add(0x58).readU32(),constant,active:false};
    }
    function verify(p){
        const code=p.active?p.code:p.original,words=p.active?p.words:p.expected;
        const constants=p.active&&p.constant?p.constant:p.constants,count=p.active&&p.constant?1:p.count;
        if(!p.fn.add(0x60).readPointer().equals(code)||p.fn.add(0x68).readU32()!==words.length||
           !p.fn.add(0x50).readPointer().equals(constants)||p.fn.add(0x58).readU32()!==count||
           !words.every((w,i)=>code.add(i*4).readU32()===w))throw Error('Foreign zoom/slider bytecode; not overwritten');
    }
    function apply(p){
        verify(p);
        if(p.constant){p.fn.add(0x50).writePointer(p.constant);p.fn.add(0x58).writeU32(1);}
        p.fn.add(0x60).writePointer(p.code);p.fn.add(0x68).writeU32(p.words.length);p.active=true;
    }
    function restore(p){
        if(!p||!p.active)return;verify(p);
        p.fn.add(0x60).writePointer(p.original);p.fn.add(0x68).writeU32(p.expected.length);
        p.fn.add(0x50).writePointer(p.constants);p.fn.add(0x58).writeU32(p.count);p.active=false;
    }
    function restoreAll(){let failure;for(const p of [zoom,view])try{restore(p);}catch(e){failure=e;}if(failure)throw failure;}
    function guarded(cb){return (vm,fn)=>{if(fault)return;try{cb(vm,fn);}catch(e){fault=String(e);try{restoreAll();}catch(_){};}};}
    function current(vm){
        const p=access.receiver(vm);if(!access.owns(p))return;
        ourView=access.get(p,'view');
        access.prop(p,'textfield').writePointer(ptr('0x1000000000002'));
        access.prop(ourView,'textFormat').writePointer(ptr('0x1000000000002'));
        const v=access.prop(p,'hackCurrent');v.writePointer(ptr('0x3000000000000'));v.writeFloat(value);
    }
    function change(vm){
        const p=access.receiver(vm);if(!access.owns(p))return;
        const arg=vm.add(0x18).readPointer().add(8);
        if(arg.readPointer().shr(48).toUInt32()!==3||!Number.isFinite(arg.readFloat()))throw Error('Invalid zoom slider value');
        const next=Math.max(0,Math.min(100,Math.round(arg.readFloat())));
        // Native HandleChange copies this argument to hackCurrent and the view.
        arg.writeFloat(next);
        if(value!==next){value=next;changes++;if(options.onZoomChange)options.onZoomChange(value);}
    }
    function display(vm,fn){
        // The method is shared with FOV and brightness: restore first, then
        // enable the two nested text controls for our view only.
        restore(view);if(!ourView||!access.receiver(vm).equals(ourView))return;
        if(view&&!view.fn.equals(fn))throw Error('Slider method owner changed');
        if(!view){
            if(fn.add(0x58).readU32()!==5)throw Error('Unexpected slider constants');
            const prefix=[W(5,1),W(7),W(10,6),W(10,144),W(10,95),W(60,24),W(2),
                W(5,1),W(7),W(10,6),W(10,144),W(10,95),W(10,143),W(60,24),W(2)];
            const words=profile.sliderCurrentWords.map(w=>[22,23,24,25,26].includes(w&255)?(w+prefix.length*256)>>>0:w);
            view=makePatch(fn,profile.sliderCurrentWords,[...prefix,...words]);
        }
        apply(view);displayCalls++;
    }
    function zoomEntry(_vm,fn){
        if(zoom&&!zoom.fn.equals(fn))throw Error('Zoom method owner changed');
        if(!zoom){
            if(fn.add(0x58).readU32()!==0)throw Error('Unexpected zoom constants');
            const constant=alloc(8);constant.writePointer(ptr('0x300003f800000'));
            zoom=makePatch(fn,profile.zoomWords,[...profile.zoomWords.slice(0,10),W(6),W(40),...profile.zoomWords.slice(10)],constant);
        }
        // At the midpoint run the exact original method, without extra math.
        verify(zoom);
        if(value===50)restore(zoom);
        else {zoom.constant.writeFloat(multiplier());apply(zoom);}
        zoomCalls++;
    }
    return {
        start(framePush,poolSlot){
            if(running)throw Error('Zoom already started');if(!enabled)return;
            try{
                for(const [c,m,cb] of [
                    ['UiOneSettingSliderController','GetCurrentValue',current],
                    ['UiOneSettingSliderController','HandleChange',change],
                    ['UiOneSettingSliderView','UpdateSliderCurrent',display],
                    ['MinimapCameraController','Zoom',zoomEntry]
                ])hooks.push(attach(framePush,poolSlot,guarded(cb),c,m));
                running=true;
            }catch(e){for(const h of hooks)h.detach();hooks=[];Interceptor.flush();fault=String(e);}
        },
        status(){return {enabled,running,status:!enabled?'disabled':fault?'incompatible':running?'active':'stopped',value,multiplier:multiplier(),changes,zoomCalls,displayCalls,fault};},
        stop(){for(const h of hooks)h.detach();hooks=[];Interceptor.flush();running=false;restoreAll();}
    };
}
