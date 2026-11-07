import hashlib
import importlib.metadata
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import re
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('autotune_seed', HERE / 'autotune-seed.py')
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)
DIRECTORY = 'flashinfer/autotune/0.7.2/sm103/0123456789abcdef'


class AutotuneSeed(unittest.TestCase):
    def layout(self, folder, data=b'{"_metadata": {}}', ranks=2):
        root, cache = folder / 'autotune', folder / 'cache'
        (root / 'sm103').mkdir(parents=True)
        (root / 'sm103/key.json').write_bytes(data)
        item = {'source': 'sm103/key.json', 'directory': DIRECTORY, 'ranks': ranks,
                'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        (root / 'manifest.json').write_text(json.dumps({'files': [item]}))
        return root, cache, item

    def test_empty_cache_gets_one_identical_file_per_rank(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, cache, _ = self.layout(Path(temporary))
            self.assertEqual(seed.seed(root, cache), 1)
            files = sorted((cache / DIRECTORY).iterdir())
            self.assertEqual([path.name for path in files], ['rank_tp0_pp0_dp0.json', 'rank_tp1_pp0_dp0.json'])
            self.assertTrue(all(path.read_bytes() == b'{"_metadata": {}}' for path in files))
            self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600 for path in files))
            self.assertEqual(seed.seed(root, cache), 0)

    def test_host_results_are_never_replaced_even_for_one_rank(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, cache, _ = self.layout(Path(temporary))
            (cache / DIRECTORY).mkdir(parents=True)
            (cache / DIRECTORY / 'rank_tp1_pp0_dp0.json').write_bytes(b'host tuned')
            self.assertEqual(seed.seed(root, cache), 0)
            self.assertEqual(sorted(path.name for path in (cache / DIRECTORY).iterdir()), ['rank_tp1_pp0_dp0.json'])
            self.assertEqual((cache / DIRECTORY / 'rank_tp1_pp0_dp0.json').read_bytes(), b'host tuned')

    def test_unverified_or_escaping_seed_fails_and_entrypoint_still_succeeds(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, cache, item = self.layout(Path(temporary))
            (root / 'sm103/key.json').write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                seed.seed(root, cache)
            self.assertFalse((cache / DIRECTORY).exists())
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(seed.main([str(root), str(cache)]), 0)
            self.assertIn('skipped (ValueError)', output.getvalue())
            for field, value in (('directory', '../../outside'), ('source', '../../outside.json'), ('ranks', 0)):
                (root / 'manifest.json').write_text(json.dumps({'files': [{**item, field: value}]}))
                with self.subTest(field=field), self.assertRaises((ValueError, OSError)):
                    seed.seed(root, cache)

    def test_missing_seed_never_blocks_startup(self):
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            self.assertEqual(seed.main([str(Path(temporary) / 'absent'), str(Path(temporary) / 'cache')]), 0)

    def test_bundled_seeds_verify_and_match_pinned_libraries(self):
        root = HERE / 'autotune'
        manifest = json.loads((root / 'manifest.json').read_text())
        requirements = HERE.parents[1] / 'bundles/glm-5-3-flash-sglang/requirements.txt'
        if requirements.is_file():
            text = requirements.read_text()
            flashinfer = re.search(r'flashinfer_python-([0-9.]+)-py3', text)[1]
            cutlass = re.search(r'nvidia_cutlass_dsl-([0-9.]+)-py3', text)[1]
        else:
            # Inside the built bundle, compare with the installed libraries instead.
            try:
                flashinfer = importlib.metadata.version('flashinfer-python')
                cutlass = importlib.metadata.version('nvidia-cutlass-dsl')
            except importlib.metadata.PackageNotFoundError:
                self.skipTest('Neither pinned requirements nor installed FlashInfer are available')
        self.assertTrue(manifest['files'])
        for item in manifest['files']:
            with self.subTest(source=item['source']):
                data = (root / item['source']).read_bytes()
                self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (item['size'], item['sha256']))
                metadata = json.loads(data)['_metadata']
                # FlashInfer ignores a seed tuned with other libraries. Refresh the
                # seeds from a host running the new bundle, or delete them.
                self.assertEqual(metadata['flashinfer_version'], flashinfer)
                self.assertIn(f'nvidia-cutlass-dsl=={cutlass}', metadata['cutlass_dsl_version'])
                self.assertTrue(item['directory'].startswith(f'flashinfer/autotune/{flashinfer}/sm103/'))
                self.assertEqual(metadata['gpu'], 'NVIDIA B300 SXM6 AC')
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(seed.seed(root, Path(temporary)), len(manifest['files']))


if __name__ == '__main__':
    unittest.main()
