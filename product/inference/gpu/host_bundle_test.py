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
        self.root = Path(self.directory.name) / 'host'
        self.root.mkdir()
        self.base_id = 'test-base'

    def tearDown(self):
        self.directory.cleanup()

    def make_bundle(self, digest):
        path = self.root / digest
        path.mkdir()
        for name in bundle.required_host_files() | {'host_state.py', 'host_bundle.py'}:
            (path / name).write_text(self.base_id if name == 'base-id' else name)
        (path / 'files.json').write_text(json.dumps({name: hashlib.sha256((path / name).read_bytes()).hexdigest()
                                                   for name in bundle.required_host_files() | {'host_state.py', 'host_bundle.py'}}))
        (path / '.bundle-sha256').write_text(digest)
        return path

    def install(self):
        self.make_bundle('a' * 64)
        launcher.write(self.root / 'status.json', {'schema': 2, 'current': 'a' * 64, 'previous': '', 'trial': ''})
        return launcher.Launcher(self.root, self.root, self.base_id)

    def test_platform_only_staging_and_launcher_reject_legacy_same_base_bundle(self):
        import host_state
        platform = self.root / 'platform-only'
        platform.touch()
        with patch.object(host_state, 'PLATFORM_ONLY', platform):
            path = self.make_bundle('a' * 64)
            self.assertTrue(launcher.verified(self.root, path.name, self.base_id))
            for tool in ('runtime-launch', 'fetch-runtime', 'download-runtime'):
                contents = (path / tool).read_bytes()
                hashes = json.loads((path / 'files.json').read_text())
                (path / tool).unlink()
                hashes.pop(tool)
                (path / 'files.json').write_text(json.dumps(hashes))
                self.assertFalse(launcher.verified(self.root, path.name, self.base_id))
                with self.assertRaises(ValueError):self.promote(path)
                (path / tool).write_bytes(contents)
                hashes[tool] = hashlib.sha256(contents).hexdigest()
                (path / 'files.json').write_text(json.dumps(hashes))
            self.assertTrue(launcher.verified(self.root, path.name, self.base_id))

    def test_bad_checksum_or_base_never_runs(self):
        path = self.make_bundle('a' * 64)
        self.assertTrue(launcher.verified(self.root, path.name, self.base_id))
        self.assertFalse(launcher.verified(self.root, path.name, 'other-base'))
        (path / 'host-agent.py').write_text('corrupted')
        self.assertFalse(launcher.verified(self.root, path.name, self.base_id))
        with self.assertRaises(ValueError):
            self.promote(path)

    def promote(self, source, base_id=None):
        archive = self.root / 'download.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            for path in source.iterdir():
                if path.name != '.bundle-sha256':
                    output.add(path, arcname='./' + path.name)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        bundle.promote_archive(archive, self.root / digest, digest, base_id or self.base_id)
        return digest

    def test_staging_promotes_verified_tree_and_rejects_symlinks(self):
        path = self.make_bundle('a' * 64)
        digest = self.promote(path)
        self.assertTrue(launcher.verified(self.root, digest, self.base_id))
        self.assertEqual((self.root / digest).stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.root / digest / 'desmondd').stat().st_mode & 0o777, 0o755)
        (path / 'desmondd').unlink()
        (path / 'desmondd').symlink_to(path / 'host-agent.py')
        with self.assertRaises(ValueError):
            self.promote(path)

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

    def test_interrupted_trial_is_rejected_before_execution(self):
        runner = self.install()
        self.make_bundle('b' * 64)
        launcher.write(self.root / 'pending', {'sha256': 'b' * 64})
        runner.update()
        runner = launcher.Launcher(self.root, self.root, self.base_id)
        self.assertFalse(runner.trial)
        self.assertEqual(runner.current, 'a' * 64)
        self.assertEqual(runner.state['failed'], 'b' * 64)

    def test_repeated_crashes_of_previous_bundle_reach_base(self):
        runner = self.install()
        self.make_bundle('b' * 64)
        launcher.write(self.root / 'pending', {'sha256': 'b' * 64})
        runner.update()
        runner.check(True, False)
        for stamp in (1, 2, 3):
            runner.check(False, True, stamp)
        self.assertEqual(runner.current, 'a' * 64)
        self.assertEqual(runner.previous, '')
        for stamp in (4, 5, 6):
            runner.check(False, True, stamp)
        self.assertEqual(runner.current, '')

    def test_failed_rollback_write_is_safe_in_memory_and_after_restart(self):
        runner = self.install()
        self.make_bundle('b' * 64)
        launcher.write(self.root / 'pending', {'sha256': 'b' * 64})
        runner.update()
        with patch.object(launcher, 'write', side_effect=OSError(28, 'disk full')):
            runner.rollback('unhealthy')
            self.assertEqual(runner.current, 'a' * 64)
            self.assertTrue(runner.dirty)
            self.assertFalse(runner.update())
        reboot = launcher.Launcher(self.root, self.root, self.base_id)
        self.assertEqual(reboot.current, 'a' * 64)
        self.assertEqual(reboot.state['failed'], 'b' * 64)
        self.assertFalse(reboot.update())

    def test_failed_stable_rollback_write_is_rejected_on_unclean_restart(self):
        runner = self.install()
        self.make_bundle('b' * 64)
        launcher.write(self.root / 'pending', {'sha256': 'b' * 64})
        runner.update()
        runner.check(True, False)
        with patch.object(launcher, 'write', side_effect=OSError(28, 'disk full')):
            runner.rollback('crash loop after health gate')
        reboot = launcher.Launcher(self.root, self.root, self.base_id)
        self.assertEqual(reboot.current, 'a' * 64)
        self.assertEqual(reboot.state['failed'], 'b' * 64)

    def test_failed_update_commit_keeps_running_agent(self):
        runner = self.install()
        self.make_bundle('b' * 64)
        launcher.write(self.root / 'pending', {'sha256': 'b' * 64})
        with patch.object(launcher, 'write', side_effect=OSError(28, 'disk full')):
            with self.assertRaises(OSError):
                runner.update()
        self.assertEqual(runner.current, 'a' * 64)
        self.assertFalse(runner.trial)

    def test_recovery_directory_is_selected_at_each_restart(self):
        runner = launcher.Launcher(self.root, self.root, self.base_id)
        self.assertEqual(runner.directory(), self.root)
        (self.root / 'recovery').mkdir()
        self.assertEqual(runner.directory(), self.root / 'recovery')

    def test_no_previous_bundle_falls_back_to_base(self):
        runner = launcher.Launcher(self.root, self.root, self.base_id)
        self.make_bundle('a' * 64)
        launcher.write(self.root / 'pending', {'sha256': 'a' * 64})
        runner.update()
        runner.check(False, False, runner.deadline)
        self.assertEqual(runner.current, '')
        self.assertEqual(json.loads((self.root / 'status.json').read_text())['current'], '')

    def test_corrupt_current_uses_previous(self):
        self.make_bundle('a' * 64)
        current = self.make_bundle('b' * 64)
        (self.root / 'current').symlink_to(current.name)
        (self.root / 'previous').symlink_to('a' * 64)
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

    def test_new_manifest_helpers_do_not_require_a_launcher_update(self):
        path = self.make_bundle('a' * 64)
        helper = path / 'new_helper.py'
        helper.write_text('VALUE = 1')
        manifest = path / 'files.json'
        hashes = json.loads(manifest.read_text())
        hashes[helper.name] = hashlib.sha256(helper.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(hashes))
        digest = self.promote(path)
        self.assertTrue(launcher.verified(self.root, digest, self.base_id))
        (self.root / digest / helper.name).write_text('VALUE = 2')
        self.assertFalse(launcher.verified(self.root, digest, self.base_id))

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
            self.assertEqual(json.loads((host_root / 'pending').read_text()), {'sha256': digest, 'epoch': 2})

    def test_real_broken_agent_rolls_back_and_preserves_independent_worker(self):
        initial = self.install()
        initial.state['running'] = ''
        initial.publish()
        good = self.root / ('a' * 64) / 'host-agent.py'
        ready = self.root / 'ready'
        helper = good.with_name('host_state.py')
        helper.write_text('healthy = True\n')
        good.write_text('import host_state,pathlib,os,time,subprocess,sys; '
                       'subprocess.run([sys.executable,"-c","import host_state"],cwd=str(pathlib.Path(__file__).parent),check=True); '
                       'pathlib.Path(' + repr(str(ready)) + ').write_text(str(os.getpid())); time.sleep(60)')
        broken = self.make_bundle('b' * 64) / 'host-agent.py'
        broken.write_text('raise SystemExit(13)')
        for path in (good, helper, broken):
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
            self.assertTrue(launcher.verified(self.root, 'a' * 64, self.base_id))
            self.assertFalse((good.parent / '__pycache__').exists())
        finally:
            supervisor.terminate()
            supervisor.wait(timeout=10)
            worker.terminate()
            worker.wait(timeout=5)

    def test_queued_update_from_a_previous_controller_epoch_is_discarded(self):
        runner = self.install()
        self.make_bundle('b' * 64)
        fence = self.root.parent / 'fence.json'
        fence.write_text('{"epoch": 2}')
        try:
            launcher.write(self.root / 'pending', {'sha256': 'b' * 64, 'epoch': 1})
            self.assertFalse(runner.update())
            self.assertEqual(runner.current, 'a' * 64)
            self.assertFalse((self.root / 'pending').exists())
        finally:
            fence.unlink()

    def test_launcher_keeps_recovery_alive_when_state_storage_is_full(self):
        base = self.root / 'base'
        base.mkdir()
        ready = self.root / 'ready'
        (base / 'host-agent.py').write_text('import pathlib,time; pathlib.Path(' + repr(str(ready)) + ').write_text("running"); time.sleep(60)')
        code = ('import importlib.util; s=importlib.util.spec_from_file_location("launcher", ' +
                repr(str(Path(launcher.__file__))) + '); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); ' +
                'root=m.Path(' + repr(str(self.root / 'state')) + '); base=m.Path(' + repr(str(base)) + '); original=m.Launcher; ' +
                'm.Launcher=lambda: original(root,base,"test-base"); ' +
                '\ndef unavailable(*args):\n    raise OSError(28, "disk full")\n'
                'm.write=unavailable; m.main()')
        with (self.root / 'launcher.log').open('wb') as log:
            process = subprocess.Popen([sys.executable, '-c', code], stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    self.assertIsNone(process.poll())
                    time.sleep(.05)
                self.assertTrue(ready.exists())
                time.sleep(1.2)
                self.assertIsNone(process.poll())
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_launcher_death_stops_only_agent_and_preserves_its_worker(self):
        base = self.root / 'base'
        base.mkdir()
        ready = self.root / 'processes.json'
        script = ('import pathlib,subprocess,sys,os,json,time; worker=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"],start_new_session=True); '
                  'pathlib.Path(' + repr(str(ready)) + ').write_text(json.dumps({"agent":os.getpid(),"worker":worker.pid})); time.sleep(60)')
        (base / 'host-agent.py').write_text(script)
        code = ('import importlib.util; s=importlib.util.spec_from_file_location("launcher", ' +
                repr(str(Path(launcher.__file__))) + '); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); ' +
                'root=m.Path(' + repr(str(self.root / 'state')) + '); base=m.Path(' + repr(str(base)) + '); original=m.Launcher; '
                'm.Launcher=lambda: original(root,base,"test-base"); m.main()')
        process = subprocess.Popen([sys.executable, '-c', code])
        children = {}
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                self.assertIsNone(process.poll())
                time.sleep(.05)
            self.assertTrue(ready.exists())
            children = json.loads(ready.read_text())
            process.kill()
            process.wait(timeout=5)
            def live(pid):
                try:
                    return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z'
                except (FileNotFoundError, ProcessLookupError):
                    return False
            deadline = time.monotonic() + 5
            while live(children['agent']) and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertFalse(live(children['agent']))
            self.assertTrue(live(children['worker']))
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            for pid in children.values():
                try:
                    os.kill(pid, 15)
                except ProcessLookupError:
                    pass

    def test_a_bundle_for_a_newer_base_is_refused_before_download(self):
        # A host on the previous base receiving a pin for a re-imaged fleet fails clearly
        # instead of downloading a bundle it cannot run.
        base_path = self.root / 'base-id'
        base_path.write_text('ubuntu24-cuda13-amd64-v2\n')
        agent = SimpleNamespace(root=self.root, lock=threading.RLock())
        with patch.object(bundle, 'BASE_ID', base_path), patch.object(bundle.subprocess, 'run') as download:
            with self.assertRaisesRegex(ValueError, 'requires a different base'):
                bundle.stage_host(agent, {'sha256': 'a' * 64, 'base_id': 'ubuntu24-cuda13-amd64-v3'}, 1)
            download.assert_not_called()

    def test_invalid_pin_rejects_before_download(self):
        for pin in ({'sha256': '../escape', 'base_id': self.base_id},
                    {'sha256': 'a' * 64, 'base_id': 'other'}):
            with self.assertRaises(ValueError):
                bundle.validate_pin(pin, self.base_id)


if __name__ == '__main__':
    unittest.main()
