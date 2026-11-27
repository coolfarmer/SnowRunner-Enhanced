"""Extend our tiny test EXE with relocated guard snippets, never a game binary."""
from pathlib import Path
import struct
import json
import pefile
from test_compatibility import PROFILE, synthetic_image


def create_image(source, target, steering=False, input_compatible=True):
    matches, sections, segments, labels, move = synthetic_image(0x100000, 0x400000)
    if not input_compatible:
        rva, raw = segments[0]
        segments[0] = (rva, bytes([raw[0] ^ 1]) + raw[1:])
    vehicle = json.loads((Path(__file__).resolve().parents[1] / 'src/vehicle-profile.json').read_text())
    shift = vehicle['guards'][0]
    segments.append((move(shift['rva']), bytes.fromhex(shift['hex'])))
    from compatibility import compile_signatures
    for filename in ('winch-profile.json', 'truck-search-profile.json', 'game-time-profile.json'):
        profile = json.loads((Path(__file__).resolve().parents[1] / 'src' / filename).read_text())
        for sig in compile_signatures(profile):
            raw = bytearray.fromhex(sig['hex'])
            rva = move(sig['rva'])
            for ref in sig['refs']:
                raw[ref['offset']:ref['offset']+ref['size']] = (move(ref['target'])-rva-ref['next']).to_bytes(ref['size'], 'little', signed=True)
            segments.append((rva, raw))
    segments.append((move(PROFILE['functionsTargetRva']), bytes.fromhex('48895c2408574883ec7048634208488bda488bf9')))
    if steering:
        from compatibility import compile_signatures
        profile = json.loads((Path(__file__).resolve().parents[1] / 'src/steering-profile.json').read_text())
        for sig in compile_signatures(profile):
            raw = bytearray.fromhex(sig['hex'])
            rva = move(sig['rva'])
            for ref in sig['refs']:
                delta = move(ref['target']) - rva - ref['next']
                raw[ref['offset']:ref['offset']+ref['size']] = delta.to_bytes(ref['size'], 'little', signed=True)
            segments.append((rva, raw))
    data = bytearray(Path(source).read_bytes())
    pe = pefile.PE(data=bytes(data))
    align = lambda value, multiple: (value + multiple - 1) // multiple * multiple
    # Windows requires contiguous section virtual ranges in an image mapping.
    sections[0]['rva'] = pe.OPTIONAL_HEADER.SizeOfImage
    sections[0]['size'] = sections[1]['rva'] - sections[0]['rva']
    header = pe.sections[-1].get_file_offset() + 40
    assert header + 80 <= pe.OPTIONAL_HEADER.SizeOfHeaders
    for i, section in enumerate(sections):
        start, size = section['rva'], section['size']
        raw = bytearray(size)
        for rva, contents in [*segments, *labels.items()]:
            if start <= rva < start + size: raw[rva-start:rva-start+len(contents)] = contents
        if i == 1:
            for n, rva in enumerate(PROFILE['ids'].values()):
                struct.pack_into('<I', raw, move(rva) - start, (n + 1) * 11)
        offset = align(len(data), pe.OPTIONAL_HEADER.FileAlignment)
        data.extend(bytes(offset - len(data)))
        data.extend(raw)
        size_raw = align(size, pe.OPTIONAL_HEADER.FileAlignment)
        data.extend(bytes(size_raw - size))
        flags = 0x60000020 if i == 0 else 0xc0000040
        struct.pack_into('<8sIIIIIIHHI', data, header + 40*i,
                         b'.testcod' if i == 0 else b'.testdat', size, start, size_raw, offset, 0, 0, 0, 0, flags)
    struct.pack_into('<H', data, pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'), len(pe.sections) + 2)
    struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),
                     align(sections[-1]['rva'] + sections[-1]['size'], pe.OPTIONAL_HEADER.SectionAlignment))
    struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum'), 0)
    Path(target).write_bytes(data)
