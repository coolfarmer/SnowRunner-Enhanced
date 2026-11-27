'use strict';

// The installer selection and runtime health are deliberately independent.
const enhancedFeatureIds = ['wheel_mouse', 'skip_startup_logos', 'map',
    'general_improvements', 'vehicle', 'steering_wheel_improvements'];

function enhancedFeatureHealth(selected, components) {
    if (!selected) return 'inactive';
    const states = components.map(component => {
        if (!component) return 'pending';
        if (component.fault || component.faults || component.failed) return 'error';
        const state = typeof component === 'string' ? component : component.status;
        if (['active', 'ready'].includes(state)) return 'active';
        if (!state || ['waiting', 'armed', 'pending', 'waiting-for-settings', 'waiting-for-controls'].includes(state)) return 'pending';
        return 'error'; // Includes incompatibility, stopped corrections and exceptions.
    });
    return states.includes('error') ? 'error' :
        states.length && states.every(state => state === 'active') ? 'active' : 'pending';
}

function enhancedFeatureStates(selected, runtime) {
    const input = {status: runtime.inputState, faults: runtime.input?.faults};
    const menu = runtime.menu || {};
    const native = runtime.native || {};
    // Active means installed and ready, not already exercised. Method guards
    // still run on first use; any later fault takes precedence over readiness.
    const map = [input, menu.zoomSensitivity, menu.panningSensitivity];
    map.push({status: 'active', fault: menu.keepNorthUp?.fault});
    const components = {
        wheel_mouse: [input],
        skip_startup_logos: [native.skip_startup_logos],
        map,
        general_improvements: [native.general_improvements, runtime.repeat],
        vehicle: [runtime.vehicleError ? {fault: runtime.vehicleError} : runtime.vehicle ?
            {status: 'active', fault: runtime.vehicle.fault, faults: runtime.vehicle.unknown} : null,
            runtime.vehicleWinchError ? {fault: runtime.vehicleWinchError} : runtime.vehicleWinch,
            runtime.truckSearchError ? {fault: runtime.truckSearchError} : runtime.truckSearch],
        steering_wheel_improvements: [native.steering_wheel_improvements]
    };
    return Object.fromEntries(enhancedFeatureIds.map(id => [id, enhancedFeatureHealth(selected[id] === true, components[id])]));
}
