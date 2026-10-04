#!/usr/bin/env python3
"""Install pinned Nomad base tools on an idle Ubuntu host without resetting its pod."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--image', required=True, help='Configured immutable nomad-base inputs tag')
parser.add_argument('--digest', required=True, help='Verified ECR image sha256 digest')
parser.add_argument('--host', required=True)
parser.add_argument('--port', required=True, type=int)
parser.add_argument('--key', required=True)
parser.add_argument('--known-hosts', required=True)
args = parser.parse_args()
if not args.digest.startswith('sha256:') or len(args.digest) != 71:
    parser.error('A sha256 image digest is required')
reference = args.image.rsplit(':', 1)[0] + '@' + args.digest
sources = (
    '/opt/gradiated/bin', '/opt/nomad/plugins', '/etc/nomad/client.hcl',
    '/etc/gradiated/base-id', '/etc/gradiated/runtime-proxy.conf.template',
    '/usr/local/bin/nomad', '/usr/local/bin/s5cmd', '/usr/bin/bsdtar', '/usr/bin/curl',
)
remote = r'''
set -euo pipefail
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 && $(uname -m) == x86_64 ]]
command -v python3 >/dev/null
python3 --version >/dev/null
! pgrep -x nomad >/dev/null
! test -f /etc/nomad/node.hcl
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
tar -xf - -C "$stage"
for binary in opt/gradiated/bin/runtime-launch opt/gradiated/bin/desmondd usr/bin/bsdtar usr/bin/curl; do
  dependencies=$(ldd "$stage/$binary")
  [[ "$dependencies" != *'not found'* ]]
done
"$stage/usr/local/bin/nomad" version >/dev/null
"$stage/usr/local/bin/s5cmd" version >/dev/null
for spec in runtime:10001 nomad:10002 downloader:10003 desmond:10004; do
  user=${spec%:*}; uid=${spec#*:}
  id "$user" >/dev/null 2>&1 || useradd --uid "$uid" --create-home --shell /usr/sbin/nologin "$user"
  [[ $(id -u "$user") == "$uid" ]]
done
install -d -m 700 -o nomad -g nomad /etc/nomad/tls /var/lib/nomad
install -d -m 755 -o nomad -g nomad /var/lib/nomad-alloc /var/lib/alloc_mounts
runuser -u runtime -- mkdir -p /workspace/gradiated/model-cache
cp -a "$stage/opt/." /opt/
cp -a "$stage/usr/." /usr/
install -d -m 700 -o downloader -g downloader /var/cache/gradiated/runtime-bundles
install -d /etc/gradiated /etc/nomad
cp -a "$stage/etc/nomad/client.hcl" /etc/nomad/client.hcl
cp -a "$stage/etc/gradiated/." /etc/gradiated/
chmod 600 /etc/gradiated/installed-base.json
printf 'Pinned base tools installed; no workloads started or provider settings changed.\n'
'''
with tempfile.TemporaryDirectory(prefix='nomad-host-tools-') as directory:
    root = Path(directory)
    container = subprocess.check_output(['docker', 'create', reference], text=True).strip()
    try:
        for source in sources:
            target = root / source.lstrip('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['docker', 'cp', container + ':' + source, str(target)], check=True)
    finally:
        subprocess.run(['docker', 'rm', container], check=True, stdout=subprocess.DEVNULL)
    files = {'/' + str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob('*') if p.is_file()}
    (root / 'etc/gradiated/installed-base.json').write_text(json.dumps({
        'image': args.image, 'digest': args.digest, 'files': files,
    }))
    archive = root / 'tools.tar'
    with tarfile.open(archive, 'w') as bundle:
        for name in ('opt', 'usr', 'etc'):
            bundle.add(root / name, arcname=name)
    with archive.open('rb') as bundle:
        subprocess.run([
            'ssh', '-i', args.key, '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile=' + args.known_hosts,
            '-p', str(args.port), 'root@' + args.host,
            'bash -c ' + "'" + remote.replace("'", "'\\''") + "'",
        ], stdin=bundle, check=True)
