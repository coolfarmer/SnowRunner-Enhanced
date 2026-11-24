import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT/'build/native/settings-host.exe'


@unittest.skipUnless(HOST.exists(), 'Build native host first')
class NativeSettingsTests(unittest.TestCase):
    def test_restart_roundtrip_default_reset_and_invalid_data(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/tmp') as folder:
            path = Path(folder)/'SnowRunnerEnhanced.settings.json'
            def run(value=None):
                args = [str(HOST), folder+'\\']
                if value is not None:
                    args.append(json.dumps(value))
                return json.loads(subprocess.check_output(args, text=True))
            self.assertEqual(run()['value'], 50)
            self.assertEqual(run()['panning'], 50)
            for value in [0,75,100,50]:
                self.assertEqual(run(dict(schemaVersion=1,zoomSensitivity=value))['saved'], 1)
                self.assertEqual(run()['value'], value)
                self.assertEqual(run()['panning'], 50)
            # Upgrade an existing preview.18 file without changing its zoom.
            path.write_text('{"schemaVersion":1,"zoomSensitivity":75}')
            self.assertEqual((run()['value'], run()['panning']), (75, 50))
            for zoom, panning in [(75,0),(100,25),(0,100),(50,50)]:
                self.assertEqual(run(dict(schemaVersion=2,zoomSensitivity=zoom,panningSensitivity=panning))['saved'], 1)
                self.assertEqual((run()['value'], run()['panning']), (zoom, panning))
                self.assertEqual(json.loads(path.read_text())['schemaVersion'], 2)
            before = path.read_bytes()
            for value in [-1,101,1.5,'75',True,None]:
                self.assertEqual(run(dict(schemaVersion=1,zoomSensitivity=value))['saved'], 0)
                self.assertEqual(run(dict(schemaVersion=2,zoomSensitivity=75,panningSensitivity=value))['saved'], 0)
                self.assertEqual(path.read_bytes(), before)
            for data in ['broken', '{}', '[]', '{"schemaVersion":2,"zoomSensitivity":75}',
                         '{"schemaVersion":1,"zoomSensitivity":75,"extra":1}', 'x'*2048]:
                path.write_text(data)
                state = run()
                self.assertEqual(state['value'], 50)
                self.assertEqual(state['panning'], 50)
                self.assertEqual(state['state'], 'invalid-file')

    def test_failed_replace_preserves_existing_destination(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/tmp') as folder:
            path = Path(folder)/'SnowRunnerEnhanced.settings.json'
            path.mkdir()
            result = json.loads(subprocess.check_output([str(HOST), folder+'\\',
                '{"schemaVersion":1,"zoomSensitivity":75}'], text=True))
            self.assertEqual(result['saved'], 0)
            self.assertEqual(result['state'], 'write-error')
            self.assertTrue(path.is_dir())
            self.assertFalse((Path(folder)/'SnowRunnerEnhanced.settings.tmp').exists())


if __name__ == '__main__':
    unittest.main()
