'use strict';
const gamepadValue=Memory.alloc(4);
const engineCategory=Memory.alloc(0xd0);engineCategory.writeByteArray(new Uint8Array(0xd0));
const menuCurrent=Memory.alloc(8);
const neutralTelemetry=Memory.alloc(8);
const navigationHold=[];
// Keep synthetic UI identities distinct for the entire test session.
const uiHold=[];
const panelUis=[Memory.alloc(64),Memory.alloc(64)];
for(const ui of panelUis){ui.writeByteArray(new Uint8Array(64));ui.add(24).writePointer(ptr(1));}
let cursorCamera=null;
const engineSlot=Memory.alloc(8); engineSlot.writePointer(engineCategory);
const wheelHardware=Memory.alloc(0x1570),wheelManager=Memory.alloc(0x80),wheelDevices=Memory.alloc(8);
wheelHardware.writeByteArray(new Uint8Array(0x1570));
wheelManager.writeByteArray(new Uint8Array(0x80));
wheelHardware.add(0x156c).writeU32(33);wheelDevices.writePointer(wheelHardware);
wheelManager.add(0x70).writePointer(wheelDevices);wheelManager.add(0x78).writeS32(1);
const target = new CModule(`
typedef unsigned int u32;
typedef unsigned long long u64;
extern u32 gamepad_value;
extern unsigned char *menu_current;
extern u32 neutral_telemetry[];
extern u32 engine_data[];
extern void SetLastError(u32);
extern u32 GetLastError(void);
u32 gamepad_mode(void) { return gamepad_value; }
void vm_push(void *vm, void *fn) {}
void wheel_abs(void *vm, void *unused, u32 count, u64 *values, u64 *out) {
    neutral_telemetry[0]++;neutral_telemetry[1]=GetLastError();
    *out=values[0] & ~(u64)0x80000000;
}
void select_type(u32 *state, const u32 *type) {
    if (*state != *type) { state[1] = 1; *state = *type; }
    state[2] = 1;
}
// The real callback stores the category then dispatches only when the
// subscriber reference at +0x18 is non-null. Count those visible events.
void notify_ui(u32 *ui, const u32 *type) { ui[8] = *type; if (ui[6]) ui[9]++; }
void menu_select(u32 *ui, int index) { ui[116] = index; ui[117]++; ui[118] = index >= 0; }
void menu_data(u32 *ui, u32 generation) { ui[119] = generation; }
void camera_update(unsigned char *camera) { ((u32 *)camera)[8]++; ((u32 *)camera)[9]=GetLastError(); }
void camera_dragging(unsigned char *camera, unsigned char value) {
    camera[0x15]=value; ((u32 *)camera)[10]++; SetLastError(0xbeef);
}
void menu_focus(unsigned char *ui, unsigned char value) {
    ui[0x103]=value;
    if(ui[0x70]<2)return;
    ((u32 *)ui)[120]++; ((u32 *)ui)[126]=GetLastError(); SetLastError(0xbeef);
}
void menu_keys(void *vm, void *unused, u32 count, u64 *args) {
    u32 *ui=(u32 *)menu_current;
    ui[121]++;ui[122]=(u32)args[0];ui[123]=(u32)args[1];ui[124]=GetLastError();
    if(count==2 && engine_data[49] && menu_current[0x103] && menu_current[0x104] &&
       !menu_current[0x51] && (u32)args[1]==5) {
        if((u32)args[0]==38)ui[116]--; else if((u32)args[0]==40)ui[116]++;
    }
}
`, {gamepad_value:gamepadValue,menu_current:menuCurrent,engine_data:engineCategory,neutral_telemetry:neutralTelemetry,
    SetLastError:Process.getModuleByName('kernel32.dll').getExportByName('SetLastError'),
    GetLastError:Process.getModuleByName('kernel32.dll').getExportByName('GetLastError')});
const caller = new CModule(`
typedef unsigned int u32;
extern void select_type(u32 *, const u32 *);
extern void notify_ui(u32 *, const u32 *);
extern void menu_keys(void *, void *, u32, void *);
extern void menu_focus(void *, unsigned char);
extern void wheel_abs(void *, void *, u32, void *, void *);
extern void camera_update(unsigned char *);
extern void vm_push(void *, void *);
extern void SetLastError(u32);
extern u32 GetLastError(void);
u32 choose(u32 *state, u32 *device, u32 *ui) {
    SetLastError(0x1234);
    select_type(state, device);
    notify_ui(ui, state);
    state[3] = device[0];
    state[4] = device[1];
    return GetLastError();
}
u32 dispatch_panels(u32 *state, u32 *first, u32 *second) {
    SetLastError(0x1234);
    if(((unsigned char *)state)[4]) {
        notify_ui(first,state); notify_ui(second,state);
        ((unsigned char *)state)[4]=0;
    }
    return GetLastError();
}
u32 press_menu(void *vm, void *values, u32 count) {
    SetLastError(0x1234); menu_keys(vm,0,count,values); return GetLastError();
}
u32 set_focus(void *ui, unsigned char value) {
    SetLastError(0x1234); menu_focus(ui,value); return GetLastError();
}
u32 neutral_compare(void *vm, void *values, u32 count, void *out) {
    SetLastError(0x1234);wheel_abs(vm,0,count,values,out);return GetLastError();
}
u32 tick_camera(unsigned char *camera) {
    SetLastError(0x1234);camera_update(camera);return GetLastError();
}
u32 push_frame(void *vm, void *fn) {
    SetLastError(0x1234); vm_push(vm,fn); return GetLastError();
}
`, {select_type: target.select_type, notify_ui: target.notify_ui,
    menu_keys:target.menu_keys, menu_focus:target.menu_focus,wheel_abs:target.wheel_abs,
    camera_update:target.camera_update, vm_push:target.vm_push,
    SetLastError: Process.getModuleByName('kernel32.dll').getExportByName('SetLastError'),
    GetLastError: Process.getModuleByName('kernel32.dll').getExportByName('GetLastError')});
const choose = new NativeFunction(caller.choose, 'uint32', ['pointer', 'pointer', 'pointer']);
const dispatchPanels=new NativeFunction(caller.dispatch_panels,'uint32',['pointer','pointer','pointer']);
const pressMenu=new NativeFunction(caller.press_menu,'uint32',['pointer','pointer','uint32']);
const setFocus=new NativeFunction(caller.set_focus,'uint32',['pointer','uint8']);
const neutralCompare=new NativeFunction(caller.neutral_compare,'uint32',['pointer','pointer','uint32','pointer']);
const tickCamera=new NativeFunction(caller.tick_camera,'uint32',['pointer']);
const pushFrame=new NativeFunction(caller.push_frame,'uint32',['pointer','pointer']);
// Controlled x64 instruction fixture: R10=engine, R11=UI; read through R10.
const getterCode = Memory.alloc(Process.pageSize);
getterCode.writeByteArray([0x56,0x49,0x8b,0xf0,0x4c,0x8b,0xd2,0x4c,0x8b,0xd9,
    0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x41,0x8b,0x02,0x5e,0xc3]);
Memory.protect(getterCode, Process.pageSize, 'r-x');
const getter = new NativeFunction(getterCode, 'uint32', ['pointer', 'pointer', 'pointer']);
// Native binding preserves the VM pointer in RSI while calling list SetData.
const menuCaller = Memory.alloc(Process.pageSize);
menuCaller.writeByteArray([0x56,0x48,0x83,0xec,0x20,0x49,0x8b,0xf0,
    0x48,0xb8,0,0,0,0,0,0,0,0,0xff,0xd0,0x48,0x83,0xc4,0x20,0x5e,0xc3]);
menuCaller.add(10).writePointer(target.menu_data);
Memory.protect(menuCaller,Process.pageSize,'r-x');
const rebuildMenu = new NativeFunction(menuCaller,'void',['pointer','uint32','pointer']);
// A separate caller supplies an exact approved return address to the predicate.
const modeCaller=Memory.alloc(Process.pageSize);
modeCaller.writeByteArray([0x48,0x83,0xec,0x28,0x48,0xb8,0,0,0,0,0,0,0,0,
    0xff,0xd0,0x48,0x83,0xc4,0x28,0xc3]);
modeCaller.add(6).writePointer(target.gamepad_mode);
Memory.protect(modeCaller,Process.pageSize,'r-x');
const approvedMode=new NativeFunction(modeCaller,'uint32',[]);
const otherMode=new NativeFunction(target.gamepad_mode,'uint32',[]);
// Exercise actual mid-function register restoration across a timer veto,
// retaining preceding eligibility checks and the function's saved registers.
const hoverCode=Memory.alloc(Process.pageSize);
hoverCode.writeByteArray([0x41,0x54,0x41,0x56,0x44,0x8b,0xe2,
    0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,
    0x41,0x83,0xf8,0x00,0x41,0xbe,0,0,0,0,0x45,0x0f,0x45,0xe6,
    0x45,0x33,0xf6,0x41,0x8b,0xc4,0x41,0x5e,0x41,0x5c,0xc3]);
Memory.protect(hoverCode,Process.pageSize,'r-x');
const hoverTest=new NativeFunction(hoverCode,'uint32',['uint32','uint32','uint32']);
const pool = Memory.alloc(8192);
const poolSlot = Memory.alloc(8);
poolSlot.writePointer(pool);
let nameOffset = 1;
const interned = new Map();
function intern(name) {
    if (interned.has(name)) return interned.get(name);
    const offset = nameOffset;
    nameOffset += name.length + 1;
    if (nameOffset + 160 > 8192) throw new Error('Fixture string overflow');
    pool.add(offset).writeByteArray([...name].map(c => c.charCodeAt(0)).concat(255));
    interned.set(name, offset);
    return offset;
}
function vmStack(className, method, query, customFrames) {
    const objects = [];
    const alloc = n => { const p = Memory.alloc(n); objects.push(p); return p; };
    let previous = ptr(0);
    const frames = customFrames || [[className, method], ...(query ? [['InputFocusDeviceListener', query]] : []),
            ['InputFocusDeviceListener', 'GetCurrentDeviceEx'],
            ['InputFocusDeviceListener', 'GetCurrentDevice']];
    for (const [clsName, methodName, receiver] of frames) {
        const cls = alloc(32); cls.add(0x18).writeU32(intern(clsName));
        const signature = alloc(8); signature.writeU32(intern(methodName));
        const fn = alloc(112); fn.add(0x40).writePointer(signature); fn.add(0x48).writePointer(cls);
        const argv=alloc(8);argv.writePointer(receiver ? receiver.or('0x20000000000000') : ptr(0));
        const frame = alloc(32);frame.writePointer(argv); frame.add(8).writePointer(fn); frame.add(0x18).writePointer(previous);
        previous = frame;
    }
    const context = alloc(64); context.add(0x30).writePointer(previous);
    return {context, objects};
}
const hudVm=vmStack('','','', [['HudNavigationPanelHolder','UpdateState'],['ScreenControllerBase','UpdateState']]);
const hudHolder=hudVm.context.add(0x30).readPointer().add(0x18).readPointer();
const hudHolderFn=hudHolder.add(8).readPointer();
const hudMethod=vmStack('NavigationPanelController','Update','', [['NavigationPanelController','Update']]);
const hudFn=hudMethod.context.add(0x30).readPointer().add(8).readPointer();
const hudCode=Memory.alloc(117*4),hudHolderCode=Memory.alloc(754*4),hudArgs=Memory.alloc(24);
const hudPrefix=[0x80000301,0x80000207,0x8000001b,0x80001118,0x80000002,
    0x80000007,0x8000350a,0x80000003,0x80000830,0x80001118,0x80000002,
    0x80000101,0x80000107,0x80000007,0x8000350a,0x80000104,0x8000080d,
    0x80001316,0x80000313,0x80000101,0x80000107,0x80000004,0x8000090d,
    0x80000007,0x8000353c,0x80000002,0x80000107,0x8000040a,0x80000007,
    0x8000073c,0x80000002];
const hudTail=[0x80000101,0x80000007,0x80000004,0x80001006,0x8000310e,0x80000002,0x80000113];
hudVm.context.add(0x18).writePointer(hudArgs);
hudFn.add(0x60).writePointer(hudCode);hudHolderFn.add(0x60).writePointer(hudHolderCode);
rpc.exports = {
    info() { return {selector: String(target.select_type), uiCallback: String(target.notify_ui),
        uiGetter: String(getterCode.add(10)), stringPoolSlot: String(poolSlot),
        roles: TEST_ROLES,
        winch: {predicate:String(target.gamepad_mode),engineSlot:String(engineSlot),
            wheelNeutral:String(target.wheel_abs),framePush:String(target.vm_push),wheelHintActivity:true,
            menuData:String(target.menu_data),menuSelect:String(target.menu_select),
            menuKeys:String(target.menu_keys),menuFocus:String(target.menu_focus),
            cameraUpdate:String(target.camera_update),cameraDragging:String(target.camera_dragging),
            hoverSite:String(hoverCode.add(7)),hoverResume:String(hoverCode.add(29)),
            callers:[String(modeCaller.add(16))]},
        ids: {keyboard: 11, mouse: 22, wheel: 33, supplemental: 44}}; },
    wheelHardware(options) {
        if (options.reset) wheelHardware.add(0x28).writeByteArray(new Uint8Array(140*4));
        if (options.clearRefresh) engineCategory.add(4).writeU32(0xabcdef00);
        for (const [index, value] of Object.entries(options.values || {}))
            wheelHardware.add(0x28 + Number(index)*4).writeFloat(value);
        engineCategory.add(0x20).writePointer(options.enabled === false ? ptr(0) : wheelManager);
        return Array.from(new Float32Array(wheelHardware.add(0x28).readByteArray(140*4)));
    },
    wheelHintRead(category, role='presentation') {
        role=role || 'presentation';
        engineCategory.writeU32(category);
        const ui=Memory.alloc(64);ui.writeByteArray(new Uint8Array(64));uiHold.push(ui);
        const vm=role==='presentation' ? vmStack('HintIconsPool','GetCurrentDeviceNames','') :
            role==='pointer' ? vmStack('MouseController','CanShowMouseCursor','') :
            vmStack('TruckInputController','Update','');
        navigationHold.push(vm);
        return {result:getter(ui,engineCategory,vm.context),category:engineCategory.readU32(),
            notificationWord:engineCategory.add(4).readU32(),
            values:Array.from(new Float32Array(wheelHardware.add(0x28).readByteArray(140*4)))};
    },
    panelNotifications(category, force) {
        engineCategory.writeU32(category);
        if(force)engineCategory.add(4).writeU8(1);
        const error=dispatchPanels(engineCategory,panelUis[0],panelUis[1]);
        return {signals:panelUis.map(p=>p.add(36).readU32()),
            delivered:panelUis.map(p=>p.add(32).readU32()),category:engineCategory.readU32(),
            dirty:engineCategory.add(4).readU8(),error};
    },
    hudHintUpdate(options) {
        const o={receiver:1,category:33,targetClass:'NavigationPanelController',targetMethod:'Update',
            holderClass:'HudNavigationPanelHolder',holderMethod:'UpdateState',holderPc:TEST_HUD_CONTEXT.holderPc,
            targetLength:117,holderLength:754,receiverTag:0x20,stateTag:0x20,boolTag:2,forced:0,...options};
        hudFn.add(0x48).readPointer().add(0x18).writeU32(intern(o.targetClass));
        hudFn.add(0x40).readPointer().writeU32(intern(o.targetMethod));
        hudHolderFn.add(0x48).readPointer().add(0x18).writeU32(intern(o.holderClass));
        hudHolderFn.add(0x40).readPointer().writeU32(intern(o.holderMethod));
        hudHolder.add(0x10).writeU32(o.holderPc);
        hudFn.add(0x68).writeU32(o.targetLength);hudHolderFn.add(0x68).writeU32(o.holderLength);
        TEST_HUD_CONTEXT.navigationCode.forEach((w,i)=>hudCode.add(4*i).writeU32(w));
        hudTail.forEach((w,i)=>hudHolderCode.add(4*(747+i)).writeU32(w));
        if(o.badCode)hudCode.add(4*16).writeU32(0);
        if(o.badTail)hudCode.add(4*81).writeU32(0);
        if(o.badHolderCode)hudHolderCode.add(4*751).writeU32(0);
        hudArgs.writeU64(uint64(o.receiverTag).shl(48).or(o.receiver));
        hudArgs.add(8).writeU64(uint64(o.stateTag).shl(48).or(o.nullState?0:1234));
        hudArgs.add(16).writeU64(uint64(o.boolTag).shl(48).or(0xc3f9c900).or(o.forced));
        const before=[0,8,16].map(n=>hudArgs.add(n).readU64().toString(16));
        engineCategory.writeU32(o.category);
        const error=pushFrame(o.invalidVm?ptr(0):hudVm.context,hudFn);
        return {before,after:[0,8,16].map(n=>hudArgs.add(n).readU64().toString(16)),
            forced:hudArgs.add(16).readU8(),error,category:engineCategory.readU32()};
    },
    menuCursor(options) {
        const o={category:33,opening:true,view:'HudInteractionPanelUiView',method:'SetData',
            enabled:1,dragging:1,tick:true,invalid:false,...options};
        const object=Memory.alloc(512);object.writeByteArray(new Uint8Array(512));
        object.add(0x1d0).writeS32(-1);
        const vm=vmStack('','','',[
            ['TruckInputController',o.opening?'TurnOnFunctions':'TurnOffFunctions'],[o.view,o.method]]);
        engineCategory.writeU32(o.category);
        cursorCamera=Memory.alloc(64);cursorCamera.writeByteArray(new Uint8Array(64));
        cursorCamera.add(0x14).writeU8(o.enabled);cursorCamera.add(0x15).writeU8(o.dragging);
        rebuildMenu(object,42,o.invalid?ptr(0):vm.context);
        uiHold.push({object,vm,camera:cursorCamera});
        const error=o.tick?tickCamera(cursorCamera):0;
        return {dragging:cursorCamera.add(0x15).readU8(),releases:cursorCamera.add(40).readU32(),
            error,entryError:cursorCamera.add(36).readU32(),category:engineCategory.readU32()};
    },
    cursorTick(enabled=1,dragging=1) {
        cursorCamera.add(0x14).writeU8(enabled ?? 1);cursorCamera.add(0x15).writeU8(dragging ?? 1);
        const error=tickCamera(cursorCamera);
        return {dragging:cursorCamera.add(0x15).readU8(),releases:cursorCamera.add(40).readU32(),
            error,entryError:cursorCamera.add(36).readU32()};
    },
    wheelNeutral(options) {
        const o={category:33,value:-1/65536,count:1,zero:0,tolerance:1e-6,
            callerClass:'TruckInputController',callerMethod:'UpdateSteeringWheelInputs',
            callerPc:464,equalClass:'__global',equalMethod:'IsEqualFloat',equalPc:6,
            nativeMethod:'AbsFloat',nativePc:0,...options};
        if(o.special==='nan')o.value=NaN;
        if(o.special==='infinity')o.value=Infinity;
        const chain=[[o.callerClass,o.callerMethod],[o.equalClass,o.equalMethod]];
        if(o.intervening)chain.push(['Other','Nested']);
        chain.push(['__global',o.nativeMethod]);
        const vm=vmStack('','','',chain);
        const nativeFrame=vm.context.add(0x30).readPointer();
        const equalFrame=nativeFrame.add(0x18).readPointer();
        const wheelFrame=equalFrame.add(0x18).readPointer();
        const absArgs=Memory.alloc(16),equalArgs=Memory.alloc(32),output=Memory.alloc(8);
        const floatVariant=(p,value)=>{p.writeU64(uint64('0x3000000000000'));p.writeFloat(value);};
        absArgs.writePointer(ptr(0));floatVariant(absArgs.add(8),o.value);
        equalArgs.writePointer(ptr(0));floatVariant(equalArgs.add(8),o.value);
        floatVariant(equalArgs.add(16),o.zero);floatVariant(equalArgs.add(24),o.tolerance);
        if(o.inputTag)absArgs.add(14).writeU8(o.inputTag);
        if(o.compareTag)equalArgs.add(14).writeU8(o.compareTag);
        if(o.differentInput)equalArgs.add(8).writeFloat(o.value*2);
        nativeFrame.writePointer(absArgs);nativeFrame.add(0x10).writeU32(o.nativePc);
        equalFrame.writePointer(equalArgs);equalFrame.add(0x10).writeU32(o.equalPc);
        wheelFrame.add(0x10).writeU32(o.callerPc);
        const equalCode=Memory.alloc(40),wheelCode=Memory.alloc(535*4);
        [2147483905,2147483911,2147484167,2147483685,2147483656,2147483908,
            2147584781,2147484423,2147486002,2147484690].forEach((v,i)=>equalCode.add(i*4).writeU32(v));
        [2147485190,2147483654,2147482887,2147483656,2147484420,2147592205,
            2147607574].forEach((v,i)=>wheelCode.add((459+i)*4).writeU32(v));
        for(const [frame,code,count] of [[equalFrame,equalCode,10],[wheelFrame,wheelCode,535]]) {
            const fn=frame.add(8).readPointer();fn.add(0x60).writePointer(code);fn.add(0x68).writeU32(count);
        }
        if(o.badCode)wheelCode.add(464*4).writeU32(0);
        if(o.badEqualCode)equalCode.add(6*4).writeU32(0);
        if(o.badLength)wheelFrame.add(8).readPointer().add(0x68).writeU32(536);
        const operand=o.foreignOperand?Memory.alloc(8).writeU64(absArgs.add(8).readU64()):absArgs.add(8);
        const original=operand.readU64().toString(16),originalArgs=equalArgs.readByteArray(32);
        engineCategory.writeU32(o.category);neutralTelemetry.writeU64(0);
        const error=neutralCompare(o.invalid?ptr(0):vm.context,operand,o.count,output);
        const result={result:output.readFloat(),original,after:operand.readU64().toString(16),
            comparisonUnchanged:JSON.stringify(Array.from(new Uint8Array(originalArgs)))===
                JSON.stringify(Array.from(new Uint8Array(equalArgs.readByteArray(32)))),
            calls:neutralTelemetry.readU32(),entryError:neutralTelemetry.add(4).readU32(),error,
            category:engineCategory.readU32(),resultBits:output.readU32()};
        uiHold.push({vm,absArgs,equalArgs,output,equalCode,wheelCode,operand});
        return result;
    },
    winchMode(category, value, approved) {
        engineCategory.writeU32(category); gamepadValue.writeU32(value);
        const result=approved ? approvedMode() : otherMode();
        return {result,category:engineCategory.readU32(),globalMode:gamepadValue.readU32()};
    },
    hoverGate(category, eligible, timedOut) {
        engineCategory.writeU32(category);
        const result=hoverTest(category,eligible,timedOut);
        return {result,category:engineCategory.readU32()};
    },
    menuRebuild(category, prior, className, method, focusable = 0) {
        engineCategory.writeU32(category);
        const object=Memory.alloc(512);object.writeByteArray(new Uint8Array(512));
        object.add(0x1d0).writeS32(prior);object.add(0x1d8).writeU32(prior>=0?1:0);
        object.add(0x104).writeU8(focusable || 0);
        const vm=vmStack(className,method,'');
        rebuildMenu(object,42,className==='<invalid>'?ptr(0):vm.context);
        if(!vm.objects.length)throw new Error('Missing VM objects');
        return {selection:object.add(0x1d0).readS32(),resets:object.add(0x1d4).readU32(),
            highlight:object.add(0x1d8).readU32(),generation:object.add(0x1dc).readU32(),
            category:engineCategory.readU32()};
    },
    menuNavigation(options) {
        const o={category:33,key:40,event:5,count:2,gate:1,focus:0,focusable:1,disabled:0,
            repeat:1,wheelPath:true,register:true,foreignOwner:false,stale:false,invalid:false,...options};
        const object=Memory.alloc(512),scriptObject=Memory.alloc(8),owner=Memory.alloc(8),other=Memory.alloc(8),reference=Memory.alloc(8);
        object.writeByteArray(new Uint8Array(512));object.add(0x70).writeU8(2);
        reference.writePointer(scriptObject.or('0x20000000000000'));
        object.add(0x18).writePointer(reference);object.add(0x1d0).writeS32(5);
        engineCategory.writeU32(o.category);engineCategory.add(0xc4).writeU32(o.gate);
        const setup=vmStack('','','',[[o.register?'HudInteractionPanelUiView':'OtherPanel','SetData'],
            ['UiListAdapter','SetData',owner],['UiCoreList','SetData',scriptObject]]);
        rebuildMenu(object,42,setup.context);
        object.add(0x1d0).writeS32(5);object.add(0x103).writeU8(o.focus);
        object.add(0x104).writeU8(o.focusable);object.add(0x51).writeU8(o.disabled);
        if(o.stale)reference.writePointer(other.or('0x20000000000000'));
        const input=vmStack('','','',[
            ['SslUiInputScreenManagerMr2',o.wheelPath?'PressWheel':'PressKeyboard'],
            ['UiListAdapter','GfxPress',o.foreignOwner?other:owner],['__global','UiHandleKeyEvent']]);
        const values=Memory.alloc(16);values.writeU64(uint64(o.key).or('0x1000000000000'));
        values.add(8).writeU64(uint64(o.event).or('0x1000000000000'));menuCurrent.writePointer(object);
        let error;
        for(let i=0;i<o.repeat;i++)error=pressMenu(o.invalid?ptr(0):input.context,values,o.count);
        navigationHold.push({object,scriptObject,owner,other,reference,setup,input,values});
        return {focus:object.add(0x103).readU8(),restores:object.add(480).readU32(),
            selection:object.add(0x1d0).readS32(),calls:object.add(484).readU32(),
            key:object.add(488).readU32(),event:object.add(492).readU32(),
            entryError:object.add(496).readU32(),error,category:engineCategory.readU32()};
    },
    menuRefresh(options) {
        const o={category:33,focus:1,focusable:1,disabled:0,gate:1,selection:5,
            caller:'HudInteractionPanelUiView',method:'SetData',adapter:'SetDataAndInitialIndex',
            current:'same',stale:false,changedReference:false,changedArguments:false,
            changedFunction:false,foreignObject:false,rebuildClosed:false,value:0,repeat:1,...options};
        const object=Memory.alloc(512),scriptObject=Memory.alloc(8),owner=Memory.alloc(8),
            view=Memory.alloc(8),other=Memory.alloc(512),reference=Memory.alloc(8),otherReference=Memory.alloc(8);
        for(const p of [object,other]){p.writeByteArray(new Uint8Array(512));p.add(0x70).writeU8(2);}
        reference.writePointer(scriptObject.or('0x20000000000000'));
        otherReference.writePointer(scriptObject.or('0x20000000000000'));
        object.add(0x18).writePointer(reference);object.add(0x103).writeU8(o.focus);
        object.add(0x104).writeU8(o.focusable);object.add(0x51).writeU8(o.disabled);
        object.add(0x1d0).writeS32(o.selection);object.add(0x1d8).writeU32(o.selection>=0?1:0);
        engineCategory.writeU32(o.category);engineCategory.add(0xc4).writeU32(o.gate);
        const setup=vmStack('','','',[[o.caller,o.method,view],
            ['UiListAdapter',o.adapter,owner],['UiCoreList','SetData',scriptObject]]);
        const nativeFrame=setup.context.add(0x30).readPointer();
        const viewFrame=nativeFrame.add(0x18).readPointer().add(0x18).readPointer();
        rebuildMenu(object,42,setup.context);
        if(o.rebuildClosed){object.add(0x104).writeU8(0);rebuildMenu(object,42,setup.context);}
        // The adapter focuses/selects the new data before the view's final blur.
        object.add(0x104).writeU8(1);object.add(0x103).writeU8(1);object.add(0x1d0).writeS32(o.selection);
        setup.context.add(0x30).writePointer(viewFrame);
        const alternative=vmStack('','','',[[o.current==='nested'?o.caller:'MouseCamera',
            o.current==='nested'?o.method:'Update',view],...(o.current==='nested'?[['UiListAdapter','FocusBtn',owner]]:[])]);
        if(o.current==='different'||o.current==='nested')setup.context.add(0x30).writePointer(alternative.context.add(0x30).readPointer());
        if(o.current==='invalid')setup.context.add(0x30).writePointer(ptr(0));
        if(o.stale)reference.writePointer(other.or('0x20000000000000'));
        if(o.changedReference)object.add(0x18).writePointer(otherReference);
        if(o.changedArguments)viewFrame.writePointer(other);
        if(o.changedFunction)viewFrame.add(8).writePointer(alternative.context.add(0x30).readPointer().add(8).readPointer());
        let error,firstFocus;
        for(let i=0;i<o.repeat;i++){
            error=setFocus(o.foreignObject?other:object,o.value);
            if(i===0)firstFocus=object.add(0x103).readU8();
        }
        navigationHold.push({object,scriptObject,owner,view,other,reference,otherReference,setup,alternative});
        return {focus:object.add(0x103).readU8(),firstFocus,calls:object.add(480).readU32(),
            selection:object.add(0x1d0).readS32(),generation:object.add(0x1dc).readU32(),
            error,entryError:object.add(504).readU32(),category:engineCategory.readU32()};
    },
    notificationSequence(sequence, axis, cursorOwner = null) {
        const state=Memory.alloc(20),device=Memory.alloc(8),ui=Memory.alloc(64);
        uiHold.push(ui);
        state.writeByteArray(new Uint8Array(20));state.writeU32(22);
        ui.writeByteArray(new Uint8Array(64));ui.add(24).writePointer(ptr(1));ui.add(32).writeU32(22);
        const result=[];
        // Model the visibility request owned by HandleOnDeviceChanged: only
        // delivered notifications run the handler, which re-reads the device.
        const vm=cursorOwner ? vmStack(cursorOwner,'HandleOnDeviceChanged','IsKeyboardOrMouse') : null;
        let signals=0, visible=true;
        for(const requested of sequence) {
            device.writeU32(requested);device.add(4).writeU32(axis);
            const error=choose(state,device,ui);
            const currentSignals=ui.add(36).readU32();
            if(vm && currentSignals!==signals) {
                const device=getter(ui,state,vm.context);
                visible=device===11 || device===22;
            }
            signals=currentSignals;
            result.push({requested,category:state.readU32(),axis:state.add(16).readU32(),
                delivered:ui.add(32).readU32(),signals,lastError:error,
                ...(vm ? {cursorVisible:visible} : {})});
        }
        if(vm)uiHold.push(vm);
        return result;
    },
    run(before, requested, axis, className = 'MouseController', method = 'CanShowMouseCursor', query = '') {
        className = className || 'MouseController';
        method = method || 'CanShowMouseCursor';
        const state = Memory.alloc(20);
        state.writeByteArray(new Uint8Array(20));
        state.writeU32(before);
        const device = Memory.alloc(8);
        device.writeU32(requested);
        device.add(4).writeU32(axis);
        const ui = Memory.alloc(64);
        uiHold.push(ui);
        ui.writeByteArray(new Uint8Array(64));
        ui.add(24).writePointer(ptr(1));
        ui.add(32).writeU32(before);
        const result = choose(state, device, ui);
        const vm = vmStack(className, method, query);
        const readBack = getter(ui, state, className === '<invalid>' ? ptr(0) : vm.context);
        // Keep every descriptor alive through the native call.
        if (!vm.objects.length) throw new Error('Missing fixture stack');
        return {state: [0, 4, 8, 12, 16].map(n => state.add(n).readU32()),
            device: [device.readU32(), device.add(4).readU32()],
            ui: ui.add(32).readU32(), readBack, lastError: result};
    }
};
