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
                       'model_id': 'kev', 'release': {'runtime_revision': 'kev-a'},
                       'gpu_uuid': 'GPU-test-0'}
        self.host = agent.Agent(self.config, self.root)
        self.pod = {'metadata': {'uid': self.uid, 'annotations': {
            'gradiated.com/model-id': 'kev', 'gradiated.com/release': json.dumps(self.config['release'])}},
            'spec': {'nodeName': 'gpu-' + self.config['instance_id'], 'containers': [{
                'image': 'gradiated/kev-bundle@sha256:' + 'a' * 64,
                'resources': {'limits': {'nvidia.com/gpu': '1', 'cpu': '16', 'memory': '64Gi'},
                              'requests': {'nvidia.com/gpu': '1', 'cpu': '16', 'memory': '48Gi'}}}]}}

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

    def test_requests_observe_profile_updates_under_the_shared_configuration_lock(self):
        import threading
        config_path = self.root / 'config.json'
        config_path.write_text(json.dumps(self.config))
        self.host.config_path = config_path
        result = []
        with agent.configuration_lock(self.root):
            thread = threading.Thread(target=lambda: result.append(self.host.request({'operation': 'ping', 'epoch': 1})))
            thread.start()
            thread.join(.05)
            self.assertTrue(thread.is_alive())
            updated = {**self.config, 'runtimes': {}}
            config_path.write_text(json.dumps(updated))
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.host.config, updated)
        self.assertEqual(result, [{'instance_id': self.config['instance_id']}])

    def test_catalogue_stages_before_activation_and_preserves_active_profiles(self):
        import time
        digest = 'a' * 64
        marker = self.root / 'bundles' / digest / '.bundle-sha256'
        marker.parent.mkdir(parents=True)
        marker.write_text(digest)
        state = self.root / 'pods' / self.uid
        state.mkdir()
        (state / 'state.json').write_text(json.dumps({'pod': self.pod}))
        profile = {'image': self.pod['spec']['containers'][0]['image'], 'model_id': 'kev', 'release': self.config['release'], 'gpus': 1, 'cpu': '16', 'memory': '64Gi'}
        self.host.request({'operation': 'configure', 'epoch': 1, 'runtimes': {digest: profile}})
        deadline = time.monotonic() + 2
        while not self.host.catalogue_ready and time.monotonic() < deadline: time.sleep(.01)
        self.assertTrue(self.host.catalogue_ready)
        self.assertEqual(self.host.config['runtimes'][digest]['release'], self.config['release'])
        self.assertEqual(self.host.config['gpu_uuids'], ['GPU-test-0'])

    def test_registered_bundle_waits_for_staging_without_creating_state(self):
        digest = 'b' * 64
        pod = json.loads(json.dumps(self.pod))
        pod['spec']['containers'][0]['image'] = 'gradiated/kev-bundle@sha256:' + digest
        self.host.catalogue_wanted = {digest: {'image': pod['spec']['containers'][0]['image']}}
        self.host.catalogue_task = None  # A failed download must remain retryable.
        with self.assertRaises(agent.RuntimeStaging):
            self.host.request({'operation': 'create', 'uid': self.uid, 'pod': pod, 'epoch': 1})
        self.assertEqual(self.host.states(), [])
        pod['spec']['containers'][0]['image'] = 'gradiated/kev-bundle@sha256:' + 'c' * 64
        with self.assertRaises(ValueError):
            self.host.request({'operation': 'create', 'uid': self.uid, 'pod': pod, 'epoch': 1})

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

    def test_tensor_parallel_and_single_gpu_claims_do_not_overlap(self):
        self.config['gpu_uuids'] = ['GPU-test-' + str(i) for i in range(4)]
        self.config['runtimes'] = {
            'a' * 64: {'image': self.pod['spec']['containers'][0]['image'], 'model_id': 'kev',
                       'release': self.config['release'], 'gpus': 1, 'cpu': '16', 'memory': '64Gi',
                       'request_memory': '48Gi', 'startup_timeout': 1800},
            'b' * 64: {'image': 'gradiated/glm-bundle@sha256:' + 'b' * 64, 'model_id': 'glm',
                       'release': {'runtime_revision': 'glm-b'}, 'gpus': 2, 'cpu': '32',
                       'memory': '400Gi', 'startup_timeout': 3600},
        }
        pods = [json.loads(json.dumps(self.pod)) for _ in range(3)]
        pods[0]['metadata']['annotations'] = {'gradiated.com/model-id': 'glm', 'gradiated.com/release': '{"runtime_revision":"glm-b"}'}
        pods[0]['spec']['containers'][0] = {'image': self.config['runtimes']['b' * 64]['image'],
            'resources': {kind: {'nvidia.com/gpu': '2', 'cpu': '32', 'memory': '400Gi'} for kind in ['limits', 'requests']}}
        assignments = []
        for pod in pods:
            pod['metadata']['uid'] = str(uuid.uuid4())
            self.host.validate(pod)
            devices, port = self.host.assignment(pod)
            directory = self.root / 'pods' / pod['metadata']['uid']
            directory.mkdir()
            agent.atomic_json(directory / 'state.json', {'pod': pod, 'gpu_uuids': devices, 'port_base': port})
            assignments.append((devices, port))
        self.assertEqual([len(devices) for devices, _ in assignments], [2, 1, 1])
        self.assertEqual(len({device for devices, _ in assignments for device in devices}), 4)
        self.assertEqual(len({port for _, port in assignments}), 3)
        self.assertTrue(all(port < 32768 for _, port in assignments))
        with self.assertRaises(ValueError):
            self.host.assignment(self.pod)

    def test_training_resources_follow_recipe_and_require_training_profile(self):
        self.config['runtimes'] = {'b' * 64: {'kind': 'training', 'image': 'gradiated/training-bundle@sha256:' + 'b' * 64,
            'model_id': 'training', 'release': {}, 'gpus': 1, 'cpu': '4', 'memory': '64Gi', 'startup_timeout': 300}}
        pod = json.loads(json.dumps(self.pod))
        pod['metadata']['annotations'] = {'gradiated.com/model-id': 'training', 'gradiated.com/release': '{}',
            'gradiated.com/workload-kind': 'training', 'gradiated.com/training-recipe': '{"gpu_count": 4}'}
        pod['spec']['containers'][0] = {'image': self.config['runtimes']['b' * 64]['image'],
            'resources': {kind: {'nvidia.com/gpu': '4', 'cpu': '16', 'memory': '256Gi'} for kind in ['limits', 'requests']}}
        self.host.validate(pod)
        pod['spec']['containers'][0]['resources']['requests']['nvidia.com/gpu'] = '1'
        with self.assertRaises(ValueError):
            self.host.validate(pod)
        pod['spec']['containers'][0]['resources']['requests']['nvidia.com/gpu'] = '4'
        pod['metadata']['annotations'].pop('gradiated.com/workload-kind')
        with self.assertRaises(ValueError):
            self.host.validate(pod)

    def test_training_readiness_uses_the_trainer_without_a_reporter(self):
        self.config['runtimes'] = {'b' * 64: {'kind': 'training', 'image': 'gradiated/training-bundle@sha256:' + 'b' * 64,
            'model_id': 'training', 'release': {}, 'gpus': 1, 'cpu': '4', 'memory': '64Gi', 'startup_timeout': 300}}
        pod = json.loads(json.dumps(self.pod))
        pod['spec']['containers'][0]['image'] = self.config['runtimes']['b' * 64]['image']
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        agent.atomic_json(directory / 'state.json', {'pod': pod, 'port_base': 38088, 'task': {'pid': 1, 'birth': 'test'}})
        with patch.object(agent, 'alive', return_value=True), patch.object(agent, 'health', return_value=True) as probe:
            result = self.host.request({'operation': 'status', 'uid': self.uid, 'epoch': 1})
        self.assertTrue(result['ready'])
        probe.assert_called_once_with(38088, '/health')

    def test_failed_task_cleanup_stops_orphan_and_preserves_unrelated_process(self):
        owned = subprocess.Popen(['sleep', '120'], start_new_session=True)
        unrelated = subprocess.Popen(['sleep', '120'], start_new_session=True)
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        agent.atomic_json(directory / 'state.json', {'pod': self.pod, 'draining': True, 'drain_started_at': 0})
        for name in ('training', 'lora'):
            cache = directory / name
            cache.mkdir()
            (cache / 'private-artifact').write_text('synthetic')
        (directory / 'runtime.log').write_text('diagnostic')
        agent.atomic_json(directory / 'runtime.json', {'runtime': agent.owner(owned),
                         'reporter': {'pid': unrelated.pid, 'birth': 'wrong-birth'}})
        try:
            with patch.object(self.host, 'refresh_proxy'):
                self.host.drain(self.uid)
            self.assertEqual(owned.wait(timeout=2), -signal.SIGTERM)
            self.assertIsNone(unrelated.poll())
            self.assertFalse((directory / 'state.json').exists())
            self.assertFalse((directory / 'training').exists())
            self.assertFalse((directory / 'lora').exists())
            self.assertTrue((directory / 'runtime.log').exists())
        finally:
            for process in [owned, unrelated]:
                if process.poll() is None:
                    process.terminate()
                process.wait()


if __name__ == '__main__':
    unittest.main()
