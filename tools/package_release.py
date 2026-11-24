"""Assemble only Enhanced-owned deliverables. No game or sibling project reads."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from asi_loaders import LOADERS, loader_path, verify

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.1.0-preview.21'
PACKAGE = ROOT / 'dist' / ('SnowRunnerEnhanced-' + VERSION)


def main():
    verify()
    files = {'Install.cmd': ROOT / 'Install.cmd',
             'Sources/Installer/SnowRunnerEnhanced.Setup.exe': ROOT / 'build/installer/SnowRunnerEnhanced.Setup.exe'}
    payload = {}
    for name in ('dinput8.dll', 'SnowRunnerEnhanced.asi'):
        source = loader_path(LOADERS[0]) if name == 'dinput8.dll' else ROOT / 'build/native' / name
        files['Sources/Payload/' + name] = source
        payload[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    for name in ('README.en.md', 'README.fr.md'):
        files['Sources/Docs/' + name] = ROOT / 'Docs' / name
    for source in (ROOT / 'Licenses').rglob('*'):
        if source.is_file():
            files['Sources/Licenses/' + source.relative_to(ROOT / 'Licenses').as_posix()] = source
    for relative, source in files.items():
        target = PACKAGE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    manifest = {'schemaVersion': 1, 'product': 'SnowRunnerEnhanced', 'version': VERSION,
                'payload': payload, 'compatibleLoaders': LOADERS, 'features': ['wheel_mouse', 'skip_startup_logos', 'map'],
                'coreComponents': ['settings_menu'],
                'validation': 'Keep North Up tested in game. Preview.21 keeps OFF selected and restores free map rotation.'}
    manifest_path = PACKAGE / 'Sources/package.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    # Explicit archive allowlist excludes Reports, test hosts, personal paths and
    # stale files even when a previously extracted package has been used.
    archive = Path(str(PACKAGE) + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for relative in sorted([*files, 'Sources/package.json']):
            z.write(PACKAGE / relative, PACKAGE.name + '/' + relative)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    Path(str(archive) + '.sha256').write_text(digest + '  ' + archive.name + '\n')
    print(json.dumps({'package': str(PACKAGE), 'archive': str(archive), 'sha256': digest,
                      'files': len(files) + 1, 'bytes': archive.stat().st_size}, indent=2))


if __name__ == '__main__':
    main()
