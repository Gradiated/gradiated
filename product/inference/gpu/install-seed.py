import json
from pathlib import Path
import shutil
import tempfile
import time
import urllib.request

from host_bundle import promote_archive, validate_pin
from host_state import atomic_json, sync_directory, PLATFORM_HOST_FILES

ROOT = Path('/var/lib/gradiated-kubelet')
INSTALL = Path('/opt/gradiated/kubelet')
BASE_ID = Path('/etc/gradiated/base-id')
REQUIRED = PLATFORM_HOST_FILES


def install(release):
    base_id = BASE_ID.read_text().strip()
    validate_pin({key: release[key] for key in ('sha256', 'base_id')}, base_id)
    url = release['url']
    if not url.startswith('https://'):
        raise ValueError('Host bootstrap requires HTTPS')
    ROOT.mkdir(parents=True, exist_ok=True)
    ROOT.chmod(0o755)
    host = ROOT / 'host'
    host.mkdir(exist_ok=True)
    # Enrollment runs under Tailscale SSH's umask 077; the downloader runs
    # fetch-runtime from the bundle in here.
    host.chmod(0o755)
    digest = release['sha256']
    destination = host / digest
    if not destination.exists():
        with tempfile.TemporaryDirectory(dir=host) as temporary:
            archive = Path(temporary) / 'seed.tar.gz'
            deadline = time.monotonic() + 180
            with urllib.request.urlopen(url, timeout=30) as incoming, archive.open('wb') as output:
                total = 0
                while data := incoming.read(1024 * 1024):
                    total += len(data)
                    if total > 64 * 1024 * 1024 or time.monotonic() > deadline:
                        raise ValueError('Host archive exceeds its size limit')
                    output.write(data)
            promote_archive(archive, destination, digest, base_id)
    from supervise import verified
    if not verified(host, digest, base_id) or not REQUIRED.issubset(json.loads((destination / 'files.json').read_text())):
        raise ValueError('Host release cannot bootstrap a platform-only image')
    INSTALL.mkdir(parents=True, exist_ok=True)
    recovery = INSTALL / 'recovery'
    if recovery.exists() and not REQUIRED.issubset(path.name for path in recovery.iterdir()):
        recovery.rename(INSTALL / 'recovery.legacy')
    if not recovery.exists():
        staging = INSTALL / 'recovery.new'
        if staging.exists():shutil.rmtree(staging)
        shutil.copytree(destination, staging)
        (staging / '.bundle-sha256').unlink()
        staging.rename(recovery)
        sync_directory(INSTALL)
    for name in ('bootstrap.py', 'supervise.py', 'host_state.py'):
        shutil.copy2(recovery / name, INSTALL / name)
    atomic_json(host / 'status.json', {'schema': 2, 'current': digest, 'previous': '',
                                     'trial': '', 'failed': '', 'running': ''})
    pointer = ROOT / 'control-program'
    temporary = ROOT / 'control-program.new'
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(recovery / 'forward-control.py')
    temporary.replace(pointer)
    sync_directory(ROOT)
    return recovery / 'bootstrap.py'
