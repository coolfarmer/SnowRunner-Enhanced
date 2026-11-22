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


def generate():
    BUILD.mkdir(parents=True, exist_ok=True)
    (ROOT / 'build/tmp').mkdir(parents=True, exist_ok=True)
    startup = json.loads((ROOT / 'src/startup-profile.json').read_text())
    rows = []
    for e in startup['edits']:
        a, b = bytes.fromhex(e['original']), bytes.fromhex(e['replacement'])
        assert len(a) == len(b) <= 64
        rows.append('{%dULL,%d,{%s},{%s}}' % (e['offset'], len(a), ','.join(map(str,a)), ','.join(map(str,b))))
    (BUILD / 'startup_profile.h').write_text(
        'typedef struct { unsigned long long offset; unsigned size; unsigned char before[64], after[64]; } StartupEdit;\n'
        + '#define STARTUP_EDIT_COUNT %d\n#define STARTUP_ARCHIVE_SIZE %dULL\n' % (len(rows), startup['size'])
        + 'static const unsigned char startup_sha256[32]={' + ','.join(map(str,bytes.fromhex(startup['sha256']))) + '};\n'
        + 'static const StartupEdit startup_edits[STARTUP_EDIT_COUNT]={' + ','.join(rows) + '};\n')
    profile = json.loads((ROOT / 'src/input-profile.json').read_text())
    parts = ["const CONFIG={test:false,gamePath:Process.mainModule.path,profile:" + json.dumps(profile) + '};',
             'const NATIVE_SIGNATURES=' + json.dumps(compile_signatures(profile)) + ';',
             (ROOT / 'src/compatibility_probe.js').read_text(), 'const nativeProbe=rpc.exports;',
             (ROOT / 'src/vm_scope.js').read_text(), (ROOT / 'src/input_agent.js').read_text(),
             'const nativeAgent=rpc.exports;', (ROOT / 'src/native/resolve.js').read_text(),
             (ROOT / 'src/native/bootstrap.js').read_text()]
    source = '\n'.join(parts).encode('utf-8')
    # An unsigned byte array avoids MSVC's individual string literal limit.
    (BUILD / 'bundle.h').write_text('static const char enhanced_bundle[] = {\n' +
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
    invoke([*common, str(ROOT / 'tests/native/harness.c'), '/link', *libs, '/OUT:native-harness.exe', '/DYNAMICBASE', '/NXCOMPAT'])
    invoke([*common, str(ROOT / 'tests/native/startup_host.c'), '/link', *libs, '/OUT:startup-host.exe', '/DYNAMICBASE', '/NXCOMPAT'])
    invoke([*common, str(ROOT / 'tests/native/game_host.c'), '/link', '/OUT:game-host.exe', '/DYNAMICBASE', '/NXCOMPAT'])
    invoke([*common, '/LD', str(ROOT / 'tests/native/companion.c'), '/link', '/OUT:companion.asi'])
    (BUILD / 'build.json').write_text(json.dumps({
        'version': '0.1.0-preview.11', 'engine': 'GumJS 17.26.3 embedded',
        'artifacts': {n: hashlib.sha256((BUILD / n).read_bytes()).hexdigest()
                      for n in ('SnowRunnerEnhanced.asi', 'native-harness.exe')},
        'v18Sources': {n: hashlib.sha256((ROOT / 'src' / n).read_bytes()).hexdigest()
                       for n in ('input_agent.js', 'vm_scope.js', 'input-profile.json')}
    }, indent=2))


if __name__ == '__main__':
    main()
