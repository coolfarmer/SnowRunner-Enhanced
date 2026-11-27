"""Exercise the diagnostic ASI through real loaders in disposable directories."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from native_host import NativeDevice

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from asi_loaders import LOADERS, loader_path, verify

MODE = os.environ.get('ENHANCED_DIAGNOSTIC_TEST_MODE', 'no-hooks')
FAST_FEATURES = int(MODE.removeprefix('fast-features-').split('-')[0],16) if MODE.startswith('fast-features-') else 0
if MODE not in ('no-hooks', 'menu-only', 'menu-grouped', 'empty-hook', 'discovery-only', 'menu-fast') and not (0 < FAST_FEATURES <= 63):
    raise ValueError('Unknown diagnostic test mode')
MENU_ONLY = MODE != 'no-hooks'
BUILD = ROOT / ('build/loading-diagnostic-' + MODE if MENU_ONLY else 'build/loading-diagnostic')
FEATURES = ('wheel_mouse', 'skip_startup_logos', 'map', 'general_improvements',
            'vehicle', 'steering_wheel_improvements')
BITS = dict(zip(FEATURES,(1,2,4,8,16,32)))
STATUS = 'SnowRunnerEnhanced.loading-diagnostic-' + MODE + '.status.json' if MENU_ONLY else 'SnowRunnerEnhanced.loading-diagnostic.status.json'


@unittest.skipUnless('ENHANCED_DIAGNOSTIC_TEST_MODE' in os.environ,
                     'Run through tools/build_loading_diagnostic.py for a built diagnostic variant')
class LoadingDiagnosticTests(unittest.TestCase):
    @unittest.skipIf(MENU_ONLY, 'Menu-only intentionally installs core hooks; tested in the synthetic host')
    def test_embedded_bundle_never_requests_hooks_or_discovery(self):
        # Exercise the exact generated JS, not just its self-reported mode.
        encoded = (BUILD / 'bundle.h').read_text().split('= {', 1)[1].split('};', 1)[0]
        values = [int(value) for value in encoded.replace('\n', '').split(',')]
        self.assertEqual(values.pop(), 0)
        bundle = bytes(values).decode('utf-8')
        device = NativeDevice()
        pid = device.spawn(None)
        try:
            prelude = '''
const attempts = [], reports = [];
const forbidden = name => function () { attempts.push(name); throw Error(name); };
const Interceptor = {attach: forbidden('attach'), replace: forbidden('replace'),
    replaceFast: forbidden('replaceFast')};
const Memory = {...globalThis.Memory, scan: forbidden('scan'), scanSync: forbidden('scanSync')};
const send = report => reports.push(report);
const ENHANCED_HOST = {gameSha256:'fixture', modules: MODULES};
'''.replace('MODULES', json.dumps(dict.fromkeys(FEATURES, True)))
            script = device.create_script('(() => {\n' + prelude + bundle + '''
rpc.exports = {check() {
    reportLoadingDiagnostic();
    return {attempts, reports, agent: nativeAgent.status()};
}};
})();
''')
            script.load()
            state = script.exports_sync.check()
            self.assertEqual(state['attempts'], [])
            self.assertFalse(state['agent']['active'])
            self.assertGreaterEqual(len(state['reports']), 2)
            self.assertTrue(all('enhancedStatus' in report for report in state['reports']))
            script.unload()
        finally:
            device.kill(pid)

    def run_case(self, loader, config, wrong_name=False, compatible=True, steering_compatible=True):
        verify()
        with tempfile.TemporaryDirectory(prefix='host-', dir=BUILD) as directory:
            folder = Path(directory)
            exe = folder / ('Other.exe' if wrong_name else 'SnowRunner.exe')
            if MENU_ONLY and not wrong_name and compatible:
                from native_image import create_image
                create_image(BUILD / 'game-host.exe', exe, steering=bool(FAST_FEATURES & 32) and steering_compatible)
            else:
                shutil.copyfile(BUILD / 'game-host.exe', exe)
            shutil.copyfile(BUILD / 'SnowRunnerEnhanced.asi', folder / 'SnowRunnerEnhanced.asi')
            shutil.copyfile(BUILD / 'companion.asi', folder / 'ZZCompanion.asi')
            shutil.copyfile(loader_path(loader), folder / 'dinput8.dll')
            if config is not None:
                (folder / 'SnowRunnerEnhanced.json').write_text(config)
            (folder / 'SnowRunnerEnhanced.settings.json').write_text(json.dumps({
                'schemaVersion': 5, 'automaticReverse': False, 'zoomSensitivity': 75,
                'panningSensitivity': 25, 'keepNorthUp': True, 'truckStorageSearch': True}))
            (folder / 'SnowRunnerEnhanced.status.json').write_text('{"previousSession":true}')
            if MENU_ONLY:
                (folder / 'SnowRunnerEnhanced.loading-diagnostic.status.json').write_text('{"previousDiagnostic":true}')
            original = {p.name: p.read_bytes() for p in folder.iterdir()}
            run = subprocess.run([exe, '4600'], cwd=folder, capture_output=True, timeout=20)
            self.assertEqual(run.returncode, 0, (run.stdout, run.stderr))
            self.assertFalse(run.stderr, run.stderr)
            self.assertIn(b'DirectInput forwarding works', run.stdout)
            self.assertIn(b'Enhanced loaded: yes', run.stdout)
            self.assertTrue((folder / 'companion.started').exists())
            for name, data in original.items():
                self.assertEqual((folder / name).read_bytes(), data, name)
            if wrong_name:
                self.assertFalse((folder / STATUS).exists())
                return
            report = json.loads((folder / STATUS).read_text())
            self.assertEqual(report['buildMode'], 'loading-diagnostic-' + MODE)
            menu = report['components']['settings_menu']
            if MENU_ONLY:
                if compatible and MODE in ('empty-hook', 'discovery-only'):
                    self.assertFalse(menu['enabled'])
                    self.assertFalse(menu['running'])
                    self.assertEqual(menu['status'], 'disabled')
                    self.assertIsNone(menu['fault'])
                    if MODE == 'discovery-only':
                        self.assertTrue(menu['probeInitialized'])
                        self.assertEqual(menu['interception'], dict(mode='discovery-only', nativeHooks=0, filters=0))
                    else:
                        self.assertEqual(menu['interception'], dict(mode='empty', nativeHooks=1, filters=0))
                elif compatible:
                    self.assertTrue(menu['enabled'])
                    self.assertTrue(menu['running'])
                    self.assertEqual(menu['status'], 'waiting-for-settings')
                    self.assertIsNone(menu['fault'])
                    if MODE == 'menu-grouped':
                        self.assertEqual(menu['interception'], dict(mode='grouped', registrations=9,
                                         activeRegistrations=9, nativeHooks=1))
                    if MODE == 'menu-fast':
                        self.assertEqual(menu['interception'], dict(mode='fast-native', registrations=9,
                                         activeRegistrations=9, nativeHooks=0, fastReplacements=1))
                    if FAST_FEATURES:
                        dispatch=report['components']['vm_dispatch']
                        self.assertEqual(dispatch['mode'],'fast-shared')
                        self.assertTrue(dispatch['committed'])
                        self.assertIsNone(dispatch['fault'])
                        self.assertEqual(dispatch['entry']['nativeHooks'],0)
                        self.assertEqual(dispatch['entry']['fastReplacements'],1)
                        if FAST_FEATURES in (1,4):
                            expected = 10 if FAST_FEATURES == 1 else 19
                            self.assertEqual(dispatch['entry']['registrations'],expected)
                            self.assertEqual(dispatch['entry']['activeRegistrations'],expected)
                            self.assertEqual(dispatch['interior']['registrations'],0)
                            self.assertEqual(dispatch['interior']['fastReplacements'],0)
                        if FAST_FEATURES in (8,16):
                            self.assertEqual(dispatch['entry']['registrations'],9)
                            self.assertEqual(dispatch['entry']['activeRegistrations'],9)
                            self.assertEqual(dispatch['interior']['registrations'],6)
                            self.assertEqual(dispatch['interior']['activeRegistrations'],6)
                            self.assertEqual(dispatch['interior']['nativeHooks'],0)
                            self.assertEqual(dispatch['interior']['fastReplacements'],1)
                            self.assertEqual(report['components']['functions_repeat']['status'],
                                             'ready' if FAST_FEATURES == 8 else 'disabled')
                        if FAST_FEATURES in (29,31,63):
                            for phase,count in (('entry',20),('interior',12)):
                                self.assertEqual(dispatch[phase]['registrations'],count)
                                self.assertEqual(dispatch[phase]['activeRegistrations'],count)
                                self.assertEqual(dispatch[phase]['nativeHooks'],0)
                                self.assertEqual(dispatch[phase]['fastReplacements'],1)
                                if MODE.endswith('-indexed'):
                                    self.assertEqual(dispatch[phase]['filter'],'positive-index-and-name-trie')
                                if '-indexed-prefix' in MODE:
                                    self.assertEqual(dispatch[phase]['filter'],'native-class-prefix-and-name-trie')
                            self.assertEqual(report['components']['functions_repeat']['status'],'ready')
                    for name in ('zoomSensitivity', 'panningSensitivity'):
                        self.assertEqual(menu[name]['enabled'],bool(FAST_FEATURES & 4))
                        self.assertEqual(menu[name]['running'],bool(FAST_FEATURES & 4))
                else:
                    self.assertFalse(menu.get('running', False))
                    self.assertEqual(menu['status'], 'waiting')
            else:
                self.assertEqual(report['diagnostic']['status'], 'running')
                self.assertFalse(report['diagnostic']['gameHooksEnabled'])
                self.assertGreaterEqual(report['diagnostic']['reports'], 2)
                self.assertGreaterEqual(report['diagnostic']['elapsedMs'], 1900)
                self.assertFalse(menu['running'])
                self.assertEqual(menu['status'], 'disabled')
            self.assertEqual(set(report['features']), set(FEATURES))
            for name,feature in report['features'].items():
                selected=bool(FAST_FEATURES & BITS[name])
                self.assertEqual(feature['enabled'],selected)
                if not selected:self.assertEqual(feature['status'], 'disabled')
                elif name == 'steering_wheel_improvements':
                    expected_active = compatible and steering_compatible
                    self.assertEqual(feature['status'], 'active' if expected_active else 'incompatible')
                    self.assertEqual(feature['armed'], expected_active)
                    self.assertEqual(feature['failed'], 0)
                    self.assertEqual(feature['applied'], 0)  # Synthetic loader does not construct a wheel.
                    if expected_active:
                        self.assertGreater(feature['relocatedGuards'], 0)
                elif compatible and name in ('wheel_mouse','map'):
                    self.assertEqual(feature['status'],'active')
                    self.assertEqual(feature['counters']['faults'],0)
                elif compatible and selected and name == 'vehicle':
                    self.assertEqual(feature['status'],'active',feature)
                    self.assertIsNone(feature['fault'])
                    self.assertIsNone(feature['reverseError'])
                    self.assertEqual(feature['unknown'],0)
                    self.assertFalse(feature['automaticReverse'])  # Fixture's saved choice.
                    self.assertEqual(feature['truckSearch']['status'],'ready')
                    self.assertTrue(feature['truckSearch']['enabled'])
                    self.assertIsNone(feature['truckSearch']['fault'])
                    self.assertEqual(feature['winch']['status'],'active')
                    self.assertIsNone(feature['winch']['fault'])
                elif selected and name in ('general_improvements','skip_startup_logos'):
                    # The disposable host has no game archive. Its archive guard
                    # must refuse that portion even when VM repeat hooks succeed.
                    self.assertEqual(feature['status'],'incompatible')
            self.assertFalse((folder / STATUS.replace('.json', '.tmp')).exists())
            self.assertEqual(set(p.name for p in folder.iterdir()) - set(original),
                             {STATUS, 'companion.started'})

    def test_all_features_selected_stay_disabled_with_both_loaders(self):
        config = json.dumps({'schemaVersion': 1, 'features':
                             {name: {'enabled': True} for name in FEATURES}})
        for loader in LOADERS:
            with self.subTest(loader=loader['version']):
                self.run_case(loader, config)

    def test_missing_and_invalid_configuration_do_not_enable_hooks(self):
        for config in (None, '{invalid'):
            with self.subTest(config=config):
                self.run_case(LOADERS[0], config)

    def test_other_executable_is_ignored(self):
        self.run_case(LOADERS[0], None, wrong_name=True)

    @unittest.skipUnless(MENU_ONLY, 'Only the menu variant performs signature discovery')
    def test_menu_waits_without_hooks_when_signatures_are_missing(self):
        self.run_case(LOADERS[0], None, compatible=False)

    @unittest.skipUnless(FAST_FEATURES & 32, 'Only variants selecting FFB exercise its isolation')
    def test_missing_steering_signatures_preserve_other_groups(self):
        self.run_case(LOADERS[0], None, steering_compatible=False)


if __name__ == '__main__':
    unittest.main()
