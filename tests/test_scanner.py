"""Exercise production signature scanning on disposable synthetic memory."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from compatibility import compile_signatures, resolve_profile
from test_compatibility import PROFILE, synthetic_image


class RealScannerTests(unittest.TestCase):
    def test_live_scanner_on_disposable_synthetic_image(self):
        import frida
        matches, sections, segments, labels, _ = synthetic_image(0x100000, 0x400000)
        size = max(s['rva'] + s['size'] for s in sections)
        setup = 'const fixtureBase=Memory.alloc(' + str(size) + ');\n'
        for rva, data in segments:
            setup += f'fixtureBase.add({rva}).writeByteArray({list(data)});\n'
        for rva, data in labels.items():
            setup += f'fixtureBase.add({rva}).writeByteArray({list(data)});\n'
        # The scanner is unmodified; only its module inventory is supplied by
        # the fixture. Memory.scanSync and reads are real Frida operations.
        setup += '(function(Process) {\n'
        setup += (ROOT / 'src/compatibility_probe.js').read_text()
        setup += '\n})({mainModule:{base:fixtureBase,size:' + str(size) + '}});'
        device = frida.get_local_device()
        pid = device.spawn([sys.executable, '-c', 'import time; time.sleep(90)'])
        session = None
        try:
            session = device.attach(pid)
            device.resume(pid)
            script = session.create_script(setup)
            script.load()
            signatures = compile_signatures(PROFILE)
            scanned = script.exports_sync.scan(signatures, sections)
            resolved, details = resolve_profile(PROFILE, signatures, scanned, sections)
            expected, _ = resolve_profile(PROFILE, signatures, matches, sections)
            self.assertEqual(resolved, expected)
            self.assertEqual(details['relocatedGuards'], len(signatures))
            script.unload()
        finally:
            if session:
                session.detach()
            device.kill(pid)


if __name__ == '__main__':
    unittest.main()
