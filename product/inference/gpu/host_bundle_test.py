import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import threading
from types import SimpleNamespace
import tarfile
import io
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_bundle as bundle
spec = importlib.util.spec_from_file_location('launcher', Path(__file__).with_name('supervise.py'))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class HostBundleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.base_id = 'test-base'

    def tearDown(self):
        self.directory.cleanup()

    def make_bundle(self, digest):
        path = self.root / digest
        path.mkdir()
        for name in bundle.FILES:
            (path / name).write_text(self.base_id if name == 'base-id' else name)
        (path / 'files.json').write_text(json.dumps({name: hashlib.sha256((path / name).read_bytes()).hexdigest()
                                                   for name in bundle.FILES}))
        (path / '.bundle-sha256').write_text(digest)
        return path

    def install(self):
        self.make_bundle('a' * 64)
        launcher.select(self.root, 'current', 'a' * 64)
        return launcher.Launcher(self.root, self.root, self.base_id)

    def test_bad_checksum_or_base_never_runs(self):
        path = self.make_bundle('a' * 64)
        self.assertTrue(launcher.verified(self.root, path.name, self.base_id))
        self.assertFalse(launcher.verified(self.root, path.name, 'other-base'))
        (path / 'host-agent.py').write_text('corrupted')
        self.assertFalse(launcher.verified(self.root, path.name, self.base_id))
        with self.assertRaises(ValueError):
            bundle.promote(path, self.root / ('b' * 64), path.name, self.base_id)

    def test_staging_copies_verified_files_and_rejects_symlinks(self):
        path = self.make_bundle('a' * 64)
        destination = self.root / 'promoted' / path.name
        destination.parent.mkdir()
        bundle.promote(path, destination, path.name, self.base_id)
        self.assertTrue(launcher.verified(destination.parent, path.name, self.base_id))
        (path / 'desmondd').unlink()
        (path / 'desmondd').symlink_to(path / 'host-agent.py')
        with self.assertRaises(ValueError):
            bundle.promote(path, self.root / 'other', path.name, self.base_id)

    def test_pending_update_rolls_back_on_timeout_and_will_not_retry(self):
        runner = self.install()
        self.make_bundle('b' * 64)
        launcher.write(self.root / 'pending', {'sha256': 'b' * 64})
        self.assertTrue(runner.update())
        self.assertEqual(runner.previous, 'a' * 64)
        self.assertTrue(runner.check(False, False, runner.deadline + 1))
        self.assertEqual(runner.current, 'a' * 64)
        self.assertEqual(runner.state['failed'], 'b' * 64)
        launcher.write(self.root / 'pending', {'sha256': 'b' * 64})
        self.assertFalse(runner.update())

    def test_interrupted_trial_is_checked_again_and_crash_loop_rolls_back(self):
        runner = self.install()
        self.make_bundle('b' * 64)
        launcher.write(self.root / 'pending', {'sha256': 'b' * 64})
        runner.update()
        runner = launcher.Launcher(self.root, self.root, self.base_id)
        self.assertTrue(runner.trial)
        runner.check(True, False)
        self.assertFalse(runner.trial)
        for stamp in (1, 2, 3):
            runner.check(False, True, stamp)
        self.assertEqual(runner.current, 'a' * 64)

    def test_no_previous_bundle_falls_back_to_base(self):
        runner = launcher.Launcher(self.root, self.root, self.base_id)
        self.make_bundle('a' * 64)
        launcher.write(self.root / 'pending', {'sha256': 'a' * 64})
        runner.update()
        runner.check(False, False, runner.deadline)
        self.assertEqual(runner.current, '')
        self.assertFalse((self.root / 'current').exists())

    def test_corrupt_current_uses_previous(self):
        self.make_bundle('a' * 64)
        current = self.make_bundle('b' * 64)
        launcher.select(self.root, 'current', current.name)
        launcher.select(self.root, 'previous', 'a' * 64)
        (current / 'host_state.py').write_text('broken')
        runner = launcher.Launcher(self.root, self.root, self.base_id)
        self.assertEqual(runner.current, 'a' * 64)

    def test_cleanup_keeps_code_used_by_a_live_worker(self):
        runner = self.install()
        for letter in 'bcde':
            path = self.make_bundle(letter * 64)
            os.utime(path, (ord(letter), ord(letter)))
        worker = self.root / ('b' * 64) / 'host-agent.py'
        worker.write_text('import time; time.sleep(60)')
        manifest = worker.with_name('files.json')
        hashes = json.loads(manifest.read_text())
        hashes['host-agent.py'] = hashlib.sha256(worker.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(hashes))
        process = subprocess.Popen([sys.executable, str(worker)])
        try:
            runner.cleanup()
            self.assertTrue(worker.exists())
            self.assertTrue((self.root / ('e' * 64)).exists())
            self.assertFalse((self.root / ('c' * 64)).exists())
        finally:
            process.terminate()
            process.wait(timeout=5)

    def test_archive_is_verified_again_after_downloader_access(self):
        source = self.make_bundle('a' * 64)
        archive = self.root / 'download.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            for path in source.iterdir():
                if path.name != '.bundle-sha256':
                    output.add(path, arcname='./' + path.name)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        bundle.promote_archive(archive, self.root / digest, digest, self.base_id)
        self.assertTrue(launcher.verified(self.root, digest, self.base_id))
        archive.write_bytes(b'attacker modified the downloaded archive')
        with self.assertRaises(ValueError):
            bundle.promote_archive(archive, self.root / ('b' * 64), digest, self.base_id)

    def test_archive_cannot_escape_root_owned_tree(self):
        archive = self.root / 'download.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            member = tarfile.TarInfo('../escaped')
            member.size = 4
            output.addfile(member, io.BytesIO(b'evil'))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            bundle.promote_archive(archive, self.root / digest, digest, self.base_id)
        self.assertFalse((self.root / 'escaped').exists())

    def test_stale_stage_cannot_request_an_update(self):
        source = self.make_bundle('a' * 64)
        archive = self.root / 'download.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            for path in source.iterdir():
                if path.name != '.bundle-sha256':
                    output.add(path, arcname='./' + path.name)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        host_root = self.root / 'host'
        host_root.mkdir()
        (host_root / 'status.json').write_text('{}')
        (self.root / 'fence.json').write_text('{"epoch": 2}')
        base_path = self.root / 'base-id'
        base_path.write_text(self.base_id)
        agent = SimpleNamespace(root=self.root, lock=threading.RLock())
        def download(command, **kwargs):
            Path(command[-1]).write_bytes(archive.read_bytes())
        synchronous = lambda target, **kwargs: SimpleNamespace(start=target)
        account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
        with patch.object(bundle, 'BASE_ID', base_path), patch.object(bundle.pwd, 'getpwnam', return_value=account), \
                patch.object(bundle.subprocess, 'run', side_effect=download), \
                patch.object(bundle.threading, 'Thread', side_effect=synchronous):
            bundle.stage_host(agent, {'sha256': digest, 'base_id': self.base_id}, 1)
            self.assertFalse((host_root / 'pending').exists())
            bundle.stage_host(agent, {'sha256': digest, 'base_id': self.base_id}, 2)
            self.assertEqual(json.loads((host_root / 'pending').read_text())['sha256'], digest)

    def test_real_broken_agent_rolls_back_and_preserves_independent_worker(self):
        self.install()
        good = self.root / ('a' * 64) / 'host-agent.py'
        ready = self.root / 'ready'
        good.write_text('import pathlib,os,time; pathlib.Path(' + repr(str(ready)) + ').write_text(str(os.getpid())); time.sleep(60)')
        broken = self.make_bundle('b' * 64) / 'host-agent.py'
        broken.write_text('raise SystemExit(13)')
        for path in (good, broken):
            manifest = path.with_name('files.json')
            hashes = json.loads(manifest.read_text())
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest.write_text(json.dumps(hashes))
        launcher.write(self.root / 'pending', {'sha256': 'b' * 64})
        code = ('import importlib.util; s=importlib.util.spec_from_file_location("launcher", ' +
                repr(str(Path(launcher.__file__))) + '); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); ' +
                'root=m.Path(' + repr(str(self.root)) + '); original=m.Launcher; ' +
                'm.Launcher=lambda: original(root,root,"test-base"); m.ROOT=root; ' +
                'm.ping=lambda digest: digest==' + repr('a' * 64) + '; m.main()')
        worker = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        supervisor = subprocess.Popen([sys.executable, '-c', code])
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                state = json.loads((self.root / 'status.json').read_text())
                if state.get('failed') == 'b' * 64 and state['current'] == 'a' * 64 and ready.exists():
                    break
                time.sleep(.1)
            else:
                self.fail('Broken agent did not roll back')
            self.assertIsNone(worker.poll())
            self.assertIsNone(supervisor.poll())
        finally:
            supervisor.terminate()
            supervisor.wait(timeout=10)
            worker.terminate()
            worker.wait(timeout=5)

    def test_invalid_pin_rejects_before_download(self):
        for pin in ({'sha256': '../escape', 'base_id': self.base_id},
                    {'sha256': 'a' * 64, 'base_id': 'other'}):
            with self.assertRaises(ValueError):
                bundle.validate_pin(pin, self.base_id)


if __name__ == '__main__':
    unittest.main()
