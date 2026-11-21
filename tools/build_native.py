"""Build the independent native package with embedded, unchanged V18 agents."""
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
EXPORTS = ['GetFileVersionInfoA', 'GetFileVersionInfoByHandle', 'GetFileVersionInfoExA',
           'GetFileVersionInfoExW', 'GetFileVersionInfoSizeA', 'GetFileVersionInfoSizeExA',
           'GetFileVersionInfoSizeExW', 'GetFileVersionInfoSizeW', 'GetFileVersionInfoW',
           'VerFindFileA', 'VerFindFileW', 'VerInstallFileA', 'VerInstallFileW',
           'VerLanguageNameA', 'VerLanguageNameW', 'VerQueryValueA', 'VerQueryValueW']


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
    (BUILD / 'proxy_names.h').write_text('static const char *proxy_names[17] = {' +
        ','.join(json.dumps(n) for n in EXPORTS) + '};\n')
    (BUILD / 'proxy.def').write_text('LIBRARY version\nEXPORTS\n' +
        '\n'.join(f' {n}=proxy_{i} @{i+1}' for i, n in enumerate(EXPORTS)) + '\n')
    asm = ['EXTERN ResolveVersion:PROC', '.code']
    regs = ['rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11']
    for index in range(17):
        asm += [f'proxy_{index} PROC FRAME', 'sub rsp, 216', '.allocstack 216', '.endprolog']
        asm += [f'mov [rsp+{128+i*8}], {reg}' for i, reg in enumerate(regs)]
        asm += ['pushfq', 'pop rax', 'mov [rsp+184], rax']
        asm += [f'movdqu [rsp+{32+i*16}], xmm{i}' for i in range(6)]
        asm += [f'mov ecx, {index}', 'call ResolveVersion', 'mov [rsp+192], rax']
        asm += [f'movdqu xmm{i}, [rsp+{32+i*16}]' for i in range(6)]
        asm += ['push qword ptr [rsp+184]', 'popfq']
        asm += [f'mov {reg}, [rsp+{128+i*8}]' for i, reg in enumerate(regs)]
        asm += ['lea rsp, [rsp+216]', 'jmp qword ptr [rsp-24]', f'proxy_{index} ENDP']
    asm += ['END']
    (BUILD / 'proxy.asm').write_text('\n'.join(asm))


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
    invoke([str(VC / 'bin/Hostx64/x64/ml64.exe'), '/nologo', '/c', '/Fo' + str(BUILD / 'proxy_thunks.obj'), str(BUILD / 'proxy.asm')])
    invoke([*common, '/LD', str(ROOT / 'src/native/proxy.c'), str(BUILD / 'proxy_thunks.obj'),
            '/link', '/DEF:' + str(BUILD / 'proxy.def'), '/OUT:version.dll', '/DYNAMICBASE', '/NXCOMPAT'])
    libs = ['user32.lib', 'shell32.lib', 'ole32.lib', 'advapi32.lib']
    invoke([*common, '/LD', str(ROOT / 'src/native/plugin.c'), '/link', *libs, '/OUT:SnowRunnerEnhanced.dll', '/DYNAMICBASE', '/NXCOMPAT'])
    invoke([*common, str(ROOT / 'tests/native/harness.c'), '/link', *libs, '/OUT:native-harness.exe', '/DYNAMICBASE', '/NXCOMPAT'])
    invoke([*common, str(ROOT / 'tests/native/game_host.c'), '/link', '/OUT:game-host.exe', '/DYNAMICBASE', '/NXCOMPAT'])
    (BUILD / 'build.json').write_text(json.dumps({
        'version': '0.1.0-preview.1', 'engine': 'GumJS 17.26.3 embedded',
        'artifacts': {n: hashlib.sha256((BUILD / n).read_bytes()).hexdigest()
                      for n in ('version.dll', 'SnowRunnerEnhanced.dll', 'native-harness.exe')},
        'v18Sources': {n: hashlib.sha256((ROOT / 'src' / n).read_bytes()).hexdigest()
                       for n in ('input_agent.js', 'vm_scope.js', 'input-profile.json')}
    }, indent=2))


if __name__ == '__main__':
    main()
