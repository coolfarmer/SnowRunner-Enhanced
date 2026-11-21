"""Extend our tiny test EXE with relocated guard snippets, never a game binary."""
from pathlib import Path
import struct
import pefile
from test_compatibility import PROFILE, synthetic_image


def create_image(source, target):
    matches, sections, segments, labels, move = synthetic_image(0x100000, 0x400000)
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
