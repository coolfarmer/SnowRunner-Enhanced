'use strict';

// CONFIG is injected by capture_input.py. No automatic installation on load.
let listeners = [];
let events = [];
let dropped = 0;
let calls = 0;
let redirected = 0;
let uiNotificationsSuppressed = 0;
let menuSelectionResets = 0;
let menuFocusRestores = 0;
let menuRefreshFocusKeeps = 0;
let menuCursorReleases = 0;
let pendingMenuCursor = null;
let hudHintHook = null;
let navigationHitAreaHook = null;
let navigationHitAreaFix = null;
let navigationHitAreaRepairs = 0;
let navigationHitAreaRestoreSkipped = 0;
let mapNotificationHitAreaFix = null;
let mapNotificationHitAreaRepairs = 0;
let mapNotificationHitAreaRestoreSkipped = 0;
let hudHintRefreshes = 0;
let hudHintChecks = 0;
const hudHintPreferences = new Map();
let wheelNeutralFiltered = 0;
let lastWheelNeutralValue = null;
let faults = 0;
let getterCalls = 0;
let getterRedirected = 0;
let winchModeCalls = 0;
let winchModeRedirected = 0;
let winchHoverCalls = 0;
let winchHoverRedirected = 0;
let lastWinchMode = '';
let active = false;
let mode = 'observe';
let names = {};
let lastSelection = '';
let lastUiSelection = '';
let lastUiRead = '';
let bindings = null;
let preferredCategory = 0;
let wheelHintBaseline = null;
let wheelHintNoiseIgnored = 0;
let wheelHintActivations = 0;
let hintNotificationRequests = 0;
const counts = {};
const getterCallers = {};
const cursorSamples = new Map();

function emit(event) {
    if (events.length < 2048) events.push({timeMs: Date.now(), ...event});
    else dropped++;
}

function fail(error) {
    faults++;
    mode = 'observe';
    restoreNavigationHitArea();
    emit({kind: 'fault', error: String(error)});
}

function restoreNavigationHitArea() {
    if (navigationHitAreaFix && !navigationHitAreaFix.restore()) navigationHitAreaRestoreSkipped++;
    if (mapNotificationHitAreaFix && !mapNotificationHitAreaFix.restore()) mapNotificationHitAreaRestoreSkipped++;
}

function label(value) { return names[value] || 'unknown:' + value; }

function setMode(next) {
    if (next !== 'observe' && next !== 'ui-mouse-priority') throw new Error('Invalid mode');
    if (next === 'ui-mouse-priority' && faults) throw new Error('Fault latched; restart capture');
    mode = next;
    if (next === 'observe') restoreNavigationHitArea();
    pendingMenuCursor = null;
    lastWheelNeutralValue = null;
    hudHintPreferences.clear();
    wheelHintBaseline = null;
    emit({kind: 'mode', mode});
    return status();
}

function status() {
    return {active, mode, calls, redirected, uiNotificationsSuppressed, menuSelectionResets, menuFocusRestores, menuRefreshFocusKeeps, getterCalls, getterRedirected,
        menuCursorReleases, hudHintRefreshes, hudHintChecks, navigationHitAreaRepairs, navigationHitAreaRestoreSkipped, wheelHintNoiseIgnored, wheelHintActivations, hintNotificationRequests, wheelNeutralFiltered, faults, dropped, queued: events.length, preferredCategory: label(preferredCategory),
        mapNotificationHitAreaRepairs, mapNotificationHitAreaRestoreSkipped,
        winchModeCalls, winchModeRedirected, winchHoverCalls, winchHoverRedirected,
        counts, getterCallers};
}

function stop() {
    mode = 'observe';
    restoreNavigationHitArea();
    pendingMenuCursor = null;
    for (const listener of listeners) listener.detach();
    listeners = [];
    Interceptor.flush();
    hudHintHook = null;
    navigationHitAreaHook = null;
    navigationHitAreaFix = null;
    mapNotificationHitAreaFix = null;
    hudHintPreferences.clear();
    wheelHintBaseline = null;
    active = false;
    return status();
}

function install(b) {
    const attachVm = b.attachVm || hookHudHintUpdates;
    if (active) throw new Error('Already installed');
    const values = Object.values(b.ids);
    if (values.some(v => !Number.isInteger(v) || v <= 0 || v > 0xffffffff) ||
            new Set(values).size !== values.length) throw new Error('Invalid device identities');
    bindings = b;
    const uiScope = makeUiScope(b.stringPoolSlot, b.callerRoles);
    names = Object.fromEntries(Object.entries(b.ids).map(([k, v]) => [v, k]));
    const keep = {};
    for (const id of Object.values(b.ids)) {
        keep[id] = Memory.alloc(4);
        keep[id].writeU32(id);
    }
    const uiNotifications = new Map();
    const menuLists = new Map();
    const menuRefreshes = new Map();
    // The guarded focus setter writes +0x103, then exits when the Scaleform
    // value type at +0x70 is zero. This inert target skips only one proven
    // redundant blur, without calling SetFocus again or changing the real list.
    const quietFocus = Memory.alloc(0x200);
    quietFocus.writeByteArray(new Uint8Array(0x200));
    // The guarded native callback needs no vtable: it reads the mapping count
    // at +0x38, stores the category at +0x20, and dispatches via +0x18.
    // A zeroed object therefore follows the native no-subscriber path. Keep
    // it alive with these hooks, without changing the real listener or engine.
    const quietUi = Memory.alloc(0x40);
    quietUi.writeByteArray(new Uint8Array(0x40));
    function uiIdentity(object) {
        return [object.add(0x18).readPointer(), object.add(0x30).readPointer(),
            object.add(0x38).readU32()].join(':');
    }
    // Presentation ownership only. The native activity timestamp accepts even
    // a one-count steering change (observed at idle); never rewrite that stamp,
    // the device samples, or the engine category used by driving readers.
    function wheelHintSamples() {
        if (!b.wheelHintActivity) return null;
        const manager = b.engineStateSlot.readPointer().add(0x20).readPointer();
        if (manager.isNull()) return null;
        const count = manager.add(0x78).readS32();
        if (count < 0 || count > 128) throw new Error('Invalid input device count');
        const devices = manager.add(0x70).readPointer(), samples = new Map();
        for (let i = 0; i < count; i++) {
            const device = devices.add(i * 8).readPointer();
            if (device.isNull() || device.add(0x156c).readU32() !== b.ids.wheel) continue;
            // Guarded wheel update: buttons 0..127, axes 128..135,
            // and directional controls 136..139 in the common value array.
            const data = device.add(0x28).readByteArray(140 * 4);
            const values = new Float32Array(data);
            if (!Array.from(values).every(Number.isFinite)) return null;
            samples.set(device.toString(), values);
        }
        return samples.size ? samples : null;
    }
    function retainKeyboardHints() {
        if (mode !== 'ui-mouse-priority' || preferredCategory !== b.ids.keyboard || !wheelHintBaseline)
            return false;
        const samples = wheelHintSamples();
        if (!samples) { wheelHintBaseline = null; return false; }
        for (const [key, values] of samples) {
            const baseline = wheelHintBaseline.get(key);
            if (!baseline) return false; // newly connected wheel
            for (let i = 0; i < values.length; i++) {
                // Anchor to the last keyboard action, not the previous frame:
                // slow intentional movement must accumulate and take ownership.
                const changed = i >= 128 && i < 136 ?
                    Math.abs(values[i] - baseline[i]) >= 0.001 : values[i] !== baseline[i];
                if (changed) return false;
            }
        }
        return true;
    }
    function noticeWheelActivity(requested) {
        if (requested !== b.ids.wheel || !wheelHintBaseline ||
                preferredCategory !== b.ids.keyboard || mode !== 'ui-mouse-priority') return;
        if (!retainKeyboardHints()) {
            preferredCategory = requested;
            wheelHintBaseline = null;
            wheelHintActivations++;
            // The native category may already be wheel because of rejected
            // idle chatter. Queue its existing notification dispatcher once
            // so open panels receive the new presentation preference too.
            // The guarded activity_dispatch owns the subscriber lifetimes and
            // clears this byte after delivery; never call cached UI pointers.
            const engine = b.engineStateSlot.readPointer();
            if (engine.readU32() === requested && engine.add(4).readU8() === 0) {
                engine.add(4).writeU8(1);
                hintNotificationRequests++;
            }
            emit({kind:'wheel-hint-activity'});
        }
    }
    try {
        if (b.hudHintFramePush && CONFIG.features?.map !== false) {
            navigationHitAreaFix = makeNavButtonHitAreaFix(b.stringPoolSlot);
            navigationHitAreaHook = attachVm(b.hudHintFramePush, b.stringPoolSlot, (_vm, fn) => {
                if (mode === 'ui-mouse-priority' && navigationHitAreaFix.apply(fn)) {
                    navigationHitAreaRepairs++;
                    emit({kind:'navigation-hit-area-repair'});
                }
            }, 'NavButtonView', 'Show');
            listeners.push(navigationHitAreaHook);
            mapNotificationHitAreaFix = makeMapNotificationHitAreaFix(b.stringPoolSlot);
            listeners.push(attachVm(b.hudHintFramePush, b.stringPoolSlot, (_vm, fn) => {
                if (mode === 'ui-mouse-priority' && mapNotificationHitAreaFix.apply(fn)) {
                    mapNotificationHitAreaRepairs++;
                    emit({kind: 'map-notification-hit-area-repaired'});
                }
            }, 'MinimapUiSidepanelView', 'HideContractBtn'));
        }
        if (b.wheelNeutral && CONFIG.features?.vehicle !== false) {
            const zero = Memory.alloc(8);
            zero.writeU64(uint64('0x3000000000000')); // immutable float variant: 0
            listeners.push(Interceptor.attach(b.wheelNeutral, {
                onEnter(args) {
                    const savedError = this.lastError;
                    try {
                        if (mode !== 'ui-mouse-priority' || args[2].toUInt32() !== 1) return;
                        const operand = args[3];
                        if (operand.readU64().shr(48).toNumber() !== 3) return;
                        const value = operand.readFloat(), magnitude = Math.abs(value);
                        // Preserve real pedal travel, non-finite values, and
                        // values the original 1e-6 comparison already accepts.
                        if (!Number.isFinite(value) || magnitude < Math.fround(0.000001) ||
                                magnitude >= Math.fround(0.0001)) return;
                        const requested = b.engineStateSlot.readPointer().readU32();
                        const wheel = requested === b.ids.wheel || requested === b.ids.supplemental ||
                            (requested === b.ids.mouse && [b.ids.wheel, b.ids.supplemental].includes(preferredCategory));
                        if (!wheel || !uiScope.isWheelNeutralComparison(args[0], operand)) return;
                        // Redirect only the temporary AbsFloat operand for the
                        // verified neutral decision. The raw axes, VM arguments,
                        // global tolerance and intentional engine commands stay real.
                        args[3] = zero;
                        wheelNeutralFiltered++;
                        if (lastWheelNeutralValue !== value) {
                            emit({kind: 'wheel-neutral-filter', value, deadzone: 0.0001});
                            lastWheelNeutralValue = value;
                        }
                    } catch (e) { fail(e); }
                    finally { this.lastError = savedError; }
                }
            }));
        }
        if (CONFIG.features?.wheel_mouse !== false) {
        if (b.hudHintFramePush) {
            hudHintHook = attachVm(b.hudHintFramePush, b.stringPoolSlot, (vm, fn) => {
                try {
                    if (mode !== 'ui-mouse-priority') return;
                    hudHintChecks++;
                    const update = uiScope.hudHintUpdate(vm, fn);
                    if (!update) return;
                    const current = b.engineStateSlot.readPointer().readU32();
                    noticeWheelActivity(current);
                    const preference = preferredCategory || current;
                    if (!preference || hudHintPreferences.get(update.key) === preference) return;
                    // The game's own cache treats keyboard and mouse as equal.
                    // Wheel input is delivered as mouse for interaction, so it
                    // needs one presentation refresh when preference changes.
                    update.forced.writeU8(1);
                    if (!hudHintPreferences.has(update.key) && hudHintPreferences.size >= 256)
                        hudHintPreferences.delete(hudHintPreferences.keys().next().value);
                    hudHintPreferences.set(update.key, preference);
                    hudHintRefreshes++;
                    emit({kind:'hud-hint-refresh', preference:label(preference)});
                } catch (e) { fail(e); }
            });
            listeners.push(hudHintHook);
        }
        if (b.menuCursor) {
            const setDragging = new NativeFunction(b.menuCursor.setDragging, 'void', ['pointer', 'uint8']);
            listeners.push(Interceptor.attach(b.menuCursor.update, {
                onEnter(args) {
                    const pending = pendingMenuCursor;
                    if (!pending) return;
                    const savedError = this.lastError;
                    try {
                        if (mode !== 'ui-mouse-priority' || Date.now() - pending.time > 500) {
                            pendingMenuCursor = null;
                            return;
                        }
                        // Consume on the active camera's next update, on the
                        // opening thread. Never retain a camera object between
                        // frames or force the cursor throughout the open menu.
                        const camera = args[0];
                        if (pending.thread !== this.threadId || camera.add(0x14).readU8() !== 1) return;
                        pendingMenuCursor = null;
                        if (camera.add(0x15).readU8() !== 1) return;
                        // The native setter restores the saved mouse position
                        // and clears dragging; the next click can capture again.
                        setDragging(camera, 0);
                        menuCursorReleases++;
                        emit({kind: 'menu-cursor-release'});
                    } catch (e) { pendingMenuCursor = null; fail(e); }
                    finally { this.lastError = savedError; }
                }
            }));
        }
        listeners.push(Interceptor.attach(b.selector, {
            onEnter(args) {
                const savedError = this.lastError;
                this.observation = null;
                try {
                    const state = args[0];
                    const requested = args[1].readU32();
                    const before = state.readU32();
                    noticeWheelActivity(requested);
                    // Engine category must remain untouched: changing it disables driving.
                    const protect = false;
                    calls++;
                    const name = label(requested);
                    counts[name] = (counts[name] || 0) + 1;
                    this.observation = {state, requested, before, protect};
                } catch (e) { fail(e); }
                finally { this.lastError = savedError; }
            },
            onLeave() {
                const savedError = this.lastError;
                try {
                    const o = this.observation;
                    if (!o) return;
                    const after = o.state.readU32();
                    const key = [o.state, o.before, o.requested, after, o.protect].join(':');
                    if (key !== lastSelection) {
                        emit({kind: 'selection', object: String(o.state), before: label(o.before),
                            requested: label(o.requested), after: label(after), redirected: o.protect});
                        lastSelection = key;
                    }
                } catch (e) { fail(e); }
                finally { this.lastError = savedError; }
            }
        }));
        listeners.push(Interceptor.attach(b.uiCallback, {
            onEnter(args) {
                const savedError = this.lastError;
                this.uiObservation = null;
                try {
                    const object = args[0];
                    const engine = args[1];
                    const requested = engine.readU32();
                    const before = object.add(0x20).readU32();
                    if (!preferredCategory) preferredCategory = before;
                    const idleWheel = requested === b.ids.wheel && retainKeyboardHints();
                    const retainPreference = requested === b.ids.mouse &&
                        [b.ids.wheel, b.ids.supplemental, b.ids.keyboard].includes(preferredCategory);
                    if (!retainPreference && !idleWheel) preferredCategory = requested;
                    if (idleWheel) wheelHintNoiseIgnored++;
                    if (requested === b.ids.keyboard && mode === 'ui-mouse-priority')
                        wheelHintBaseline = wheelHintSamples();
                    else if (![b.ids.keyboard, b.ids.mouse, b.ids.wheel].includes(requested))
                        wheelHintBaseline = null;
                    // Winch handlers also consume the event argument directly.
                    // Keep UI interaction mouse-capable; hint readers separately
                    // receive preferredCategory (wheel until a keyboard input).
                    const isWheel = requested === b.ids.wheel || requested === b.ids.supplemental;
                    const protect = mode === 'ui-mouse-priority' && isWheel;
                    const delivered = protect ? b.ids.mouse : requested;
                    const identity = uiIdentity(object);
                    const previous = uiNotifications.get(object.toString());
                    const wheelContext = isWheel || (requested === b.ids.mouse &&
                        [b.ids.wheel, b.ids.supplemental].includes(preferredCategory));
                    const suppressed = mode === 'ui-mouse-priority' && wheelContext &&
                        before === delivered && previous && previous.mode === mode &&
                        previous.preference === preferredCategory && previous.identity === identity;
                    // This callback reads only the category word from its argument.
                    // The engine's active category and input dispatch remain unchanged.
                    if (protect) { args[1] = keep[b.ids.mouse]; redirected++; }
                    if (suppressed) { args[0] = quietUi; uiNotificationsSuppressed++; }
                    this.uiObservation = {object, engine, requested, before, protect,
                        suppressed: !!suppressed, identity, preference: preferredCategory, mode};
                } catch (e) { fail(e); }
                finally { this.lastError = savedError; }
            },
            onLeave() {
                const savedError = this.lastError;
                try {
                    const o = this.uiObservation;
                    if (!o) return;
                    const after = o.object.add(0x20).readU32();
                    const engineAfter = o.engine.readU32();
                    const objectKey = o.object.toString();
                    if (!uiNotifications.has(objectKey) && uiNotifications.size >= 256)
                        uiNotifications.delete(uiNotifications.keys().next().value);
                    uiNotifications.set(objectKey, {identity: o.identity,
                        preference: o.preference, mode: o.mode});
                    const key = [o.object, o.before, o.requested, after, o.protect, o.suppressed].join(':');
                    if (key !== lastUiSelection) {
                        emit({kind: 'ui-selection', object: String(o.object), before: label(o.before),
                            requested: label(o.requested), after: label(after),
                            engineAfter: label(engineAfter), redirected: o.protect,
                            notificationSuppressed: o.suppressed});
                        lastUiSelection = key;
                    }
                } catch (e) { fail(e); }
                finally { this.lastError = savedError; }
            }
        }));
        // A bare instruction callback avoids treating this mid-function site
        // as a function entry (its stack pointer is already inside the prologue).
        listeners.push(Interceptor.attach(b.uiGetter, function () {
                const savedError = this.lastError;
                try {
                    // Verified instruction site after the original loads the
                    // engine pointer into R10 and the UI object into R11.
                    // Redirect this local register only, never the global state.
                    const object = this.context.r11;
                    const engine = this.context.r10;
                    const requested = engine.readU32();
                    noticeWheelActivity(requested);
                    const before = object.add(0x20).readU32();
                    const isWheel = requested === b.ids.wheel || requested === b.ids.supplemental;
                    const preferred = preferredCategory || before;
                    const wasWheel = preferred === b.ids.wheel || preferred === b.ids.supplemental;
                    const scope = uiScope(this.context);
                    let delivered = requested;
                    if (mode === 'ui-mouse-priority') {
                        // Pointer/map behavior is independent from the displayed hints.
                        if (scope.role === 'pointer' && (isWheel ||
                                (wasWheel && requested === b.ids.mouse))) delivered = b.ids.mouse;
                        // Presentation includes wheel-specific menu actions as well
                        // as hints. Driving readers also handle mouse picking and
                        // must see the original device.
                        if (scope.role === 'presentation' &&
                                wasWheel && requested === b.ids.mouse) delivered = preferred;
                        if (scope.role === 'presentation' && preferred === b.ids.keyboard &&
                                wheelHintBaseline && (requested === b.ids.wheel || requested === b.ids.mouse))
                            delivered = preferred;
                    }
                    const protect = delivered !== requested;
                    getterCalls++;
                    if (Object.keys(getterCallers).length < 128 || getterCallers[scope.caller]) {
                        const counter = getterCallers[scope.caller] || {calls: 0, redirected: 0};
                        counter.calls++;
                        if (protect) counter.redirected++;
                        getterCallers[scope.caller] = counter;
                    }
                    if (protect) { this.context.r10 = keep[delivered]; getterRedirected++; }
                    const key = [object, before, requested, protect].join(':');
                    if (key !== lastUiRead) {
                        emit({kind: 'ui-read', requested: label(requested),
                            delivered: label(delivered), redirected: protect,
                            caller: scope.caller, role: scope.role});
                        lastUiRead = key;
                    }
                } catch (e) { fail(e); }
                finally { this.lastError = savedError; }
        }));
        if (b.menuList) {
            const selectIndex = new NativeFunction(b.menuList.selectIndex, 'void', ['pointer', 'int']);
            listeners.push(Interceptor.attach(b.menuList.setData, {
                onEnter(args) {
                    const savedError = this.lastError;
                    try {
                        menuRefreshes.delete(args[0].toString());
                        if (!uiScope.hasCaller(this.context, 'HudInteractionPanelUiView.SetData')) return;
                        let scriptObject = null;
                        if (b.menuKeys) {
                            const owner = uiScope.receiver(this.context, 'UiListAdapter.SetData') ||
                                uiScope.receiver(this.context, 'UiListAdapter.SetDataAndInitialIndex');
                            scriptObject = uiScope.receiver(this.context, 'UiCoreList.SetData');
                            if (owner && scriptObject && !owner.isNull() && !scriptObject.isNull()) {
                                if (menuLists.size >= 16 && !menuLists.has(owner.toString()))
                                    menuLists.delete(menuLists.keys().next().value);
                                menuLists.set(owner.toString(), {object: args[0], scriptObject});
                            }
                        }
                        if (mode !== 'ui-mouse-priority') return;
                        const engine = b.engineStateSlot.readPointer();
                        const requested = engine.readU32();
                        if (b.menuCursor && Object.values(b.ids).includes(requested) &&
                                uiScope.hasCaller(this.context, 'TruckInputController.TurnOnFunctions')) {
                            pendingMenuCursor = {thread: this.threadId, time: Date.now()};
                        }
                        const wheel = requested === b.ids.wheel || requested === b.ids.supplemental ||
                            (requested === b.ids.mouse &&
                             [b.ids.wheel, b.ids.supplemental].includes(preferredCategory));
                        if (!wheel) return;
                        const object = args[0];
                        if (scriptObject && object.add(0x104).readU8() === 1 &&
                                object.add(0x103).readU8() === 1 && object.add(0x51).readU8() === 0 &&
                                object.add(0x1d0).readS32() >= 0 && engine.add(0xc4).readU32() !== 0) {
                            const reference = object.add(0x18).readPointer();
                            const frame = uiScope.frame(this.context, 'HudInteractionPanelUiView.SetData');
                            if (frame && !reference.isNull() &&
                                    reference.readPointer().and('0xff00ffffffffffff').equals(scriptObject)) {
                                if (menuRefreshes.size >= 16)
                                    menuRefreshes.delete(menuRefreshes.keys().next().value);
                                menuRefreshes.set(object.toString(), {vm: this.context.rsi, frame,
                                    fn: frame.add(8).readPointer(), argv: frame.readPointer(),
                                    reference, scriptObject, thread: this.threadId, time: Date.now()});
                            }
                        }
                        // Only clear the old renderer selection when reopening
                        // a list made non-focusable by Deactivate/HidePanel.
                        // An active list can refresh later (e.g. engine state)
                        // and must keep its selection through that replacement.
                        if (object.add(0x104).readU8() !== 0) return;
                        // SetData has already saved the action to restore. Use
                        // the game's own setter (also updates Scaleform).
                        // Negative index notifications return before saving any
                        // action in UiListAdapter.HandleOnIndexChange.
                        const before = object.add(0x1d0).readS32();
                        if (before < 0) return;
                        selectIndex(object, -1);
                        menuSelectionResets++;
                        emit({kind: 'menu-selection-reset', object: String(object), before});
                    } catch (e) { fail(e); }
                    finally { this.lastError = savedError; }
                }
            }));
        }
        if (b.menuKeys) {
            listeners.push(Interceptor.attach(b.menuKeys.focus, {
                onEnter(args) {
                    const savedError = this.lastError;
                    try {
                        if ((args[1].toUInt32() & 255) !== 0) return;
                        const object = args[0], key = object.toString();
                        const pending = menuRefreshes.get(key);
                        // Consume on the first blur, even when it belongs to
                        // another path. A later camera/close must never be kept.
                        menuRefreshes.delete(key);
                        if (!pending || mode !== 'ui-mouse-priority' || pending.thread !== this.threadId ||
                                Date.now() - pending.time > 1000) return;
                        const frame = pending.vm.add(0x30).readPointer();
                        if (!frame.equals(pending.frame) || !frame.add(8).readPointer().equals(pending.fn) ||
                                !frame.readPointer().equals(pending.argv) ||
                                !uiScope.hasCaller({rsi: pending.vm}, 'HudInteractionPanelUiView.SetData')) return;
                        if (!object.add(0x18).readPointer().equals(pending.reference) ||
                                !pending.reference.readPointer().and('0xff00ffffffffffff').equals(pending.scriptObject) ||
                                object.add(0x103).readU8() !== 1 || object.add(0x104).readU8() !== 1 ||
                                object.add(0x51).readU8() !== 0 || object.add(0x1d0).readS32() < 0) return;
                        // Only the original view frame may consume this marker.
                        // Nested FocusBtn calls, other views, reopening and
                        // previously unfocused lists keep their normal setter.
                        args[0] = quietFocus;
                        menuRefreshFocusKeeps++;
                        emit({kind: 'menu-refresh-focus-keep', object: key,
                            selection: object.add(0x1d0).readS32()});
                    } catch (e) { fail(e); }
                    finally { this.lastError = savedError; }
                }
            }));
            const focus = new NativeFunction(b.menuKeys.focus, 'void', ['pointer', 'uint8']);
            listeners.push(Interceptor.attach(b.menuKeys.dispatch, {
                onEnter(args) {
                    const savedError = this.lastError;
                    try {
                        if (mode !== 'ui-mouse-priority' || args[2].toUInt32() !== 2) return;
                        const key = args[3].readS32(), event = args[3].add(8).readS32();
                        if (event !== 5 || ![37, 38, 39, 40].includes(key)) return;
                        const context = {rsi: args[0]};
                        if (!uiScope.hasCaller(context, 'SslUiInputScreenManagerMr2.PressWheel')) return;
                        const owner = uiScope.receiver(context, 'UiListAdapter.GfxPress');
                        const list = owner && menuLists.get(owner.toString());
                        if (!list) return;
                        const engine = b.engineStateSlot.readPointer();
                        const requested = engine.readU32();
                        const wheel = requested === b.ids.wheel || requested === b.ids.supplemental ||
                            (requested === b.ids.mouse &&
                             [b.ids.wheel, b.ids.supplemental].includes(preferredCategory));
                        if (!wheel || engine.add(0xc4).readU32() === 0) return;
                        const object = list.object, reference = object.add(0x18).readPointer();
                        // Match the live script binding and leave disabled lists
                        // alone. Only an explicit wheel navigation press takes
                        // focus back; mouse clicks/motion and wheel axes do not.
                        if (reference.isNull() || !reference.readPointer().and('0xff00ffffffffffff').equals(list.scriptObject) ||
                                object.add(0x104).readU8() !== 1 || object.add(0x51).readU8() !== 0 ||
                                object.add(0x103).readU8() !== 0) return;
                        focus(object, 1);
                        menuFocusRestores++;
                        emit({kind: 'menu-focus-restore', object: String(object), key});
                    } catch (e) { fail(e); }
                    finally { this.lastError = savedError; }
                }
            }));
        }
        if (b.gamepadMode) {
            const allowed = new Set(b.winchCallers.map(p => p.toString()));
            listeners.push(Interceptor.attach(b.gamepadMode, {
                onEnter() { this.winchCaller = allowed.has(this.returnAddress.toString()) ?
                    this.returnAddress.toString() : null; },
                onLeave(result) {
                    if (!this.winchCaller) return;
                    const savedError = this.lastError;
                    try {
                        const requested = b.engineStateSlot.readPointer().readU32();
                        const original = result.toUInt32() & 255;
                        const wheel = requested === b.ids.wheel || requested === b.ids.supplemental ||
                            (requested === b.ids.mouse &&
                            [b.ids.wheel,b.ids.supplemental].includes(preferredCategory));
                        const protect = mode === 'ui-mouse-priority' && wheel && original !== 0;
                        winchModeCalls++;
                        if (protect) { result.replace(0); winchModeRedirected++; }
                        const key = [this.winchCaller, requested, original, protect].join(':');
                        if (key !== lastWinchMode) {
                            emit({kind:'winch-mode-read', caller:this.winchCaller,
                                device:label(requested), original, delivered:protect ? 0 : original});
                            lastWinchMode = key;
                        }
                    } catch(e) { fail(e); }
                    finally { this.lastError = savedError; }
                }
            }));
        }
        if (b.winchHover) {
            // This mouse-idle timer is advanced by the native wheel UI path.
            // The script hover test still succeeds, but this later test hides
            // the native winch area. Bypass only the timer veto, preserving R12
            // (the preceding truck/interaction eligibility checks) and the
            // original global timer used by the camera and other consumers.
            const pendingHover = new Map();
            listeners.push(Interceptor.attach(b.winchHover.before, function () {
                const savedError = this.lastError;
                try {
                    winchHoverCalls++;
                    const requested = b.engineStateSlot.readPointer().readU32();
                    const wheel = requested === b.ids.wheel || requested === b.ids.supplemental ||
                        (requested === b.ids.mouse &&
                         [b.ids.wheel, b.ids.supplemental].includes(preferredCategory));
                    if (mode === 'ui-mouse-priority' && wheel) {
                        pendingHover.set(this.threadId, {stack: this.context.rsp.toString(),
                            eligible: this.context.r12.toUInt32() & 255});
                    } else pendingHover.delete(this.threadId);
                } catch (e) { fail(e); }
                finally { this.lastError = savedError; }
            }));
            listeners.push(Interceptor.attach(b.winchHover.after, function () {
                const savedError = this.lastError;
                try {
                    const pending = pendingHover.get(this.threadId);
                    pendingHover.delete(this.threadId);
                    if (mode !== 'ui-mouse-priority' || !pending ||
                            pending.stack !== this.context.rsp.toString()) return;
                    if ((this.context.r12.toUInt32() & 255) !== pending.eligible) {
                        this.context.r12 = ptr(pending.eligible);
                        winchHoverRedirected++;
                    }
                } catch (e) { fail(e); }
                finally { this.lastError = savedError; }
            }));
        }
        if (b.cursor) listeners.push(Interceptor.attach(b.cursor, {
            onEnter(args) {
                const savedError = this.lastError;
                this.cursorEvent = null;
                try {
                    // Ignore other modules' cursor calls, including overlays.
                    if (this.returnAddress.compare(b.base) < 0 ||
                            this.returnAddress.compare(b.base.add(b.size)) >= 0) return;
                    const caller = this.returnAddress.sub(b.base).toString();
                    const time = Date.now();
                    const sample = cursorSamples.get(caller);
                    if (sample && time - sample.time < 100) return;
                    const event = {kind: 'cursor', callerRva: caller,
                        x: args[0].toInt32(), y: args[1].toInt32()};
                    if (!sample) {
                        event.stack = Thread.backtrace(this.context, Backtracer.ACCURATE)
                            .slice(0, 16).map(a => {
                                const m = Process.findModuleByAddress(a);
                                return m ? m.name + '+' + a.sub(m.base) : String(a);
                            });
                    }
                    cursorSamples.set(caller, {time});
                    this.cursorEvent = event;
                } catch (e) { fail(e); }
                finally { this.lastError = savedError; }
            },
            onLeave(result) {
                const savedError = this.lastError;
                if (this.cursorEvent) emit({...this.cursorEvent, success: result.toInt32() !== 0});
                this.lastError = savedError;
            }
        }));
        } // wheel_mouse hooks
        active = true;
        setMode('observe');
        Interceptor.flush();
        return status();
    } catch (e) { stop(); throw e; }
}

function startGame(attachVm = hookHudHintUpdates) {
    if (CONFIG.test) throw new Error('Test agent cannot attach to game');
    if (Process.arch !== 'x64' || Process.platform !== 'windows') throw new Error('Windows x64 required');
    const game = Process.mainModule;
    const normalize = p => p.replaceAll('/', '\\').toLowerCase();
    if (game.name.toLowerCase() !== 'snowrunner.exe' ||
            normalize(game.path) !== normalize(CONFIG.gamePath)) throw new Error('Wrong executable');
    for (const guard of CONFIG.profile.guards) {
        const actual = new Uint8Array(game.base.add(guard.rva).readByteArray(guard.hex.length / 2));
        const hex = Array.from(actual, v => v.toString(16).padStart(2, '0')).join('');
        if (hex !== guard.hex) throw new Error('Code mismatch: ' + guard.name);
    }
    const ids = Object.fromEntries(Object.entries(CONFIG.profile.ids)
        .map(([name, rva]) => [name, game.base.add(rva).readU32()]));
    return install({attachVm, selector: game.base.add(CONFIG.profile.selectorRva),
        uiCallback: game.base.add(CONFIG.profile.uiCallbackRva), ids,
        uiGetter: game.base.add(CONFIG.profile.uiGetterSiteRva),
        stringPoolSlot: game.base.add(CONFIG.profile.stringPoolSlotRva),
        callerRoles: CONFIG.profile.callerRoles,
        gamepadMode: game.base.add(CONFIG.profile.gamepadModeRva),
        engineStateSlot: game.base.add(CONFIG.profile.engineStateSlotRva),
        winchCallers: CONFIG.profile.winchGamepadCallers.map(rva => game.base.add(rva)),
        winchHover: {before: game.base.add(CONFIG.profile.winchHoverTimerBeforeRva),
            after: game.base.add(CONFIG.profile.winchHoverTimerAfterRva)},
        menuList: {setData: game.base.add(CONFIG.profile.menuListSetDataRva),
            selectIndex: game.base.add(CONFIG.profile.menuListSelectIndexRva)},
        menuKeys: {dispatch: game.base.add(CONFIG.profile.menuKeyDispatchRva),
            focus: game.base.add(CONFIG.profile.menuFocusSetterRva)},
        menuCursor: {update: game.base.add(CONFIG.profile.menuCursorCameraUpdateRva),
            setDragging: game.base.add(CONFIG.profile.menuCursorSetDraggingRva)},
        wheelNeutral: game.base.add(CONFIG.profile.wheelNeutralAbsFloatRva),
        wheelHintActivity: CONFIG.profile.guards.some(g => g.name === 'wheel_state_values'),
        hudHintFramePush: game.base.add(CONFIG.profile.guards.find(g => g.name === 'vm_frame_push_entry').rva),
        cursor: Process.getModuleByName('user32.dll').getExportByName('SetCursorPos'),
        base: game.base, size: game.size});
}

rpc.exports = {
    start: startGame,
    mode: setMode,
    status,
    drain() { const result = events; events = []; return result; },
    stop,
    fixturePreference(value) {
        if (!CONFIG.test) throw new Error('Fixture only');
        preferredCategory = value;
    },
    fixture(address, uiAddress, getterAddress, poolSlot, roles, ids, winch) {
        if (!CONFIG.test || Process.mainModule.name.toLowerCase() === 'snowrunner.exe')
            throw new Error('Fixture only');
        return install({selector: ptr(address), uiCallback: ptr(uiAddress), uiGetter: ptr(getterAddress),
            stringPoolSlot: ptr(poolSlot), callerRoles: roles, ids,
            gamepadMode: ptr(winch.predicate), engineStateSlot: ptr(winch.engineSlot),
            winchCallers: winch.callers.map(p=>ptr(p)),
            menuList: {setData: ptr(winch.menuData), selectIndex: ptr(winch.menuSelect)},
            menuKeys: winch.menuKeys ? {dispatch: ptr(winch.menuKeys), focus: ptr(winch.menuFocus)} : null,
            menuCursor: winch.cameraUpdate ? {update: ptr(winch.cameraUpdate), setDragging: ptr(winch.cameraDragging)} : null,
            wheelNeutral: winch.wheelNeutral ? ptr(winch.wheelNeutral) : null,
            wheelHintActivity: !!winch.wheelHintActivity,
            hudHintFramePush: winch.framePush ? ptr(winch.framePush) : null,
            winchHover: {before: ptr(winch.hoverSite), after: ptr(winch.hoverResume)}});
    }
};
