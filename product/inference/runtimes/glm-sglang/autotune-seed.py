"""Seed FlashInfer autotune results tuned on an earlier host into an empty cache.

A host's first start otherwise spends 5-11 minutes tuning tactics that are the
same on every host of a GPU type: the cache key covers the model and parallel
settings, and the file's metadata stamp covers library versions and the GPU.
Seeding is best effort and never blocks startup. It fills a tuning directory
only when no rank has a file there, so a host's own results are never
replaced and every rank sees the same file. FlashInfer ignores a file whose
metadata disagrees with the running libraries or GPU, and SGLang discards
caches that differ across ranks, so a stale seed only costs the tuning it
would have saved.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import tempfile


def seed(source_root, cache):
    """Seed missing tuning directories under cache and return how many were seeded."""
    manifest = json.loads((source_root / 'manifest.json').read_text())
    cache.mkdir(parents=True, exist_ok=True)
    seeded = 0
    with (cache / 'autotune-seed.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for item in manifest['files']:
            ranks = item['ranks']
            if type(ranks) is not int or not 1 <= ranks <= 64:
                raise ValueError('Autotune seed rank count is invalid')
            source = (source_root / item['source']).resolve()
            directory = (cache / item['directory']).resolve()
            if not source.is_relative_to(source_root.resolve()) or not directory.is_relative_to(cache.resolve()):
                raise ValueError('Autotune seed path escaped its root')
            data = source.read_bytes()
            if len(data) != item['size'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError('Bundled autotune seed failed verification: ' + item['source'])
            names = [f'rank_tp{rank}_pp0_dp0.json' for rank in range(ranks)]
            if directory.exists() and any((directory / name).exists() for name in names):
                continue
            directory.mkdir(parents=True, exist_ok=True)
            for name in names:
                with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
                    temporary = Path(output.name)
                    try:
                        output.write(data)
                        output.flush()
                        temporary.chmod(0o600)
                        temporary.replace(directory / name)
                    finally:
                        temporary.unlink(missing_ok=True)
            seeded += 1
    return seeded


def main(arguments):
    source_root, cache = Path(arguments[0]), Path(arguments[1])
    try:
        print(f'autotune-seed: seeded {seed(source_root, cache)} tuning directories', flush=True)
    except Exception as error:
        # A missing seed only means this start tunes from scratch.
        print(f'autotune-seed: skipped ({type(error).__name__})', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
