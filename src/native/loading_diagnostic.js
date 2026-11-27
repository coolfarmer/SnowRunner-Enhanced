'use strict';

// Diagnostic bootstrap only. Keep the embedded runtime and periodic native
// reporting, without discovery, menu callbacks, game hooks or preference writes.
const diagnosticStarted = Date.now();
let diagnosticReports = 0;
function reportLoadingDiagnostic() {
    send({enhancedStatus: {
        schemaVersion: 1, version: '1.0.1',
        buildMode: 'loading-diagnostic-no-hooks',
        processId: Process.id, timeUtc: new Date().toISOString(),
        gameSha256: ENHANCED_HOST.gameSha256,
        diagnostic: {status: 'running', gameHooksEnabled: false,
            reports: ++diagnosticReports, elapsedMs: Date.now() - diagnosticStarted},
        components: {
            settings_menu: {enabled: false, running: false, status: 'disabled'},
            functions_repeat: {status: 'disabled'}
        },
        features: Object.fromEntries(Object.keys(ENHANCED_HOST.modules).map(key =>
            [key, {enabled: false, status: 'disabled'}])),
        validation: 'Diagnostic only; compare loading times with the same save.'
    }});
}
// Drain native report replies so the normal reporting path remains bounded.
const receiveDiagnostic = () => recv('enhanced-runtime', () => receiveDiagnostic());
receiveDiagnostic();
reportLoadingDiagnostic();
setInterval(reportLoadingDiagnostic, 2000);
