import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request


def fetch(manifest, destination):
    pins = json.loads(manifest.read_text())
    for item in pins['files']:
        target = destination / item['path']
        if not target.resolve().is_relative_to(destination.resolve()):
            raise ValueError('Artifact escaped destination')
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + '.partial')
        for attempt in range(3):
            try:
                digest, size = hashlib.sha256(), 0
                with urllib.request.urlopen(pins['repository'] + item['path'], timeout=120) as response, temporary.open('wb') as output:
                    while block := response.read(1024 * 1024):
                        size += len(block)
                        if size > item['size']:
                            raise ValueError('Artifact exceeds pinned size')
                        digest.update(block)
                        output.write(block)
                if size != item['size'] or digest.hexdigest() != item['sha256']:
                    raise ValueError('Artifact checksum mismatch: ' + item['path'])
                temporary.replace(target)
                break
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
            finally:
                temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('artifacts.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    fetch(args.manifest, args.output)
