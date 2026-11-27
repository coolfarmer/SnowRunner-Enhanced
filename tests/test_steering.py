"""Production C resolver and Gum callback in disposable hosts; no game or wheel."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from compatibility import compile_signatures

PROFILE = json.loads((ROOT / 'src/steering-profile.json').read_text())
SIGNATURES = compile_signatures(PROFILE)
HOST = Path(os.environ.get('ENHANCED_STEERING_TEST_HOST', ROOT / 'build/native/steering-host.exe'))


def image_fixture(relocated=True):
    code_delta, data_delta = (0x100000, 0x400000) if relocated else (0, 0)
    def move(rva):
        for i, sig in enumerate(SIGNATURES):
            if sig['rva'] - 128 <= rva < sig['rva'] + len(bytes.fromhex(sig['hex'])) + 128:
                return rva + code_delta + (i * 0x10000 if relocated else 0)
        return rva + (code_delta if rva < 0x21c0000 else data_delta)
    sections = [(0x1000, 0x21bf000 + code_delta, 1, 1), (0x21c0000 + data_delta, 0x1000000, 0, 1)]
    data = bytearray(sections[-1][0] + sections[-1][1])
    for sig in SIGNATURES:
        raw = bytearray.fromhex(sig['hex'])
        rva = move(sig['rva'])
        for ref in sig['refs']:
            displacement = move(ref['target']) - rva - ref['next']
            raw[ref['offset']:ref['offset'] + ref['size']] = displacement.to_bytes(ref['size'], 'little', signed=True)
        data[rva:rva+len(raw)] = raw
    return data, sections, move


@unittest.skipUnless(HOST.exists(), 'Build steering-host.exe first')
class SteeringTests(unittest.TestCase):
    def run_image(self, data, sections, target=None):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build/tests', prefix='steering-') as directory:
            path = Path(directory) / 'image.bin'
            with path.open('wb') as file:
                file.write(struct.pack('<II', len(data), len(sections)))
                for section in sections:
                    file.write(struct.pack('<IIII', *section))
                file.write(data)
            result = subprocess.run([HOST, 'resolve', path], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0 if target is not None else 3, result.stdout + result.stderr)
        if target is not None:
            self.assertIn(f'PASS target={target} ', result.stdout)
        return result.stdout

    def test_native_callback(self):
        for case in ('guards', 'abi', 'semantics', 'readonly', 'boundary', 'executable', 'overflow', 'null'):
            with self.subTest(case=case):
                result = subprocess.run([HOST, case], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PASS ' + case, result.stdout)

    def test_original_reference(self):
        data, sections, move = image_fixture(False)
        self.run_image(data, sections, move(PROFILE['constructorRva']))

    def test_independent_function_and_data_relocation(self):
        data, sections, move = image_fixture()
        # Unrelated code may change without any version or executable hash gate.
        data[0x2000:0x2008] = b'NEWBUILD'
        self.run_image(data, sections, move(PROFILE['constructorRva']))

    def test_changed_object_field_is_refused(self):
        data, sections, move = image_fixture()
        sig = next(s for s in SIGNATURES if s['name'] == 'transient_calculation')
        offset = bytes.fromhex(sig['hex']).index(bytes.fromhex('f3440f584744')) + 5
        self.assertTrue(sig['mask'][offset])
        data[move(sig['rva'])+offset] = 0x48
        self.assertIn('Missing or changed', self.run_image(data, sections))

    def test_changed_constructor_is_refused(self):
        data, sections, move = image_fixture()
        data[move(PROFILE['constructorRva'])] ^= 1
        self.run_image(data, sections)

    def test_duplicate_constructor_is_disambiguated_by_calls(self):
        data, sections, move = image_fixture()
        sig = next(s for s in SIGNATURES if s['name'] == 'constructor')
        rva, length = move(sig['rva']), len(sig['mask'])
        data[0x2000:0x2000+length] = data[rva:rva+length]
        self.run_image(data, sections, move(PROFILE['constructorRva']))

    def test_common_getter_is_resolved_among_thousands_of_matches(self):
        data, sections, move = image_fixture()
        sig = next(s for s in SIGNATURES if s['name'] == 'parameter_getter')
        raw = bytes.fromhex(sig['hex'])
        for i in range(5500):
            rva = 0x30000 + i * 16
            data[rva:rva+len(raw)] = raw
        self.run_image(data, sections, move(PROFILE['constructorRva']))

    def test_two_complete_candidates_are_refused(self):
        data, sections, move = image_fixture()
        sections[0] = (0x1000, sections[1][0]-0x1000, 1, 1)
        for sig in SIGNATURES:
            rva = move(sig['rva']) + 0x400000
            raw = bytearray.fromhex(sig['hex'])
            for ref in sig['refs']:
                delta = move(ref['target']) + 0x400000 - rva - ref['next']
                raw[ref['offset']:ref['offset']+ref['size']] = delta.to_bytes(ref['size'], 'little', signed=True)
            data[rva:rva+len(raw)] = raw
        self.assertIn('Ambiguous', self.run_image(data, sections))

    def test_inconsistent_constructor_reference_is_refused(self):
        data, sections, move = image_fixture()
        sig = next(s for s in SIGNATURES if s['name'] == 'allocation_1')
        ref = next(r for r in sig['refs'] if r['target'] == PROFILE['constructorRva'])
        rva = move(sig['rva'])
        struct.pack_into('<i', data, rva+ref['offset'], move(ref['target'])+0x100-rva-ref['next'])
        self.assertIn('Inconsistent', self.run_image(data, sections))

    def test_non_executable_signature_is_refused(self):
        data, sections, move = image_fixture()
        sections[0] = (*sections[0][:2], 0, 1)
        self.run_image(data, sections)


if __name__ == '__main__':
    (ROOT / 'build/tests').mkdir(parents=True, exist_ok=True)
    unittest.main()
