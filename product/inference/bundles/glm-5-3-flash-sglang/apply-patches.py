import argparse
import hashlib
import json
from pathlib import Path
import subprocess


REVISIONS = {
    'patches.json': 'f171859219b54e1dad45dda60028034490836974',
    'smg-patches.json': '91b3e0c440f9ab7971aa3ba48b049d951bd963de',
}


def apply(site, directory, manifest_name='patches.json'):
    if manifest_name not in REVISIONS:
        raise ValueError('Unexpected patch manifest')
    manifest = json.loads((directory / manifest_name).read_text())
    if manifest['upstream_sha'] != REVISIONS[manifest_name]:
        raise ValueError('Unexpected source revision')
    for item in manifest['files']:
        target = site / item['path']
        if not target.resolve().is_relative_to(site.resolve()):
            raise ValueError('Patch target escaped site-packages')
        if hashlib.sha256(target.read_bytes()).hexdigest() != item['original_sha256']:
            raise ValueError('Upstream patch input changed: ' + item['path'])
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(site),
                        '-i', str((directory / 'patches' / item['patch']).resolve())], check=True)
        if hashlib.sha256(target.read_bytes()).hexdigest() != item['overlay_sha256']:
            raise ValueError('Qualified patch output changed: ' + item['path'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('site', type=Path)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--manifest', choices=REVISIONS, default='patches.json')
    args = parser.parse_args()
    apply(args.site, args.directory, args.manifest)
