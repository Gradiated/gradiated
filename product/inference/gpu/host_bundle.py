import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import stat
import threading
import tarfile
import tempfile
import uuid

from host_state import atomic_json, atomic_write, sync_directory

BASE_ID = Path('/etc/gradiated/base-id')

FILES = {'host-agent.py', 'desmondd', 'base-id'}


def host_version(root):
    marker = Path(__file__).resolve().with_name('.bundle-sha256')
    status = root / 'host' / 'status.json'
    try:
        state = json.loads(status.read_text())
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    staging = root / 'host' / 'staging-error.json'
    try:
        failure = json.loads(staging.read_text())
        if not isinstance(failure, dict):
            failure = {}
    except (OSError, ValueError):
        failure = {}
    return {'host_bundle_sha256': marker.read_text().strip() if marker.exists() else '',
            'previous_host_bundle_sha256': state.get('previous', ''),
            'host_bundle_trial': bool(state.get('trial')),
            'host_bundle_failed_sha256': state.get('failed', ''),
            'host_launcher': status.exists(),
            'host_bundle_staging_failed_sha256': failure.get('sha256', '')}


def validate_pin(pin, base_id):
    if (not isinstance(pin, dict) or set(pin) != {'sha256', 'base_id'} or
            not isinstance(pin['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', pin['sha256'])):
        raise ValueError('A pinned host bundle is required')
    if pin['base_id'] != base_id:
        raise ValueError('Host bundle requires a different base')


def promote_archive(source, destination, digest, base_id):
    with tempfile.TemporaryDirectory(prefix='.verify-', dir=destination.parent) as work:
        root = Path(work)
        archive = root / 'bundle.tar.gz'
        checksum = hashlib.sha256()
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        size = 0
        with os.fdopen(fd, 'rb') as incoming, archive.open('wb') as output:
            if not stat.S_ISREG(os.fstat(incoming.fileno()).st_mode):
                raise ValueError('Host archive must be a regular file')
            while data := incoming.read(1024 * 1024):
                size += len(data)
                if size > 64 * 1024 * 1024:
                    raise ValueError('Host archive exceeds its size limit')
                checksum.update(data)
                output.write(data)
        if checksum.hexdigest() != digest:
            raise ValueError('Host archive checksum mismatch')
        tree = root / 'tree'
        tree.mkdir()
        total = 0
        with tarfile.open(archive, 'r:gz') as contents:
            for count, member in enumerate(contents, 1):
                if count > 128:
                    raise ValueError('Host archive exceeds its member limit')
                if member.name == '.' and member.isdir():
                    continue
                name = member.name.removeprefix('./')
                total += member.size
                if (not member.isfile() or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,127}', name) or
                        member.size < 0 or (tree / name).exists() or
                        len(list(tree.iterdir())) >= 65 or total > 128 * 1024 * 1024):
                    raise ValueError('Unsafe host archive contents')
                with contents.extractfile(member) as incoming, (tree / name).open('wb') as output:
                    shutil.copyfileobj(incoming, output)
                    output.flush()
                    os.fsync(output.fileno())
                (tree / name).chmod(0o755 if member.mode & 0o111 else 0o644)
        hashes = json.loads((tree / 'files.json').read_text())
        if (not isinstance(hashes, dict) or not FILES.issubset(hashes) or 'files.json' in hashes or
                {path.name for path in tree.iterdir()} != set(hashes) | {'files.json'} or
                (tree / 'base-id').read_text().strip() != base_id):
            raise ValueError('Incomplete or incompatible host bundle')
        for name, checksum in hashes.items():
            path = tree / name
            if not isinstance(checksum, str) or not re.fullmatch('[0-9a-f]{64}', checksum) or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                raise ValueError('Host bundle file checksum mismatch')
            if name == 'desmondd':
                path.chmod(0o755)
        atomic_write(tree / '.bundle-sha256', (digest + '\n').encode())
        tree.chmod(0o755)
        sync_directory(tree)
        if destination.exists() or destination.is_symlink():
            raise ValueError('Host bundle destination already exists')
        tree.rename(destination)
        sync_directory(destination.parent)


def stage_host(agent, pin, epoch):
    base_id = BASE_ID.read_text().strip()
    validate_pin(pin, base_id)
    version = host_version(agent.root)
    digest = pin['sha256']
    if not version['host_launcher']:
        raise ValueError('Host launcher must be installed before host updates')
    if digest in (version['host_bundle_sha256'], version['host_bundle_failed_sha256']):
        return
    if getattr(agent, 'host_staging', None):
        return
    agent.host_staging = digest
    downloader = Path(__file__).resolve().with_name('download-runtime')
    if not downloader.is_file():downloader = Path('/opt/gradiated/bin/download-runtime')

    def stage():
        try:
            root = agent.root / 'host'
            downloads = agent.root / 'host-downloads'
            downloads.mkdir(exist_ok=True)
            account = pwd.getpwnam('downloader')
            os.chown(downloads, account.pw_uid, account.pw_gid)
            destination = root / digest
            if not destination.exists():
                fd = os.open(agent.root / 'host-download.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'r+') as download_lock:
                    fcntl.flock(download_lock, fcntl.LOCK_EX)
                    archive = downloads / (digest + '.' + uuid.uuid4().hex + '.tar.gz')
                    try:
                        with (agent.root / 'host-download.log').open('ab') as log:
                            subprocess.run(['runuser', '-u', 'downloader', '--', 'python3', str(downloader),
                                f'https://gradiated-prod-model-artifacts-873716897517.s3-accelerate.amazonaws.com/bundles/sha256/{digest}.tar.gz',
                                str(archive)], stdout=log, stderr=log, check=True, timeout=1800)
                        promote_archive(archive, destination, digest, base_id)
                    finally:
                        archive.unlink(missing_ok=True)
            with agent.lock:
                fd = os.open(agent.root / 'config.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'r+') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    if json.loads((agent.root / 'fence.json').read_text())['epoch'] == epoch:
                        atomic_json(root / 'pending', {'sha256': digest, 'epoch': epoch})
                        (root / 'staging-error.json').unlink(missing_ok=True)
        except Exception as error:
            try:
                atomic_json(agent.root / 'host' / 'staging-error.json', {'sha256': digest, 'error': type(error).__name__})
            except OSError:
                pass
            print(f'Host bundle staging failed: {type(error).__name__}', flush=True)
        finally:
            agent.host_staging = None
    threading.Thread(target=stage, daemon=True).start()
