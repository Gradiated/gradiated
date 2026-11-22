"""Materialise pinned autonomous RTL without editing the baseline."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def materialise(baseline, output):
    manifest = json.loads((HERE/'manifest.json').read_text())
    files = {}
    for name, expected in manifest['baseline'].items():
        source = baseline/(name+'.sv')
        original = source.read_bytes()
        if hashlib.sha256(original).hexdigest() != expected:
            raise ValueError(f'Frozen RTL differs: {source}')
        data = (HERE/'rtl'/(name+'.sv')).read_bytes() if name in manifest['overrides'] else original
        if hashlib.sha256(data).hexdigest() != manifest['generated'][name]:
            raise ValueError(f'Autonomous RTL differs: {name}')
        files[name] = data
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        (output/(name+'.sv')).write_bytes(data)
    (output/'source-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return list(files)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=HERE.parents[1]/'rtl')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    materialise(args.baseline, args.output)
