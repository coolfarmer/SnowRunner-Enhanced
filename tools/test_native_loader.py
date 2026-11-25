"""Test the shipped DLLs via the real shared ASI loaders."""
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
from asi_loaders import LOADERS, loader_path, verify
PACKAGE = ROOT / 'dist/SnowRunnerEnhanced-0.1.0-preview.25/Sources'
SETUP = PACKAGE / 'Installer/SnowRunnerEnhanced.Setup.exe'
STATUS = 'SnowRunnerEnhanced.status.json'
GUARD_COUNT = len(json.loads((ROOT / 'src/input-profile.json').read_text())['guards'])


def run_case(name, config, expected, delay=2200, wrong_name=False, synthetic=False, loader=None, map_state=None, zoom_value=50):
    with tempfile.TemporaryDirectory(prefix='loader-', dir=ROOT / 'build/tests') as directory:
        folder = Path(directory)
        exe = folder / ('Other.exe' if wrong_name else 'SnowRunner.exe')
        if synthetic: create_image(ROOT / 'build/native/game-host.exe', exe)
        else: shutil.copyfile(ROOT / 'build/native/game-host.exe', exe)
        for binary in ('dinput8.dll', 'SnowRunnerEnhanced.asi'):
            shutil.copyfile(PACKAGE / 'Payload' / binary, folder / binary)
        if loader is not None:
            shutil.copyfile(loader_path(loader), folder / 'dinput8.dll')
        shutil.copyfile(ROOT / 'build/native/companion.asi', folder / 'ZZCompanion.asi')
        if config is not None:
            (folder / 'SnowRunnerEnhanced.json').write_text(json.dumps(config), encoding='utf-8')
        if zoom_value != 50:
            (folder / 'SnowRunnerEnhanced.settings.json').write_text(json.dumps({'schemaVersion':2,'zoomSensitivity':zoom_value,'panningSensitivity':0}))
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
                assert len(status['features']['wheel_mouse']['compatibility']['candidateCounts']) == GUARD_COUNT
                assert status['gameSha256'] == original[exe.name]
            stdout, stderr = process.communicate(timeout=delay / 1000 + 10)
            assert process.returncode == 0, (process.returncode, stdout, stderr)
            assert b'DirectInput forwarding works' in stdout, stdout
            assert b'Enhanced loaded: yes' in stdout, stdout
            assert (folder / 'companion.started').exists(), 'Shared loader did not initialize companion'
            assert not stderr, stderr
            if wrong_name: assert not (folder / STATUS).exists()
            else:
                status = json.loads((folder / STATUS).read_text())
                assert status['features']['wheel_mouse']['status'] == expected, status
                assert status['processId'] == process.pid
                startup = bool(config and config.get('features', {}).get('skip_startup_logos', {}).get('enabled', False))
                assert status['features']['skip_startup_logos']['enabled'] == startup
                assert status['features']['skip_startup_logos']['status'] == ('incompatible' if startup else 'disabled')
                general = bool(config and config.get('features', {}).get('general_improvements', {}).get('enabled', False))
                general_state = 'configuration-error' if expected == 'configuration-error' else 'incompatible' if general else 'disabled'
                assert status['features']['general_improvements'] == {'enabled': general, 'status': general_state}
                if map_state is not None:
                    assert status['features']['map']['status'] == map_state, status
                if synthetic:
                    core = status['components']['settings_menu']
                    assert core['enabled'] and core['running'], status
                    assert core['status'] == 'waiting-for-settings' and core['fault'] is None, status
                    zoom = core['zoomSensitivity']
                    panning = core['panningSensitivity']
                    assert panning['value'] == (0 if zoom_value != 50 else 50), status
                    assert panning['enabled'] == config['features'].get('map',{}).get('enabled',False), status
                    map_enabled = bool(config.get('features', {}).get('map', {}).get('enabled', False))
                    assert zoom['enabled'] == map_enabled and zoom['running'] == map_enabled, status
                    assert zoom['value'] == zoom_value and zoom['fault'] is None, status
                    assert status['settingsPersistence'] == ('default' if zoom_value == 50 else 'loaded'), status
                    assert set(status['features']) == {'wheel_mouse', 'map', 'skip_startup_logos', 'general_improvements', 'vehicle'}
                    for feature in status['features'].values():
                        if feature['status'] == 'active':
                            assert feature['compatibility']['relocatedGuards'] == GUARD_COUNT
                            assert feature['counters']['active']
                            assert feature['counters']['faults'] == 0
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
            assert not (folder / 'SnowRunnerEnhanced.asi').exists()
            process.communicate(timeout=10)
            assert process.returncode == 0
        finally:
            if process.poll() is None: process.kill(); process.wait()
    print('PASS running executable blocks installation', flush=True)


if __name__ == '__main__':
    (ROOT / 'build/tests').mkdir(exist_ok=True)
    verify()
    test_running_game_guard()
    for loader in LOADERS:
        run_case('shared loader ' + loader['version'],
                 {'schemaVersion': 1, 'features': {'wheel_mouse': {'enabled': True}}},
                 'active', delay=6000, synthetic=True, loader=loader)
    for name, config, state in [
        ('disabled', {'schemaVersion': 1, 'features': {'wheel_mouse': {'enabled': False}}}, 'disabled'),
        ('startup only, unsupported archive', {'schemaVersion': 1, 'features': {'skip_startup_logos': {'enabled': True}}}, 'disabled'),
        ('general improvements only, unsupported archive', {'schemaVersion': 1, 'features': {'general_improvements': {'enabled': True}}}, 'disabled'),
        ('omitted feature', {'schemaVersion': 1, 'features': {}}, 'disabled'),
        ('missing configuration', None, 'configuration-error'),
        ('unknown feature', {'schemaVersion': 1, 'features': {'other': {'enabled': True}}}, 'configuration-error'),
        ('invalid boolean', {'schemaVersion': 1, 'features': {'wheel_mouse': {'enabled': 'true'}}}, 'configuration-error')]:
        run_case(name, config, state)
    run_case('wrong executable', None, None, wrong_name=True)
    run_case('active relocated image', {'schemaVersion': 1, 'features': {'wheel_mouse': {'enabled': True}}},
             'active', delay=6000, synthetic=True)
    run_case('both features independent', {'schemaVersion': 1, 'features': {'wheel_mouse': {'enabled': True}, 'skip_startup_logos': {'enabled': True}}}, 'active', delay=6000, synthetic=True)
    run_case('unrecognized signatures', {'schemaVersion': 1, 'features': {'wheel_mouse': {'enabled': True}}},
             'incompatible', delay=68000)

    for wheel, map_enabled in ((False, False), (False, True), (True, False), (True, True)):
        run_case('independent Map=' + str(map_enabled) + ' wheel=' + str(wheel),
                 {'schemaVersion': 1, 'features': {'wheel_mouse': {'enabled': wheel}, 'map': {'enabled': map_enabled}}},
                 'active' if wheel else 'disabled', delay=6000,
                 synthetic=True, map_state='active' if map_enabled else 'disabled', zoom_value=75)
