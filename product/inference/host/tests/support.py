import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile

HOST = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HOST), str(HOST.parent / 'gpu')]

from gradiated_host.paths import Layout  # noqa: E402

BASE_ID = 'test-base'


class TestLayout(Layout):
    """Every account is the current user, so tests run unprivileged."""

    def account(self, name):
        return os.getuid(), os.getgid()


def temporary_root(test):
    # Short paths: Unix socket names are limited to about 100 bytes.
    directory = tempfile.TemporaryDirectory(dir='/tmp', prefix='gh-')
    test.addCleanup(directory.cleanup)
    root = Path(directory.name)
    layout = TestLayout(root)
    for path in (layout.etc, layout.tailscale_state, layout.tailscale_bin, layout.logs, layout.install):
        path.mkdir(parents=True, exist_ok=True)
    layout.base_id.write_text(BASE_ID + '\n')
    return layout


def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)
    return path


def host_bundle(base_id=BASE_ID):
    """A host bundle archive and its digest, shaped like the published one."""
    contents = {'host-agent.py': b'print("agent")\n', 'desmondd': b'#!/bin/sh\n', 'base-id': base_id.encode() + b'\n',
                'supervise.py': b'print("launcher")\n', 'host_state.py': b'STATE = 1\n'}
    contents['files.json'] = json.dumps({name: hashlib.sha256(data).hexdigest()
                                         for name, data in contents.items()}).encode()
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        for name, data in contents.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o755 if name == 'desmondd' else 0o644
            archive.addfile(info, io.BytesIO(data))
    data = output.getvalue()
    return data, hashlib.sha256(data).hexdigest()


def mode(path):
    return Path(path).stat().st_mode & 0o7777
