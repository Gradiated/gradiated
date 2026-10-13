import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import signal
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
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

        self.term = str(uuid.uuid4())
        self.host.request({'operation': 'claim', 'epoch': 0, 'term': self.term})

    def request(self, body):
        return self.host.request({'term': self.term, **body})

    def tearDown(self):
        self.directory.cleanup()

    def test_completed_children_are_reaped_without_losing_live_children(self):
        completed = subprocess.Popen(['python3', '-c', 'pass'])
        live = subprocess.Popen(['python3', '-c', 'import time; time.sleep(60)'])
        try:
            completed.wait(timeout=5)
            self.host.children = {'completed': completed, 'live': live}
            self.host.reap_children()
            self.assertEqual(self.host.children, {'live': live})
        finally:
            live.terminate()
            live.wait(timeout=5)

    def test_diagnostic_count_is_bounded_even_for_recent_retirements(self):
        import os
        now = 1000
        for index in range(25):
            path = self.root / 'pods' / str(uuid.uuid4())
            path.mkdir()
            os.utime(path, (now - index, now - index))
        self.host.housekeep(now)
        self.assertEqual(len(list((self.root / 'pods').iterdir())), 20)

    def test_claim_retries_are_idempotent_and_survive_agent_restart(self):
        term = str(uuid.uuid4())
        request = {'operation': 'claim', 'epoch': 1, 'term': term}
        self.assertEqual(self.request(request), {'epoch': 2})
        restarted = agent.Agent(self.config, self.root)
        self.assertEqual(restarted.request(request), {'epoch': 2})
        with self.assertRaises(ValueError):
            restarted.request({'operation': 'claim', 'epoch': 1, 'term': str(uuid.uuid4())})
        for epoch in (1, 3, 1000):
            with self.assertRaises(ValueError):
                restarted.request({'operation': 'list', 'epoch': epoch, 'term': term})
        self.assertEqual(restarted.request({'operation': 'list', 'epoch': 2, 'term': term}), [])

    def test_competing_claims_have_one_winner(self):
        import concurrent.futures
        def claim(_):
            try:
                return self.request({'operation': 'claim', 'epoch': 1, 'term': str(uuid.uuid4())})
            except ValueError:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(claim, range(8)))
        self.assertEqual([result for result in results if result], [{'epoch': 2}])

    def test_failed_fence_write_does_not_acknowledge_the_claim(self):
        request = {'operation': 'claim', 'epoch': 1, 'term': str(uuid.uuid4())}
        with patch.object(agent, 'atomic_json', side_effect=OSError('disk full')), self.assertRaises(OSError):
            self.request(request)
        self.assertEqual(self.request({'operation': 'fence'}), {'epoch': 1})
        self.assertEqual(self.request(request), {'epoch': 2})

    def test_cleanup_protects_active_and_staging_bundles_and_recent_retirement(self):
        import os
        now = 10 * 86400
        bundles = self.root / 'bundles'
        bundles.mkdir()
        self.host.catalogue_wanted = {'b' * 64: {}}
        for index, letter in enumerate('abcdefg'):
            path = bundles / (letter * 64)
            path.mkdir()
            (path / '.bundle-sha256').write_text(path.name)
            os.utime(path, (index, index))
        link = bundles / ('h' * 64)
        link.symlink_to(bundles / ('a' * 64))
        self.host.housekeep(now)
        self.assertEqual({path.name for path in bundles.iterdir()}, {letter * 64 for letter in 'abefgh'})

    def test_retired_diagnostics_are_pruned_but_live_orphans_block_bundle_cleanup(self):
        import os
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        (directory / 'runtime.log').write_text('diagnostic')
        os.utime(directory, (0, 0))
        bundles = self.root / 'bundles'
        bundles.mkdir()
        for letter in 'bcdef':
            path = bundles / (letter * 64)
            path.mkdir()
            (path / '.bundle-sha256').write_text(path.name)
            os.utime(path, (0, 0))
        agent.atomic_json(directory / 'runtime.json', {'runtime': {'pid': 1, 'birth': 'synthetic'}})
        os.utime(directory, (0, 0))
        with patch.object(agent, 'alive', return_value=True):
            self.host.housekeep(10 * 86400)
        self.assertTrue(directory.exists())
        self.assertEqual(len(list(bundles.iterdir())), 5)
        with patch.object(agent, 'alive', return_value=False):
            self.host.housekeep(10 * 86400)
        self.assertFalse(directory.exists())
        self.assertEqual(len(list(bundles.iterdir())), 2)

    def test_corrupt_owner_state_prevents_cleanup(self):
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        (directory / 'state.json').write_text('{')
        with self.assertRaises(ValueError):
            self.host.housekeep(10 * 86400)
        self.assertTrue((directory / 'state.json').exists())

    def test_recovery_preserves_live_tasks_and_never_retries_finished_training(self):
        state = {'pod': self.pod, 'task': {'pid': 1, 'birth': 'synthetic'}}
        with patch.object(agent, 'alive', return_value=True), patch.object(agent.subprocess, 'Popen') as spawn:
            self.host.ensure_task(state)
            spawn.assert_not_called()
        self.config['runtimes'] = {'a' * 64: {'image': self.pod['spec']['containers'][0]['image'],
            'kind': 'training', 'model_id': 'training', 'release': {}, 'gpus': 1, 'cpu': '4', 'memory': '64Gi'}}
        with patch.object(agent, 'alive', return_value=False), patch.object(agent.subprocess, 'Popen') as spawn:
            self.host.ensure_task(state)
            spawn.assert_not_called()

    def test_recovery_does_not_start_over_unrecorded_processes(self):
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        group = self.root / 'cgroup'
        group.mkdir()
        (group / 'cgroup.procs').write_text('12345')
        with patch.object(agent, 'pod_cgroup', return_value=group), patch.object(self.host, 'stop'), patch.object(agent.subprocess, 'Popen') as spawn:
            with self.assertRaises(RuntimeError):
                self.host.ensure_task({'pod': self.pod})
            spawn.assert_not_called()

    def test_process_handle_from_another_boot_or_namespace_is_not_signalled(self):
        handle = {'pid': 1234, 'birth': '1', **agent.PROCESS_SCOPE}
        for key in agent.PROCESS_SCOPE:
            with patch.object(agent, 'process_birth', return_value='1'), patch.object(agent.os, 'killpg') as kill:
                agent.owned_signal({**handle, key: 'another-scope'}, signal.SIGTERM)
                kill.assert_not_called()

    def test_interrupted_creation_recovers_once_then_preserves_the_live_task(self):
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        state = {'pod': self.pod}
        agent.atomic_json(directory / 'state.json', state)
        process = subprocess.Popen(['sleep', '120'], start_new_session=True)
        try:
            with patch.object(agent.subprocess, 'Popen', return_value=process) as spawn:
                self.host.ensure_task(state)
                recovered = json.loads((directory / 'state.json').read_text())
                agent.Agent(self.config, self.root).ensure_task(recovered)
                self.assertEqual(spawn.call_count, 1)
                self.assertTrue(agent.alive(recovered['task']))
        finally:
            process.terminate()
            process.wait(timeout=5)

    def test_real_http_storage_failure_is_retryable_and_private(self):
        import threading
        import urllib.error
        import urllib.request
        server = agent.ThreadingHTTPServer(('127.0.0.1', 0), agent.handler_for(self.host, 'synthetic-key'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        payload = {'operation': 'claim', 'epoch': 1, 'term': str(uuid.uuid4())}
        request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/_kubelet',
            data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer synthetic-key'})
        try:
            with patch.object(agent, 'atomic_json', side_effect=OSError('synthetic-private-detail')):
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    urllib.request.urlopen(request, timeout=2)
                self.assertEqual(failure.exception.code, 503)
                self.assertEqual(json.loads(failure.exception.read()), {'error': 'host_unavailable'})
            with urllib.request.urlopen(request, timeout=2) as response:
                self.assertEqual(json.load(response), {'epoch': 2})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_controller_restart_preserves_workloads_and_rejects_stale_leader(self):
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        agent.atomic_json(directory / 'state.json', {'pod': self.pod})
        term = str(uuid.uuid4())
        self.request({'operation': 'claim', 'epoch': 1, 'term': term})
        restarted = agent.Agent(self.config, self.root)
        self.assertEqual(restarted.request({'operation': 'list', 'epoch': 2, 'term': term}), [self.pod])
        with self.assertRaises(ValueError):
            self.request({'operation': 'delete', 'uid': self.uid, 'epoch': 1})
        self.assertTrue((directory / 'state.json').exists())

    def test_requests_observe_profile_updates_under_the_shared_configuration_lock(self):
        import threading
        config_path = self.root / 'config.json'
        config_path.write_text(json.dumps(self.config))
        self.host.config_path = config_path
        result = []
        with agent.configuration_lock(self.root):
            thread = threading.Thread(target=lambda: result.append(self.request({'operation': 'ping', 'epoch': 1})))
            thread.start()
            thread.join(.05)
            self.assertTrue(thread.is_alive())
            updated = {**self.config, 'runtimes': {}}
            config_path.write_text(json.dumps(updated))
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.host.config, updated)
        self.assertEqual(result, [{'instance_id': self.config['instance_id'], 'epoch': 1}])

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
        self.request({'operation': 'configure', 'epoch': 1, 'runtimes': {digest: profile}})
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
            self.request({'operation': 'create', 'uid': self.uid, 'pod': pod, 'epoch': 1})
        self.assertEqual(self.host.states(), [])
        pod['spec']['containers'][0]['image'] = 'gradiated/kev-bundle@sha256:' + 'c' * 64
        with self.assertRaises(ValueError):
            self.request({'operation': 'create', 'uid': self.uid, 'pod': pod, 'epoch': 1})

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
            self.request({'operation': 'create', 'uid': str(uuid.uuid4()), 'pod': self.pod, 'epoch': 1})
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

    def test_live_proxy_recovers_lost_route_updates_without_restarting(self):
        proxy = self.root / 'proxy'
        proxy.mkdir()
        path = self.root / 'nginx.conf'
        path.write_text('stale configuration with a retired allocation route')
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        agent.atomic_json(directory / 'state.json', {'pod': self.pod, 'port_base': 38080})
        process = subprocess.Popen(['python3', '-c', 'import time; time.sleep(60)', str(path)])
        (proxy / 'nginx.pid').write_text(str(process.pid))
        try:
            with patch.object(agent.subprocess, 'run'), patch.object(agent.os, 'kill') as signal_proxy:
                self.host.ensure_proxy()
                signal_proxy.assert_called_once_with(process.pid, signal.SIGHUP)
                self.assertIn('/alloc/' + self.uid + '/', path.read_text())
                self.assertNotIn('retired allocation', path.read_text())
                self.host.ensure_proxy()
                signal_proxy.assert_called_once_with(process.pid, signal.SIGHUP)
                self.assertIsNone(process.poll())
        finally:
            process.terminate()
            process.wait(timeout=5)

    def test_proxy_timeout_covers_the_production_generation_budget(self):
        import re
        import yaml
        config = next(doc for doc in yaml.safe_load_all((Path(__file__).resolve().parents[2] /
            'infra/environments/prod/us-east-1/kubernetes/workloads/gateway.yaml').read_text())
                      if doc['kind'] == 'ConfigMap')['data']
        request_limit = int(config['GATEWAY_GENERATION_TIMEOUT_SECONDS'])
        timeout = int(re.search(r'proxy_read_timeout (\d+)s;', self.host.proxy_config()).group(1))
        self.assertGreaterEqual(timeout, request_limit + 30)
        self.assertEqual(timeout, agent.REQUEST_DRAIN_SECONDS)

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
            result = self.request({'operation': 'status', 'uid': self.uid, 'epoch': 1})
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


def fcntl_locked(path):
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
        return False


class ModelCacheTest(unittest.TestCase):
    revision = 'a' * 40

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.home = Path(self.directory.name)
        self.hub = self.home / 'hub'
        self.hub.mkdir()
        self.config = {'hf_home': str(self.home), 'model_cache_reserve_gib': 0}
        self.free = 0
        self.sizes = {}
        self.logs = []

    def tearDown(self):
        self.directory.cleanup()

    def usage(self, _path):
        evicted = sum(size for name, size in self.sizes.items() if not (self.hub / name).exists())
        return SimpleNamespace(free=self.free + evicted)

    def cached(self, repo, size, used, files=('model.safetensors',)):
        directory = agent.repo_directory(self.hub, repo)
        snapshot = directory / 'snapshots' / self.revision
        snapshot.mkdir(parents=True)
        for name in files:
            (snapshot / name).write_bytes(b'x')
        (directory / agent.CACHE_MARKER).touch()
        os.utime(directory / agent.CACHE_MARKER, (used, used))
        self.sizes[directory.name] = size
        return directory

    def serving(self, repo, revision=revision):
        return {'release': {'model_path': repo, 'model_revision': revision}}

    def prepare(self, profile, pods=(), files=lambda _repo, _revision: {'model.safetensors': 100, 'config.json': 1}):
        agent.prepare_model_cache(self.config, profile, self.home / 'pod', lambda: [(pod, self.home / f'pod-{index}') for index, pod in enumerate(pods)],
                                  self.logs.append, files, self.usage)

    def test_cache_hit_evicts_nothing_and_marks_the_model_used(self):
        old = self.cached('org/old', 500, 1)
        model = self.cached('org/model', 101, 2, ('model.safetensors', 'config.json'))

        self.prepare(self.serving('org/model'))

        self.assertTrue(old.exists())
        self.assertGreater(agent.last_used(model), 2)
        self.assertEqual(self.logs, [])

    def test_miss_evicts_least_recently_used_until_the_pull_fits(self):
        oldest = self.cached('org/oldest', 60, 1)
        older = self.cached('org/older', 60, 2)
        recent = self.cached('org/recent', 60, 3)

        self.prepare(self.serving('org/new'))

        self.assertFalse(oldest.exists())
        self.assertFalse(older.exists())
        self.assertTrue(recent.exists())
        self.assertEqual(self.logs, ['Evicted cached model models--org--oldest', 'Evicted cached model models--org--older'])

    def test_models_used_by_pods_on_the_host_are_never_evicted(self):
        running = self.cached('org/running', 500, 1)
        base = self.cached('org/base', 500, 1)
        stale = self.cached('org/stale', 50, 5)
        training = {'kind': 'training', 'recipe': {'model': 'org/base', 'revision': self.revision}}

        self.prepare(self.serving('org/new'), [self.serving('org/running'), training])

        self.assertTrue(running.exists())
        self.assertTrue(base.exists())
        self.assertFalse(stale.exists())
        self.assertIn('needs', self.logs[-1])

    def test_downloads_in_progress_keep_their_space(self):
        stale = self.cached('org/stale', 150, 1)
        self.free = 150

        self.prepare(self.serving('org/new'), [self.serving('org/downloading')])

        self.assertFalse(stale.exists())

    def test_lora_caches_keep_their_unused_budget(self):
        stale = self.cached('org/stale', 150, 1)
        self.cached('org/model', 101, 2, ('model.safetensors', 'config.json'))
        self.free = 20
        lora = {**self.serving('org/model'), 'environment': {'LORA_ENABLED': 'true', 'LORA_DISK_CACHE_BYTES': '200'}}
        cache = self.home / 'pod-0' / 'lora'
        cache.mkdir(parents=True)
        (cache / 'adapter.safetensors').write_bytes(b'x' * 150)

        self.prepare(self.serving('org/model'), [lora])

        self.assertFalse(stale.exists())

    def test_sizing_skips_unused_weight_formats_and_failures_do_not_block(self):
        listing = {'siblings': [{'rfilename': 'model.safetensors', 'size': 10},
                                {'rfilename': 'pytorch_model.bin', 'size': 10},
                                {'rfilename': 'tokenizer.json', 'size': 1}]}
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(listing).encode()
        with patch.object(agent.urllib.request, 'urlopen', return_value=response):
            self.assertEqual(agent.hub_files('org/model', self.revision), {'model.safetensors': 10, 'tokenizer.json': 1})

        def unavailable(_repo, _revision):
            raise OSError('offline')
        self.prepare(self.serving('org/model'), files=unavailable)

        self.assertIn('Could not size', self.logs[0])

    def test_base_repositories_loaded_with_the_model_are_protected_and_sized(self):
        base = self.cached('org/base', 500, 1)
        stale = self.cached('org/stale', 150, 2)
        kev = {'release': {'model_path': 'org/model', 'model_revision': self.revision,
                           'tokenizer_path': 'org/base', 'tokenizer_revision': self.revision}}
        sized = []

        def files(repo, _revision):
            sized.append(repo)
            return {'model.safetensors': 100, 'config.json': 1}
        self.prepare(kev, files=files)

        self.assertTrue(base.exists())
        self.assertFalse(stale.exists())
        self.assertEqual(sorted(sized), ['org/base', 'org/model'])
        self.assertGreater(agent.last_used(base), 1)

    def test_repositories_of_unpinned_pods_on_the_host_are_protected(self):
        unpinned = self.cached('org/unpinned', 500, 1)
        stale = self.cached('org/stale', 150, 2)
        training = {'kind': 'training', 'recipe': {'model': 'org/unpinned'}}

        self.prepare(self.serving('org/new'), [training])

        self.assertTrue(unpinned.exists())
        self.assertFalse(stale.exists())

    def test_unreadable_pod_state_skips_eviction(self):
        pods = Path(self.directory.name) / 'pods'
        (pods / 'broken').mkdir(parents=True)
        (pods / 'broken' / 'state.json').write_text('{')
        (pods / 'current').mkdir()
        (pods / 'current' / 'state.json').write_text('{')
        with patch.object(agent, 'ROOT', Path(self.directory.name)):
            with self.assertRaises(ValueError):
                agent.host_pods(self.config, 'current')
            (pods / 'broken' / 'state.json').unlink()
            self.assertEqual(agent.host_pods(self.config, 'current'), [])

    def test_pods_and_missing_files_are_read_under_the_cache_lock(self):
        model = self.cached('org/model', 101, 2, ('model.safetensors', 'config.json'))
        stale = self.cached('org/stale', 150, 1)
        seen = []

        def pods():
            # A concurrent start evicted this pod's weights while it waited for the lock.
            seen.append(fcntl_locked(self.home / '.gradiated-cache.lock'))
            shutil.rmtree(model)
            self.sizes.pop(model.name)
            return []
        agent.prepare_model_cache(self.config, self.serving('org/model'), self.home / 'pod', pods,
                                  self.logs.append, lambda _repo, _revision: {'model.safetensors': 100, 'config.json': 1}, self.usage)

        self.assertEqual(seen, [True])
        self.assertFalse(stale.exists())

    def test_profiles_without_pinned_weights_are_ignored(self):
        old = self.cached('org/old', 500, 1)

        self.prepare({'release': {'model_path': 'org/model', 'model_revision': 'main'}})
        self.prepare({'kind': 'training', 'recipe': {}})

        self.assertTrue(old.exists())

if __name__ == '__main__':
    unittest.main()
