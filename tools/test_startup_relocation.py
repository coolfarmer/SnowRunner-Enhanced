"""Exercise the archive resolver with relocated game movies in temporary ZIPs."""
import argparse
from pathlib import Path
import struct
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MEMBER = '[gfx]/gfxbundle.gfxbundle'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    with zipfile.ZipFile(args.archive) as archive:
        bundle = archive.read(MEMBER)
    count = struct.unpack_from('<I', bundle, 11)[0]
    pos = 20
    names = []
    for _ in range(count):
        length, = struct.unpack_from('<I', bundle, pos)
        names.append(bundle[pos+4:pos+4+length])
        pos += 4+length
    assert bundle[pos] == 1
    sizes = struct.unpack_from(f'<{count}I', bundle, pos+1)
    pos += 1+4*count
    movies = []
    for name, size in zip(names, sizes):
        if name in (b'hud_lib.gfx', b'loading_screen.gfx', b'loading_screen_jp.gfx'):
            movies.append((name, bundle[pos:pos+size]))
        pos += size
    assert len(movies) == 3
    movies.reverse()
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as temp:
        game = Path(temp)
        folder = game/'Sources/Bin'
        folder.mkdir(parents=True)
        target = game/'preload/paks/client/gfx.pak'
        target.parent.mkdir(parents=True)
        host = [ROOT/'build/native/startup-host.exe', str(folder)+'\\', '10']

        def repack(entries, compression=zipfile.ZIP_STORED):
            head = bundle[:11]+struct.pack('<I', len(entries))+bundle[15:20]
            directory = b''.join(struct.pack('<I',len(n))+n for n,_ in entries)
            sizes = b''.join(struct.pack('<I',len(b)) for _,b in entries)
            with zipfile.ZipFile(target,'w',compression) as archive:
                archive.writestr('unrelated', b'padding'*137)
                archive.writestr(MEMBER, head+directory+b'\x01'+sizes+b''.join(b for _,b in entries))

        repack(movies)
        subprocess.run(host, check=True)
        for changed, expected in [(b'hud_lib.gfx','armed incompatible'),
                                  (b'loading_screen_jp.gfx','incompatible armed')]:
            repack([(n, data[:-1]+bytes([data[-1]^1]) if n==changed else data) for n,data in movies])
            assert subprocess.check_output([*host,'status'],text=True).strip() == expected
        repeated = next(m for m in movies if m[0]==b'loading_screen.gfx')
        repack([*movies,repeated])
        assert subprocess.check_output([*host,'status'],text=True).strip() == 'incompatible armed'
        repack(movies, zipfile.ZIP_DEFLATED)
        assert subprocess.check_output([*host,'status'],text=True).strip() == 'incompatible incompatible'


if __name__ == '__main__':
    main()
