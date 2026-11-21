'use strict';

// Native-bundle counterpart of compatibility.py. The signatures are compiled
// at build time; no Python, disassembler or external profile is used in-game.
function resolveNativeProfile(profile, signatures, matches, sections) {
    const fields = [];
    for (const [key, value] of Object.entries(profile))
        if (key.endsWith('Rva')) fields.push([[key], value]);
    for (const [key, value] of Object.entries(profile.ids)) fields.push([['ids', key], value]);
    profile.winchGamepadCallers.forEach((v, i) => fields.push([['winchGamepadCallers', i], v]));
    const symbols = new Set(fields.map(f => f[1]));
    signatures.forEach(s => { symbols.add(s.rva); s.refs.forEach(r => symbols.add(r.target)); });
    const bytes = hex => Uint8Array.from(hex.match(/../g).map(x => parseInt(x, 16)));
    const contained = (rva, size = 1, code = false) => sections.some(s =>
        s.rva <= rva && rva + size <= s.rva + s.size && (code ? s.executable : s.readable));
    const choices = {};
    for (const sig of signatures) {
        const original = bytes(sig.hex);
        choices[sig.name] = [];
        for (const match of matches[sig.name] || []) {
            const raw = bytes(match.hex), rva = match.rva;
            if (raw.length !== original.length || !contained(rva, raw.length, true) ||
                    raw.some((v, i) => sig.mask[i] && v !== original[i])) continue;
            const facts = new Map();
            for (const symbol of symbols)
                if (symbol >= sig.rva && symbol < sig.rva + raw.length)
                    facts.set(symbol, rva + symbol - sig.rva);
            if (sig.groupOrigin !== null) facts.set(sig.groupOrigin, rva + sig.groupOrigin - sig.rva);
            let valid = true;
            const view = new DataView(raw.buffer);
            for (const ref of sig.refs) {
                const displacement = ref.size === 1 ? view.getInt8(ref.offset) : view.getInt32(ref.offset, true);
                const target = rva + ref.next + displacement;
                if (!contained(target, 1, ref.kind === 'code') ||
                        (facts.has(ref.target) && facts.get(ref.target) !== target)) { valid = false; break; }
                facts.set(ref.target, target);
            }
            if (valid) choices[sig.name].push({...match, facts});
        }
    }
    let changed = true;
    while (changed && Object.values(choices).every(a => a.length)) {
        changed = false;
        for (const symbol of symbols) {
            const owners = Object.keys(choices).filter(k => choices[k][0].facts.has(symbol));
            if (owners.length < 2) continue;
            let allowed = new Set(choices[owners[0]].map(c => c.facts.get(symbol)));
            for (const owner of owners.slice(1)) {
                const other = new Set(choices[owner].map(c => c.facts.get(symbol)));
                allowed = new Set([...allowed].filter(v => other.has(v)));
            }
            for (const owner of owners) {
                const filtered = choices[owner].filter(c => allowed.has(c.facts.get(symbol)));
                if (filtered.length !== choices[owner].length) { choices[owner] = filtered; changed = true; }
            }
            if (!Object.values(choices).every(a => a.length)) break;
        }
    }
    const counts = Object.fromEntries(Object.entries(choices).map(([k, v]) => [k, v.length]));
    if (Object.values(counts).some(n => n !== 1)) {
        const error = new Error('Signatures missing, changed or ambiguous');
        error.details = {candidateCounts: counts}; throw error;
    }
    const result = JSON.parse(JSON.stringify(profile)), mapping = new Map();
    for (const candidates of Object.values(choices))
        for (const [symbol, target] of candidates[0].facts) {
            if (mapping.has(symbol) && mapping.get(symbol) !== target) throw new Error('Inconsistent references');
            mapping.set(symbol, target);
        }
    for (const [path, old] of fields) {
        if (!mapping.has(old)) throw new Error('Unresolved address');
        let parent = result;
        for (const key of path.slice(0, -1)) parent = parent[key];
        parent[path[path.length - 1]] = mapping.get(old);
    }
    result.guards = signatures.map(s => ({name: s.name, rva: choices[s.name][0].rva, hex: choices[s.name][0].hex}));
    for (const rva of Object.values(result.ids)) if (!contained(rva, 4)) throw new Error('Invalid category slot');
    for (const key of ['stringPoolSlotRva', 'engineStateSlotRva'])
        if (!contained(result[key], 8)) throw new Error('Invalid pointer slot');
    return {profile: result, details: {method: 'signatures-and-references', candidateCounts: counts,
        relocatedGuards: result.guards.filter((g, i) => g.rva !== profile.guards[i].rva).length}};
}
