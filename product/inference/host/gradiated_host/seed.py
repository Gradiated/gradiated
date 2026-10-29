import json
import shutil
import tempfile
import time
import urllib.request

import host_bundle

from . import files

LIMIT = 64 * 1024 * 1024


def fetch(url, destination, seconds=180):
    if not url.startswith('https://'):
        raise ValueError('The host bundle must be fetched over HTTPS')
    deadline = time.monotonic() + seconds
    with urllib.request.urlopen(url, timeout=30) as incoming, open(destination, 'wb') as output:
        total = 0
        while data := incoming.read(1024 * 1024):
            total += len(data)
            if total > LIMIT or time.monotonic() > deadline:
                raise ValueError('The host bundle exceeds its size or time limit')
            output.write(data)


def install(layout, release, download=fetch):
    base_id = layout.base_id.read_text().strip()
    digest = release['sha256']
    host_bundle.validate_pin({'sha256': digest, 'base_id': release['base_id']}, base_id)
    root = layout.account('root')
    files.directory(layout.state, 0o755, root)
    host = files.directory(layout.state / 'host', 0o755, root)
    destination = host / digest
    if not destination.exists():
        with tempfile.TemporaryDirectory(dir=host) as temporary:
            archive = f'{temporary}/seed.tar.gz'
            download(release['url'], archive)
            host_bundle.promote_archive(archive, destination, digest, base_id)
    # The launcher falls back to this copy when no verified bundle is selected.
    files.directory(layout.install, 0o755, root)
    recovery = layout.install / 'recovery'
    if not recovery.exists():
        staging = layout.install / 'recovery.new'
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(destination, staging, ignore=shutil.ignore_patterns('.bundle-sha256'))
        files.directory(staging, 0o755, root)
        staging.rename(recovery)
        files.sync_directory(layout.install)
    # A retried enrollment keeps the launcher and the bundle it has selected since.
    for name in ('supervise.py', 'host_state.py'):
        if not (layout.install / name).exists():
            files.write(layout.install / name, (destination / name).read_bytes(), 0o644, root)
    if not (host / 'status.json').exists():
        files.write(host / 'status.json', json.dumps({'schema': 2, 'current': digest, 'previous': '', 'trial': '',
                                                       'failed': '', 'running': ''}), 0o600, root)
    return destination
