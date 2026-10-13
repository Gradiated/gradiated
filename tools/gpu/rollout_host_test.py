import importlib.util
import contextlib
import io
import json
import pathlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('rollout', Path(__file__).with_name('rollout-host.py'))
rollout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout)
pin_spec = importlib.util.spec_from_file_location('pin_host', Path(__file__).with_name('pin-host.py'))
pin_host = importlib.util.module_from_spec(pin_spec)
pin_spec.loader.exec_module(pin_host)


class RolloutTests(unittest.TestCase):
    def test_migration_waits_for_a_fresh_agent_when_the_launcher_already_exists(self):
        for restart_during_ping in (False, True):
            with self.subTest(restart_during_ping=restart_during_ping), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                state = root / 'state'
                state.mkdir()
                proc = root / 'proc'
                proc.mkdir()
                token = root / 'token'
                token.write_text('test-management-token')
                config = root / 'config.json'
                config.write_text(json.dumps({'instance_id': 'first', 'token_file': str(token)}))

                def process(pid, birth, arguments=None):
                    path = proc / str(pid)
                    path.mkdir()
                    (path / 'cmdline').write_bytes(arguments or b'python3\0-B\0/opt/gradiated/kubelet/host-agent.py\0')
                    (path / 'stat').write_text(f'{pid} (python3) S ' + '0 ' * 18 + str(birth) + ' 0')

                process(100, 10)
                process(102, 10, b'python3\0-B\0/opt/gradiated/kubelet/host-agent.py\0proxy\0')
                process(103, 10, b'python3\0-B\0/opt/gradiated/kubelet/host-agent.py\0task\0uid\0')
                def restart(_):
                    if (proc / '100').exists():
                        shutil.rmtree(proc / '100')
                        process(101, 20)

                paths = {'/var/lib/gradiated-kubelet': state, '/etc/gradiated/kubelet.json': config, '/proc': proc}
                original_path = pathlib.PosixPath
                output = io.StringIO()
                payload = {'instance_id': 'first', 'installer': 'def install(payload): pass'}
                ping = json.dumps({'instance_id': 'first', 'host_launcher': True})
                replies = 0
                def reply(*args, **kwargs):
                    nonlocal replies
                    replies += 1
                    if restart_during_ping and replies == 2:
                        restart(None)
                    return io.StringIO(ping)
                with patch('pathlib.Path', side_effect=lambda value: paths.get(str(value), original_path(value))), \
                        patch('sys.stdin', io.StringIO(json.dumps(payload))), \
                        patch('urllib.request.urlopen', side_effect=reply), \
                        patch('time.sleep', side_effect=restart) as wait, contextlib.redirect_stdout(output):
                    exec(compile(rollout.REMOTE, 'remote-migration', 'exec'), {})
                wait.assert_called_once()
                self.assertEqual(json.loads(output.getvalue()),
                                 {'instance_id': 'first', 'host_launcher': True, 'preserved_processes': 0})

    def test_host_pin_cannot_select_a_model_runtime_artifact(self):
        release = {'sha256': 'a' * 64, 'baseId': 'base', 'bundle': 'host'}
        self.assertEqual(pin_host.pin(release), {'sha256': 'a' * 64, 'base_id': 'base'})
        with self.assertRaises(ValueError):
            pin_host.pin({**release, 'bundle': 'training'})

    def test_stops_on_first_failure(self):
        called = []
        def run(command, **kwargs):
            called.append(command)
            raise subprocess.CalledProcessError(1, command)
        with self.assertRaises(subprocess.CalledProcessError):
            rollout.rollout([{'instance_id': 'first', 'ssh': 'root@gpu-a'},
                             {'instance_id': 'second', 'ssh': 'root@gpu-b'}], b'binary', 'base', run)
        self.assertEqual(len(called), 1)

    def test_rejects_ssh_option_injection(self):
        with self.assertRaises(ValueError):
            rollout.rollout([{'instance_id': 'first', 'ssh': '-oProxyCommand=evil'}], b'binary', 'base')


if __name__ == '__main__':
    unittest.main()
