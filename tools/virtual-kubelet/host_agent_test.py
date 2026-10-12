import importlib.util
import json
from pathlib import Path
import subprocess
import signal
import tempfile
import unittest
from unittest.mock import patch
import uuid

spec = importlib.util.spec_from_file_location('agent', Path(__file__).with_name('host-agent.py'))
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class HostAgentTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / 'pods').mkdir()
        self.uid = str(uuid.uuid4())
        self.config = {'instance_id': str(uuid.uuid4()), 'bundle_sha256': 'a' * 64,
                       'model_id': 'kev', 'release': {'runtime_revision': 'kev-a'}}
        self.host = agent.Agent(self.config, self.root)
        self.pod = {'metadata': {'uid': self.uid, 'annotations': {
            'gradiated.com/model-id': 'kev', 'gradiated.com/release': json.dumps(self.config['release'])}},
            'spec': {'nodeName': 'gpu-' + self.config['instance_id'], 'containers': [{
                'image': 'gradiated/kev-bundle@sha256:' + 'a' * 64,
                'resources': {'limits': {'nvidia.com/gpu': '1', 'cpu': '16', 'memory': '64Gi'}}}]}}

    def tearDown(self):
        self.directory.cleanup()

    def test_controller_restart_preserves_workloads_and_rejects_stale_leader(self):
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        agent.atomic_json(directory / 'state.json', {'pod': self.pod})
        self.host.request({'operation': 'ping', 'epoch': 3})
        restarted = agent.Agent(self.config, self.root)
        self.assertEqual(restarted.request({'operation': 'list', 'epoch': 4}), [self.pod])
        with self.assertRaises(ValueError):
            self.host.request({'operation': 'delete', 'uid': self.uid, 'epoch': 3})
        self.assertTrue((directory / 'state.json').exists())

    def test_no_execution_or_credential_overrides(self):
        for key, value in [('env', [{'name': 'TOKEN', 'value': 'secret'}]),
                           ('envFrom', [{'secretRef': {'name': 'db'}}]),
                           ('command', ['bash']), ('volumeMounts', [{'name': 'secret'}])]:
            with self.subTest(key=key):
                pod = json.loads(json.dumps(self.pod))
                pod['spec']['containers'][0][key] = value
                with self.assertRaises(ValueError):
                    self.host.validate(pod)
        with self.assertRaises(ValueError):
            self.host.request({'operation': 'create', 'uid': str(uuid.uuid4()), 'pod': self.pod, 'epoch': 1})
        self.assertEqual(self.host.states(), [])

    def test_configuration_validation_preserves_the_live_proxy_pid(self):
        proxy = self.root / 'proxy'
        proxy.mkdir()
        process = subprocess.Popen(['python3', '-c', 'import time;time.sleep(60)', str(self.root / 'nginx.conf')], start_new_session=True)
        pid_file = proxy / 'nginx.pid'
        pid_file.write_text(str(process.pid))
        def validate(command, **_):
            candidate = Path(command[-1]).read_text()
            self.assertIn(f'pid {proxy}/nginx-test.pid;', candidate)
            (proxy / 'nginx-test.pid').write_text('')
        try:
            with patch.object(agent.subprocess, 'run', side_effect=validate), patch.object(agent.os, 'kill') as signal_proxy:
                self.host.refresh_proxy()
            signal_proxy.assert_called_once_with(process.pid, signal.SIGHUP)
            self.assertEqual(pid_file.read_text(), str(process.pid))
            self.assertFalse((proxy / 'nginx-test.pid').exists())
        finally:
            process.terminate()
            process.wait()

    def test_failed_task_cleanup_stops_orphan_and_preserves_unrelated_process(self):
        owned = subprocess.Popen(['sleep', '120'], start_new_session=True)
        unrelated = subprocess.Popen(['sleep', '120'], start_new_session=True)
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        agent.atomic_json(directory / 'state.json', {'pod': self.pod, 'draining': True, 'drain_started_at': 0})
        agent.atomic_json(directory / 'runtime.json', {'runtime': agent.owner(owned),
                         'reporter': {'pid': unrelated.pid, 'birth': 'wrong-birth'}})
        try:
            with patch.object(self.host, 'refresh_proxy'):
                self.host.drain(self.uid)
            self.assertEqual(owned.wait(timeout=2), -signal.SIGTERM)
            self.assertIsNone(unrelated.poll())
            self.assertFalse((directory / 'state.json').exists())
        finally:
            for process in [owned, unrelated]:
                if process.poll() is None:
                    process.terminate()
                process.wait()


if __name__ == '__main__':
    unittest.main()
