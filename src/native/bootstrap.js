'use strict';

// Core UI belongs to the plugin, never to a configurable enhancement group.
CONFIG.features = {wheel_mouse: ENHANCED_HOST.wheelMouse !== false, map: ENHANCED_HOST.map !== false, vehicle: ENHANCED_HOST.vehicle === true};
let attempts = 0, timer = null, featureState = 'waiting', settingsMenu = null;
let vehicle = null, vehicleError = null;
let vehicleWinch = null, vehicleWinchError = null;
let truckSearch = null, truckSearchError = null;
let lastReportExtra = {};
let fastVmHooks = null;
let menuFailure = null, functionsRepeat = null, repeatState = ENHANCED_HOST.general ? 'pending' : 'disabled';
let nativeRuntime = null, nativeRuntimeTime = 0;
if (typeof recv === 'function') {
    const receive = () => recv('enhanced-runtime', message => {
        if (message.payload?.processId === Process.id) {
            nativeRuntime = message.payload.features;
            nativeRuntimeTime = Date.now();
        }
        receive();
    });
    receive();
}
function menuFeatureStates() {
    return enhancedFeatureStates(ENHANCED_HOST.modules || CONFIG.features, {
        inputState: featureState, input: nativeAgent.status(),
        native: Date.now() - nativeRuntimeTime < 6500 ? nativeRuntime : null,
        menu: settingsMenu?.status(), vehicle: vehicle?.status(), vehicleError,
        vehicleWinch: vehicleWinch?.status(), vehicleWinchError, truckSearch: truckSearch?.status(), truckSearchError,
        repeat: functionsRepeat?.status() || repeatState
    });
}
function reportNative(state, extra = {}) {
    featureState = state; lastReportExtra = extra;
    const {vehicle: vehicleEnabled, ...inputFeatures} = CONFIG.features;
    send({enhancedStatus: {schemaVersion: 1, version: '1.0.1',
        gameSha256: ENHANCED_HOST.gameSha256, timeUtc: new Date().toISOString(), processId: Process.id,
        components: {...(fastVmHooks ? {vm_dispatch:fastVmHooks.status()} : {}), functions_repeat: {status: functionsRepeat?.status() || repeatState}, settings_menu: settingsMenu ? settingsMenu.status() :
            {enabled: true, status: menuFailure ? 'error' : state, reason: menuFailure}},
        features: {vehicle: {enabled: vehicleEnabled, status: vehicleEnabled ? menuFeatureStates().vehicle : 'disabled', ...vehicle?.status(),
            reverseError: vehicleError, truckSearch: truckSearch?.status() || {status: truckSearchError ? 'error' : vehicleEnabled ? 'waiting' : 'disabled', fault: truckSearchError}, winch: vehicleWinch?.status() || {status: vehicleWinchError ? 'error' : vehicleEnabled ? 'waiting' : 'disabled', fault: vehicleWinchError}}, ...Object.fromEntries(Object.entries(inputFeatures).map(([key, enabled]) =>
            [key, enabled ? {enabled, status: state, ...extra} : {enabled, status: 'disabled'}]))},
        validation: 'Preview: see packaged validation notes'}});
}
function attemptStart() {
    attempts++;
    const wantsAgent = Object.values(CONFIG.features).some(Boolean);
    let result, info;
    try {
        info = nativeProbe.describe();
        if (info.name.toLowerCase() !== 'snowrunner.exe') throw new Error('Wrong executable');
        const matches = nativeProbe.scan(NATIVE_SIGNATURES, info.sections);
        result = resolveNativeProfile(CONFIG.profile, NATIVE_SIGNATURES, matches, info.sections);
        if (wantsAgent) {
            const identities = Object.values(result.profile.ids).map(rva => Process.mainModule.base.add(rva).readU32());
            if (identities.some(value => value === 0) || new Set(identities).size !== identities.length)
                throw new Error('Waiting for input categories to initialize');
        }
    } catch (error) {
        const failure = error.details || {reason: String(error.message).slice(0, 160)};
        if (attempts < 30) {
            reportNative('waiting', {attempt: attempts, compatibility: failure});
            timer = setTimeout(attemptStart, 2000);
        } else reportNative('incompatible', {compatibility: failure});
        return;
    }
    CONFIG.profile = result.profile;
    if(typeof makeFastVmHooks === 'function') {
        try { fastVmHooks=makeFastVmHooks(result.profile); }
        catch(error) { menuFailure=String(error);reportNative('error',{reason:menuFailure});return; }
    }
    let agentState = 'active', agentReason;
    if (wantsAgent) {
        try { nativeAgent.start(fastVmHooks?.attach); nativeAgent.mode('ui-mouse-priority'); }
        catch (_) {
            if (nativeAgent.status().active) nativeAgent.stop();
            agentState = 'error'; agentReason = 'Hook installation failed; correction stopped';
        }
    }
    if (ENHANCED_HOST.vehicle === true) {
        try {
            const matches = nativeProbe.scan(VEHICLE_SIGNATURES, info.sections);
            const resolved = resolveNativeProfile(VEHICLE_PROFILE, VEHICLE_SIGNATURES, matches, info.sections);
            vehicle = makeVehicleReverse(resolved.profile);
            vehicle.set(ENHANCED_HOST.automaticReverse !== false);
        } catch (error) { vehicleError = String(error); vehicle = null; }
        try {
            const matches = nativeProbe.scan(WINCH_SIGNATURES, info.sections);
            const resolved = resolveNativeProfile(WINCH_PROFILE, WINCH_SIGNATURES, matches, info.sections);
            vehicleWinch = makeVehicleWinchRange(resolved.profile);
        } catch (error) { vehicleWinchError = String(error); vehicleWinch = null; }
    }
    if (ENHANCED_HOST.vehicle === true) {
        try {
            const matches = nativeProbe.scan(TRUCK_SEARCH_SIGNATURES, info.sections);
            const resolved = resolveNativeProfile(TRUCK_SEARCH_PROFILE, TRUCK_SEARCH_SIGNATURES, matches, info.sections);
            truckSearch = makeVehicleTruckSearch(resolved.profile,
                Process.mainModule.base.add(result.profile.guards.find(g => g.name === 'vm_frame_push').rva + 8),
                Process.mainModule.base.add(result.profile.stringPoolSlotRva), ENHANCED_HOST.truckStorageSearch === true,
                fastVmHooks?.attach);
        } catch (error) { truckSearchError = String(error); }
    }
    // The optional agent validates original entry bytes before either component
    // attaches to the shared VM entry point. Its failure does not disable the UI.
    try {
        const validPreference = value => Number.isInteger(value) && value >= 0 && value <= 100 ? value : 50;
        const preferences = {schemaVersion: 5, truckStorageSearch: ENHANCED_HOST.truckStorageSearch===true, automaticReverse: ENHANCED_HOST.automaticReverse!==false, zoomSensitivity: validPreference(ENHANCED_HOST.zoomSensitivity),
            panningSensitivity: validPreference(ENHANCED_HOST.panningSensitivity), keepNorthUp: ENHANCED_HOST.keepNorthUp===true};
        const savePreference = (key, value) => { preferences[key] = value; send({enhancedSettings: {...preferences}}); };
        const menuGuard = result.profile.guards.find(g => g.name === 'vm_frame_push_entry');
        const menuAttach = fastVmHooks ? fastVmHooks.attach : typeof makeFastMenuHooks === 'function' ? makeFastMenuHooks({
            address: Process.mainModule.base.add(menuGuard.rva), hex: menuGuard.hex}) :
            typeof makeGroupedMenuHooks === 'function' ? makeGroupedMenuHooks() : hookHudHintUpdates;
        const createMenu = typeof makeEmptyMenuProbe === 'function' ? makeEmptyMenuProbe : makeEnhancedSettingsMenu;
        settingsMenu = createMenu(SETTINGS_PROFILE, menuAttach, {
            modules: {...ENHANCED_HOST.modules, map: CONFIG.features.map, vehicle: CONFIG.features.vehicle},
            getFeatureStates: menuFeatureStates,
            automaticReverse: preferences.automaticReverse,
            truckStorageSearch: preferences.truckStorageSearch,
            onSearchChange: value => { truckSearch?.set(value); savePreference('truckStorageSearch', value); },
            onReverseChange: value => { vehicle?.set(value); savePreference('automaticReverse', value); },
            zoomSensitivity: preferences.zoomSensitivity,
            panningSensitivity: preferences.panningSensitivity, keepNorthUp: preferences.keepNorthUp,
            onNorthChange: value => savePreference('keepNorthUp', value),
            onZoomChange: value => savePreference('zoomSensitivity', value),
            onPanningChange: value => savePreference('panningSensitivity', value)
        });
        settingsMenu.start(Process.mainModule.base.add(result.profile.guards.find(g => g.name === 'vm_frame_push_entry').rva),
            Process.mainModule.base.add(result.profile.stringPoolSlotRva));
    } catch (error) { menuFailure = String(error); settingsMenu = null; }
    if (ENHANCED_HOST.general === true) {
        repeatState = 'unsupported';
        try { functionsRepeat = startFunctionsRepeat(result.profile,fastVmHooks?.attach); }
        catch (error) { repeatState = String(error); }
    }
    if(fastVmHooks) {
        try { fastVmHooks.commit(); }
        catch(error) {
            // Commit disarms both phases. Stop their owners before reporting;
            // never leave an optional component claiming a working VM filter.
            try { if(nativeAgent.status().active)nativeAgent.stop(); } catch(_) {}
            try { settingsMenu?.stop(); } catch(_) {}
            settingsMenu=null;menuFailure=String(error);
            try { functionsRepeat?.stop(); } catch(_) {}
            functionsRepeat=null;
            if(ENHANCED_HOST.general)repeatState=String(error);
            if(ENHANCED_HOST.vehicle) {
                for(const hook of truckSearch?.keepAlive || []) { try{hook.detach();}catch(_){} }
                truckSearch=null;truckSearchError=String(error);
            }
            agentState='error';agentReason=String(error);
        }
    }
    function report() { reportNative(agentState, {compatibility: result.details, counters: nativeAgent.status(), reason: agentReason}); }
    report();
    timer = setInterval(() => {
        // A fault in an optional correction does not stop the core settings UI.
        if (wantsAgent && agentState === 'active') {
            try {
                const counters = nativeAgent.status(); nativeAgent.drain();
                if (counters.faults) {
                    nativeAgent.stop(); agentState = 'faulted';
                    agentReason = 'Correction stopped after an instrumentation fault';
                }
            } catch (_) {
                nativeAgent.stop(); agentState = 'faulted'; agentReason = 'Correction stopped after a runtime error';
            }
        }
        report(); // Also samples native-only failures and lazy archive patches.
    }, 2000);
}
reportNative('waiting');
// Native FFB remains independent when discovery of the other modules fails.
if (ENHANCED_HOST.modules?.steering_wheel_improvements)
    setInterval(() => reportNative(featureState, lastReportExtra), 2000);
setTimeout(attemptStart, 1000);
