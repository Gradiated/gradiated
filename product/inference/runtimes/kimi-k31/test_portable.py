import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / 'bundles/kimi-k31-pro/portable.py'
if SOURCE.exists():
    spec = importlib.util.spec_from_file_location('kimi_portable', SOURCE)
    portable = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(portable)
else:
    portable = None


@unittest.skipIf(portable is None, 'Packaging source is not installed in runtime archives')
class Portability(unittest.TestCase):
    def test_absolute_prebuilt_cubin_link_is_relative_and_resolves_after_relocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'python/lib/cubins/hashed/header.h'
            target.parent.mkdir(parents=True)
            target.write_text('verified header')
            link = root / 'python/lib/cubins/export/header.h'
            link.parent.mkdir()
            link.symlink_to('/opt/sglang/lib/cubins/hashed/header.h')
            portable.relocate_links(root, '/opt/python/cpython-3.12')
            self.assertFalse(link.readlink().is_absolute())
            self.assertEqual(link.read_text(), 'verified header')

    def test_unknown_absolute_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'external').symlink_to('/private/nonportable')
            with self.assertRaises(ValueError):
                portable.relocate_links(root, '/opt/python/cpython-3.12')


if __name__ == '__main__':
    unittest.main()
