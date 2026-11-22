'use strict';

// Lives entirely in Enhanced's private GumJS runtime. No RPC listener/server,
// external injection, filesystem scripts or shared ASI loader.
let attempts = 0, lastFailure = null, timer = null, featureState = 'waiting';
function reportNative(state, extra = {}) {
    featureState = state;
    send({enhancedStatus: {schemaVersion: 1, version: '0.1.0-preview.11',
        gameSha256: ENHANCED_HOST.gameSha256, timeUtc: new Date().toISOString(),
        processId: Process.id,
        features: {wheel_mouse: {enabled: true, status: state, ...extra}},
        validation: 'Preview: game and physical validation pending'}});
}
function attemptStart() {
    attempts++;
    let installing = false;
    try {
        const info = nativeProbe.describe();
        if (info.name.toLowerCase() !== 'snowrunner.exe') throw new Error('Wrong executable');
        const matches = nativeProbe.scan(NATIVE_SIGNATURES, info.sections);
        const result = resolveNativeProfile(CONFIG.profile, NATIVE_SIGNATURES, matches, info.sections);
        // VERSION may be called early in startup. Code can already be unpacked
        // while category constructors have not run yet. This is read-only and
        // stays in the discovery retry phase, before installing any hooks.
        const identities = Object.values(result.profile.ids).map(rva => Process.mainModule.base.add(rva).readU32());
        if (identities.some(value => value === 0) || new Set(identities).size !== identities.length)
            throw new Error('Waiting for input categories to initialize');
        CONFIG.profile = result.profile;
        installing = true;
        nativeAgent.start();
        nativeAgent.mode('ui-mouse-priority');
        reportNative('active', {compatibility: result.details, counters: nativeAgent.status()});
        let previous = '';
        timer = setInterval(() => {
          try {
            const counters = nativeAgent.status();
            nativeAgent.drain();
            if (counters.faults) {
                nativeAgent.stop(); clearInterval(timer);
                reportNative('faulted', {reason: 'Correction stopped after an instrumentation fault', counters});
                return;
            }
            const serialized = JSON.stringify(counters);
            if (serialized !== previous) {
                previous = serialized;
                reportNative('active', {compatibility: result.details, counters});
            }
          } catch (_) {
            nativeAgent.stop(); clearInterval(timer);
            reportNative('faulted', {reason: 'Correction stopped after a runtime error'});
          }
        }, 2000);
    } catch (error) {
        // A failed installation already detaches its own hooks. Do not retry a
        // partly installed agent. Discovery alone may retry while Steam unpacks.
        if (nativeAgent.status().active) nativeAgent.stop();
        lastFailure = error.details || {reason: String(error.message).slice(0, 160)};
        if (installing) {
            reportNative('error', {reason: 'Hook installation failed; correction stopped'});
        } else if (attempts < 30 && !nativeAgent.status().faults) {
            reportNative('waiting', {attempt: attempts, compatibility: lastFailure});
            timer = setTimeout(attemptStart, 2000);
        } else reportNative('incompatible', {compatibility: lastFailure});
    }
}
reportNative('waiting');
setTimeout(attemptStart, 1000);
