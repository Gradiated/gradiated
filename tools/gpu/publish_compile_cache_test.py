import importlib.util
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('publish', Path(__file__).with_name('publish-compile-cache.py'))
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)


class CompileCacheArchive(unittest.TestCase):
    def cache(self, folder):
        cache = folder / 'cache'
        (cache / 'glm-sglang/jit/build').mkdir(parents=True)
        (cache / 'glm-sglang/qualification').mkdir()
        (cache / 'triton/ab').mkdir(parents=True)
        (cache / 'gradiated').mkdir()
        kernel = cache / 'glm-sglang/jit/build/kernel.so'
        kernel.write_bytes(b'so'); kernel.chmod(0o700)
        tactics = cache / 'triton/ab/tactics.json'
        tactics.write_bytes(b'{}'); tactics.chmod(0o600)
        (cache / 'glm-sglang/qualification/record.json').write_text('{}')
        (cache / 'triton/ab/escape').symlink_to('/etc/passwd')
        os.utime(kernel, (1000, 1000))
        return cache

    def test_archive_keeps_timestamps_and_readable_modes_without_links_or_host_records(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            cache = self.cache(folder)
            archive = publish.package(folder / 'cache.tar.gz', ['glm-sglang', 'triton'], cache=cache)
            self.assertEqual(publish.inspect(archive), ['glm-sglang', 'triton'])
            with tarfile.open(archive, 'r:gz') as opened:
                members = {member.name: member for member in opened}
            self.assertEqual(members['glm-sglang/jit/build/kernel.so'].mtime, 1000)
            self.assertEqual(members['glm-sglang/jit/build/kernel.so'].mode, 0o755)
            self.assertEqual(members['triton/ab/tactics.json'].mode, 0o644)
            self.assertNotIn('triton/ab/escape', members)
            self.assertFalse(any('qualification' in name for name in members))
            self.assertTrue(all(member.uid == 0 and member.gid == 0 for member in members.values()))
            again = publish.package(folder / 'again.tar.gz', ['triton', 'glm-sglang'], cache=cache)
            self.assertEqual(Path(again).read_bytes(), Path(archive).read_bytes())
            for directories in ([], ['gradiated'], ['../escape'], ['missing']):
                with self.subTest(directories=directories), self.assertRaises(ValueError):
                    publish.package(folder / 'bad.tar.gz', directories, cache=cache)

    def test_inspection_rejects_entries_a_host_must_not_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name, kind, mode in (('../escape', tarfile.REGTYPE, 0o644), ('/abs', tarfile.REGTYPE, 0o644),
                                     ('triton/link', tarfile.SYMTYPE, 0o644), ('triton/private', tarfile.REGTYPE, 0o600),
                                     ('gradiated/lock', tarfile.REGTYPE, 0o644), ('x/qualification/r', tarfile.REGTYPE, 0o644)):
                with self.subTest(name=name):
                    path = folder / 'bad.tar.gz'
                    with tarfile.open(path, 'w:gz') as archive:
                        info = tarfile.TarInfo(name); info.type, info.mode = kind, mode
                        archive.addfile(info)
                    with self.assertRaises(ValueError):
                        publish.inspect(path)

    def test_packaging_loads_from_a_lone_copy_on_a_host(self):
        # A copy at /root/publish-compile-cache.py has no repository above it.
        source = Path(__file__).with_name('publish-compile-cache.py').read_text()
        namespace = {'__file__': '/publish-compile-cache.py', '__name__': 'lone'}
        exec(compile(source, '/publish-compile-cache.py', 'exec'), namespace)
        self.assertTrue(callable(namespace['package']))

    def test_pin_adds_the_cache_for_the_pinned_base_only_to_named_runtimes(self):
        runtimes = {'a' * 64: {'bundles': {'base': 'b' * 64}}, 'c' * 64: {'bundles': {'base': 'd' * 64}}}
        updated = publish.pin(runtimes, ['a' * 64], 'base', 'e' * 64)
        self.assertEqual(updated['a' * 64]['compile_caches'], {'base': 'e' * 64})
        self.assertNotIn('compile_caches', updated['c' * 64])
        self.assertNotIn('compile_caches', runtimes['a' * 64])
        for keys, base in ((['f' * 64], 'base'), (['a' * 64], 'other')):
            with self.subTest(keys=keys, base=base), self.assertRaises(ValueError):
                publish.pin(runtimes, keys, base, 'e' * 64)


if __name__ == '__main__':
    unittest.main()
