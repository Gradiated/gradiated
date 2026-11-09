import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('kimi_draft', HERE / 'draft.py')
draft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(draft)


class DraftPackage(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        contents = {'config.json': b'{"architectures":["DFlash2DraftModel"]}', 'model.safetensors': b'synthetic-weights'}
        value = {'repository': draft.REPOSITORY, 'revision': draft.REVISION,
                 'files': [{'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                           for name, data in contents.items()]}
        manifest = root / 'draft-manifest.json'
        manifest.write_text(json.dumps(value))
        pinned = patch.object(draft, 'MANIFEST_SHA256', hashlib.sha256(manifest.read_bytes()).hexdigest())
        pinned.start()
        self.addCleanup(pinned.stop)
        return root, manifest, contents

    def package(self, manifest, destination, contents):
        def download(url, timeout):
            self.assertEqual(timeout, 120)
            prefix = f'https://huggingface.co/{draft.REPOSITORY}/resolve/{draft.REVISION}/'
            self.assertTrue(url.startswith(prefix))
            return io.BytesIO(contents[url[len(prefix):]])
        with patch.object(draft.urllib.request, 'urlopen', side_effect=download):
            return draft.package(manifest, destination)

    def test_verified_draft_is_inside_relocatable_archive(self):
        root, manifest, contents = self.fixture()
        destination = root / 'bundle' / draft.RELATIVE_PATH
        identity = self.package(manifest, destination, contents)
        relocated = root / 'relocated'
        (root / 'bundle').rename(relocated)
        self.assertEqual(draft.verify(relocated / draft.RELATIVE_PATH), identity)
        self.assertEqual(identity['revision'], draft.REVISION)
        self.assertEqual(identity['path'], 'models/kimi-dflash')
        self.assertFalse(any(path.is_symlink() for path in relocated.rglob('*')))

    def test_truncated_corrupt_and_oversized_downloads_never_publish(self):
        for payload in (b'short', b'wrong-data-bytes!', b'synthetic-weights-extra'):
            with self.subTest(payload=payload):
                root, manifest, contents = self.fixture()
                destination = root / 'bundle' / draft.RELATIVE_PATH
                with self.assertRaises(ValueError):
                    self.package(manifest, destination, contents | {'model.safetensors': payload})
                self.assertFalse(destination.exists())
                self.assertEqual(list(destination.parent.iterdir()), [])

    def test_same_size_corruption_symlink_and_extra_file_rejected(self):
        for mutation in ('same-size', 'symlink', 'extra'):
            with self.subTest(mutation=mutation):
                root, manifest, contents = self.fixture()
                destination = root / 'bundle' / draft.RELATIVE_PATH
                self.package(manifest, destination, contents)
                model = destination / 'model.safetensors'
                if mutation == 'same-size':
                    model.write_bytes(b'X' * len(contents['model.safetensors']))
                elif mutation == 'symlink':
                    outside = root / 'outside'
                    model.rename(outside)
                    model.symlink_to(outside)
                else:
                    (destination / 'unverified.json').write_text('{}')
                with self.assertRaises(ValueError):
                    draft.verify(destination)

    def test_manifest_tamper_and_existing_destination_rejected(self):
        root, manifest, contents = self.fixture()
        destination = root / 'bundle' / draft.RELATIVE_PATH
        self.package(manifest, destination, contents)
        with self.assertRaises(ValueError):
            self.package(manifest, destination, contents)
        (destination / 'manifest.json').write_bytes(manifest.read_bytes() + b'\n')
        with self.assertRaises(ValueError):
            draft.verify(destination)

    def test_unpinned_repository_and_path_escape_rejected(self):
        for field, value in (('repository', 'other/model'), ('revision', 'main'), ('path', '../outside')):
            with self.subTest(field=field):
                root, manifest, _ = self.fixture()
                data = json.loads(manifest.read_text())
                if field == 'path':
                    data['files'][0]['path'] = value
                else:
                    data[field] = value
                manifest.write_text(json.dumps(data))
                with patch.object(draft, 'MANIFEST_SHA256', hashlib.sha256(manifest.read_bytes()).hexdigest()):
                    with self.assertRaises(ValueError):
                        draft.manifest(manifest)

    def test_repository_manifest_hash_and_exact_weight_size(self):
        path = HERE.parents[1] / 'bundles/kimi-k31-pro/draft-manifest.json'
        if not path.exists():
            self.skipTest('Build manifest is not separately installed in archives')
        _, value = draft.manifest(path)
        weights = next(item for item in value['files'] if item['path'] == 'model.safetensors')
        self.assertEqual(weights['size'], 5_569_631_720)
        self.assertEqual(weights['sha256'], '1e07d2352fc44ea3967862309abeaa670faa3cf386c37adc35b8c97396f27b3f')


if __name__ == '__main__':
    unittest.main()
