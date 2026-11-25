"""Runtime readiness and health, including errors detected after first use."""
import json
from pathlib import Path
import unittest
from native_host import NativeDevice

ROOT = Path(__file__).resolve().parents[1]


class FeatureStatusTests(unittest.TestCase):
    def setUp(self):
        self.device = NativeDevice()
        self.pid = self.device.spawn(None)
        source = (ROOT / 'src/feature_status.js').read_text(encoding='utf-8')
        self.script = self.device.create_script(source + '\nrpc.exports={states:enhancedFeatureStates,health:enhancedFeatureHealth};')
        self.script.load()
        self.api = self.script.exports_sync
        self.selected = dict.fromkeys(('wheel_mouse', 'skip_startup_logos', 'map',
                                      'general_improvements', 'vehicle', 'steering_wheel_improvements'), True)
        self.runtime = dict(inputState='active', input=dict(faults=0, navigationHitAreaRepairs=1,
                            mapNotificationHitAreaRepairs=1), repeat='ready', vehicle=dict(unknown=0), vehicleWinch=dict(status='active'),
                            native={key: dict(status='active') for key in
                                    ('skip_startup_logos', 'general_improvements', 'steering_wheel_improvements')},
                            menu=dict(zoomSensitivity=dict(status='active', zoomCalls=1),
                                      panningSensitivity=dict(status='active', rotationCalls=1),
                                      keepNorthUp=dict(fault=None)))

    def tearDown(self):
        self.script.unload()
        self.device.kill(self.pid)

    def test_all_installer_combinations_preserve_disabled_features(self):
        for mask in range(64):
            selected = {key: bool(mask & (1 << i)) for i, key in enumerate(self.selected)}
            actual = self.api.states(selected, self.runtime)
            self.assertEqual(actual, {key: 'active' if value else 'inactive' for key, value in selected.items()})

    def test_selected_is_not_evidence_of_success(self):
        self.assertEqual(set(self.api.states(self.selected, {}).values()), {'pending'})
        for state in ('waiting', 'armed', 'pending'):
            self.assertEqual(self.api.health(True, [dict(status=state)]), 'pending')

    def test_error_overrides_pending_and_active(self):
        for failure in ('incompatible', 'faulted', 'error', 'unsupported', 'stopped', 'disabled', 'Error: hook rejected'):
            self.assertEqual(self.api.health(True, ['ready', 'pending', failure]), 'error')
            self.assertEqual(self.api.health(False, [failure]), 'inactive')

    def test_native_steering_failure_is_independent_of_input(self):
        self.runtime['native']['steering_wheel_improvements'] = dict(status='active', failed=1)
        result = self.api.states(self.selected, self.runtime)
        self.assertEqual(result['steering_wheel_improvements'], 'error')
        self.assertEqual(result['wheel_mouse'], 'active')

    def test_map_is_active_before_first_use_when_components_are_ready(self):
        for key in ('navigationHitAreaRepairs', 'mapNotificationHitAreaRepairs'):
            self.runtime['input'][key] = 0
        for key, counter in (('zoomSensitivity', 'zoomCalls'), ('panningSensitivity', 'rotationCalls')):
            self.runtime['menu'][key][counter] = 0
        self.assertEqual(self.api.states(self.selected, self.runtime)['map'], 'active')

    def test_map_waits_for_component_initialization(self):
        for key in ('zoomSensitivity', 'panningSensitivity'):
            runtime = json.loads(json.dumps(self.runtime))
            runtime['menu'][key]['status'] = 'waiting'
            self.assertEqual(self.api.states(self.selected, runtime)['map'], 'pending')
            del runtime['menu'][key]
            self.assertEqual(self.api.states(self.selected, runtime)['map'], 'pending')
        self.runtime['inputState'] = 'waiting'
        self.assertEqual(self.api.states(self.selected, self.runtime)['map'], 'pending')

    def test_map_detects_late_partial_failure_after_becoming_active(self):
        for key in ('zoomSensitivity', 'panningSensitivity'):
            runtime = json.loads(json.dumps(self.runtime))
            self.assertEqual(self.api.states(self.selected, runtime)['map'], 'active')
            runtime['menu'][key]['fault'] = 'Changed bytecode'
            self.assertEqual(self.api.states(self.selected, runtime)['map'], 'error')
            self.selected['map'] = False
            self.assertEqual(self.api.states(self.selected, runtime)['map'], 'inactive')
            self.selected['map'] = True
        self.runtime['menu']['keepNorthUp']['fault'] = 'Changed camera layout'
        self.assertEqual(self.api.states(self.selected, self.runtime)['map'], 'error')
        self.runtime['menu']['keepNorthUp']['fault'] = None
        self.runtime['input']['faults'] = 1
        self.assertEqual(self.api.states(self.selected, self.runtime)['map'], 'error')

    def test_repeat_and_vehicle_errors_are_not_hidden_by_other_components(self):
        self.runtime['repeat'] = 'Error: repeat hook failed'
        self.runtime['vehicle']['fault'] = 'Foreign patch'
        result = self.api.states(self.selected, self.runtime)
        self.assertEqual(result['general_improvements'], 'error')
        self.assertEqual(result['vehicle'], 'error')
        self.assertEqual(result['map'], 'active')

    def test_default_vehicle_option_is_still_an_active_module(self):
        self.runtime['vehicle']['automaticReverse'] = True
        self.assertEqual(self.api.states(self.selected, self.runtime)['vehicle'], 'active')
        self.runtime['vehicle']['unknown'] = 1
        self.assertEqual(self.api.states(self.selected, self.runtime)['vehicle'], 'error')

    def test_vehicle_includes_winch_readiness_and_faults(self):
        self.runtime['vehicleWinch'] = None
        self.assertEqual(self.api.states(self.selected, self.runtime)['vehicle'], 'pending')
        self.runtime['vehicleWinchError'] = 'Unsupported signature'
        self.assertEqual(self.api.states(self.selected, self.runtime)['vehicle'], 'error')
        self.runtime['vehicleWinchError'] = None
        self.runtime['vehicleWinch'] = dict(status='error', fault='Invalid registry')
        self.assertEqual(self.api.states(self.selected, self.runtime)['vehicle'], 'error')
        self.selected['vehicle'] = False
        self.assertEqual(self.api.states(self.selected, self.runtime)['vehicle'], 'inactive')


if __name__ == '__main__':
    unittest.main()
