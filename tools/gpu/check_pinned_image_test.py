import gzip
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import unittest

spec = importlib.util.spec_from_file_location('check_pinned_image', Path(__file__).with_name('check_pinned_image.py'))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

IMAGE = '873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/inference:gpu-base-inputs-' + 'c' * 64
GZIP = 'application/vnd.oci.image.layer.v1.tar+gzip'


def layer(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return gzip.compress(buffer.getvalue())


class FakeRegistry:
    """An image whose layers are the given file sets, plus one large layer."""

    def __init__(self, *layers, large=check.SMALL_LAYER + 1, index=False):
        self.blobs = {}
        entries = [{'mediaType': GZIP, 'digest': 'sha256:' + 'f' * 64, 'size': large}]
        for files in layers:
            data = layer(files)
            digest = 'sha256:' + hashlib.sha256(data).hexdigest()
            self.blobs[digest] = data
            entries.append({'mediaType': GZIP, 'digest': digest, 'size': len(data)})
        self.image = {'layers': entries}
        self.manifests = {'sha256:' + 'a' * 64: self.image}
        if index:
            self.top = {'manifests': [
                {'digest': 'sha256:' + 'b' * 64, 'platform': {'os': 'linux', 'architecture': 'arm64'}},
                {'digest': 'sha256:' + 'a' * 64, 'platform': {'os': 'linux', 'architecture': 'amd64'}},
            ]}
        else:
            self.top = self.image
        self.read = []

    def manifest(self, reference):
        if reference.startswith('sha256:'):
            return reference, self.manifests[reference]
        return 'sha256:' + 'd' * 64, self.top

    def blob(self, digest):
        self.read.append(digest)
        return self.blobs[digest]


def pins(digest='sha256:' + 'd' * 64, base='ubuntu24-cuda13-amd64-v3'):
    return {'image': IMAGE, 'imageDigest': digest, 'hostBundle': {'sha256': 'e' * 64, 'baseId': base}}


class CheckPinnedImageTest(unittest.TestCase):
    def test_accepts_a_matching_digest_and_base_id(self):
        registry = FakeRegistry({'etc/gradiated/platform-only': b''},
                                {'etc/gradiated/base-id': b'ubuntu24-cuda13-amd64-v3\n'})
        self.assertEqual(check.problems(pins(), registry), [])
        # The large layer is never downloaded.
        self.assertNotIn('sha256:' + 'f' * 64, registry.read)

    def test_follows_an_index_to_the_amd64_image(self):
        registry = FakeRegistry({'etc/gradiated/base-id': b'ubuntu24-cuda13-amd64-v3\n'}, index=True)
        self.assertEqual(check.problems(pins(), registry), [])

    def test_rejects_a_tag_that_resolves_to_another_digest(self):
        registry = FakeRegistry({'etc/gradiated/base-id': b'ubuntu24-cuda13-amd64-v3\n'})
        [problem] = check.problems(pins(digest='sha256:' + '9' * 64), registry)
        self.assertIn('resolves to sha256:' + 'd' * 64, problem)

    def test_rejects_an_image_and_bundle_on_different_bases(self):
        registry = FakeRegistry({'etc/gradiated/base-id': b'ubuntu24-cuda13-amd64-v2\n'})
        [problem] = check.problems(pins(), registry)
        self.assertIn('has base ID ubuntu24-cuda13-amd64-v2', problem)

    def test_uses_the_last_layer_that_writes_the_base_id(self):
        registry = FakeRegistry({'etc/gradiated/base-id': b'ubuntu24-cuda13-amd64-v2\n'},
                                {'./etc/gradiated/base-id': b'ubuntu24-cuda13-amd64-v3\n'})
        self.assertEqual(check.problems(pins(), registry), [])

    def test_rejects_an_image_without_a_base_id(self):
        registry = FakeRegistry({'etc/hostname': b'x'})
        [problem] = check.problems(pins(), registry)
        self.assertIn('has no /etc/gradiated/base-id', problem)


if __name__ == '__main__':
    unittest.main()
