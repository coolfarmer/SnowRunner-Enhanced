"""Test the shipped DLLs via Windows' real VERSION import mechanism."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from native_image import create_image
PACKAGE = ROOT / 'dist/SnowRunnerEnhanced-0.1.0-preview.1/Sources'
SETUP = PACKAGE / 'Installer/SnowRunnerEnhanced.Setup.exe'
STATUS = 'SnowRunnerEnhanced.status.json'


def run_case(name, config, expected, delay=2200, wrong_name=False, synthetic=False):
    with tempfile.TemporaryDirectory(prefix='loader-', dir=ROOT / 'build/tests') as directory:
        folder = Path(directory)
        exe = folder / ('Other.exe' if wrong_name else 'SnowRunner.exe')
        if synthetic: create_image(ROOT / 'build/native/game-host.exe', exe)
        else: shutil.copyfile(ROOT / 'build/native/game-host.exe', exe)
        for binary in ('version.dll', 'SnowRunnerEnhanced.dll'):
            shutil.copyfile(PACKAGE / 'Payload' / binary, folder / binary)
        if config is not None:
            (folder / 'SnowRunnerEnhanced.json').write_text(json.dumps(config), encoding='utf-8')
        original = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
        process = subprocess.Popen([exe, str(delay)], cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            if expected == 'incompatible':
                # Inspect while the real loader/runtime are alive. No game is run.
                deadline = time.monotonic() + 66
                previous = None
                while time.monotonic() < deadline:
                    if process.poll() is not None: break
                    try:
                        status = json.loads((folder / STATUS).read_text())
                        state = status['features']['wheel_mouse']['status']
                        if state != previous:
                            print(name + ': ' + state, flush=True)
                            previous = state
                        if state == expected: break
                    except (FileNotFoundError, json.JSONDecodeError, PermissionError): pass
                    time.sleep(0.2)
                assert previous == expected, previous
                assert len(status['features']['wheel_mouse']['compatibility']['candidateCounts']) == 28
                assert status['gameSha256'] == original[exe.name]
            stdout, stderr = process.communicate(timeout=delay / 1000 + 10)
            assert process.returncode == 0, (process.returncode, stdout, stderr)
            assert b'VERSION exports work' in stdout, stdout
            assert (b'Enhanced loaded: no' if wrong_name else b'Enhanced loaded: yes') in stdout, stdout
            assert not stderr, stderr
            if wrong_name: assert not (folder / STATUS).exists()
            else:
                status = json.loads((folder / STATUS).read_text())
                assert status['features']['wheel_mouse']['status'] == expected, status
                assert status['processId'] == process.pid
                if synthetic:
                    assert status['features']['wheel_mouse']['compatibility']['relocatedGuards'] == 28
                    assert status['features']['wheel_mouse']['counters']['active']
                    assert status['features']['wheel_mouse']['counters']['faults'] == 0
            for file, digest in original.items():
                assert hashlib.sha256((folder / file).read_bytes()).hexdigest() == digest
        finally:
            if process.poll() is None: process.kill(); process.wait()
        print('PASS ' + name, flush=True)


def test_running_game_guard():
    with tempfile.TemporaryDirectory(prefix='running-', dir=ROOT / 'build/tests') as directory:
        folder = Path(directory)
        shutil.copyfile(ROOT / 'build/native/game-host.exe', folder / 'SnowRunner.exe')
        process = subprocess.Popen([folder / 'SnowRunner.exe', '2500'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            result = subprocess.run([SETUP, '--action', 'install', '--game-directory', folder, '--json'],
                                    capture_output=True, timeout=10)
            assert result.returncode == 2 and not json.loads(result.stdout)['ok'], result.stdout
            assert not (folder / 'version.dll').exists()
            process.communicate(timeout=10)
            assert process.returncode == 0
        finally:
            if process.poll() is None: process.kill(); process.wait()
    print('PASS running executable blocks installation', flush=True)


if __name__ == '__main__':
    (ROOT / 'build/tests').mkdir(exist_ok=True)
    test_running_game_guard()
    for name, config, state in [
        ('disabled', {'schemaVersion': 1, 'features': {'wheel_mouse': {'enabled': False}}}, 'disabled'),
        ('omitted feature', {'schemaVersion': 1, 'features': {}}, 'disabled'),
        ('missing configuration', None, 'configuration-error'),
        ('unknown feature', {'schemaVersion': 1, 'features': {'other': {'enabled': True}}}, 'configuration-error'),
        ('invalid boolean', {'schemaVersion': 1, 'features': {'wheel_mouse': {'enabled': 'true'}}}, 'configuration-error')]:
        run_case(name, config, state)
    run_case('wrong executable', None, None, wrong_name=True)
    run_case('active relocated image', {'schemaVersion': 1, 'features': {'wheel_mouse': {'enabled': True}}},
             'active', delay=6000, synthetic=True)
    run_case('unrecognized signatures', {'schemaVersion': 1, 'features': {'wheel_mouse': {'enabled': True}}},
             'incompatible', delay=68000)
