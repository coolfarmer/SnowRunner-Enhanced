"""Exercise the published installer against temporary native game fixtures."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'dist/SnowRunnerEnhanced-0.1.0-preview.3'
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
        self.assertTrue(self.run_setup('install')['wheelMouseEnabled'])
        self.assertFalse(self.run_setup('configure', '--wheel-mouse', 'false')['wheelMouseEnabled'])
        self.assertTrue(self.run_setup('configure', '--wheel-mouse', 'true')['wheelMouseEnabled'])
        self.run_setup('uninstall')
        self.assertEqual(set(p.name for p in self.folder.iterdir()), {'SnowRunner.exe', *self.sentinels})
        self.assertEqual(hashlib.sha256((self.folder / 'SnowRunner.exe').read_bytes()).hexdigest(), before)

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
                path.write_bytes(b'existing settings')
                self.run_setup('install', success=False)
                self.assertEqual(path.read_bytes(), b'existing settings')
                self.assertFalse((self.folder / RECEIPT).exists())
                path.unlink()

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
        status = self.run_setup('status')
        self.assertFalse(status['loaderSupported'])
        self.assertIn('missing', status['loaderReason'])
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
                                input='2\n1\n\n2\n2\n2\n3\n3\n1\n3\n4\n1\n\n2\n1\n\n5\n', capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('MAIN MENU', result.stdout)
        self.assertIn('ADVANCED OPTIONS', result.stdout)
        self.assertIn('Enhanced is not installed.', result.stdout)
        self.assertIn('MENU PRINCIPAL', result.stdout)
        self.assertIn('PLUS D’OPTIONS', result.stdout)
        self.assertIn('Désactivé', result.stdout)
        self.assertIn('Installation terminée.', result.stdout)
        self.assertNotIn('Installer Enhanced dans ce dossier ?', result.stdout)
        self.assertNotIn('Destination :', result.stdout)
        self.assertNotIn('\x1b', result.stdout)
        self.assertTrue((self.folder / RECEIPT).exists())
        self.assertFalse(self.run_setup('status')['wheelMouseEnabled'])

    def test_linked_folder_refused(self):
        linked = self.folder / 'linked'
        # Windows junctions do not require the symbolic-link privilege.
        command = f"New-Item -ItemType Junction -Path '{str(linked).replace(chr(39), chr(39)*2)}' -Target '{str(self.folder).replace(chr(39), chr(39)*2)}' | Out-Null"
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        try: self.run_setup('install', game=linked, success=False)
        finally: os.rmdir(linked)


if __name__ == '__main__': unittest.main(verbosity=2)
