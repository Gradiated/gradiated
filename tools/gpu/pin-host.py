#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def pin(release):
    if release.get('bundle') != 'host':
        raise ValueError('Expected a verified host release, not a model runtime release')
    digest, base_id = release['sha256'], release['baseId']
    if not re.fullmatch('[0-9a-f]{64}', digest) or not re.fullmatch('[A-Za-z0-9._-]+', base_id):
        raise ValueError('Invalid verified host release')
    return {'sha256': digest, 'baseId': base_id}


def main():
    parser = argparse.ArgumentParser(description='Pin a published host bundle and render the fleet configuration.')
    parser.add_argument('release', type=Path, help='host-runtime-release/release.json from Model deployment')
    parser.add_argument('--infra-root', type=Path, default=None,
                        help='infrastructure checkout holding infra/ manifests when separate from product source')
    args = parser.parse_args()
    infra_root = args.infra_root.resolve() if args.infra_root is not None else ROOT
    env_base = infra_root / 'environments' if (infra_root / 'environments').is_dir() else infra_root / 'infra/environments'
    path = env_base / 'prod/us-east-1/kubernetes/gpu-inference/pins.json'
    pins = json.loads(path.read_text())
    pins['hostBundle'] = pin(json.loads(args.release.read_text()))
    path.write_text(json.dumps(pins, indent=2) + '\n')
    command = ['python3', str(ROOT / 'tools/gpu/render-config.py')]
    if args.infra_root is not None:
        command.extend(['--infra-root', str(infra_root)])
    subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
