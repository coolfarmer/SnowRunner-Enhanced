"""Signature relocation and refusal tests; no running SnowRunner required."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from compatibility import (IncompatibleError, address_fields, compile_signatures,
                           find_matches, resolve_profile)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / 'src/input-profile.json').read_text())
SIGNATURES = compile_signatures(PROFILE)


def synthetic_image(code_delta=0, data_delta=0):
    # Different relocation for executable code and data also exercises RIP
    # displacements; changing every address by the same amount would not.
    def move(address):
        return address + (code_delta if address < 0x21c0000 else data_delta)

    sections = [{'rva': 0x1000 + code_delta, 'size': 0x21bf000,
                 'executable': True, 'readable': True},
                {'rva': 0x21c0000 + data_delta, 'size': 0x1000000,
                 'executable': False, 'readable': True}]
    matches, segments, labels = {}, [], {}
    for sig in SIGNATURES:
        raw = bytearray.fromhex(sig['hex'])
        rva = move(sig['rva'])
        for ref in sig['refs']:
            offset, size = ref['offset'], ref['size']
            displacement = move(ref['target']) - (rva + ref['next'])
            raw[offset:offset + size] = displacement.to_bytes(size, 'little', signed=True)
        matches[sig['name']] = [{'rva': rva, 'hex': raw.hex()}]
        segments.append((rva, bytes(raw)))
        if sig['identity']:
            labels[move(sig['refs'][0]['target'])] = sig['identity'].encode() + b'\0'
    return matches, sections, segments, labels, move


class CompatibilityTests(unittest.TestCase):
    def test_original_profile_reconstructed(self):
        matches, sections, *_ = synthetic_image()
        resolved, details = resolve_profile(PROFILE, SIGNATURES, matches, sections)
        self.assertEqual(resolved, PROFILE)
        self.assertEqual(details['relocatedGuards'], 0)

    def test_code_and_data_move_independently(self):
        matches, sections, segments, labels, move = synthetic_image(0x100000, 0x400000)
        # Scan individual nonoverlapping guard buffers to avoid duplicate copies
        # of the overlapping hover-timer and winch blocks in this test fixture.
        for sig in SIGNATURES:
            segment = next(s for s in segments if s[0] == move(sig['rva']))
            found = find_matches(sig, [segment], lambda rva, size: labels.get(rva, b'')[:size])
            self.assertEqual(found, matches[sig['name']])
        resolved, details = resolve_profile(PROFILE, SIGNATURES, matches, sections)
        for path, old in address_fields(PROFILE):
            value = resolved
            for key in path:
                value = value[key]
            self.assertEqual(value, move(old), path)
        self.assertEqual(details['relocatedGuards'], len(SIGNATURES))

    def test_changed_wheel_value_layout_refused(self):
        matches, sections, *_ = synthetic_image()
        item = matches['wheel_state_values'][0]
        item['hex'] = item['hex'].replace('28020000', '2c020000', 1)
        with self.assertRaises(IncompatibleError):
            resolve_profile(PROFILE, SIGNATURES, matches, sections)

    def test_changed_opcode_refused(self):
        matches, sections, *_ = synthetic_image()
        item = matches['menu_key_dispatch'][0]
        item['hex'] = '90' + item['hex'][2:]
        with self.assertRaises(IncompatibleError):
            resolve_profile(PROFILE, SIGNATURES, matches, sections)

    def test_changed_field_offset_refused(self):
        matches, sections, *_ = synthetic_image()
        item = matches['menu_focus_setter'][0]
        item['hex'] = item['hex'].replace('03010000', '05010000', 1)
        with self.assertRaises(IncompatibleError):
            resolve_profile(PROFILE, SIGNATURES, matches, sections)

    def test_missing_signature_refused(self):
        matches, sections, *_ = synthetic_image()
        matches['wheel_neutral_abs_float'] = []
        with self.assertRaises(IncompatibleError):
            resolve_profile(PROFILE, SIGNATURES, matches, sections)

    def test_ambiguous_signature_refused(self):
        matches, sections, *_ = synthetic_image()
        sig = next(s for s in SIGNATURES if s['name'] == 'ui_center')
        clone = deepcopy(matches['ui_center'][0])
        clone['rva'] += 0x100000
        raw = bytearray.fromhex(clone['hex'])
        for ref in sig['refs']:
            target = ref['target']
            if sig['rva'] <= target < sig['rva'] + len(raw):
                target += 0x100000
            raw[ref['offset']:ref['offset'] + ref['size']] = (
                target - clone['rva'] - ref['next']).to_bytes(ref['size'], 'little', signed=True)
        clone['hex'] = raw.hex()
        matches['ui_center'].append(clone)
        with self.assertRaises(IncompatibleError):
            resolve_profile(PROFILE, SIGNATURES, matches, sections)

    def test_individual_function_can_move(self):
        matches, sections, *_ = synthetic_image()
        sig = next(s for s in SIGNATURES if s['name'] == 'wheel_neutral_abs_float')
        item = matches[sig['name']][0]
        item['rva'] += 0x10000
        raw = bytearray.fromhex(item['hex'])
        for ref in sig['refs']:
            target = ref['target']
            if sig['rva'] <= target < sig['rva'] + len(raw):
                target += 0x10000
            raw[ref['offset']:ref['offset'] + ref['size']] = (
                target - item['rva'] - ref['next']).to_bytes(ref['size'], 'little', signed=True)
        item['hex'] = raw.hex()
        resolved, details = resolve_profile(PROFILE, SIGNATURES, matches, sections)
        self.assertEqual(resolved['wheelNeutralAbsFloatRva'], PROFILE['wheelNeutralAbsFloatRva'] + 0x10000)
        self.assertEqual(details['relocatedGuards'], 1)

    def test_inconsistent_call_refused(self):
        matches, sections, *_ = synthetic_image()
        item = matches['winch_point_mode_1'][0]
        raw = bytearray.fromhex(item['hex'])
        displacement = int.from_bytes(raw[1:5], 'little', signed=True)
        raw[1:5] = (displacement + 32).to_bytes(4, 'little', signed=True)
        item['hex'] = raw.hex()
        with self.assertRaises(IncompatibleError):
            resolve_profile(PROFILE, SIGNATURES, matches, sections)

    def test_wrong_identity_string_ignored(self):
        _, _, segments, _, _ = synthetic_image()
        sig = next(s for s in SIGNATURES if s['name'] == 'wheel_identity')
        self.assertEqual(find_matches(sig, segments, lambda rva, size: b'x' * size), [])

    def test_reference_outside_image_refused(self):
        matches, sections, *_ = synthetic_image()
        item = matches['supplemental_identity'][0]
        raw = bytearray.fromhex(item['hex'])
        raw[10:14] = (0x70000000).to_bytes(4, 'little', signed=True)
        item['hex'] = raw.hex()
        with self.assertRaises(IncompatibleError):
            resolve_profile(PROFILE, SIGNATURES, matches, sections)

    def test_data_must_not_replace_code(self):
        matches, sections, *_ = synthetic_image()
        sections[0]['executable'] = False
        with self.assertRaises(IncompatibleError):
            resolve_profile(PROFILE, SIGNATURES, matches, sections)


if __name__ == '__main__':
    unittest.main()
