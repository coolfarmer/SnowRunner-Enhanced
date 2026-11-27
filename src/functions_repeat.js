'use strict';

// Drive repeats from SnowRunner's game thread using the vertical UI events that
// the Functions adapter produced for this press. No physical bindings are assumed.
function startFunctionsRepeat(profile, attach = hookHudHintUpdates) {
    const base = Process.mainModule.base;
    const pool = base.add(profile.stringPoolSlotRva);
    const scope = makeUiScope(pool, {});
    const frame = base.add(profile.guards.find(g => g.name === 'vm_frame_push').rva);
    const site = base.add(profile.functionsCallRva);
    const target = base.add(profile.functionsTargetRva);
    if (site.readU8() !== 0xe8 || !site.add(5 + site.add(1).readS32()).equals(target))
        throw Error('Unsupported Functions key dispatch');
    const entry = '48 89 5c 24 08 57 48 83 ec 70 48 63 42 08 48 8b da 48 8b f9';
    if (Memory.scanSync(target, 20, entry).length !== 1)
        throw Error('Unsupported Functions dispatch target');
    const dispatch = new NativeFunction(target, 'void', ['pointer','pointer','uint8']);
    const user = Process.getModuleByName('user32.dll');
    const foreground = new NativeFunction(user.getExportByName('GetForegroundWindow'),'pointer',[]);
    const windowPid = new NativeFunction(user.getExportByName('GetWindowThreadProcessId'),'uint32',['pointer','pointer']);
    const pid = Memory.alloc(4), hooks = [];
    let adapter = null, press = null, held = null, fault = null;
    function clear() { press = null; held = null; }
    function guarded(callback) {
        return function (...args) {
            if (fault) return;
            try { callback.apply(this,args); }
            catch (error) { clear(); fault = String(error); }
        };
    }
    function watch(cls, method, callback) {
        hooks.push(attach(frame, pool, guarded(vm => callback(vm.add(0x18).readPointer())), cls, method, true));
    }
    function stop() {
        clear();
        for (const hook of hooks.splice(0).reverse()) hook.detach();
        Interceptor.flush();
    }
    try {
        hooks.push(Interceptor.attach(base.add(profile.menuListSetDataRva), {onEnter: guarded(function () {
            if (!scope.hasCaller(this.context,'HudInteractionPanelUiView.SetData')) return;
            adapter = scope.receiver(this.context,'UiListAdapter.SetData') ||
                      scope.receiver(this.context,'UiListAdapter.SetDataAndInitialIndex');
            clear();
        })}));
        const object = args => args.readPointer().and('0xffffffffffff');
        watch('SslUiInputEvent','Press', args => {
            clear(); press = {event:object(args), thread:Process.getCurrentThreadId(), time:Date.now()};
        });
        watch('UiListAdapter','GfxPress', args => {
            const key = args.add(8).readS32();
            if (!press || !adapter || !object(args).equals(adapter) || (key !== 38 && key !== 40) ||
                press.thread !== Process.getCurrentThreadId() || Date.now()-press.time > 200) return;
            held = {...press,key,packets:[],next:Date.now()+420};
            press = null;
        });
        watch('SslUiInputEvent','Release', args => {
            if ((held || press)?.event.equals(object(args))) clear();
        });
        watch('UiListAdapter','Deactivate', args => { if (adapter && object(args).equals(adapter)) clear(); });
        watch('HudInteractionPanelUiView','HidePanel', clear);
        hooks.push(Interceptor.attach(site,guarded(function () {
            if (!held || held.thread !== this.threadId || held.packets.length === 2) return;
            const packet = this.context.rdx;
            if (packet.add(8).readS32() !== held.key || packet.readS32() !== 5+held.packets.length) {clear(); return;}
            held.ui = this.context.rcx;
            const copy = Memory.alloc(24);
            copy.writeByteArray(packet.readByteArray(24));
            held.packets.push(copy);
        })));
        watch('TruckInputController','Update', () => {
            if (!held || held.packets.length !== 2 || Date.now() < held.next || Process.getCurrentThreadId() !== held.thread) return;
            windowPid(foreground(),pid);
            const manager = base.add(profile.functionsManagerSlotRva).readPointer();
            const engine = base.add(profile.engineStateSlotRva).readPointer();
            if (pid.readU32() !== Process.id || engine.isNull() || !engine.add(0xc4).readU32() ||
                manager.isNull() || !manager.add(0x68).readPointer().equals(held.ui) || held.ui.add(8).readPointer().isNull()) {clear(); return;}
            const {packets,ui} = held;
            held.next = Date.now()+140;
            for (const packet of packets) dispatch(ui,packet,1);
        });
    } catch (error) { stop(); throw error; }
    return {stop,status:()=>fault || 'ready',hooks};
}
