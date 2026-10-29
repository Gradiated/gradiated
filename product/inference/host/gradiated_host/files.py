# Modes are set explicitly: enrollment runs under Tailscale SSH's umask 077.
import os
from pathlib import Path
import uuid


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def directory(path, mode, owner):
    # Missing parents get 0755 and the same owner; existing ones are left alone.
    path = Path(path)
    if path.is_symlink():
        raise OSError(f'{path} is a symbolic link')
    if not path.parent.exists():
        directory(path.parent, 0o755, owner)
    path.mkdir(exist_ok=True)
    os.chown(path, *owner)
    os.chmod(path, mode)
    return path


def write(path, data, mode, owner):
    path = Path(path)
    if path.is_symlink():
        raise OSError(f'{path} is a symbolic link')
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.new')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            os.fchown(output.fileno(), *owner)
            os.fchmod(output.fileno(), mode)
            output.write(data if isinstance(data, bytes) else data.encode())
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def log(path):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    os.fchmod(descriptor, 0o600)
    return os.fdopen(descriptor, 'ab', buffering=0)
