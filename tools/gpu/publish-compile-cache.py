#!/usr/bin/env python3
"""Package the kernels a qualified host compiled for a runtime, then publish and pin them.

A new host spends most of its first start compiling kernels: measured on a
B300 TP2 GLM SGLang replica, about 410 s inside weight loading, 650 s inside
FlashInfer autotune and 200 s on first requests. Restoring a qualified host's
cache at the same path with its timestamps brought a first start from 1688 s
to 392 s.

1. On a host that just qualified the runtime, as root (stdlib only):
   python3 publish-compile-cache.py package /tmp/compile-cache.tar.gz glm-sglang triton torchinductor
2. Copy the archive here, then upload it and pin it for each runtime built from
   that host's bundle:
   python3 tools/gpu/publish-compile-cache.py publish compile-cache.tar.gz --runtime <key> [--write]

Hosts stage the pinned archive like a bundle and copy it into
/home/runtime/.cache before a pod starts, never replacing files already there.
The archive is executable code for every host that runs the runtime, so publish
only from a production host serving that exact bundle.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

CACHE = Path('/home/runtime/.cache')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*')
# Locks, models and per-host qualification records never travel between hosts.
EXCLUDED_TOP = {'gradiated', 'huggingface'}
EXCLUDED_PARTS = {'qualification'}
BUCKET = 'gradiated-prod-model-artifacts-873716897517'


def repository():
    # Packaging runs from a lone copy on a host, so resolve the checkout only to publish.
    return Path(__file__).resolve().parents[2]


def package(output, directories, cache=CACHE):
    """Write a gzip tar of the named cache directories with their timestamps and readable modes."""
    if not directories or any(not NAME.fullmatch(name) or name in EXCLUDED_TOP for name in directories):
        raise ValueError('Name cache directories under the runtime cache, such as glm-sglang triton torchinductor')
    members = []
    for name in sorted(set(directories)):
        top = cache / name
        if top.is_symlink() or not top.is_dir():
            raise ValueError(f'{top} is not a cache directory')
        for directory, names, files in os.walk(top):
            names[:] = sorted(item for item in names if item not in EXCLUDED_PARTS)
            relative = Path(directory).relative_to(cache)
            members.append(relative)
            members += [relative / item for item in sorted(files)]
    # Fixed owners and modes keep the archive independent of the host; the
    # extracted copy belongs to the downloader, so files must stay readable.
    with open(output, 'wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed, \
            tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as archive:
        for member in members:
            path = cache / member
            status = path.lstat()
            if path.is_symlink():
                continue
            info = tarfile.TarInfo(member.as_posix())
            info.mtime, info.uid, info.gid, info.uname, info.gname = status.st_mtime, 0, 0, '', ''
            if path.is_dir():
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                archive.addfile(info)
            elif path.is_file():
                info.size, info.mode = status.st_size, 0o755 if status.st_mode & 0o111 else 0o644
                with path.open('rb') as stream:
                    archive.addfile(info, stream)
    return output


def inspect(archive_path):
    """Reject anything a host should not copy into its runtime cache; return the top-level names."""
    tops = set()
    with tarfile.open(archive_path, 'r:gz') as archive:
        for member in archive:
            parts = Path(member.name).parts
            if (member.name.startswith('/') or '..' in parts or not parts or not (member.isfile() or member.isdir())
                    or any(part in EXCLUDED_PARTS for part in parts)):
                raise ValueError(f'Compile cache archive holds an unsafe entry: {member.name}')
            if member.mode & 0o004 == 0:
                raise ValueError(f'Compile cache entry is not world-readable: {member.name}')
            tops.add(parts[0])
    if not tops or any(not NAME.fullmatch(top) or top in EXCLUDED_TOP for top in tops):
        raise ValueError(f'Compile cache archive has unexpected top-level entries: {sorted(tops)}')
    return sorted(tops)


def pin(runtimes, keys, base, digest):
    updated = json.loads(json.dumps(runtimes))
    for key in keys:
        runtime = updated.get(key)
        if runtime is None:
            raise ValueError(f'Unknown runtime {key}')
        if base not in runtime.get('bundles', {}):
            raise ValueError(f'Runtime {key} has no bundle for base {base}')
        runtime['compile_caches'] = {**runtime.get('compile_caches', {}), base: digest}
    return updated


def publish(archive_path, keys, write, profile='gradiated-developer'):
    tops = inspect(archive_path)
    digest = hashlib.sha256(Path(archive_path).read_bytes()).hexdigest()
    root = repository()
    runtimes_path = root / 'product/inference/gpu/runtimes.json'
    base = json.loads((root / 'infra/environments/prod/us-east-1/kubernetes/gpu-inference/pins.json').read_text())['hostBundle']['baseId']
    runtimes = json.loads(runtimes_path.read_text())
    updated = pin(runtimes, keys, base, digest)
    key = f'bundles/sha256/{digest}.tar.gz'
    if write:
        exists = subprocess.run(['aws', '--profile', profile, 's3api', 'head-object', '--bucket', BUCKET, '--key', key],
                                capture_output=True).returncode == 0
        if not exists:
            subprocess.run(['aws', '--profile', profile, 's3', 'cp', str(archive_path), f's3://{BUCKET}/{key}',
                            '--only-show-errors'], check=True)
        runtimes_path.write_text(json.dumps(updated, indent=2) + '\n')
    return {'write': write, 'digest': digest, 'base': base, 'directories': tops, 'runtimes': keys,
            'size_bytes': Path(archive_path).stat().st_size,
            'next': 'python3 tools/gpu/render-config.py; review and commit' if write else 'rerun with --write'}


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    packaging = commands.add_parser('package', help='run on the qualified host as root')
    packaging.add_argument('output', type=Path)
    packaging.add_argument('directories', nargs='+')
    publishing = commands.add_parser('publish', help='upload the archive and pin it for runtimes')
    publishing.add_argument('archive', type=Path)
    publishing.add_argument('--runtime', action='append', required=True, help='runtimes.json key; repeat for each')
    publishing.add_argument('--profile', default='gradiated-developer')
    publishing.add_argument('--write', action='store_true', help='upload and edit runtimes.json; otherwise a dry run')
    args = parser.parse_args(arguments)
    if args.command == 'package':
        package(args.output, args.directories)
        print(json.dumps({'archive': str(args.output), 'directories': inspect(args.output),
                          'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest()}))
    else:
        print(json.dumps(publish(args.archive, args.runtime, args.write, args.profile), indent=2))


if __name__ == '__main__':
    sys.exit(main())
