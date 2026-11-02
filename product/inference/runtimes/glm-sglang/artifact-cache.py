import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile


def seed(root, cache):
    manifest = json.loads((root / 'artifacts.json').read_text())
    cache.mkdir(parents=True, exist_ok=True)
    with (cache / 'seed.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for item in manifest['files']:
            source = root / 'flashinfer-artifacts' / item['path']
            destination = cache / item['path']
            if not source.resolve().is_relative_to((root / 'flashinfer-artifacts').resolve()) or not destination.resolve().is_relative_to(cache.resolve()):
                raise ValueError('Artifact path escaped cache')
            if source.stat().st_size != item['size'] or hashlib.sha256(source.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError('Bundled FlashInfer artifact failed verification: ' + item['path'])
            if destination.exists() and destination.stat().st_size == item['size'] and hashlib.sha256(destination.read_bytes()).hexdigest() == item['sha256']:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
                temporary = Path(output.name)
                try:
                    with source.open('rb') as stream:
                        shutil.copyfileobj(stream, output)
                    output.flush()
                    temporary.chmod(0o644)
                    temporary.replace(destination)
                finally:
                    temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    seed(Path(sys.argv[1]), Path(sys.argv[2]))
