"""Fetch Enhanced-owned native build dependencies; never reads another project."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tarfile
from urllib.parse import unquote
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MSVC = [
 ('aad09a18-fd5d-45d3-91e5-9fc87e932d9f', 'b42af543b1261f0fce5b88fb9fe876c1e3d7579cf768f37cbd676aa571942a07', 'Microsoft.VC.14.52.CRT.x64.Store.base.vsix'),
 ('aad09a18-fd5d-45d3-91e5-9fc87e932d9f', '97fac068e1b7d84d2596394523ffd13f4d93878f7313361d39bbf7579a803fe4', 'Microsoft.VC.14.52.CRT.Headers.base.vsix'),
 ('aad09a18-fd5d-45d3-91e5-9fc87e932d9f', '6e94791c63d5bd58f1495e2e0ab6c37756f1b06fc9400ef72c729ea0661413d3', 'Microsoft.VC.14.52.CRT.x64.Desktop.base.vsix'),
 ('aad09a18-fd5d-45d3-91e5-9fc87e932d9f', 'e8805f002246115e6c5a8444ba87a9f30e86c35943129f798f6deb99825685f8', 'Microsoft.VC.14.52.Tools.HostX64.TargetX64.base.vsix'),
 ('aad09a18-fd5d-45d3-91e5-9fc87e932d9f', 'fbeb2488e009141ff915ad300569305efb24a79b7258cdfc50d73c05dc9a934e', 'Microsoft.VC.14.52.Tools.HostX64.TargetX64.Res.base.enu.vsix'),
]


def download(url, digest, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        data = urlopen(url, timeout=120).read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Download hash mismatch: ' + path.name)
        path.write_bytes(data)
    return path


def main():
    entries = []
    def fetch(row):
        group, digest, name = row
        url = f'https://download.visualstudio.microsoft.com/download/pr/{group}/{digest}/{name}'
        path = download(url, digest, ROOT / '.toolchain/downloads' / name)
        return path, {'name': name, 'url': url, 'sha256': digest}
    with ThreadPoolExecutor(max_workers=4) as pool:
        fetched = list(pool.map(fetch, MSVC))
    target = (ROOT / '.toolchain/msvc').resolve()
    for archive, entry in fetched:
        with zipfile.ZipFile(archive) as package:
            for name in package.namelist():
                if not name.startswith('Contents/') or name.endswith('/'):
                    continue
                dest = (target / unquote(name[len('Contents/'):])).resolve()
                if not dest.is_relative_to(target):
                    raise ValueError('Unsafe archive path')
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(package.read(name))
        entries.append(entry)
    url = 'https://github.com/frida/frida/releases/download/17.26.3/frida-gumjs-devkit-17.26.3-windows-x86_64.tar.xz'
    digest = '71cc9091e2b786493bcc1915f81c3ca14091e6acdfccd1324898bdf40b7ab15d'
    archive = download(url, digest, ROOT / 'vendor/downloads/frida-gumjs-17.26.3.tar.xz')
    with tarfile.open(archive) as package:
        package.extractall(ROOT / 'vendor/frida-gumjs', filter='data')
    entries.append({'name': archive.name, 'url': url, 'sha256': digest})
    files = {str(p.relative_to(ROOT / 'vendor')): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (ROOT / 'vendor/frida-gumjs').iterdir() if p.is_file()}
    (ROOT / 'vendor/manifest.json').write_text(json.dumps({'downloads': entries, 'files': files}, indent=2))
    print('Verified Enhanced-owned MSVC tools and GumJS 17.26.3')


if __name__ == '__main__':
    main()
