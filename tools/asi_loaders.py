"""Pinned upstream x64 loaders; Enhanced keeps its own downloads and tests."""
import hashlib
import io
from pathlib import Path
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOADERS = [
    dict(version='10.0.2', architecture='x64',
         sha256='57ec56390c92a18b82f58855e63c93985e254d1e29d5f75cbc28dc08f96c8a12',
         url='https://github.com/ThirteenAG/Ultimate-ASI-Loader/releases/download/v10.0.2/Ultimate-ASI-Loader-NoPDB_x64.zip',
         archiveSha256='fe964adf4de7f467ff39c440a4059de02e37d0574a62944eef2f55a35edafa2f'),
    dict(version='8.5.0', architecture='x64',
         sha256='66fd34b4f7944c1ef3e67a1b4c5d4973109405f824971cbe19372bb9c9ac6535',
         url='https://github.com/drafty46/SMT/releases/download/v1.5/SMT.v1.5.zip',
         archiveSha256='e89b18bb2dc9debb9e79d1719281e8a72457024f05c6672d98c03463dcf9a8e8'),
]

def loader_path(entry):
    return ROOT / 'vendor/asi-loader' / ('dinput8-' + entry['version'] + '.dll')

def verify():
    for entry in LOADERS:
        if hashlib.sha256(loader_path(entry).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Unverified ASI loader: ' + entry['version'])

def fetch():
    for entry in LOADERS:
        target = loader_path(entry)
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == entry['sha256']:
            continue
        data = urlopen(entry['url'], timeout=120).read()
        if hashlib.sha256(data).hexdigest() != entry['archiveSha256']:
            raise ValueError('ASI loader archive hash mismatch')
        # SMT is a test source for its loader only; never extract or ship SMT.asi.
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            binary = archive.read('dinput8.dll')
        if hashlib.sha256(binary).hexdigest() != entry['sha256']:
            raise ValueError('ASI loader binary hash mismatch')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(binary)
    verify()

if __name__ == '__main__':
    fetch()
