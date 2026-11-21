'use strict';

// Read-only discovery. No hooks, game calls, device I/O or memory writes.
rpc.exports = {
    describe() {
        const game = Process.mainModule, base = game.base;
        if (Process.arch !== 'x64' || Process.platform !== 'windows')
            throw new Error('Windows x64 required');
        if (base.readU16() !== 0x5a4d) throw new Error('Invalid DOS header');
        const offset = base.add(0x3c).readU32();
        if (offset > 0x100000) throw new Error('Invalid PE offset');
        const pe = base.add(offset);
        if (pe.readU32() !== 0x4550 || pe.add(4).readU16() !== 0x8664 ||
                pe.add(24).readU16() !== 0x20b) throw new Error('Invalid PE x64 header');
        const count = pe.add(6).readU16(), optionalSize = pe.add(20).readU16();
        if (count < 1 || count > 96) throw new Error('Invalid section count');
        const sections = [];
        for (let i = 0; i < count; i++) {
            const entry = pe.add(24 + optionalSize + i * 40);
            const rva = entry.add(12).readU32(), size = entry.add(8).readU32();
            const flags = entry.add(36).readU32();
            if (rva + size > game.size) throw new Error('Invalid section bounds');
            sections.push({rva, size, executable: (flags & 0x20000000) !== 0,
                readable: (flags & 0x40000000) !== 0});
        }
        return {name: game.name, path: game.path, size: game.size, sections};
    },
    scan(signatures, sections) {
        const game = Process.mainModule, result = {};
        for (const sig of signatures) {
            const matches = [];
            for (const section of sections) {
                if (!section.executable || !section.readable || !section.size) continue;
                if (section.rva < 0 || section.rva + section.size > game.size)
                    throw new Error('Scan outside module');
                for (const match of Memory.scanSync(game.base.add(section.rva), section.size, sig.pattern)) {
                    if (sig.identity) {
                        const ref = sig.refs[0];
                        const target = match.address.add(ref.next).add(match.address.add(ref.offset).readS32());
                        if (target.compare(game.base) < 0 ||
                                target.add(sig.identity.length + 1).compare(game.base.add(game.size)) > 0) continue;
                        const expected = sig.identity + '\0';
                        const label = new Uint8Array(target.readByteArray(expected.length));
                        if (!Array.from(label).every((byte, index) => byte === expected.charCodeAt(index))) continue;
                    }
                    const bytes = new Uint8Array(match.address.readByteArray(sig.mask.length));
                    matches.push({rva: match.address.sub(game.base).toUInt32(),
                        hex: Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')});
                    if (matches.length > 4096) throw new Error('Too many matches: ' + sig.name);
                }
            }
            result[sig.name] = matches;
        }
        return result;
    }
};
