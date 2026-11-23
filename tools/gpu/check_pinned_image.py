#!/usr/bin/env python3
"""Checks the pinned GPU base image against gpu-inference/pins.json in ECR.

The image tag must resolve to `imageDigest`, and the image's
/etc/gradiated/base-id must equal `hostBundle.baseId`, or a host re-imaged to
it rejects the pinned bundle. The same holds for `awsImage`, the tag or digest
AWS hosts run, when it is set. The base ID is read from the image's small layers,
so the multi-gigabyte CUDA layers are never downloaded.

Needs the AWS CLI with credentials that can read the image's ECR repository.
"""

import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
PINS = ROOT / 'infra/environments/prod/us-east-1/kubernetes/gpu-inference/pins.json'
IMAGE = re.compile(r'(?P<registry>\d{12}\.dkr\.ecr\.(?P<region>[a-z0-9-]+)\.amazonaws\.com)/(?P<repository>[a-z0-9/._-]+):(?P<tag>[A-Za-z0-9._-]+)')
AWS_IMAGE = re.compile(r'(?P<repository>[^:@]+)(:(?P<tag>[A-Za-z0-9._-]+)|@(?P<digest>sha256:[0-9a-f]{64}))')
BASE_ID = 'etc/gradiated/base-id'
# The base-id COPY makes a layer of a few hundred bytes; the largest layer
# read is far below the CUDA and apt layers.
SMALL_LAYER = 1 << 20
MANIFESTS = ', '.join([
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.v2+json',
])
GZIP_LAYERS = {
    'application/vnd.oci.image.layer.v1.tar+gzip',
    'application/vnd.docker.image.rootfs.diff.tar.gzip',
}


class Ecr:
    """The registry API of one ECR repository, authenticated through the AWS CLI."""

    def __init__(self, registry, region, repository):
        self.base = f'https://{registry}/v2/{repository}'
        token = subprocess.check_output(
            ['aws', 'ecr', 'get-authorization-token', '--region', region,
             '--query', 'authorizationData[0].authorizationToken', '--output', 'text'],
            text=True).strip()
        self.authorization = f'Basic {token}'
        # Blob downloads redirect to S3, which refuses the registry credential.
        self.opener = urllib.request.build_opener(NoRedirect)

    def _get(self, url, accept=None):
        headers = {'Authorization': self.authorization}
        if accept:
            headers['Accept'] = accept
        try:
            with self.opener.open(urllib.request.Request(url, headers=headers), timeout=60) as response:
                return response.headers, response.read()
        except urllib.error.HTTPError as error:
            if error.code not in (301, 302, 303, 307, 308):
                raise
            with urllib.request.urlopen(error.headers['Location'], timeout=60) as response:
                return response.headers, response.read()

    def manifest(self, reference):
        _, body = self._get(f'{self.base}/manifests/{reference}', MANIFESTS)
        # A manifest's digest is the SHA-256 of its bytes. ECR does not always
        # send Docker-Content-Digest.
        return 'sha256:' + hashlib.sha256(body).hexdigest(), json.loads(body)

    def blob(self, digest):
        return self._get(f'{self.base}/blobs/{digest}')[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def amd64(registry, digest, manifest):
    """The linux/amd64 image manifest, following an index if there is one."""
    if 'manifests' not in manifest:
        return manifest
    for entry in manifest['manifests']:
        platform = entry.get('platform', {})
        if platform.get('os') == 'linux' and platform.get('architecture') == 'amd64':
            return registry.manifest(entry['digest'])[1]
    raise ValueError(f'{digest} has no linux/amd64 image')


def base_id(registry, manifest):
    """The last /etc/gradiated/base-id among the image's small layers."""
    found = None
    for layer in manifest['layers']:
        if layer['size'] > SMALL_LAYER:
            continue
        if layer['mediaType'] not in GZIP_LAYERS:
            raise ValueError(f'layer {layer["digest"]} has unsupported media type {layer["mediaType"]}')
        data = gzip.decompress(registry.blob(layer['digest']))
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive.getmembers():
                if member.name.lstrip('./') == BASE_ID and member.isfile():
                    found = archive.extractfile(member).read().decode().strip()
    return found


def problems(pins, registry):
    """What is wrong with the pinned image, as messages; empty when it matches."""
    reference = IMAGE.fullmatch(pins['image'])
    digest, manifest = registry.manifest(reference['tag'])
    found = []
    if digest != pins['imageDigest']:
        found.append(f'{pins["image"]} resolves to {digest}, but pins.json pins {pins["imageDigest"]}')
        return found
    found += base_problems(pins['image'], registry, digest, manifest, pins['hostBundle']['baseId'])
    if 'awsImage' in pins:
        aws = AWS_IMAGE.fullmatch(pins['awsImage'])
        if not aws or aws['repository'] != pins['image'].split(':')[0]:
            found.append(f'awsImage {pins["awsImage"]} is not a tag or digest in {pins["image"].split(":")[0]}')
            return found
        aws_digest, aws_manifest = registry.manifest(aws['digest'] or aws['tag'])
        if aws['digest'] and aws_digest != aws['digest']:
            found.append(f'{pins["awsImage"]} resolves to {aws_digest}')
            return found
        found += base_problems(pins['awsImage'], registry, aws_digest, aws_manifest, pins['hostBundle']['baseId'])
    return found


def base_problems(image, registry, digest, manifest, expected):
    image_base = base_id(registry, amd64(registry, digest, manifest))
    if image_base is None:
        return [f'{image} has no /{BASE_ID} in a layer under {SMALL_LAYER} bytes']
    if image_base != expected:
        return [f'{image} has base ID {image_base}, but the pinned host bundle is for '
                f'{expected}; hosts on this image would reject it']
    return []


def main():
    pins = json.loads(PINS.read_text())
    reference = IMAGE.fullmatch(pins['image'])
    if not reference:
        sys.exit(f'pins.json image is not an ECR image tag: {pins["image"]}')
    registry = Ecr(reference['registry'], reference['region'], reference['repository'])
    found = problems(pins, registry)
    for problem in found:
        print(problem, file=sys.stderr)
    if found:
        sys.exit(1)
    print(f'{pins["image"]} is {pins["imageDigest"]} with base ID {pins["hostBundle"]["baseId"]}')
    if 'awsImage' in pins:
        print(f'{pins["awsImage"]} has base ID {pins["hostBundle"]["baseId"]}')


if __name__ == '__main__':
    main()
