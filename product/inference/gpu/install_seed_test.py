import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location('seed', Path(__file__).with_name('install-seed.py'))
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


class SeedTests(unittest.TestCase):
    def archive(self, missing=None):
        files = {name: name.encode() for name in seed.REQUIRED | {'base-id'}}
        files['base-id'] = b'test-base'
        files.pop(missing, None)
        files['files.json'] = json.dumps({name: hashlib.sha256(data).hexdigest()
                                         for name, data in files.items()}).encode()
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w:gz') as archive:
            for name, data in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                member.mode = 0o755 if name in ('runtime-launch', 'desmondd', 'fetch-runtime') else 0o644
                archive.addfile(member, io.BytesIO(data))
        return output.getvalue()

    def install(self, root, archive, digest=None):
        base = root / 'base-id'
        base.write_text('test-base')
        with patch.object(seed, 'ROOT', root / 'state'), patch.object(seed, 'INSTALL', root / 'install'), \
                patch.object(seed, 'BASE_ID', base), patch.object(seed.urllib.request, 'urlopen', return_value=io.BytesIO(archive)):
            return seed.install({'sha256': digest or hashlib.sha256(archive).hexdigest(),
                                 'base_id': 'test-base', 'url': 'https://artifacts.example/seed'})

    def test_platform_enrollment_creates_verified_current_and_independent_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.archive()
            digest = hashlib.sha256(archive).hexdigest()
            bootstrap = self.install(root, archive)
            self.assertEqual(bootstrap, root / 'install/recovery/bootstrap.py')
            self.assertFalse((bootstrap.parent / '.bundle-sha256').exists())
            self.assertEqual(json.loads((root / 'state/host/status.json').read_text())['current'], digest)
            self.assertEqual((root / 'state/control-program').resolve(), bootstrap.parent / 'forward-control.py')
            (root / 'state/host' / digest / 'host-agent.py').write_text('corrupt active copy')
            self.assertEqual((bootstrap.parent / 'host-agent.py').read_text(), 'host-agent.py')
            with self.assertRaises(ValueError):self.install(root, archive)

    def test_host_bundles_stay_reachable_by_the_downloader_under_a_private_umask(self):
        previous = os.umask(0o077)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.install(root, self.archive())
                self.assertEqual(stat.S_IMODE((root / 'state/host').stat().st_mode), 0o755)
        finally:
            os.umask(previous)

    def test_checksum_failure_never_installs_or_activates_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):self.install(root, self.archive(), 'a' * 64)
            self.assertFalse((root / 'install').exists())
            self.assertFalse((root / 'state/host/status.json').exists())

    def test_legacy_host_archive_cannot_bootstrap_new_platform(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):self.install(root, self.archive(missing='runtime-launch'))
            self.assertFalse((root / 'state/host/status.json').exists())


if __name__ == '__main__':unittest.main()
