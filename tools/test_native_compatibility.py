"""Run the existing signature refusal/relocation suite in native QuickJS."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import frida
import test_compatibility as tests
from compatibility import IncompatibleError
from native_host import NativeDevice
from test_scanner import RealScannerTests

device = NativeDevice()
pid = device.spawn(None)
try:
    script = device.create_script((ROOT / 'src/native/resolve.js').read_text() +
        '\nrpc.exports={resolve:resolveNativeProfile};')
    script.load()
    def resolve(profile, signatures, matches, sections):
        try:
            result = script.exports_sync.resolve(profile, signatures, matches, sections)
            return result['profile'], result['details']
        except frida.RPCException as error:
            raise IncompatibleError(str(error)) from error
    with patch.object(tests, 'resolve_profile', side_effect=resolve):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(tests.CompatibilityTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful(): raise SystemExit(1)
    script.unload()
finally:
    device.kill(pid)
with patch.object(frida, 'get_local_device', side_effect=NativeDevice):
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RealScannerTests))
    if not result.wasSuccessful(): raise SystemExit(1)
