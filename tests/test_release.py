"""Exercise the published installer against temporary native game fixtures."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time
import unittest
import pefile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'dist/SnowRunnerEnhanced-1.0.0'
SETUP = PACKAGE / 'Sources/Installer/SnowRunnerEnhanced.Setup.exe'
CONFIG = 'SnowRunnerEnhanced.json'
RECEIPT = 'SnowRunnerEnhanced.install.json'
BINARY = 'SnowRunnerEnhanced.asi'


@unittest.skipUnless(SETUP.is_file(), 'Build and package the native release first')
class ReleaseTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'build/tests').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='release-', dir=ROOT / 'build/tests')
        self.folder = Path(self.temp.name)
        shutil.copyfile(ROOT / 'build/native/game-host.exe', self.folder / 'SnowRunner.exe')
        self.sentinels = {'dinput8.dll': (PACKAGE / 'Sources/Payload/dinput8.dll').read_bytes(),
                          'SnowRunnerFFBFix.asi': b'existing independent correction',
                          'SnowRunnerFFBFix.ini': b'untouched settings'}
        for name, content in self.sentinels.items(): (self.folder / name).write_bytes(content)

    def tearDown(self):
        for name, content in self.sentinels.items():
            self.assertEqual((self.folder / name).read_bytes(), content)
        self.temp.cleanup()

    def run_setup(self, action, *extra, success=True, game=None):
        result = subprocess.run([SETUP, '--action', action, '--game-directory', game or self.folder,
                                 '--json', *extra], capture_output=True, text=True, encoding='utf-8', timeout=30)
        data = json.loads(result.stdout)
        self.assertEqual(data['ok'], success, result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0 if success else 2, result.stdout)
        return data.get('result', data)

    def test_install_toggle_uninstall_preserves_other_mod(self):
        before = hashlib.sha256((self.folder / 'SnowRunner.exe').read_bytes()).hexdigest()
        self.assertFalse(self.run_setup('check')['installed'])
        installed = self.run_setup('install')
        for flag in ('wheelMouseEnabled', 'mapEnabled', 'skipStartupLogosEnabled', 'generalImprovementsEnabled'):
            self.assertTrue(installed[flag], flag)
        self.assertFalse(self.run_setup('configure', '--wheel-mouse', 'false')['wheelMouseEnabled'])
        self.assertTrue(self.run_setup('configure', '--wheel-mouse', 'true')['wheelMouseEnabled'])
        self.run_setup('uninstall')
        self.assertEqual(set(p.name for p in self.folder.iterdir()), {'SnowRunner.exe', *self.sentinels})
        self.assertEqual(hashlib.sha256((self.folder / 'SnowRunner.exe').read_bytes()).hexdigest(), before)

    def test_startup_option_is_independent_and_preserved(self):
        result=self.run_setup('install', '--wheel-mouse', 'false', '--skip-startup-logos', 'true')
        self.assertFalse(result['wheelMouseEnabled'])
        self.assertTrue(result['skipStartupLogosEnabled'])
        result=self.run_setup('configure', '--wheel-mouse', 'true')
        self.assertTrue(result['skipStartupLogosEnabled'])
        result=self.run_setup('configure', '--skip-startup-logos', 'false')
        self.assertTrue(result['wheelMouseEnabled'])
        self.assertFalse(result['skipStartupLogosEnabled'])
        self.run_setup('configure', '--skip-startup-logos', 'invalid', success=False)
        self.run_setup('uninstall')

    def test_each_enhancement_change_reinstalls_plugin(self):
        self.run_setup('install')
        plugin = self.folder / BINARY
        expected = plugin.read_bytes()
        preference = self.folder / 'SnowRunnerEnhanced.settings.json'
        preference.write_bytes(b'{"schemaVersion":2,"zoomSensitivity":75}')
        options = (
            ('wheel-mouse', 'wheelMouseEnabled'), ('skip-startup-logos', 'skipStartupLogosEnabled'),
            ('map', 'mapEnabled'), ('general-improvements', 'generalImprovementsEnabled'),
            ('vehicle', 'vehicleEnabled'), ('steering-wheel-improvements', 'steeringWheelImprovementsEnabled'))
        for option, status in options:
            for enabled in (False, True):
                with self.subTest(option=option, enabled=enabled):
                    previous_file_id = plugin.stat().st_ino
                    result = self.run_setup('configure', '--' + option, str(enabled).lower())
                    self.assertEqual(result[status], enabled)
                    self.assertNotEqual(plugin.stat().st_ino, previous_file_id)
                    self.assertEqual(plugin.read_bytes(), expected)
                    for _, other in options:
                        if other != status:
                            self.assertTrue(result[other])
                    self.assertEqual(preference.read_bytes(), b'{"schemaVersion":2,"zoomSensitivity":75}')
        self.run_setup('uninstall')

    def test_interactive_update_feedback_in_both_languages(self):
        self.run_setup('install')
        for language, message, saved in (
                ('fr', 'Mise à jour du plugin en cours…', 'Choix enregistré.'),
                ('en', 'Updating plugin…', 'Selection saved.')):
            with self.subTest(language=language):
                started = time.monotonic()
                result = subprocess.run(
                    [SETUP, '--plain', '--language', language, '--game-directory', self.folder],
                    # Advanced > Customize: disable, enable, then save unchanged.
                    input='2\n2\n' + '2\n' * 6 + '2\n2\n' + '1\n' * 6
                          + '2\n2\n' + '1\n' * 6 + '5\n',
                    capture_output=True, text=True, encoding='utf-8', timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.count(message), 2)
                self.assertGreaterEqual(time.monotonic() - started, 2)
                self.assertEqual(result.stdout.count(saved), 3)
                self.assertLess(result.stdout.index(message), result.stdout.index(saved))
                self.assertTrue(self.run_setup('status')['wheelMouseEnabled'])
        self.run_setup('uninstall')

    def test_unchanged_choices_keep_plugin(self):
        self.run_setup('install')
        before = (self.folder / BINARY).stat().st_ino
        self.run_setup('configure', '--map', 'true')
        self.assertEqual((self.folder / BINARY).stat().st_ino, before)
        self.run_setup('uninstall')

    def test_failed_update_restores_plugin_and_choices(self):
        self.run_setup('install')
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        for locked in (BINARY, CONFIG, RECEIPT):
            with self.subTest(locked=locked):
                before = {name: (self.folder / name).read_bytes() for name in (BINARY, CONFIG, RECEIPT)}
                handle = kernel.CreateFileW(str(self.folder / locked), 0x80000000, 1, None, 3, 0, None)
                self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
                try:
                    self.run_setup('configure', '--map', 'false', success=False)
                    for name, content in before.items():
                        self.assertEqual((self.folder / name).read_bytes(), content)
                finally:
                    kernel.CloseHandle(handle)
        self.run_setup('uninstall')

    def test_map_preferences_survive_configure_and_reinstall(self):
        preference = self.folder/'SnowRunnerEnhanced.settings.json'
        contents = b'{"schemaVersion":2,"zoomSensitivity":75,"panningSensitivity":0}\n'
        self.run_setup('install')
        preference.write_bytes(contents)
        self.run_setup('configure', '--map', 'false')
        self.run_setup('uninstall')
        self.assertEqual(preference.read_bytes(), contents)
        self.run_setup('install')
        self.assertEqual(preference.read_bytes(), contents)
        self.run_setup('uninstall')

    def test_map_option_is_independent(self):
        result = self.run_setup('install', '--wheel-mouse', 'false')
        self.assertTrue(result['mapEnabled'])
        self.assertFalse(result['wheelMouseEnabled'])
        result = self.run_setup('configure', '--map', 'false', '--wheel-mouse', 'true')
        self.assertFalse(result['mapEnabled'])
        self.assertTrue(result['wheelMouseEnabled'])
        result = self.run_setup('configure', '--skip-startup-logos', 'true')
        self.assertFalse(result['mapEnabled'])
        result = self.run_setup('configure', '--map', 'true', '--wheel-mouse', 'false')
        self.assertTrue(result['mapEnabled'])
        self.assertFalse(result['wheelMouseEnabled'])
        self.assertTrue(result['skipStartupLogosEnabled'])
        self.run_setup('configure', '--map', 'invalid', success=False)
        self.run_setup('uninstall')

    def test_legacy_configuration_keeps_startup_disabled(self):
        self.run_setup('install')
        (self.folder / CONFIG).write_text(json.dumps({'schemaVersion':1,'features':{'wheel_mouse':{'enabled':True}}}))
        result=self.run_setup('configure', '--wheel-mouse', 'false')
        self.assertFalse(result['skipStartupLogosEnabled'])
        self.assertFalse(result['generalImprovementsEnabled'])
        self.run_setup('uninstall')

    def test_existing_preview_updates_preserving_feature_choices(self):
        self.run_setup('install', '--wheel-mouse', 'false', '--map', 'false',
                       '--skip-startup-logos', 'false', '--general-improvements', 'false')
        receipt_path = self.folder / RECEIPT
        receipt = json.loads(receipt_path.read_text())
        del receipt['allEnabledDefaults']
        plugin = self.folder / 'SnowRunnerEnhanced.asi'
        original = plugin.read_bytes()
        plugin.write_bytes(b'prior preview')
        receipt['files'][plugin.name] = hashlib.sha256(plugin.read_bytes()).hexdigest()
        receipt_path.write_text(json.dumps(receipt))
        result = self.run_setup('install')
        self.assertEqual(plugin.read_bytes(), original)
        for flag in ('wheelMouseEnabled', 'mapEnabled', 'skipStartupLogosEnabled', 'generalImprovementsEnabled'):
            self.assertFalse(result[flag])
        self.run_setup('configure', '--map', 'false')
        self.assertFalse(self.run_setup('configure')['mapEnabled'])
        self.run_setup('uninstall')

    def test_steering_option_and_update_preserve_choices(self):
        result = self.run_setup('install', '--map', 'false', '--steering-wheel-improvements', 'false')
        self.assertFalse(result['steeringWheelImprovementsEnabled'])
        self.assertTrue(self.run_setup('configure', '--steering-wheel-improvements', 'true')['steeringWheelImprovementsEnabled'])
        self.assertFalse(self.run_setup('configure')['mapEnabled'])
        self.run_setup('configure', '--steering-wheel-improvements', 'invalid', success=False)
        # Model an older configuration with no sixth enhancement.
        config = json.loads((self.folder / CONFIG).read_text())
        del config['features']['steering_wheel_improvements']
        (self.folder / CONFIG).write_text(json.dumps(config))
        receipt = json.loads((self.folder / RECEIPT).read_text())
        receipt['version'] = '0.1.0-preview.29'
        (self.folder / RECEIPT).write_text(json.dumps(receipt))
        result = self.run_setup('install')
        self.assertTrue(result['steeringWheelImprovementsEnabled'])
        self.assertFalse(result['mapEnabled'])
        self.run_setup('configure', '--steering-wheel-improvements', 'false')
        self.assertFalse(self.run_setup('configure', '--vehicle', 'false')['steeringWheelImprovementsEnabled'])
        self.run_setup('uninstall')

    def test_independent_vehicle_configuration(self):
        self.assertTrue(self.run_setup('install')['vehicleEnabled'])
        self.assertFalse(self.run_setup('configure', '--vehicle', 'false')['vehicleEnabled'])
        self.assertFalse(self.run_setup('configure', '--map', 'false')['vehicleEnabled'])
        result = self.run_setup('configure', '--vehicle', 'true')
        self.assertTrue(result['vehicleEnabled'])
        self.assertFalse(result['mapEnabled'])
        self.run_setup('uninstall')

    def test_general_improvements_can_run_alone(self):
        result = self.run_setup('install', '--wheel-mouse', 'false', '--map', 'false', '--skip-startup-logos', 'false')
        self.assertTrue(result['generalImprovementsEnabled'])
        self.assertFalse(result['skipStartupLogosEnabled'])
        result = self.run_setup('configure', '--general-improvements', 'false')
        self.assertFalse(result['generalImprovementsEnabled'])
        result = self.run_setup('configure', '--skip-startup-logos', 'true')
        self.assertFalse(result['generalImprovementsEnabled'])
        result = self.run_setup('configure', '--general-improvements', 'true')
        self.assertTrue(result['generalImprovementsEnabled'])
        self.assertTrue(result['skipStartupLogosEnabled'])
        self.assertFalse(result['mapEnabled'])
        self.run_setup('uninstall')

    def test_unrelated_version_loader_is_preserved(self):
        (self.folder / 'version.dll').write_bytes(b'another mod')
        self.run_setup('install')
        self.run_setup('uninstall')
        self.assertEqual((self.folder / 'version.dll').read_bytes(), b'another mod')
        self.assertFalse((self.folder / BINARY).exists())

    def test_modified_binary_is_preserved(self):
        self.run_setup('install')
        with (self.folder / BINARY).open('ab') as stream: stream.write(b'changed')
        self.run_setup('uninstall', success=False)
        self.run_setup('configure', '--wheel-mouse', 'false', success=False)
        self.assertTrue((self.folder / BINARY).read_bytes().endswith(b'changed'))
        self.assertTrue((self.folder / 'dinput8.dll').exists())

    def test_bundled_loader_is_installed_once_and_retained(self):
        self.sentinels.pop('dinput8.dll')
        (self.folder / 'dinput8.dll').unlink()
        self.run_setup('install')
        receipt = json.loads((self.folder / RECEIPT).read_text())
        self.assertFalse(receipt['loader']['reused'])
        self.assertEqual(set(receipt['files']), {BINARY})
        result = self.run_setup('uninstall')
        self.assertIn('dinput8.dll', result['preserved'])
        self.assertEqual((self.folder / 'dinput8.dll').read_bytes(),
                         (PACKAGE / 'Sources/Payload/dinput8.dll').read_bytes())

    def test_smt_loader_is_reused_and_preserved(self):
        data = (ROOT / 'vendor/asi-loader/dinput8-8.5.0.dll').read_bytes()
        self.sentinels['dinput8.dll'] = data
        (self.folder / 'dinput8.dll').write_bytes(data)
        self.sentinels['SMT.asi'] = b'fixture, never executed'
        (self.folder / 'SMT.asi').write_bytes(self.sentinels['SMT.asi'])
        self.run_setup('install')
        receipt = json.loads((self.folder / RECEIPT).read_text())
        self.assertTrue(receipt['loader']['reused'])
        self.assertEqual(receipt['loader']['sha256'], hashlib.sha256(data).hexdigest())
        self.run_setup('uninstall')

    def test_unknown_loader_blocks_install_without_changes(self):
        self.sentinels['dinput8.dll'] = b'unknown proxy'
        (self.folder / 'dinput8.dll').write_bytes(self.sentinels['dinput8.dll'])
        self.assertFalse(self.run_setup('check')['loaderSupported'])
        self.run_setup('install', success=False)
        self.assertFalse((self.folder / BINARY).exists())
        self.assertFalse((self.folder / RECEIPT).exists())

    def test_loader_configuration_blocks_install_without_changes(self):
        for relative in ('dinput8.ini', 'plugins/global.ini', 'dinput8Hooked.dll'):
            with self.subTest(relative=relative):
                path = self.folder / relative
                path.parent.mkdir(exist_ok=True)
                content = b'[GlobalSets]\nLoadPlugins=0\n' if relative.endswith('.ini') else b'existing proxy'
                path.write_bytes(content)
                self.run_setup('install', success=False)
                self.assertEqual(path.read_bytes(), content)
                self.assertFalse((self.folder / RECEIPT).exists())
                path.unlink()

    def set_loader(self, data):
        self.sentinels['dinput8.dll'] = bytes(data)
        (self.folder / 'dinput8.dll').write_bytes(data)

    def test_standard_x64_loader_lifecycle(self):
        self.set_loader((ROOT / 'vendor/asi-loader/dinput8-10.0.2-standard.dll').read_bytes())
        self.assertTrue(self.run_setup('install')['loaderSupported'])
        self.run_setup('configure', '--wheel-mouse', 'false')
        receipt = json.loads((self.folder / RECEIPT).read_text())
        self.assertTrue(receipt['loader']['reused'])
        self.assertEqual(receipt['loader']['sha256'], hashlib.sha256(self.sentinels['dinput8.dll']).hexdigest())
        self.run_setup('uninstall')

    def test_unlisted_loader_version_is_accepted_silently(self):
        data = self.sentinels['dinput8.dll']
        # Change only version-resource text, without adding an allowlisted hash.
        old, new = '10.0.2'.encode('utf-16-le'), '99.0.0'.encode('utf-16-le')
        self.assertIn(old, data)
        self.set_loader(data.replace(old, new))
        result = self.run_setup('install')
        self.assertTrue(result['loaderSupported'])
        self.assertFalse(result['loaderKnownHash'])
        self.assertEqual(result['loaderVersion'], '99.0.0')
        self.assertNotIn('loaderReason', result)
        for language in ('fr', 'en'):
            output = subprocess.run([SETUP, '--action', 'status', '--game-directory', self.folder,
                                     '--plain', '--language', language], capture_output=True, text=True,
                                    encoding='utf-8', timeout=30)
            self.assertEqual(output.returncode, 0, output.stdout)
            self.assertNotIn('99.0.0', output.stdout)
            self.assertNotIn('loader', output.stdout.lower())
            self.assertNotIn('chargeur', output.stdout.lower())
        self.run_setup('configure', '--wheel-mouse', 'false')
        self.run_setup('uninstall')

    def test_loader_identity_and_exports_are_required(self):
        original = self.sentinels['dinput8.dll']
        with pefile.PE(data=original) as pe:
            marker = next(x for x in pe.DIRECTORY_ENTRY_EXPORT.symbols if x.name == b'IsUltimateASILoader')
            marker_offset = marker.name_offset
            addresses = pe.get_offset_from_rva(pe.DIRECTORY_ENTRY_EXPORT.struct.AddressOfFunctions)
            marker_index = marker.ordinal - pe.DIRECTORY_ENTRY_EXPORT.struct.Base
            export_rva = pe.OPTIONAL_HEADER.DATA_DIRECTORY[0].VirtualAddress
        bad_address = bytearray(original)
        struct.pack_into('<I', bad_address, addresses + marker_index * 4, 0)
        forwarded = bytearray(original)
        struct.pack_into('<I', forwarded, addresses + marker_index * 4, export_rva)
        bad_name = bytearray(original)
        bad_name[marker_offset] = ord('X')
        publisher = 'ThirteenAG'.encode('utf-16-le')
        self.assertIn(publisher, original)
        for data in (bad_name, bad_address, forwarded,
                     original.replace(publisher, 'OtherMaker'.encode('utf-16-le')),
                     original.replace(b'DirectInput8Create\0', b'XirectInput8Create\0')):
            with self.subTest(hash=hashlib.sha256(data).hexdigest()):
                self.set_loader(data)
                result = self.run_setup('install', '--language', 'en', success=False)
                self.assertIn('not recognized', result['error'])
                self.assertFalse((self.folder / RECEIPT).exists())
                self.assertFalse((self.folder / BINARY).exists())

    def test_wrong_architecture_and_corrupt_loaders_have_clear_errors(self):
        original = self.sentinels['dinput8.dll']
        pe_offset = struct.unpack_from('<I', original, 0x3c)[0]
        x86 = bytearray(original)
        struct.pack_into('<H', x86, pe_offset + 4, 0x14c)
        malformed = bytearray(original)
        with pefile.PE(data=original) as pe:
            offset = pe.OPTIONAL_HEADER.DATA_DIRECTORY[0].get_file_offset()
        struct.pack_into('<I', malformed, offset, 0x7fffffff)
        for data, english, french in ((x86, '32-bit', '32 bits'),
                                      (b'not a DLL', 'not a valid', 'pas une DLL'),
                                      (malformed, 'not a valid', 'pas une DLL')):
            self.set_loader(data)
            for language, expected in (('en', english), ('fr', french)):
                with self.subTest(language=language, expected=expected):
                    result = self.run_setup('install', '--language', language, success=False)
                    self.assertIn(expected, result['error'])
                    status = self.run_setup('check', '--language', language)
                    self.assertFalse(status['loaderSupported'])
                    self.assertIn(expected, status['loaderReason'])
                    self.assertFalse((self.folder / RECEIPT).exists())

    def test_harmless_loader_configuration_is_preserved(self):
        for relative in ('dinput8.ini', 'global.ini', 'scripts/global.ini', 'plugins/global.ini', 'update/global.ini', 'plugins/dinput8.ini'):
            path = self.folder / relative
            path.parent.mkdir(exist_ok=True)
            content = b'[GlobalSets]\nDebugLog=1\nLoadPlugins=1\nLoadFromScriptsOnly=0\nDontLoadFromDllMain=1\n'
            self.sentinels[relative] = content
            path.write_bytes(content)
        self.run_setup('install')
        self.run_setup('configure', '--wheel-mouse', 'false')
        self.run_setup('uninstall')

    def test_loader_configuration_precedence(self):
        # Later global.ini files override individual keys, including dinput8.ini.
        files = [('dinput8.ini', 0), ('global.ini', 1), ('scripts/global.ini', 0),
                 ('plugins/global.ini', 1), ('update/global.ini', 0)]
        for relative, enabled in files:
            path = self.folder / relative
            path.parent.mkdir(exist_ok=True)
            content = f'[gLoBaLsEtS]\nlOaDpLuGiNs={enabled}\n'.encode()
            self.sentinels[relative] = content
            path.write_bytes(content)
            self.assertEqual(self.run_setup('check')['loaderSupported'], bool(enabled))
        result = self.run_setup('install', '--language', 'en', success=False)
        self.assertIn('update\\global.ini', result['error'])
        self.sentinels['update/global.ini'] = b'[Other]\nLoadPlugins=0\n'
        (self.folder / 'update/global.ini').write_bytes(self.sentinels['update/global.ini'])
        self.run_setup('install')
        self.run_setup('uninstall')

    def test_loader_settings_explain_actionable_blockages(self):
        for key, value in (('LoadPlugins', 0), ('LoadFromScriptsOnly', 1), ('DontLoadFromDllMain', 0)):
            for encoding in ('utf-8', 'utf-16'):
                content = f'[GlobalSets]\n{key}={value}\n'.encode(encoding)
                (self.folder / 'dinput8.ini').write_bytes(content)
                for language, hint in (('en', 'Setting to change'), ('fr', 'Réglage à corriger')):
                    result = self.run_setup('install', '--language', language, success=False)
                    self.assertIn(hint, result['error'])
                    self.assertIn(key + '=' + str(1 - value), result['error'])
                    self.assertEqual((self.folder / 'dinput8.ini').read_bytes(), content)
                    self.assertFalse((self.folder / RECEIPT).exists())

    def test_configuration_error_identifies_last_explicit_override(self):
        (self.folder / 'dinput8.ini').write_text('[GlobalSets]\nLoadPlugins=0\n')
        (self.folder / 'global.ini').write_text('[GlobalSets]\nLoadPlugins=0\n')
        result = self.run_setup('install', '--language', 'en', success=False)
        self.assertIn('global.ini:', result['error'])

    def test_explicit_extra_plugin_allows_scripts_only_configuration(self):
        content = b'[GlobalSets]\nLoadFromScriptsOnly=1\nLoadExtraPlugins=other.asi|.\\SnowRunnerEnhanced.asi\n'
        self.sentinels['dinput8.ini'] = content
        (self.folder / 'dinput8.ini').write_bytes(content)
        self.run_setup('install')
        self.run_setup('uninstall')
        (self.folder / 'global.ini').write_text('[GlobalSets]\nLoadExtraPlugins=other.asi\n')
        result = self.run_setup('install', '--language', 'en', success=False)
        self.assertIn('LoadFromScriptsOnly=0', result['error'])
        (self.folder / 'global.ini').unlink()
        self.set_loader((ROOT / 'vendor/asi-loader/dinput8-8.5.0.dll').read_bytes())
        result = self.run_setup('install', '--language', 'en', success=False)
        self.assertIn('LoadFromScriptsOnly=0', result['error'])

    def test_changed_shared_loader_does_not_block_removal(self):
        self.run_setup('install')
        self.sentinels['dinput8.dll'] = b'replaced by another mod'
        (self.folder / 'dinput8.dll').write_bytes(self.sentinels['dinput8.dll'])
        self.assertFalse(self.run_setup('status')['loaderSupported'])
        self.run_setup('uninstall')
        self.assertFalse((self.folder / BINARY).exists())

    def test_missing_shared_loader_is_reported_and_does_not_block_removal(self):
        self.run_setup('install')
        self.sentinels.pop('dinput8.dll')
        (self.folder / 'dinput8.dll').unlink()
        for language, expected in (('en', 'missing'), ('fr', 'manquant')):
            status = self.run_setup('status', '--language', language)
            self.assertFalse(status['loaderSupported'])
            self.assertIn(expected, status['loaderReason'])
        self.run_setup('uninstall')
        self.assertFalse((self.folder / BINARY).exists())

    def test_legacy_installation_requires_old_uninstaller(self):
        old = {'product': 'SnowRunnerEnhanced', 'schemaVersion': 1,
               'files': {'version.dll': '0' * 64, 'SnowRunnerEnhanced.dll': '0' * 64}}
        (self.folder / RECEIPT).write_text(json.dumps(old))
        for name in ('version.dll', 'SnowRunnerEnhanced.dll'):
            (self.folder / name).write_bytes(b'legacy')
        for action in ('install', 'uninstall'):
            result = self.run_setup(action, success=False)
            self.assertIn('preview.1', json.dumps(result))
        self.assertEqual(json.loads((self.folder / RECEIPT).read_text()), old)
        self.assertFalse((self.folder / BINARY).exists())

    def test_modified_config_retained_on_uninstall(self):
        self.run_setup('install')
        content = (self.folder / CONFIG).read_text() + '\n'
        (self.folder / CONFIG).write_text(content)
        result = self.run_setup('uninstall')
        self.assertIn(CONFIG, result['preserved'])
        self.assertEqual((self.folder / CONFIG).read_text(), content)

    def test_invalid_or_unknown_configuration_is_rejected(self):
        self.run_setup('install')
        for features in ({'wheel_mouse': {'enabled': 'false'}}, {'unknown': {'enabled': True}}):
            content = json.dumps({'schemaVersion': 1, 'features': features})
            (self.folder / CONFIG).write_text(content)
            self.run_setup('configure', '--wheel-mouse', 'false', success=False)
            self.assertEqual((self.folder / CONFIG).read_text(), content)

    def test_incomplete_install_can_be_removed(self):
        self.run_setup('install')
        (self.folder / BINARY).unlink()
        (self.folder / CONFIG).unlink()
        self.run_setup('uninstall')
        self.assertFalse((self.folder / BINARY).exists())

    def test_locked_dll_prevents_partial_uninstall(self):
        self.run_setup('install')
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(self.folder / BINARY), 0x80000000, 1, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            self.run_setup('uninstall', success=False)
            for name in ('dinput8.dll', BINARY, RECEIPT, CONFIG): self.assertTrue((self.folder / name).exists())
        finally: kernel.CloseHandle(handle)
        self.run_setup('uninstall')

    def test_executable_without_dinput_import_refused(self):
        shutil.copyfile(ROOT / 'build/native/native-harness.exe', self.folder / 'SnowRunner.exe')
        self.run_setup('install', success=False)
        self.assertFalse((self.folder / RECEIPT).exists())

    def test_uninstall_survives_changed_game_imports(self):
        self.run_setup('install')
        shutil.copyfile(ROOT / 'build/native/native-harness.exe', self.folder / 'SnowRunner.exe')
        self.assertFalse(self.run_setup('status')['loaderSupported'])
        self.run_setup('uninstall')
        self.assertFalse((self.folder / BINARY).exists())

    def test_invalid_configuration_still_allows_diagnostic(self):
        self.run_setup('install')
        (self.folder / CONFIG).write_text('{broken')
        result = self.run_setup('status')
        self.assertIn('configurationError', result)

    def test_package_corruption_is_rejected(self):
        other = self.folder / 'package'
        shutil.copytree(PACKAGE / 'Sources', other / 'Sources', ignore=shutil.ignore_patterns('Reports'))
        (other / 'Sources/Payload/SnowRunnerEnhanced.asi').write_bytes(b'broken')
        result = subprocess.run([other / 'Sources/Installer/SnowRunnerEnhanced.Setup.exe',
            '--action', 'install', '--game-directory', self.folder, '--json'], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)['ok'])
        self.assertFalse((self.folder / RECEIPT).exists())

    def test_game_root_and_unicode_paths(self):
        root = self.folder / 'Jeu été test'
        bin = root / 'Sources/Bin'
        bin.mkdir(parents=True)
        shutil.copyfile(ROOT / 'build/native/game-host.exe', bin / 'SnowRunner.exe')
        result = self.run_setup('install', '--wheel-mouse', 'false', game=root)
        self.assertFalse(result['wheelMouseEnabled'])
        self.run_setup('uninstall', game=bin / 'SnowRunner.exe')

    def test_plain_preview_and_eof_do_not_change_game(self):
        for language in ('fr', 'en'):
            result = subprocess.run([SETUP, '--preview', '--plain', '--language', language],
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0)
            self.assertIn(b'SnowRunner Enhanced', result.stdout)
        result = subprocess.run([SETUP, '--plain', '--language', 'fr', '--game-directory', self.folder],
                                input=b'', capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertFalse((self.folder / RECEIPT).exists())

    def test_duplicate_arguments_rejected(self):
        self.run_setup('install', '--wheel-mouse', 'true', '--wheel-mouse', 'false', success=False)
        self.assertFalse((self.folder / RECEIPT).exists())

    def test_language_screen_can_exit_without_opening_a_game(self):
        result = subprocess.run([SETUP, '--plain'], input='3\n', capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Choisissez votre langue / Choose your language', result.stdout)
        self.assertIn('Quitter / Exit', result.stdout)
        self.assertNotIn('MAIN MENU', result.stdout)

    def test_navigation_changes_language_and_preserves_pending_fixes(self):
        result = subprocess.run([SETUP, '--plain', '--language', 'en', '--game-directory', self.folder],
                                input='2\n1\n1\n2\n2\n2\n2\n2\n2\n2\n2\n3\n3\n1\n3\n4\n1\n\n2\n1\n1\n5\n', capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('MAIN MENU', result.stdout)
        self.assertIn('ADVANCED OPTIONS', result.stdout)
        self.assertIn('1. Back', result.stdout)
        self.assertIn('1. Retour', result.stdout)
        self.assertNotIn('Enter  Back', result.stdout)
        self.assertNotIn('Entrée  Retour', result.stdout)
        self.assertIn('Enhanced is not installed.', result.stdout)
        self.assertIn('Steering Wheel Improvements', result.stdout)
        self.assertIn('MENU PRINCIPAL', result.stdout)
        self.assertIn('PLUS D’OPTIONS', result.stdout)
        self.assertIn('Désactivé', result.stdout)
        self.assertIn('Installation terminée.', result.stdout)
        self.assertNotIn('Installer Enhanced dans ce dossier ?', result.stdout)
        self.assertNotIn('Destination :', result.stdout)
        self.assertNotIn('\x1b', result.stdout)
        self.assertTrue((self.folder / RECEIPT).exists())
        self.assertFalse(self.run_setup('status')['wheelMouseEnabled'])
        self.assertFalse(self.run_setup('status')['mapEnabled'])
        self.assertFalse(self.run_setup('status')['generalImprovementsEnabled'])
        self.assertFalse(self.run_setup('status')['steeringWheelImprovementsEnabled'])

    def test_linked_folder_refused(self):
        linked = self.folder / 'linked'
        # Windows junctions do not require the symbolic-link privilege.
        command = f"New-Item -ItemType Junction -Path '{str(linked).replace(chr(39), chr(39)*2)}' -Target '{str(self.folder).replace(chr(39), chr(39)*2)}' | Out-Null"
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        try: self.run_setup('install', game=linked, success=False)
        finally: os.rmdir(linked)


if __name__ == '__main__': unittest.main(verbosity=2)
