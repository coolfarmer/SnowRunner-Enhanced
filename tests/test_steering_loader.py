"""Steering lifecycle through the packaged ASI, using only synthetic executables."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_native_loader import run_case, PACKAGE


@unittest.skipUnless((PACKAGE / 'Payload/SnowRunnerEnhanced.asi').exists(), 'Package the native release first')
class SteeringLoaderTests(unittest.TestCase):
    def run_steering(self, *, wheel=False, selected=True, compatible=True, input_compatible=True):
        config = {'schemaVersion': 1, 'features': {
            'steering_wheel_improvements': {'enabled': selected},
            'wheel_mouse': {'enabled': wheel}, 'vehicle': {'enabled': False}}}
        expected = ('active' if wheel else 'disabled') if input_compatible else 'waiting'
        run_case(self._testMethodName, config, expected, delay=4200, synthetic=True,
                 steering=compatible, input_compatible=input_compatible)

    def test_steering_only(self):
        self.run_steering()

    def test_coexistence(self):
        self.run_steering(wheel=True)

    def test_incompatible_steering_preserves_input(self):
        self.run_steering(wheel=True, compatible=False)

    def test_disabled_steering_with_valid_signatures(self):
        self.run_steering(selected=False)

    def test_steering_remains_active_when_input_discovery_fails(self):
        self.run_steering(wheel=True, input_compatible=False)


if __name__ == '__main__':
    unittest.main()
