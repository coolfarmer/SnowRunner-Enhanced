"""Compile relocatable FFB guards using the same decoder as Enhanced's other profiles."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from compatibility import compile_signatures


def generate(destination):
    profile = json.loads((ROOT / 'src/steering-profile.json').read_text())
    signatures = compile_signatures(profile)
    rows, declarations = [], []
    for i, sig in enumerate(signatures):
        raw = bytes.fromhex(sig['hex'])
        for label, data in [('bytes', raw), ('mask', sig['mask'])]:
            declarations.append(f'static const unsigned char sw_{label}_{i}[]={{' + ','.join(str(int(b)) for b in data) + '};')
        refs = [f'{{{r["offset"]},{r["size"]},{r["next"]},{r["target"]},{int(r["kind"] == "code")}}}' for r in sig['refs']]
        declarations.append(f'static const SwRef sw_refs_{i}[]={{' + ','.join(refs or ['{0}']) + '};')
        rows.append(f'{{"{sig["name"]}",{sig["rva"]},{len(raw)},sw_bytes_{i},sw_mask_{i},sw_refs_{i},{len(refs)}}}')
    destination.write_text('/* Generated from steering-profile.json; no runtime overrides. */\n' +
        '\n'.join(declarations) + '\nstatic const SwSignature sw_signatures[]={' + ','.join(rows) + '};\n' +
        f'#define SW_CONSTRUCTOR_RVA {profile["constructorRva"]}u\n', encoding='utf-8')
