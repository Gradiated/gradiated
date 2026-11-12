"""Apply ordered, hash-pinned Kimi overlays and verify installed source."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

UPSTREAM = 'afcd7d6b487a9cbe73e25941971b4cc107e6f9ae'
ORDER = ('manifest.json', 'baseline-request-seed-manifest.json', 'dflash-request-seed-manifest.json', 'dflash-experiment-admission-manifest.json', 'cache-accounting-manifest.json', 'fused-philox-manifest.json')
PROFILES = {'correctness': ORDER[:1], 'baseline-seeded': ORDER[:2], 'dflash-seeded': ORDER[:3], 'dflash-experiment-admitted': ORDER[:4], 'dflash-admitted-cache-accounting': ORDER[:5], 'dflash-admitted-cache-accounting-fused-philox': ORDER}
NEW_FILE = 'sglang/srt/speculative/seeded_dflash.py'
EMPTY = hashlib.sha256(b'').hexdigest()
MARKER = '.gradiated-kimi-overlay.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe(root, name):
    path = root / name
    if Path(name).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes overlay root: ' + name)
    return path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def apply(site, patches, profile, pins):
    """Validate entire lineage in a scratch tree before publishing any changes."""
    final = {}
    oracles = {}
    manifest_hashes = {}
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        for name in PROFILES[profile]:
            raw = (patches / name).read_bytes()
            if digest(raw) != pins[name]:
                raise ValueError('Manifest hash changed: ' + name)
            manifest_hashes[name] = digest(raw)
            manifest = json.loads(raw)
            if manifest['upstream_sha'] != UPSTREAM:
                raise ValueError('Unexpected upstream')
            for relative, expected in manifest.get('oracle_sources', {}).items():
                data = safe(site, relative).read_bytes()
                if digest(data) != expected:
                    raise ValueError('Oracle source changed: ' + relative)
                target = safe(stage, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                oracles[relative] = expected
            groups = {}
            for item in manifest['files']:
                relative = item['path']
                source = safe(site, relative)
                target = safe(stage, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                if relative not in final:
                    if relative == NEW_FILE:
                        if source.exists() or source.is_symlink() or item['original_sha256'] != EMPTY:
                            raise ValueError('New helper must not already exist')
                    else:
                        target.write_bytes(source.read_bytes())
                current = target.read_bytes() if target.exists() else b''
                if digest(current) != item['original_sha256']:
                    raise ValueError('Input source hash changed: ' + relative)
                patch_name = item.get('patch', manifest.get('patch'))
                patch_hash = item.get('patch_sha256', manifest.get('patch_sha256'))
                patch = safe(patches, patch_name)
                if digest(patch.read_bytes()) != patch_hash:
                    raise ValueError('Patch hash changed: ' + patch_name)
                groups.setdefault(patch_name, []).append(item)
            for patch_name, entries in groups.items():
                patch = safe(patches, patch_name)
                headers = set()
                for line in patch.read_text().splitlines():
                    if line.startswith(('--- ', '+++ ')):
                        value = line[4:].split('\t')[0]
                        if value != '/dev/null':
                            if not value.startswith(('a/', 'b/')):
                                raise ValueError('Unexpected patch path')
                            headers.add(value[2:])
                if headers != {entry['path'] for entry in entries}:
                    raise ValueError('Patch target set differs from manifest')
                subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(stage), '-i', str(patch.resolve())], check=True, capture_output=True)
                for item in entries:
                    data = safe(stage, item['path']).read_bytes()
                    if digest(data) != item['overlay_sha256']:
                        raise ValueError('Output source hash changed: ' + item['path'])
                    compile(data, item['path'], 'exec')
                    final[item['path']] = item['overlay_sha256']
        identity = {'upstream_sha': UPSTREAM, 'profile': profile, 'manifests': manifest_hashes, 'files': final, 'oracle_sources': oracles}
        identity['fingerprint'] = digest(canonical(identity))
        for relative in final:
            target = safe(site, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(safe(stage, relative).read_bytes())
        (site / MARKER).write_bytes(canonical(identity) + b'\n')
        return identity


def verify(site, expected):
    identity = json.loads((site / MARKER).read_bytes())
    fingerprint = identity.pop('fingerprint')
    if fingerprint != expected or digest(canonical(identity)) != expected:
        raise ValueError('Unexpected Kimi overlay identity')
    for relative, sha in (identity['files'] | identity.get('oracle_sources', {})).items():
        if digest(safe(site, relative).read_bytes()) != sha:
            raise ValueError('Kimi overlay source modified: ' + relative)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('site', type=Path)
    parser.add_argument('patches', type=Path)
    parser.add_argument('--profile', choices=PROFILES, required=True)
    parser.add_argument('--pins', type=Path, default=Path(__file__).with_name('manifest-pins.json'))
    args = parser.parse_args()
    print(json.dumps(apply(args.site, args.patches, args.profile, json.loads(args.pins.read_text())), indent=2))
