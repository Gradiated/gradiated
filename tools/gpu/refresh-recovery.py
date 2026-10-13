#!/usr/bin/env python3
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    destination = ROOT / 'product/inference/images/gpu-base/recovery'
    destination.mkdir(exist_ok=True)
    for name in ('host-agent.py', 'host_state.py', 'host_bundle.py'):
        shutil.copyfile(ROOT / 'product/inference/gpu' / name, destination / name)
    print('Refreshed the frozen recovery sources; review and qualify the GPU base before pinning it.')


if __name__ == '__main__':
    main()
