"""Builds what the gpu-fleet end-to-end rejoin test runs: the GPU base image with
only nvidia-smi faked, the host bundle it enrolls with, and TLS material for the
test's control server and artifact store.

Usage: python3 e2e_image.py <output directory>
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from enrollment_test import CONTEXT, GPU_BASE, UBUNTU, docker, host_bundle_stage
from image_build import build_image

IMAGE = 'gradiated-gpu-base-e2e'


def certificates(output):
    # One test CA signs the control server's and the artifact store's certificates.
    def openssl(*args):
        subprocess.run(['openssl', *args], check=True, capture_output=True)

    openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2', '-subj', '/CN=gpu-fleet-e2e-ca',
            '-keyout', str(output / 'ca.key'), '-out', str(output / 'ca.pem'))
    for name in ('headscale', 'artifacts'):
        with tempfile.TemporaryDirectory() as directory:
            request, extensions = Path(directory) / 'request.csr', Path(directory) / 'san.ext'
            extensions.write_text(f'subjectAltName=DNS:{name}\n')
            openssl('req', '-newkey', 'rsa:2048', '-nodes', '-subj', f'/CN={name}',
                    '-keyout', str(output / f'{name}.key'), '-out', str(request))
            openssl('x509', '-req', '-in', str(request), '-CA', str(output / 'ca.pem'),
                    '-CAkey', str(output / 'ca.key'), '-CAcreateserial', '-days', '2',
                    '-extfile', str(extensions), '-out', str(output / f'{name}.pem'))
        (output / f'{name}.key').chmod(0o644)
    (output / 'ca.key').unlink()


def main(output):
    output.mkdir(parents=True, exist_ok=True)
    certificates(output)
    staging = CONTEXT / 'images' / 'gpu-base' / 'tests' / '.e2e-ca.pem'
    shutil.copyfile(output / 'ca.pem', staging)
    try:
        dockerfile = (GPU_BASE / 'Dockerfile').read_text().splitlines()
        if not dockerfile[0].startswith('FROM nvidia/cuda:'):
            raise AssertionError('Unexpected GPU base parent image')
        dockerfile[0:1] = [f'FROM {UBUNTU}',
                           'RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates']
        entrypoint = dockerfile.pop()
        dockerfile += [
            # The real Tailscale client and gradiated-host; only the GPUs are faked.
            'COPY --chmod=755 images/gpu-base/tests/fake-nvidia-smi /usr/bin/nvidia-smi',
            'COPY images/gpu-base/tests/.e2e-ca.pem /usr/local/share/ca-certificates/gpu-fleet-e2e.crt',
            'RUN update-ca-certificates',
            # Lets gradiated-host join the test's control server; production images never have it.
            'RUN touch /etc/gradiated/test-control-server',
            'COPY --from=host-bundle /runtime.tar.gz /opt/e2e/host-bundle.tar.gz',
            entrypoint,
        ]
        build_image(IMAGE, host_bundle_stage() + dockerfile, CONTEXT)
    finally:
        staging.unlink(missing_ok=True)

    container = docker('create', '--platform', 'linux/amd64', IMAGE).stdout.strip()
    try:
        bundle = output / 'host-bundle.tar.gz'
        docker('cp', f'{container}:/opt/e2e/host-bundle.tar.gz', str(bundle))
        base_id = docker('run', '--rm', '--platform', 'linux/amd64', '--entrypoint', 'cat', IMAGE,
                         '/etc/gradiated/base-id').stdout.strip()
    finally:
        docker('rm', container)
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (output / 'artifacts').mkdir(exist_ok=True)
    bundle.rename(output / 'artifacts' / f'{digest}.tar.gz')
    (output / 'manifest.json').write_text(json.dumps(
        {'image': IMAGE, 'hostBundle': {'sha256': digest, 'baseId': base_id}}, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'image': IMAGE, 'sha256': digest, 'baseId': base_id}))


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
