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
from unittest.mock import Mock, patch
import uuid

import tailnet_ssh

# Real entries from the committed inventory.
HOSTS = json.loads(tailnet_ssh.HOSTS.read_text())
FIRST, SECOND = HOSTS[0]['instance_id'], HOSTS[1]['instance_id']


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
                payload = {'instance_id': 'first', 'installer': 'def install(payload): print(\'{"instance_id":"first","updated":true}\')'}
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
                    namespace = {}
                    exec(compile(rollout.REMOTE, 'remote-migration', 'exec'), namespace)
                wait.assert_called_once()
                self.assertEqual(json.loads(output.getvalue()),
                                 {'instance_id': 'first', 'host_launcher': True, 'preserved_processes': 0})

    def test_uses_tailscale_ssh_to_the_committed_address(self):
        run = Mock()
        rollout.rollout([{'instance_id': FIRST}], b'binary', 'base', run=run)
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ['tailscale', 'ssh', 'root@' + HOSTS[0]['tailscale_ip']])
        self.assertTrue(command[3].startswith('python3 -c '))
        payload = json.loads(run.call_args.kwargs['input'])
        self.assertEqual(payload['instance_id'], FIRST)
        self.assertEqual(payload['desmondd'], 'YmluYXJ5')
        self.assertIn('installer', payload)

    def test_every_committed_host_resolves_to_its_tailnet_address(self):
        for host in HOSTS:
            self.assertEqual(tailnet_ssh.resolve(host['instance_id']), (host['instance_id'], host['tailscale_ip']))
        with self.assertRaises(ValueError):
            tailnet_ssh.resolve(str(uuid.uuid4()))

    def test_rejects_public_and_duplicate_addresses(self):
        with tempfile.TemporaryDirectory() as directory:
            hosts = Path(directory) / 'hosts.json'
            hosts.write_text(json.dumps([{**HOSTS[0], 'tailscale_ip': '203.0.113.1'}, HOSTS[1], HOSTS[1]]))
            for instance in (FIRST, SECOND):
                with self.subTest(instance=instance), self.assertRaises(ValueError):
                    tailnet_ssh.resolve(instance, hosts)

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
            rollout.rollout([{'instance_id': FIRST}, {'instance_id': SECOND}], b'binary', 'base', run)
        self.assertEqual(len(called), 1)

    def test_rejects_public_ssh_targets_and_mismatched_addresses(self):
        for target in ({'instance_id': FIRST, 'ssh': 'root@203.0.113.1'},
                       {'instance_id': FIRST, 'tailscale_ip': '100.64.0.9'}):
            with self.subTest(target=target), self.assertRaises(ValueError):
                rollout.rollout([target], b'binary', 'base', Mock())
        with self.assertRaises(ValueError):
            tailnet_ssh.command('-oProxyCommand=evil', 'true')


if __name__ == '__main__':
    unittest.main()
