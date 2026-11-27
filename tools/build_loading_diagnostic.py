"""Build, validate and package an isolated diagnostic ASI. Never installs it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import build_native

ROOT = build_native.ROOT
BUILD = ROOT / 'build/loading-diagnostic'
NAME = 'SnowRunnerEnhanced-1.0.1-loading-diagnostic-no-hooks'
FEATURE_BITS = {'wheel_mouse':1, 'skip_startup_logos':2, 'map':4,
                'general_improvements':8, 'vehicle':16, 'steering_wheel_improvements':32}


def main():
    global BUILD, NAME
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--menu-only', action='store_true', help='Keep normal core discovery and menu hooks; force optional features off')
    modes.add_argument('--menu-grouped', action='store_true', help='Keep core menu, grouping its registrations into one native hook')
    modes.add_argument('--empty-hook', action='store_true', help='Keep core discovery and one empty native entry callback; no menu')
    modes.add_argument('--discovery-only', action='store_true', help='Same initialization as empty-hook, without attaching it')
    modes.add_argument('--menu-fast', action='store_true', help='Experimental direct native menu gate, optional features off')
    modes.add_argument('--fast-features', nargs='+', choices=FEATURE_BITS,
                       help='Experimental shared VM dispatcher; force exactly these groups on')
    parser.add_argument('--indexed-filter', action='store_true', help='Use the positive target index and exact name tries')
    parser.add_argument('--prefix-filter', action='store_true', help='Add the native class prefix prefilter to an indexed build')
    args = parser.parse_args()
    if args.indexed_filter and not args.fast_features:
        parser.error('--indexed-filter requires --fast-features')
    if args.prefix_filter and not args.indexed_filter:
        parser.error('--prefix-filter requires --indexed-filter')
    features = sum(FEATURE_BITS[name] for name in set(args.fast_features or []))
    args.menu_fast = args.menu_fast or bool(features)
    menu = args.menu_only or args.menu_grouped or args.empty_hook or args.discovery_only or args.menu_fast
    mode = 'menu-fast' if args.menu_fast else 'discovery-only' if args.discovery_only else 'empty-hook' if args.empty_hook else 'menu-grouped' if args.menu_grouped else 'menu-only' if menu else 'no-hooks'
    if features:
        mode = f'fast-features-{features:02x}'
        if args.indexed_filter:
            mode += '-indexed'
        if args.prefix_filter:
            mode += '-prefix'
    if menu:
        BUILD = ROOT / ('build/loading-diagnostic-' + mode)
        NAME = 'SnowRunnerEnhanced-1.0.1-loading-diagnostic-' + mode
    manifest = json.loads((ROOT / 'vendor/manifest.json').read_text())
    for name, expected in manifest['files'].items():
        if hashlib.sha256((ROOT / 'vendor' / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Dependency modified: ' + name)
    build_native.BUILD = BUILD
    build_native.generate(loading_diagnostic=True, diagnostic_menu=menu,
                          diagnostic_grouped=args.menu_grouped, diagnostic_empty=args.empty_hook or args.discovery_only,
                          diagnostic_discovery_only=args.discovery_only, diagnostic_fast=args.menu_fast,
                          diagnostic_features=features, diagnostic_indexed=args.indexed_filter, diagnostic_prefixes=args.prefix_filter)
    env = build_native.environment()
    vm_test_env = dict(os.environ, ENHANCED_TEST_VM_PREFIXES=str(int(args.prefix_filter)))
    cl = str(build_native.VC / 'bin/Hostx64/x64/cl.exe')
    common = [cl, '/nologo', '/O2', '/MT', '/W3', '/D_CRT_SECURE_NO_WARNINGS', '/DJSON_STATIC_BUILD',
              '/I' + str(BUILD), '/I' + str(ROOT / 'vendor/frida-gumjs')]
    libs = ['user32.lib', 'shell32.lib', 'ole32.lib', 'advapi32.lib']
    subprocess.run([*common, '/LD', str(ROOT / 'src/native/plugin.c'), '/link', *libs,
                    '/OUT:SnowRunnerEnhanced.asi', '/DYNAMICBASE', '/NXCOMPAT'],
                   cwd=BUILD, env=env, check=True)
    subprocess.run([*common, str(ROOT / 'tests/native/game_host.c'), '/link', '/OUT:game-host.exe'],
                   cwd=BUILD, env=env, check=True)
    subprocess.run([*common, '/LD', str(ROOT / 'tests/native/companion.c'), '/link', '/OUT:companion.asi'],
                   cwd=BUILD, env=env, check=True)
    if features & 8:
        subprocess.run([*common, str(ROOT / 'tests/native/startup_host.c'),
                        '/link', *libs, '/OUT:startup-host.exe'], cwd=BUILD, env=env, check=True)
    if features & 32:
        subprocess.run([str(build_native.VC / 'bin/Hostx64/x64/ml64.exe'), '/nologo', '/c',
                        '/Fosteering_fixture.obj', str(ROOT / 'tests/native/steering_fixture.asm')],
                       cwd=BUILD, env=env, check=True)
        subprocess.run([*common, str(ROOT / 'tests/native/steering_host.c'), 'steering_fixture.obj',
                        '/link', *libs, '/OUT:steering-host.exe', '/DYNAMICBASE', '/NXCOMPAT'],
                       cwd=BUILD, env=env, check=True)
        (ROOT / 'build/tests').mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests',
                        '-p', 'test_steering.py', '-v'], cwd=ROOT,
                       env=dict(os.environ, ENHANCED_STEERING_TEST_HOST=str(BUILD / 'steering-host.exe')), check=True)
    if args.menu_fast:
        subprocess.run([*common, '/DENHANCED_FAST_MENU_TEST', str(ROOT / 'tests/native/harness.c'),
                        '/link', *libs, '/OUT:native-harness.exe'], cwd=BUILD, env=env, check=True)
        subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests',
                        '-p', 'test_fast_menu_hooks.py', '-v'], cwd=ROOT,
                       env=dict(vm_test_env, ENHANCED_FAST_TEST_BUILD=str(BUILD), ENHANCED_VM_INDEXED=str(int(args.indexed_filter))), check=True)
        if features:
            for suite in ('test_fast_vm_hooks.py','test_fast_vm_bootstrap.py'):
                subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests',
                                '-p', suite, '-v'], cwd=ROOT,
                               env=dict(vm_test_env, ENHANCED_FAST_TEST_BUILD=str(BUILD), ENHANCED_VM_INDEXED=str(int(args.indexed_filter))), check=True)
        if args.indexed_filter:
            subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests',
                            '-p', 'test_fast_vm_indexed.py', '-v'], cwd=ROOT,
                            env=dict(vm_test_env, ENHANCED_FAST_TEST_BUILD=str(BUILD)), check=True)
    subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests',
                    '-p', 'test_loading_diagnostic.py', '-v'], cwd=ROOT,
                   env=dict(os.environ, ENHANCED_DIAGNOSTIC_TEST_MODE=mode), check=True)
    if args.menu_grouped:
        subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests',
                        '-p', 'test_grouped_menu_hooks.py', '-v'], cwd=ROOT, check=True)
    if args.empty_hook or args.discovery_only:
        subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests',
                        '-p', 'test_empty_menu_probe.py', '-v'], cwd=ROOT, check=True)

    package = ROOT / 'dist' / NAME
    package.mkdir(parents=True, exist_ok=True)
    files = {'SnowRunnerEnhanced.asi': BUILD / 'SnowRunnerEnhanced.asi',
             'DIAGNOSTIC.txt': ROOT / ('Docs/LOADING_DIAGNOSTIC_FAST.txt' if args.menu_fast else 'Docs/LOADING_DIAGNOSTIC_DISCOVERY.txt' if args.discovery_only else 'Docs/LOADING_DIAGNOSTIC_EMPTY.txt' if args.empty_hook else 'Docs/LOADING_DIAGNOSTIC_GROUPED.txt' if args.menu_grouped else 'Docs/LOADING_DIAGNOSTIC_MENU.txt' if menu else 'Docs/LOADING_DIAGNOSTIC.txt')}
    if features:
        files['DIAGNOSTIC.txt'] = ROOT / ('Docs/LOADING_DIAGNOSTIC_FAST_WHEEL_MOUSE.txt' if features == 1 else
                                         'Docs/LOADING_DIAGNOSTIC_FAST_GENERAL.txt' if features == 8 else
                                         'Docs/LOADING_DIAGNOSTIC_FAST_VEHICLE.txt' if features == 16 else
                                         'Docs/LOADING_DIAGNOSTIC_FAST_COMBINED.txt' if features == 29 else
                                         'Docs/LOADING_DIAGNOSTIC_FAST_FEATURES.txt')
    if args.menu_fast:
        files['native-benchmark.json'] = BUILD / 'benchmark.json'
    if args.indexed_filter:
        files['DIAGNOSTIC.txt'] = ROOT / ('Docs/LOADING_DIAGNOSTIC_FAST_INDEXED_ALL.txt' if features == 63 else
                                         'Docs/LOADING_DIAGNOSTIC_FAST_INDEXED_LOGOS.txt' if features == 31 else
                                         'Docs/LOADING_DIAGNOSTIC_FAST_INDEXED.txt')
        files['indexed-benchmark.json'] = BUILD / 'indexed-benchmark.json'
    if args.prefix_filter:
        files['DIAGNOSTIC.txt'] = ROOT / 'Docs/LOADING_DIAGNOSTIC_FAST_PREFIX.txt'
    for source in (ROOT / 'Licenses').rglob('*'):
        if source.is_file():
            files['Licenses/' + source.relative_to(ROOT / 'Licenses').as_posix()] = source
    for relative, source in files.items():
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    build = {
        'version': '1.0.1', 'buildMode': 'loading-diagnostic-' + mode,
        'forcedFeatures': {name:bool(features & bit) for name,bit in FEATURE_BITS.items()},
        'indexedFilter': args.indexed_filter,
        'nativePrefixFilter': args.prefix_filter,
        'sourceCommit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'sourceHashes': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                         ('src/native/plugin.c', 'src/native/loading_diagnostic.js', 'src/native/bootstrap.js',
                          'src/native/grouped_menu_hooks.js', 'src/settings_menu.js',
                          'src/native/empty_menu_probe.js',
                          'src/native/fast_menu.h', 'src/native/fast_menu_hooks.js',
                          'src/native/fast_vm_hooks.js', 'src/input_agent.js', 'src/functions_repeat.js',
                          'tools/build_native.py', 'tools/build_loading_diagnostic.py',
                          'tests/test_loading_diagnostic.py', 'tests/test_grouped_menu_hooks.py',
                          'tests/test_empty_menu_probe.py', 'tests/test_fast_menu_hooks.py',
                          'tests/test_fast_vm_hooks.py', 'tests/test_fast_vm_bootstrap.py',
                          'tests/test_fast_vm_indexed.py', 'tests/test_fast_menu_hooks.py', 'tests/test_steering.py',
                          'src/native/steering.h', 'src/steering-profile.json',
                          'tests/native/steering_host.c', 'tests/native/steering_fixture.asm')},
        'bundleSha256': hashlib.sha256((BUILD / 'bundle.h').read_bytes()).hexdigest(),
        'files': {name: hashlib.sha256(source.read_bytes()).hexdigest() for name, source in files.items()},
        'validation': ('Native steering resolver/callback tests passed; ' if features & 32 else '') +
                      ('Native gate, shared dispatcher, indexed filter and disposable ASI-loader tests passed; ' if args.indexed_filter else
                       '16 gate/bootstrap tests and disposable ASI-loader tests passed; ' if features else
                       '9 native gate tests and disposable ASI-loader tests passed; ' if args.menu_fast else
                       'Disposable ASI-loader tests passed; ') + 'real-game loading time has not been measured.'
    }
    (package / 'diagnostic-build.json').write_text(json.dumps(build, indent=2) + '\n', encoding='utf-8')
    archive = ROOT / 'dist' / (NAME + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for relative in sorted([*files, 'diagnostic-build.json']):
            output.write(package / relative, NAME + '/' + relative)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    Path(str(archive) + '.sha256').write_text(digest + '  ' + archive.name + '\n')
    print(json.dumps({'archive': str(archive), 'sha256': digest, 'installed': False}, indent=2))


if __name__ == '__main__':
    main()
