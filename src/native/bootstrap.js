'use strict';

// Core UI belongs to the plugin, never to a configurable enhancement group.
CONFIG.features = {wheel_mouse: ENHANCED_HOST.wheelMouse !== false, map: ENHANCED_HOST.map !== false};
let attempts = 0, timer = null, featureState = 'waiting', settingsMenu = null;
let menuFailure = null;
function reportNative(state, extra = {}) {
    featureState = state;
    send({enhancedStatus: {schemaVersion: 1, version: '0.1.0-preview.21',
        gameSha256: ENHANCED_HOST.gameSha256, timeUtc: new Date().toISOString(), processId: Process.id,
        components: {settings_menu: settingsMenu ? settingsMenu.status() :
            {enabled: true, status: menuFailure ? 'error' : state, reason: menuFailure}},
        features: Object.fromEntries(Object.entries(CONFIG.features).map(([key, enabled]) =>
            [key, enabled ? {enabled, status: state, ...extra} : {enabled, status: 'disabled'}])),
        validation: 'Preview: see packaged validation notes'}});
}
function attemptStart() {
    attempts++;
    const wantsAgent = Object.values(CONFIG.features).some(Boolean);
    let result;
    try {
        const info = nativeProbe.describe();
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
    let agentState = 'active', agentReason;
    if (wantsAgent) {
        try { nativeAgent.start(); nativeAgent.mode('ui-mouse-priority'); }
        catch (_) {
            if (nativeAgent.status().active) nativeAgent.stop();
            agentState = 'error'; agentReason = 'Hook installation failed; correction stopped';
        }
    }
    // The optional agent validates original entry bytes before either component
    // attaches to the shared VM entry point. Its failure does not disable the UI.
    try {
        const validPreference = value => Number.isInteger(value) && value >= 0 && value <= 100 ? value : 50;
        const preferences = {schemaVersion: 3, zoomSensitivity: validPreference(ENHANCED_HOST.zoomSensitivity),
            panningSensitivity: validPreference(ENHANCED_HOST.panningSensitivity), keepNorthUp: ENHANCED_HOST.keepNorthUp===true};
        const savePreference = (key, value) => { preferences[key] = value; send({enhancedSettings: {...preferences}}); };
        settingsMenu = makeEnhancedSettingsMenu(SETTINGS_PROFILE, hookHudHintUpdates, {
            mapEnabled: CONFIG.features.map, zoomSensitivity: preferences.zoomSensitivity,
            panningSensitivity: preferences.panningSensitivity, keepNorthUp: preferences.keepNorthUp,
            onNorthChange: value => savePreference('keepNorthUp', value),
            onZoomChange: value => savePreference('zoomSensitivity', value),
            onPanningChange: value => savePreference('panningSensitivity', value)
        });
        settingsMenu.start(Process.mainModule.base.add(result.profile.guards.find(g => g.name === 'vm_frame_push_entry').rva),
            Process.mainModule.base.add(result.profile.stringPoolSlotRva));
    } catch (error) { menuFailure = String(error); settingsMenu = null; }
    function report() { reportNative(agentState, {compatibility: result.details, counters: nativeAgent.status(), reason: agentReason}); }
    report();
    let previous = '';
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
        const serialized = JSON.stringify([agentState, nativeAgent.status(), settingsMenu ? settingsMenu.status() : menuFailure]);
        if (serialized !== previous) { previous = serialized; report(); }
    }, 2000);
}
reportNative('waiting');
setTimeout(attemptStart, 1000);
