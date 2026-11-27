"""Truck search matching and compatibility in the shipped embedded runtime."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from native_host import NativeDevice

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from compatibility import compile_signatures, resolve_profile, IncompatibleError


class TruckSearchTests(unittest.TestCase):
    def setUp(self):
        self.device = NativeDevice()
        self.pid = self.device.spawn(None)
        production = (ROOT/'src/truck_search.js').read_text()
        fixture = (ROOT/'tests/truck_search_fixture.js').read_text().replace('PRODUCTION_SOURCE', production)
        profile = 'const PROFILE='+(ROOT/'src/truck-search-profile.json').read_text()+';\n'
        self.script = self.device.create_script(profile+production + '''
rpc.exports = {
 matches: truckSearchMatches,
 shift: (words, offset) => truckSearchShift(words, offset)
};'''+fixture)
        self.script.load()

    def tearDown(self):
        self.script.unload()
        self.device.kill(self.pid)

    def test_lifecycle_focus_isolation_images_and_toggle(self):
        result = self.script.exports_sync.lifecycle('normal')
        self.assertIsNone(result['status']['fault'], result)
        self.assertEqual(result['selected'], [1])
        for flag in ('firstHoverBlocked','unrelatedActivation','unfocusedActivation','releaseBeforeArray','hoverBlocked','unrelatedHover','deviceBlocked','keysBlocked',
                     'unrelatedKeys','unfocusedHover','queryCleared','off','on','originalListIntact'):
            self.assertTrue(result[flag], (flag,result))
        self.assertEqual((result['dropped'],result['cleared']), (1,1))
        self.assertEqual(result['retainedListeners'], 9)

    def test_changed_warehouse_method_stops_search(self):
        result = self.script.exports_sync.lifecycle('changed')
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['installations'], 0)

    def test_search_uses_localized_display_name(self):
        result = self.script.exports_sync.lifecycle('localized')
        self.assertIsNone(result['status']['fault'], result)
        self.assertEqual(result['selected'], [2])

    def test_mod_names_case_accents_and_multiple_words(self):
        for query in ('', '  ', 'forester', 'FORESTER', 'aramatsu 1910', '1910 aramatsu'):
            self.assertTrue(self.script.exports_sync.matches(query, 'Aramatsu Forester 1910', 'mod_forester'))
        self.assertTrue(self.script.exports_sync.matches('equipe', 'Camion équipé', 'custom_mod'))
        self.assertTrue(self.script.exports_sync.matches('custom mod', 'Camion équipé', 'custom_mod'))
        self.assertFalse(self.script.exports_sync.matches('forester 420', 'Aramatsu Forester 1910', 'mod_forester'))
        self.assertFalse(self.script.exports_sync.matches('azov', 'TUZ 420 "Tatarin"', 'tuz_420'))

    def test_all_branch_targets_move_but_constants_and_calls_do_not(self):
        word = lambda op, arg: ((arg + 0x800000) * 256 + op) & 0xffffffff
        original = [word(op, 7) for op in (6, 7, 13, 22, 23, 24, 25, 26, 60)]
        actual = self.script.exports_sync.shift(original, 19)
        self.assertEqual(actual, [word(op, 26 if op in (22,23,24,25,26) else 7)
                                  for op in (6,7,13,22,23,24,25,26,60)])


class TruckSearchCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((ROOT/'src/truck-search-profile.json').read_text())
        self.signatures = compile_signatures(self.profile)
        self.matches = {g['name']: [dict(rva=g['rva'], hex=g['hex'])] for g in self.signatures}
        self.sections = [dict(rva=0x1000, size=0x4000000, readable=True, executable=True)]

    def test_every_native_address_is_resolved(self):
        actual, _ = resolve_profile(self.profile, self.signatures, self.matches, self.sections)
        for key, value in self.profile.items():
            if key.endswith('Rva'):
                self.assertEqual(actual[key], value)

    def test_missing_or_changed_signature_is_refused(self):
        for signature in self.signatures:
            matches = deepcopy(self.matches)
            matches[signature['name']] = []
            with self.assertRaises(IncompatibleError):
                resolve_profile(self.profile, self.signatures, matches, self.sections)
            matches = deepcopy(self.matches)
            raw = bytearray.fromhex(signature['hex'])
            raw[next(i for i, keep in enumerate(signature['mask']) if keep)] ^= 1
            matches[signature['name']][0]['hex'] = raw.hex()
            with self.assertRaises(IncompatibleError):
                resolve_profile(self.profile, self.signatures, matches, self.sections)


if __name__ == '__main__':
    unittest.main()
