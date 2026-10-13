#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def pin(release):
    digest, base_id = release['sha256'], release['baseId']
    if not re.fullmatch('[0-9a-f]{64}', digest) or not re.fullmatch('[A-Za-z0-9._-]+', base_id):
        raise ValueError('Invalid verified host release')
    return {'sha256': digest, 'base_id': base_id}


def main():
    parser = argparse.ArgumentParser(description='Pin a published host release and render controller configuration.')
    parser.add_argument('release', type=Path, help='host-runtime-release/release.json from Model deployment')
    args = parser.parse_args()
    value = pin(json.loads(args.release.read_text()))
    path = ROOT / 'infra/environments/prod/us-east-1/kubernetes/gpu-inference/host.json'
    path.write_text(json.dumps(value, indent=2) + '\n')
    subprocess.run(['python3', str(ROOT / 'tools/gpu/render-config.py')], check=True)


if __name__ == '__main__':
    main()
