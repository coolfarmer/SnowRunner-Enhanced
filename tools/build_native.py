"""Build the independent native package with embedded V18 agents and targeted pointer fixes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from compatibility import compile_signatures
from steering_profile import generate as generate_steering_profile

BUILD = ROOT / 'build/native'
VC = ROOT / '.toolchain/msvc/VC/Tools/MSVC/14.52.37025'
SDK = Path(os.environ.get('WINDOWS_SDK_ROOT', r'C:\Program Files (x86)\Windows Kits\10'))
SDK_VERSION = '10.0.26100.0'


def environment():
    env = dict(os.environ)
    env['PATH'] = str(VC / 'bin/Hostx64/x64') + os.pathsep + env.get('PATH', '')
    env['INCLUDE'] = os.pathsep.join(map(str, [VC / 'include', *[
        SDK / 'Include' / SDK_VERSION / d for d in ('ucrt', 'shared', 'um')]]))
    env['LIB'] = os.pathsep.join(map(str, [VC / 'lib/x64', *[
        SDK / 'Lib' / SDK_VERSION / d / 'x64' for d in ('ucrt', 'um')], ROOT / 'vendor/frida-gumjs']))
    env['TEMP'] = env['TMP'] = str(ROOT / 'build/tmp')
    return env


def generate(*, loading_diagnostic=False, diagnostic_menu=False, diagnostic_grouped=False, diagnostic_empty=False, diagnostic_discovery_only=False, diagnostic_fast=False, diagnostic_features=0, diagnostic_indexed=False, diagnostic_prefixes=False):
    if diagnostic_prefixes and not diagnostic_indexed:
        raise ValueError('Native prefix filtering requires the indexed filter')
    if diagnostic_indexed and not diagnostic_features:
        raise ValueError('Indexed filtering requires the experimental shared dispatcher')
    if not isinstance(diagnostic_features, int) or diagnostic_features < 0 or diagnostic_features > 63 or (diagnostic_features and not diagnostic_fast):
        raise ValueError('Optional diagnostic features require the isolated fast dispatcher')
    if diagnostic_fast and (not diagnostic_menu or diagnostic_grouped or diagnostic_empty):
        raise ValueError('Fast native menu requires an isolated menu-only build')
    if diagnostic_discovery_only and not diagnostic_empty:
        raise ValueError('Discovery-only control requires the empty-probe bootstrap')
    if diagnostic_empty and (not diagnostic_menu or diagnostic_grouped):
        raise ValueError('Empty hook requires core discovery and cannot use the grouped dispatcher')
    if diagnostic_grouped and not diagnostic_menu:
        raise ValueError('Grouped hooks require the menu-only diagnostic')
    if diagnostic_menu and not loading_diagnostic:
        raise ValueError('The menu-only mode requires a diagnostic build')
    fast = not loading_diagnostic or diagnostic_fast
    shared = not loading_diagnostic or bool(diagnostic_features)
    indexed = not loading_diagnostic or diagnostic_indexed
    prefixes = not loading_diagnostic or diagnostic_prefixes
    BUILD.mkdir(parents=True, exist_ok=True)
    (ROOT / 'build/tmp').mkdir(parents=True, exist_ok=True)
    generate_steering_profile(BUILD / 'steering_profile.h')
    startup = json.loads((ROOT / 'src/startup-profile.json').read_text())
    movies = list(startup['movies'])
    def initializer(raw):
        return '{' + ','.join(map(str, raw)) + '}'
    movie_rows = []
    for name, movie in startup['movies'].items():
        movie_rows.append('{"%s",%d,%s}' % (name, movie['size'], initializer(bytes.fromhex(movie['sha256']))))
    rows = []
    for feature, edits in [(2, startup['edits']), (8, startup['functionsMenuEdits'])]:
        for e in edits:
            a, b = bytes.fromhex(e['original']), bytes.fromhex(e['replacement'])
            assert 0 < len(a) == len(b) < 63
            rows.append('{%dULL,%d,%d,%d,{%s},{%s}}' % (e['offset'], len(a), feature, movies.index(e['movie']), ','.join(map(str,a)), ','.join(map(str,b))))
    (BUILD / 'startup_profile.h').write_text(
        'typedef struct { unsigned long long offset; unsigned size, feature, movie; unsigned char before[64], after[64]; } StartupEdit;\n'
        + '#define STARTUP_EDIT_COUNT %d\n#define MOVIE_COUNT %d\n' % (len(rows), len(movies))
        + 'static const struct {const char *name; unsigned size; unsigned char hash[32];} movies[MOVIE_COUNT]={' + ','.join(movie_rows) + '};\n'
        + 'static StartupEdit startup_edits[STARTUP_EDIT_COUNT]={'  + ','.join(rows) + '};\n')
    profile = json.loads((ROOT / 'src/input-profile.json').read_text())
    vehicle = json.loads((ROOT / 'src/vehicle-profile.json').read_text())
    winch = json.loads((ROOT / 'src/winch-profile.json').read_text())
    search = json.loads((ROOT / 'src/truck-search-profile.json').read_text())
    game_time = json.loads((ROOT / 'src/game-time-profile.json').read_text())
    parts = ["const CONFIG={test:false,gamePath:Process.mainModule.path,profile:" + json.dumps(profile) + '};',
             'const VEHICLE_PROFILE=' + json.dumps(vehicle) + ';',
             'const GAME_TIME_PROFILE=' + json.dumps(game_time) + ';',
             'const GAME_TIME_SIGNATURES=' + json.dumps(compile_signatures(game_time)) + ';',
             'const VEHICLE_SIGNATURES=' + json.dumps(compile_signatures(vehicle)) + ';',
             'const TRUCK_SEARCH_PROFILE=' + json.dumps(search) + ';',
             'const TRUCK_SEARCH_SIGNATURES=' + json.dumps(compile_signatures(search)) + ';',
             'const WINCH_PROFILE=' + json.dumps(winch) + ';',
             'const WINCH_SIGNATURES=' + json.dumps(compile_signatures(winch)) + ';',
             'const NATIVE_SIGNATURES=' + json.dumps(compile_signatures(profile)) + ';',
             (ROOT / 'src/compatibility_probe.js').read_text(), 'const nativeProbe=rpc.exports;',
             (ROOT / 'src/vm_scope.js').read_text(), (ROOT / 'src/input_agent.js').read_text(),
             'const nativeAgent=rpc.exports;',
             'const SETTINGS_PROFILE=' + (ROOT / 'src/settings-profile.json').read_text(encoding='utf-8') + ';',
             (ROOT / 'src/vehicle.js').read_text(encoding='utf-8'),
             (ROOT / 'src/game_time.js').read_text(encoding='utf-8'),
             (ROOT / 'src/vehicle_winch.js').read_text(encoding='utf-8'),
             (ROOT / 'src/truck_search_vm.js').read_text(encoding='utf-8'),
             (ROOT / 'src/truck_search.js').read_text(encoding='utf-8'),
             (ROOT / 'src/functions_repeat.js').read_text(encoding='utf-8'),
             (ROOT / 'src/map_zoom.js').read_text(encoding='utf-8'),
             (ROOT / 'src/map_panning.js').read_text(encoding='utf-8'),
             (ROOT / 'src/feature_status.js').read_text(encoding='utf-8'),
             (ROOT / 'src/settings_menu.js').read_text(encoding='utf-8'),
             (ROOT / 'src/native/resolve.js').read_text(),
             (ROOT / 'src/native/grouped_menu_hooks.js').read_text() if diagnostic_grouped else '',
             (ROOT / 'src/native/fast_menu_hooks.js').read_text() if fast else '',
             (ROOT / 'src/native/fast_vm_hooks.js').read_text() if shared else '',
             'const ENHANCED_VM_INDEXED=true;' if indexed else '',
             'const ENHANCED_VM_PREFIXES=true;' if prefixes else '',
             'const ENHANCED_DISCOVERY_ONLY=true;' if diagnostic_discovery_only else '',
             (ROOT / 'src/native/empty_menu_probe.js').read_text() if diagnostic_empty else '',
             (ROOT / ('src/native/loading_diagnostic.js' if loading_diagnostic and not diagnostic_menu else 'src/native/bootstrap.js')).read_text()]
    source = '\n'.join(parts).encode('utf-8')
    # An unsigned byte array avoids MSVC's individual string literal limit.
    diagnostic_defines = ''
    if loading_diagnostic:
        mode = 'menu-fast' if diagnostic_fast else 'discovery-only' if diagnostic_discovery_only else 'empty-hook' if diagnostic_empty else 'menu-grouped' if diagnostic_grouped else 'menu-only' if diagnostic_menu else 'no-hooks'
        if diagnostic_features:
            mode = f'fast-features-{diagnostic_features:02x}'
            if diagnostic_indexed:
                mode += '-indexed'
            if diagnostic_prefixes:
                mode += '-prefix'
        report = 'loading-diagnostic-' + mode if diagnostic_menu else 'loading-diagnostic'
        diagnostic_defines = ('#define ENHANCED_LOADING_DIAGNOSTIC 1\n'
            f'#define ENHANCED_DIAGNOSTIC_FEATURES {diagnostic_features}\n'
            f'#define ENHANCED_LOADING_DIAGNOSTIC_MODE "loading-diagnostic-{mode}"\n'
            f'#define ENHANCED_LOADING_DIAGNOSTIC_REPORT L"SnowRunnerEnhanced.{report}.status"\n')
    if fast:
        diagnostic_defines += '#define ENHANCED_FAST_MENU 1\n'
    (BUILD / 'bundle.h').write_text(diagnostic_defines +
        'static const char enhanced_bundle[] = {\n' +
        ',\n'.join(','.join(str(b) for b in source[i:i+32]) for i in range(0, len(source), 32)) + ',0};\n')


def main():
    manifest = json.loads((ROOT / 'vendor/manifest.json').read_text())
    for name, expected in manifest['files'].items():
        if hashlib.sha256((ROOT / 'vendor' / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Dependency modified: ' + name)
    generate()
    env = environment()
    cl = str(VC / 'bin/Hostx64/x64/cl.exe')
    def invoke(args):
        subprocess.run(args, env=env, cwd=BUILD, check=True)
    common = [cl, '/nologo', '/O2', '/MT', '/W3', '/D_CRT_SECURE_NO_WARNINGS', '/DJSON_STATIC_BUILD',
              '/I' + str(BUILD), '/I' + str(ROOT / 'vendor/frida-gumjs')]
    libs = ['user32.lib', 'shell32.lib', 'ole32.lib', 'advapi32.lib']
    invoke([*common, '/LD', str(ROOT / 'src/native/plugin.c'), '/link', *libs, '/OUT:SnowRunnerEnhanced.asi', '/DYNAMICBASE', '/NXCOMPAT'])
    invoke([*common, '/DENHANCED_FAST_MENU_TEST', str(ROOT / 'tests/native/harness.c'), '/link', *libs, '/OUT:native-harness.exe', '/DYNAMICBASE', '/NXCOMPAT'])
    invoke([str(VC / 'bin/Hostx64/x64/ml64.exe'), '/nologo', '/c', '/Fosteering_fixture.obj', str(ROOT / 'tests/native/steering_fixture.asm')])
    invoke([*common, str(ROOT / 'tests/native/steering_host.c'), 'steering_fixture.obj', '/link', *libs, '/OUT:steering-host.exe', '/DYNAMICBASE', '/NXCOMPAT'])
    invoke([*common, str(ROOT / 'tests/native/settings_host.c'), '/link', *libs, '/OUT:settings-host.exe', '/DYNAMICBASE', '/NXCOMPAT'])
    invoke([*common, str(ROOT / 'tests/native/startup_host.c'), '/link', *libs, '/OUT:startup-host.exe', '/DYNAMICBASE', '/NXCOMPAT'])
    invoke([*common, str(ROOT / 'tests/native/game_host.c'), '/link', '/OUT:game-host.exe', '/DYNAMICBASE', '/NXCOMPAT'])
    invoke([*common, '/LD', str(ROOT / 'tests/native/companion.c'), '/link', '/OUT:companion.asi'])
    (BUILD / 'build.json').write_text(json.dumps({
        'version': '1.1.0', 'engine': 'GumJS 17.26.3 embedded',
        'vmDispatch': 'indexed-prefix', 'featureSelection': 'configuration',
        'artifacts': {n: hashlib.sha256((BUILD / n).read_bytes()).hexdigest()
                      for n in ('SnowRunnerEnhanced.asi', 'native-harness.exe')},
        'v18Sources': {n: hashlib.sha256((ROOT / 'src' / n).read_bytes()).hexdigest()
                       for n in ('input_agent.js', 'vm_scope.js', 'input-profile.json', 'map_zoom.js', 'map_panning.js', 'settings_menu.js', 'settings-profile.json', 'vehicle_winch.js', 'winch-profile.json', 'truck-search-profile.json', 'truck_search_vm.js', 'truck_search.js', 'game_time.js', 'game-time-profile.json')}
    }, indent=2))


if __name__ == '__main__':
    main()
