import json
import os
from pathlib import Path
import stat
import uuid


HOST_FILES = {'host-agent.py', 'desmondd', 'base-id'}
PLATFORM_HOST_FILES = HOST_FILES | {
    'bootstrap.py', 'supervise.py', 'host_state.py', 'host_bundle.py',
    'runtime-launch', 'fetch-runtime', 'download-runtime', 'install-tailscale.py',
    'control-listener.py', 'forward-control.py', 'run-tailscale.sh',
    'start-tailscale.sh', 'run-control.sh', 'start-control.sh',
}
PLATFORM_ONLY = Path('/etc/gradiated/platform-only')


def required_host_files():
    return PLATFORM_HOST_FILES if PLATFORM_ONLY.exists() else HOST_FILES


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, value, uid=None, gid=None):
    atomic_write(path, json.dumps(value).encode(), uid, gid)


def atomic_write(path, encoded, uid=None, gid=None):
    path = Path(path)
    if path.is_symlink():
        raise OSError('State files cannot be symbolic links')
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.new')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as output:
            if uid is not None:
                os.fchown(output.fileno(), uid, gid)
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def bound_log(path, limit=32 * 1024 * 1024):
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Only regular diagnostic files may be truncated')
        if info.st_size > limit:
            os.lseek(fd, info.st_size - limit // 2, os.SEEK_SET)
            tail = os.read(fd, limit // 2)
            os.ftruncate(fd, 0)
            os.pwrite(fd, tail, 0)
    finally:
        os.close(fd)
