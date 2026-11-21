"""Relocate the V18 profile by code shape and cross references, never by version.

Only external PC-relative operands are wildcarded. Instructions, field offsets,
constants and branches inside a guarded block remain exact. Ambiguity is fatal.
"""
from copy import deepcopy

from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_GRP_CALL, CS_GRP_JUMP
from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


class IncompatibleError(RuntimeError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


IDENTITY_NAMES = {
    'keyboard_identity': 'keyboard', 'mouse_identity': 'mouse',
    'wheel_identity': 'steering_wheel', 'supplemental_identity': 'sw_supplemental',
}


def address_fields(profile):
    for key, value in profile.items():
        if key.endswith('Rva'):
            yield (key,), value
    for key, value in profile['ids'].items():
        yield ('ids', key), value
    for index, value in enumerate(profile['winchGamepadCallers']):
        yield ('winchGamepadCallers', index), value


def compile_signatures(profile):
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    signatures = []
    identity_origin = next(g['rva'] for g in profile['guards'] if g['name'] == 'keyboard_identity')
    for guard in profile['guards']:
        raw = bytes.fromhex(guard['hex'])
        begin, end = guard['rva'], guard['rva'] + len(raw)
        instructions = list(decoder.disasm(raw, begin))
        if sum(i.size for i in instructions) != len(raw):
            raise ValueError('Incomplete reference instruction: ' + guard['name'])
        mask, refs = [True] * len(raw), []
        for ins in instructions:
            for operand in ins.operands:
                branch = operand.type == X86_OP_IMM and (
                    ins.group(CS_GRP_CALL) or ins.group(CS_GRP_JUMP))
                rip = operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP
                if not branch and not rip:
                    continue
                offset = ins.imm_offset if branch else ins.disp_offset
                # RIP addressing uses disp32. Capstone 5.0.7 reports disp_size=2
                # for some 0x66-prefixed SSE instructions in this reference.
                size = ins.imm_size if branch else 4
                target = operand.imm if branch else ins.address + ins.size + operand.mem.disp
                ref = {'offset': ins.address - begin + offset, 'size': size,
                       'next': ins.address - begin + ins.size, 'target': target,
                       'kind': 'code' if branch else 'memory'}
                refs.append(ref)
                if reference_target(ref, begin, raw) != target:
                    raise ValueError('Invalid reference encoding: ' + guard['name'])
                if not begin <= target < end:
                    mask[ref['offset']:ref['offset'] + size] = [False] * size
        signatures.append({**guard, 'mask': mask, 'refs': refs,
                           'pattern': ' '.join(f'{b:02x}' if keep else '??'
                                               for b, keep in zip(raw, mask)),
                           'groupOrigin': identity_origin if guard['name'] in IDENTITY_NAMES else None,
                           'identity': IDENTITY_NAMES.get(guard['name'])})
    return signatures


def find_matches(signature, segments, read):
    """Offline equivalent of the read-only Frida scanner, for evidence/tests."""
    raw = bytes.fromhex(signature['hex'])
    # Search the longest literal run, then check the whole pattern. This avoids
    # a full regex lookahead at every byte of a 35 MB executable section.
    runs, begin = [], None
    for index, keep in enumerate(signature['mask'] + [False]):
        if keep and begin is None:
            begin = index
        elif not keep and begin is not None:
            runs.append((begin, index))
            begin = None
    begin, end = max(runs, key=lambda pair: pair[1] - pair[0])
    needle = raw[begin:end]
    matches = []
    for start, data in segments:
        offset = data.find(needle)
        while offset >= 0:
            position = offset - begin
            offset = data.find(needle, offset + 1)
            if position < 0 or position + len(raw) > len(data):
                continue
            rva, found = start + position, data[position:position + len(raw)]
            if any(keep and a != b for a, b, keep in zip(raw, found, signature['mask'])):
                continue
            if signature['identity']:
                ref = signature['refs'][0]
                target = reference_target(ref, rva, found)
                expected = signature['identity'].encode() + b'\0'
                if read(target, len(expected)) != expected:
                    continue
            matches.append({'rva': rva, 'hex': found.hex()})
            if len(matches) > 4096:
                raise IncompatibleError('Too many matches: ' + signature['name'])
    return matches


def reference_target(ref, rva, raw):
    offset, size = ref['offset'], ref['size']
    return rva + ref['next'] + int.from_bytes(raw[offset:offset + size], 'little', signed=True)


def resolve_profile(profile, signatures, matches, sections):
    symbols = {value for _, value in address_fields(profile)}
    symbols.update(g['rva'] for g in signatures)
    symbols.update(ref['target'] for g in signatures for ref in g['refs'])

    def contained(rva, size=1, executable=False):
        return any(s['rva'] <= rva and rva + size <= s['rva'] + s['size'] and
                   (s['executable'] if executable else s['readable']) for s in sections)

    choices = {}
    for sig in signatures:
        candidates = []
        original = bytes.fromhex(sig['hex'])
        for match in matches.get(sig['name'], []):
            raw, rva = bytes.fromhex(match['hex']), match['rva']
            if len(raw) != len(original) or not contained(rva, len(raw), executable=True):
                continue
            if any(keep and a != b for a, b, keep in zip(original, raw, sig['mask'])):
                continue
            facts = {symbol: rva + symbol - sig['rva'] for symbol in symbols
                     if sig['rva'] <= symbol < sig['rva'] + len(raw)}
            # The four adjacent category constructors form one verified block.
            # Many other subsystems intern the same strings; their constructors
            # must not be mistaken for this input engine's category slots.
            if sig['groupOrigin'] is not None:
                facts[sig['groupOrigin']] = rva + sig['groupOrigin'] - sig['rva']
            valid = True
            for ref in sig['refs']:
                target = reference_target(ref, rva, raw)
                if not contained(target, executable=ref['kind'] == 'code') or (
                        ref['target'] in facts and facts[ref['target']] != target):
                    valid = False
                    break
                facts[ref['target']] = target
            if valid:
                candidates.append({**match, 'facts': facts})
        choices[sig['name']] = candidates

    # Arc consistency: two observations of the same reference must agree.
    # This disambiguates short getters via the calls from longer winch blocks.
    changed = True
    while changed and all(choices.values()):
        changed = False
        for symbol in symbols:
            owners = [name for name, values in choices.items() if symbol in values[0]['facts']]
            if len(owners) < 2:
                continue
            allowed = set.intersection(*(
                {c['facts'][symbol] for c in choices[name]} for name in owners))
            for name in owners:
                narrowed = [c for c in choices[name] if c['facts'][symbol] in allowed]
                if len(narrowed) != len(choices[name]):
                    choices[name] = narrowed
                    changed = True
            if not all(choices.values()):
                break
    counts = {name: len(values) for name, values in choices.items()}
    if any(count != 1 for count in counts.values()):
        raise IncompatibleError('Missing, changed or ambiguous code; feature disabled',
                                {'candidateCounts': counts})
    resolved = deepcopy(profile)
    mapping = {}
    for values in choices.values():
        for symbol, target in values[0]['facts'].items():
            if symbol in mapping and mapping[symbol] != target:
                raise IncompatibleError('Inconsistent code references')
            mapping[symbol] = target
    for path, old in address_fields(profile):
        if old not in mapping:
            raise IncompatibleError('Unresolved address: ' + str(path))
        parent = resolved
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = mapping[old]
    resolved['guards'] = [{'name': sig['name'], 'rva': choices[sig['name']][0]['rva'],
                           'hex': choices[sig['name']][0]['hex']} for sig in signatures]
    # Data slots must be fully readable, not just their first byte.
    for address in resolved['ids'].values():
        if not contained(address, 4):
            raise IncompatibleError('Invalid category slot')
    for key in ('stringPoolSlotRva', 'engineStateSlotRva'):
        if not contained(resolved[key], 8):
            raise IncompatibleError('Invalid pointer slot')
    return resolved, {'method': 'signatures-and-references', 'candidateCounts': counts,
                      'relocatedGuards': sum(a['rva'] != b['rva'] for a, b in
                                             zip(profile['guards'], resolved['guards']))}
