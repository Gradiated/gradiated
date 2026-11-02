import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def apply(site, directory):
    manifest = json.loads((directory / 'patches.json').read_text())
    if manifest['upstream_sha'] != 'f171859219b54e1dad45dda60028034490836974':
        raise ValueError('Unexpected SGLang source revision')
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
    args = parser.parse_args()
    apply(args.site, args.directory)
