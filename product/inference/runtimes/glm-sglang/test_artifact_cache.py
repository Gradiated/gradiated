import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('artifact_seed', HERE / 'artifact-cache.py')
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


class ArtifactCache(unittest.TestCase):
    def layout(self, folder):
        root, cache = folder / 'bundle', folder / 'cache'
        source = root / 'flashinfer-artifacts/pinned/include/header.h'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'verified public header')
        item = {'path': 'pinned/include/header.h', 'size': source.stat().st_size,
                'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
        (root / 'artifacts.json').write_text(json.dumps({'files': [item]}))
        return root, cache, source, item

    def test_empty_cache_is_verified_and_seeded_before_rank_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, cache, source, item = self.layout(Path(temporary))
            seed.seed(root, cache)
            self.assertEqual((cache / item['path']).read_bytes(), source.read_bytes())
            original = (cache / item['path']).stat().st_ino
            seed.seed(root, cache)
            self.assertEqual((cache / item['path']).stat().st_ino, original)

    def test_bad_cached_copy_is_replaced_only_from_verified_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, cache, source, item = self.layout(Path(temporary))
            destination = cache / item['path']; destination.parent.mkdir(parents=True)
            destination.write_bytes(b'tampered')
            seed.seed(root, cache)
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            source.write_bytes(b'unverified source')
            with self.assertRaises(ValueError): seed.seed(root, cache)

    def test_path_escape_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, cache, source, item = self.layout(Path(temporary))
            item['path'] = '../../outside'
            (root / 'artifacts.json').write_text(json.dumps({'files': [item]}))
            with self.assertRaises(ValueError): seed.seed(root, cache)


if __name__ == '__main__':
    unittest.main()
