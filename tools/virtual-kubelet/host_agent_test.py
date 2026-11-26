import fcntl
import importlib.util
import os
import json
import os
from pathlib import Path
import shutil
import subprocess
import signal
import time
import select
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import uuid

spec = importlib.util.spec_from_file_location('agent', os.environ.get('HOST_AGENT_TEST_SOURCE', Path(__file__).with_name('host-agent.py')))
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class HostAgentTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / 'pods').mkdir()
        (self.root / 'base-id').write_text('test-base\n')
        base = patch.object(agent, 'BASE_ID', self.root / 'base-id', create=True)
        base.start()
        self.addCleanup(base.stop)
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

    @unittest.skipIf("recovery" in Path(agent.__file__).parts, "the frozen recovery agent predates SGLang profiles")
    def test_sglang_hardware_profiles_are_validated_and_allow_proxy_rebuilds(self):
        digest = 'a' * 64
        profile = {'image': self.pod['spec']['containers'][0]['image'], 'warmup': True,
                   'environment': {'GLM_SGLANG_PROFILE': 'h200-tp2'}}
        self.host.config['runtimes'] = {digest: profile}
        for name in ('b300-pcp2', 'b200-pcp2', 'h200-tp2'):
            with self.subTest(profile=name):
                profile['environment']['GLM_SGLANG_PROFILE'] = name
                self.assertEqual(agent.runtime_profile(self.host.config, self.pod)[1], profile)
                with patch.object(self.host, 'states', return_value=[{'pod': self.pod, 'port_base': 38080}]):
                    configuration = self.host.proxy_config()
                self.assertIn(f'location /alloc/{self.uid}/', configuration)
                self.assertIn('proxy_pass http://127.0.0.1:38083/health;', configuration)
        for name in ('', 'h200', 'unknown', 'h200-tp2 extra', 4, None):
            profile['environment']['GLM_SGLANG_PROFILE'] = name
            with self.subTest(invalid_profile=name), self.assertRaises(ValueError):
                agent.runtime_profile(self.host.config, self.pod)

    @unittest.skipIf("recovery" in Path(agent.__file__).parts, "the frozen recovery agent predates prefill budget overrides")
    def test_prefill_budget_must_allow_at_least_four_sequences(self):
        digest = 'a' * 64
        profile = {'image': self.pod['spec']['containers'][0]['image'],
                   'environment': {'GLM_PREFILL_TOKEN_BUDGET': '2048'}}
        config = {**self.config, 'runtimes': {digest: profile}}
        self.assertEqual(agent.runtime_profile(config, self.pod)[1]['environment'],
                         {'GLM_PREFILL_TOKEN_BUDGET': '2048'})
        for value in ('0', '1', '2', '3', '-1', '2048 extra', 2048):
            profile['environment']['GLM_PREFILL_TOKEN_BUDGET'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                agent.runtime_profile(config, self.pod)

    @unittest.skipIf("recovery" in Path(agent.__file__).parts, "the frozen recovery agent predates queue cap overrides")
    def test_queue_caps_and_prefill_threshold_are_validated_before_runtime_launch(self):
        digest = 'a' * 64
        profile = {'image': self.pod['spec']['containers'][0]['image'],
                   'environment': {'MAX_QUEUED_TOKENS': '32768', 'MAX_QUEUED_REQUESTS': '4',
                                   'GLM_LONG_PREFILL_TOKEN_THRESHOLD': '2048', 'GLM_PREFIX_MATCH_UNIT': '128'}}
        config = {**self.config, 'runtimes': {digest: profile}}
        self.assertEqual(agent.runtime_profile(config, self.pod)[1], profile)
        for name in ('MAX_QUEUED_TOKENS', 'MAX_QUEUED_REQUESTS', 'GLM_LONG_PREFILL_TOKEN_THRESHOLD', 'GLM_PREFIX_MATCH_UNIT'):
            for value in ('0', '-1', '1.5', 'bad', 4):
                with self.subTest(name=name, value=value):
                    config['runtimes'][digest] = {**profile, 'environment': {name: value}}
                    with self.assertRaises(ValueError):
                        agent.runtime_profile(config, self.pod)
        config['runtimes'][digest] = {**profile, 'environment': {'GLM_LONG_PREFILL_TOKEN_THRESHOLD': '1048577'}}
        with self.assertRaises(ValueError):
            agent.runtime_profile(config, self.pod)
        for unit in ('3', '256', '1048577', '064', '0128', '08'):
            config['runtimes'][digest] = {**profile, 'environment': {'GLM_PREFIX_MATCH_UNIT': unit}}
            with self.subTest(prefix_unit=unit), self.assertRaises(ValueError):
                agent.runtime_profile(config, self.pod)
        config['runtimes'][digest] = {**profile, 'environment': {'GLM_PREFIX_MATCH_UNIT': '64'}}
        self.assertEqual(agent.runtime_profile(config, self.pod)[1]['environment']['GLM_PREFIX_MATCH_UNIT'], '64')

    def test_task_and_proxy_imports_preserve_the_bundle_with_explicit_environments(self):
        bundle = self.root / 'bundle'
        bundle.mkdir()
        (bundle / 'host_state.py').write_text('healthy = True\n')
        (self.root / 'pods' / self.uid).mkdir()
        cgroup = self.root / 'cgroup'
        cgroup.mkdir()
        (cgroup / 'gradiated-proxy').mkdir()
        (cgroup / 'gradiated-proxy' / 'cgroup.procs').write_text('')
        original_spawn = subprocess.Popen

        def probe(command, **kwargs):
            script = command.index(agent.__file__)
            return original_spawn([*command[:script], '-c', 'import host_state,time; time.sleep(1)'],
                                  **{**kwargs, 'cwd': str(bundle)})

        for mode in ('task', 'proxy'):
            with self.subTest(mode=mode), patch.object(agent.subprocess, 'Popen', side_effect=probe), \
                    patch.object(agent, 'CGROUP', cgroup), \
                    patch.object(agent, 'pod_cgroup', return_value=cgroup / 'unused'), \
                    patch.object(self.host, 'stop'), patch.object(self.host, 'refresh_proxy'):
                if mode == 'task':
                    self.host.ensure_task({'pod': self.pod})
                    process = self.host.children[self.uid]
                else:
                    self.host.ensure_proxy()
                    process = self.host.children['proxy']
                try:
                    self.assertEqual(process.wait(timeout=5), 0)
                    self.assertEqual({path.name for path in bundle.iterdir()}, {'host_state.py'})
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=5)

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

    @unittest.skipUnless(hasattr(agent, 'startup_parts'), 'the frozen recovery agent predates startup parts')
    def test_startup_parts_follow_the_bundles_and_weights_on_disk(self):
        digest, bundle, revision = 'c' * 64, 'd' * 64, 'e' * 40
        home = self.root / 'hf'
        self.host.config = {**self.config, 'hf_home': str(home), 'runtimes': {digest: {
            'image': 'gradiated/kev-bundle@sha256:' + digest, 'bundles': {'test-base': bundle},
            'release': {'model_path': 'org/model', 'model_revision': revision,
                        'tokenizer_path': 'org/model', 'tokenizer_revision': revision}}}}
        self.host.housekeep()
        self.assertEqual(self.request({'operation': 'startup_parts'}), {'parts': []})
        (self.root / 'bundles' / bundle).mkdir(parents=True)
        (self.root / 'bundles' / bundle / '.bundle-sha256').write_text(bundle + '\n')
        repo = agent.repo_directory(home / 'hub', 'org/model')
        snapshot = repo / 'snapshots' / revision
        snapshot.mkdir(parents=True)
        (repo / 'blobs').mkdir()
        (snapshot / 'config.json').write_text('{}')
        (snapshot / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': {'a': 'one.safetensors', 'b': 'two.safetensors'}}))
        (snapshot / 'one.safetensors').write_text('1')
        (repo / 'blobs' / 'two.incomplete').write_text('')
        self.host.housekeep()
        self.assertEqual(self.request({'operation': 'startup_parts'}), {'parts': ['bundle.' + 'c' * 16]})
        (repo / 'blobs' / 'two.incomplete').unlink()
        (snapshot / 'two.safetensors').write_text('2')
        self.host.housekeep()
        self.assertEqual(self.request({'operation': 'startup_parts'})['parts'], ['bundle.' + 'c' * 16, 'weights.' + 'c' * 16])
        shutil.rmtree(repo)
        self.host.housekeep()
        self.assertEqual(self.request({'operation': 'startup_parts'})['parts'], ['bundle.' + 'c' * 16])

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

    @unittest.skipUnless(hasattr(agent, 'UnknownPod'), 'the frozen recovery agent predates unknown-pod reporting')
    def test_real_http_status_of_an_unknown_pod_is_not_a_host_failure(self):
        import threading
        import urllib.error
        import urllib.request
        server = agent.ThreadingHTTPServer(('127.0.0.1', 0), agent.handler_for(self.host, 'synthetic-key'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        payload = {'operation': 'status', 'uid': str(uuid.uuid4()), 'epoch': 1, 'term': self.term}
        request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/_kubelet',
            data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer synthetic-key'})
        try:
            with self.assertRaises(urllib.error.HTTPError) as failure:
                urllib.request.urlopen(request, timeout=2)
            self.assertEqual(failure.exception.code, 404)
            self.assertEqual(json.loads(failure.exception.read()), {'error': 'unknown_pod'})
        finally:
            server.shutdown()
            server.server_close()

    @unittest.skipUnless(hasattr(agent, 'runtime_directory'), 'the frozen recovery agent predates no-follow runtime directories')
    def test_runtime_directories_refuse_links_the_runtime_user_plants(self):
        user = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
        with tempfile.TemporaryDirectory() as root:
            home, outside = Path(root, 'home'), Path(root, 'etc')
            home.mkdir()
            outside.mkdir()
            directory = agent.runtime_directory(user, '.cache', 'gradiated', 'gpu-locks', home=home)
            try:
                with agent.runtime_file(user, directory, '0') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                Path(outside, 'shadow').write_text('root')
                os.symlink(outside / 'shadow', home / '.cache/gradiated/gpu-locks/1')
                os.link(outside / 'shadow', home / '.cache/gradiated/gpu-locks/2')
                with self.assertRaises(OSError):
                    agent.runtime_file(user, directory, '1')
                with self.assertRaisesRegex(ValueError, 'linked runtime file'):
                    agent.runtime_file(user, directory, '2')
            finally:
                os.close(directory)
            self.assertTrue(Path(home, '.cache/gradiated/gpu-locks/0').is_file())
            shutil.rmtree(home / '.cache')
            os.symlink(outside, home / '.cache')
            with self.assertRaises(OSError):
                agent.runtime_directory(user, '.cache', 'gradiated', home=home)
            self.assertEqual(sorted(path.name for path in outside.iterdir()), ['shadow'])
            self.assertEqual(Path(outside, 'shadow').read_text(), 'root')

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

    @unittest.skipUnless(hasattr(agent, 'StaleFence'), 'the frozen recovery agent reports every rejection as 422')
    def test_real_http_reports_stale_fencing_apart_from_invalid_operations(self):
        import threading
        import urllib.error
        import urllib.request
        server = agent.ThreadingHTTPServer(('127.0.0.1', 0), agent.handler_for(self.host, 'synthetic-key'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def post(payload):
            request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/_kubelet',
                data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer synthetic-key'})
            try:
                with urllib.request.urlopen(request, timeout=2) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as failure:
                return failure.code, json.loads(failure.read())
        try:
            stale = (409, {'error': 'stale_epoch'})
            self.assertEqual(post({'operation': 'list', 'epoch': 1, 'term': self.term}), (200, []))
            self.assertEqual(post({'operation': 'list', 'epoch': 2, 'term': self.term}), stale)
            self.assertEqual(post({'operation': 'list', 'epoch': 1, 'term': str(uuid.uuid4())}), stale)
            invalid = (422, {'error': 'invalid_host_operation'})
            self.assertEqual(post({'operation': 'list', 'term': self.term}), invalid)
            self.assertEqual(post({'operation': 'reboot', 'epoch': 1, 'term': self.term}), invalid)
            self.assertEqual(post({'operation': 'claim', 'epoch': 0, 'term': str(uuid.uuid4())}), invalid)
            # A re-image starts the host with no fence file.
            (self.root / 'fence.json').unlink()
            self.assertEqual(post({'operation': 'list', 'epoch': 1, 'term': self.term}), stale)
            self.assertEqual(post({'operation': 'fence'}), (200, {'epoch': 0}))
            self.assertEqual(post({'operation': 'claim', 'epoch': 0, 'term': self.term}), (200, {'epoch': 1}))
            self.assertEqual(post({'operation': 'list', 'epoch': 1, 'term': self.term}), (200, []))
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
        self.assertEqual([{key: value[key] for key in ('instance_id', 'epoch')} for value in result],
                         [{'instance_id': self.config['instance_id'], 'epoch': 1}])

    def test_catalogue_stages_before_activation_and_preserves_active_profiles(self):
        import time
        digest = 'a' * 64
        marker = self.root / 'bundles' / digest / '.bundle-sha256'
        marker.parent.mkdir(parents=True)
        marker.write_text(digest)
        state = self.root / 'pods' / self.uid
        state.mkdir()
        (state / 'state.json').write_text(json.dumps({'pod': self.pod}))
        profile = {'image': self.pod['spec']['containers'][0]['image'], 'bundles': {'test-base': digest},
                   'model_id': 'kev', 'release': self.config['release'], 'gpus': 1, 'cpu': '16', 'memory': '64Gi'}
        self.request({'operation': 'configure', 'epoch': 1, 'runtimes': {digest: profile}})
        deadline = time.monotonic() + 2
        while not self.host.catalogue_ready and time.monotonic() < deadline: time.sleep(.01)
        self.assertTrue(self.host.catalogue_ready)
        self.assertEqual(self.host.config['runtimes'][digest]['release'], self.config['release'])
        self.assertEqual(self.host.config['gpu_uuids'], ['GPU-test-0'])

    def wait_for_catalogue(self):
        import time
        deadline = time.monotonic() + 2
        while not self.host.catalogue_ready and time.monotonic() < deadline: time.sleep(.01)
        self.assertTrue(self.host.catalogue_ready)

    @unittest.skipUnless(hasattr(agent, 'runtime_bundle'), 'the frozen recovery agent predates per-base bundles')
    def test_catalogue_stages_the_bundle_built_for_the_host_base(self):
        release, bundle, other = '9' * 64, 'b' * 64, 'c' * 64
        image = 'gradiated/kev-bundle@sha256:' + release
        fetched = []

        def fetch(command, **kwargs):
            digest, destination = command[-2], Path(command[-1])
            fetched.append(digest)
            destination.mkdir(parents=True)
            (destination / '.bundle-sha256').write_text(digest)

        profile = {'image': image, 'bundles': {'old-base': other, 'test-base': bundle}, 'model_id': 'kev',
                   'release': self.config['release'], 'gpus': 1, 'cpu': '16', 'memory': '64Gi'}
        with patch.object(agent.subprocess, 'run', side_effect=fetch):
            self.request({'operation': 'configure', 'epoch': 1, 'runtimes': {release: profile}})
            self.wait_for_catalogue()
        self.assertEqual(fetched, [bundle])
        self.assertEqual(agent.runtime_bundle(self.host.config['runtimes'][release]), bundle)
        (self.root / 'base-id').write_text('new-base\n')
        with self.assertRaisesRegex(ValueError, 'no bundle for base new-base'):
            agent.runtime_bundle(profile)

    @unittest.skipUnless(hasattr(agent, 'runtime_bundle'), 'the frozen recovery agent predates per-base bundles')
    def test_release_without_a_bundle_for_the_host_base_is_not_staged(self):
        release = '9' * 64
        profile = {'image': 'gradiated/kev-bundle@sha256:' + release, 'bundles': {'old-base': release},
                   'model_id': 'kev', 'release': self.config['release'], 'gpus': 1, 'cpu': '16', 'memory': '64Gi'}
        with patch.object(agent.subprocess, 'run') as fetch:
            self.request({'operation': 'configure', 'epoch': 1, 'runtimes': {release: profile}})
            self.wait_for_catalogue()
        fetch.assert_not_called()
        self.assertEqual(self.host.config['runtimes'], {})
        for invalid in ({**profile, 'bundles': None}, {**profile, 'bundles': {'test-base': '../escape'}}):
            with self.subTest(bundles=invalid['bundles']), self.assertRaises(ValueError):
                self.request({'operation': 'configure', 'epoch': 1, 'runtimes': {release: invalid}})

    @unittest.skipUnless(hasattr(agent, 'runtime_bundle'), 'the frozen recovery agent predates per-base bundles')
    def test_cleanup_keeps_the_bundle_each_release_built_for_the_host_base(self):
        import os
        bundles = self.root / 'bundles'
        bundles.mkdir()
        for index, letter in enumerate('bcdef'):
            path = bundles / (letter * 64)
            path.mkdir()
            (path / '.bundle-sha256').write_text(path.name)
            os.utime(path, (index, index))
        self.config['runtimes'] = {'9' * 64: {'image': 'gradiated/kev-bundle@sha256:' + '9' * 64,
                                              'bundles': {'old-base': 'c' * 64, 'test-base': 'b' * 64}}}
        self.host.housekeep(10 * 86400)
        # The oldest directory survives only because it is this base's bundle.
        self.assertEqual({path.name for path in bundles.iterdir()}, {letter * 64 for letter in 'bef'})

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

    def proxy_process(self, path, start_new_session=False):
        process = subprocess.Popen(['python3', '-c', 'import time;print("ready",flush=True);time.sleep(60)', str(path)],
                                   stdout=subprocess.PIPE, start_new_session=start_new_session)
        try:
            self.assertTrue(select.select([process.stdout], [], [], 5)[0], 'Proxy fixture did not start')
            self.assertEqual(process.stdout.readline(), b'ready\n')
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            process.stdout.close()
        return process

    def test_configuration_validation_preserves_the_live_proxy_pid(self):
        proxy = self.root / 'proxy'
        proxy.mkdir()
        process = self.proxy_process(self.root / 'nginx.conf', start_new_session=True)
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
        process = self.proxy_process(path)
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
        # Production gateway generation budget (GATEWAY_GENERATION_TIMEOUT_SECONDS in Gradiated/infrastructure).
        request_limit = 630
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

    @unittest.skipIf("recovery" in Path(agent.__file__).parts, "the frozen recovery agent predates admitted request preservation")
    def test_memory_request_rollout_preserves_reconciliation_and_drain_of_admitted_pods(self):
        import copy
        self.config['runtimes'] = {'a' * 64: {
            'image': self.pod['spec']['containers'][0]['image'], 'model_id': 'kev',
            'release': self.config['release'], 'gpus': 1, 'cpu': '16', 'memory': '64Gi',
            'request_memory': '32Gi', 'startup_timeout': 1800}}
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        agent.atomic_json(directory / 'state.json', {'pod': self.pod})
        # The admitted pod still requests 48 GiB despite the new 32 GiB profile.
        with patch.object(self.host, 'ensure_task'), patch.object(self.host, 'refresh_proxy'):
            self.assertEqual(self.request({'operation': 'create', 'epoch': 1,
                                           'uid': self.uid, 'pod': self.pod}), {'created': True})
            with patch.object(agent.threading.Thread, 'start'):
                self.assertEqual(self.request({'operation': 'delete', 'epoch': 1,
                                               'uid': self.uid, 'pod': self.pod}), {'deleted': False})
        self.assertTrue(json.loads((directory / 'state.json').read_text())['draining'])
        changed = copy.deepcopy(self.pod)
        changed['spec']['containers'][0]['resources']['requests']['memory'] = '32Gi'
        with self.assertRaises(ValueError):
            self.host.validate(changed)
        fresh = copy.deepcopy(self.pod)
        fresh['metadata']['uid'] = str(uuid.uuid4())
        with self.assertRaises(ValueError):
            self.host.validate(fresh)
        fresh['spec']['containers'][0]['resources']['requests']['memory'] = '32Gi'
        self.assertEqual(self.host.validate(fresh), fresh['metadata']['uid'])
        fresh['spec']['containers'][0]['resources']['limits']['memory'] = '128Gi'
        with self.assertRaises(ValueError):
            self.host.validate(fresh)

    @unittest.skipUnless(hasattr(agent, 'runtime_bundle'), 'requires per-base bundles')
    def test_distinct_resource_profiles_share_bundle_and_preserve_existing_requests(self):
        import copy
        original = agent.runtime_profile(self.config, self.pod)[1]
        compact = {**copy.deepcopy(original),
                   'image': 'gradiated/kev-bundle@sha256:' + 'b' * 64,
                   'request_memory': '32Gi'}
        self.host.config = {**self.config, 'runtimes': {
            'a' * 64: original, 'b' * 64: compact}}
        candidate = copy.deepcopy(self.pod)
        candidate['metadata']['uid'] = str(uuid.uuid4())
        candidate['spec']['containers'][0]['image'] = compact['image']
        candidate['spec']['containers'][0]['resources']['requests']['memory'] = '32Gi'
        self.assertEqual(self.host.validate(candidate), candidate['metadata']['uid'])
        self.assertEqual(self.host.validate(self.pod), self.uid)
        self.assertEqual(agent.runtime_bundle(original), agent.runtime_bundle(compact))
        self.assertEqual(agent.runtime_bundle(compact), 'a' * 64)
        candidate['spec']['containers'][0]['resources']['requests']['memory'] = '48Gi'
        with self.assertRaises(ValueError):
            self.host.validate(candidate)
        candidate['spec']['containers'][0]['resources']['requests']['memory'] = '32Gi'
        candidate['spec']['containers'][0]['resources']['limits']['memory'] = '128Gi'
        with self.assertRaises(ValueError):
            self.host.validate(candidate)

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

    @unittest.skipIf("recovery" in Path(agent.__file__).parts, "the frozen recovery agent predates weighted routing")
    def test_reporter_environment_carries_the_runtime_active_request_limit(self):
        profile = {'model_id': 'glm', 'release': {'runtime_revision': 'glm-a', 'model_revision': 'rev'}}
        reporting = agent.reporter_environment(profile, self.uid, 38080, '/usr/bin')
        self.assertNotIn('DESMOND_ACTIVE_REQUESTS', reporting)
        self.assertEqual(reporting['DESMOND_RUNTIME_PORT'], '38080')
        reporting = agent.reporter_environment({**profile, 'active_requests': 16, 'warmup': True}, self.uid, 38080, '/usr/bin')
        self.assertEqual(reporting['DESMOND_ACTIVE_REQUESTS'], '16')
        self.assertEqual(reporting['DESMOND_RUNTIME_PORT'], '38083')

    @unittest.skipIf("recovery" in Path(agent.__file__).parts, "the frozen recovery agent predates weighted routing")
    def test_runtime_active_request_limit_must_be_a_bounded_integer(self):
        digest = 'a' * 64
        image = self.pod['spec']['containers'][0]['image']
        config = {**self.config, 'runtimes': {digest: {'image': image, 'active_requests': 4}}}
        self.assertEqual(agent.runtime_profile(config, self.pod)[1]['active_requests'], 4)
        # Desmond refuses these, and a reporter that cannot start takes its pod down.
        for value in (0, 4097, '4', 4.0, True, None):
            config['runtimes'][digest]['active_requests'] = value
            with self.assertRaises(ValueError):
                agent.runtime_profile(config, self.pod)

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


@unittest.skipUnless(hasattr(agent.Agent, 'wait_for_drain'), 'the frozen recovery agent uses a fixed drain')
class DrainTest(unittest.TestCase):
    setUp = HostAgentTest.setUp
    tearDown = HostAgentTest.tearDown
    request = HostAgentTest.request

    def test_draining_proxy_rejects_all_new_allocation_requests(self):
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        agent.atomic_json(directory / 'state.json', {'pod': self.pod, 'draining': True})
        configuration = self.host.proxy_config()
        self.assertIn(f'location /alloc/{self.uid}/ {{ return 503; }}', configuration)
        self.assertIn(f'location = /_draining/{self.uid} {{ return 200 "$pid"; }}', configuration)
        self.assertNotIn(f'proxy_pass http://127.0.0.1:38080/', configuration)

    def test_drain_releases_early_only_when_proxy_confirms_requests_finished(self):
        self.check_wait([False, False, True], elapsed=2)

    def test_unverifiable_proxy_keeps_the_original_maximum_drain(self):
        self.check_wait([False] * 660, elapsed=660)

    def test_agent_restart_preserves_the_remaining_deadline(self):
        self.check_wait([False] * 10, elapsed=10, started=350)

    def test_expired_and_unqualified_drains_do_not_wait(self):
        self.check_wait([], elapsed=0, started=0)
        self.check_wait([], elapsed=0, duration=0)

    def test_dead_task_does_not_delay_orphan_cleanup(self):
        self.check_wait([], elapsed=0, live=False)

    def test_early_drain_does_not_release_a_claim_when_process_cleanup_fails(self):
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        state = {'pod': self.pod, 'draining': True, 'drain_started_at': 0}
        agent.atomic_json(directory / 'state.json', state)
        group = self.root / 'cgroup'
        group.mkdir()
        (group / 'cgroup.procs').write_text('1234')
        clock = [0]
        def sleep(seconds):
            clock[0] += seconds
        with patch.object(self.host, 'wait_for_drain'), patch.object(self.host, 'stop'), \
                patch.object(agent, 'pod_cgroup', return_value=group), \
                patch.object(agent.time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(agent.time, 'sleep', side_effect=sleep), \
                patch.object(self.host, 'refresh_proxy') as refresh:
            with self.assertRaisesRegex(RuntimeError, 'GPU claim retained'):
                self.host.drain(self.uid)
        self.assertEqual(json.loads((directory / 'state.json').read_text()), state)
        self.assertEqual((group / 'cgroup.kill').read_text(), '1')
        refresh.assert_not_called()

    def check_wait(self, responses, elapsed, started=1000, duration=660, live=True):
        clock = [0]
        def sleep(seconds):
            clock[0] += seconds
        with patch.object(agent.time, 'time', return_value=1000), \
                patch.object(agent.time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(agent.time, 'sleep', side_effect=sleep), \
                patch.object(agent, 'alive', return_value=live), \
                patch.object(self.host, 'proxy_drained', side_effect=responses) as drained:
            self.host.wait_for_drain(self.uid, {'drain_started_at': started, 'drain_seconds': duration})
        self.assertEqual(clock[0], elapsed)
        self.assertEqual(drained.call_count, len(responses))

    def test_unavailable_or_invalid_proxy_acknowledgement_is_not_empty(self):
        import urllib.error
        for error in (OSError('unavailable'), urllib.error.HTTPError('test', 404, 'missing', {}, None)):
            with self.subTest(error=error), patch.object(agent.urllib.request, 'build_opener') as opener:
                opener.return_value.open.side_effect = error
                self.assertFalse(self.host.proxy_drained(self.uid))
        for status, body in ((503, b'1'), (200, b'invalid'), (200, b'1234')):
            with self.subTest(status=status, body=body), patch.object(agent.urllib.request, 'build_opener') as opener:
                response = opener.return_value.open.return_value.__enter__.return_value
                response.status, response.read.return_value = status, body
                self.assertFalse(self.host.proxy_drained(self.uid))

    def test_proxy_drain_requires_its_only_worker_and_a_stable_master(self):
        proxy = self.root / 'proxy'
        proxy.mkdir()
        (proxy / 'nginx.pid').write_text('100')
        master = self.root / 'proc/100'
        (master / 'task/100').mkdir(parents=True)
        children = master / 'task/100/children'
        children.write_text('200')
        command = master / 'cmdline'
        command.write_bytes(b'nginx: master process -c ' + str(self.root / 'nginx.conf').encode())
        worker = self.root / 'proc/200'
        worker.mkdir()
        (worker / 'cmdline').write_bytes(b'nginx: worker process')

        def proc_path(path):
            return self.root / path.lstrip('/') if str(path).startswith('/proc/') else Path(path)

        with patch.object(agent.urllib.request, 'build_opener') as opener, \
                patch.object(agent, 'Path', side_effect=proc_path), \
                patch.object(agent, 'process_birth', return_value='stable') as birth:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.status, response.read.return_value = 200, b'200'
            self.assertTrue(self.host.proxy_drained(self.uid))
            for value in ('200 201', '', '201'):
                children.write_text(value)
                self.assertFalse(self.host.proxy_drained(self.uid))
            children.write_text('200')
            birth.side_effect = ['stable', 'stable', 'reused']
            self.assertFalse(self.host.proxy_drained(self.uid))
            birth.side_effect = None
            command.write_bytes(b'unrelated master')
            self.assertFalse(self.host.proxy_drained(self.uid))

    @unittest.skipUnless(shutil.which('nginx'), 'Nginx is required for the real proxy drain test')
    def test_real_proxy_preserves_streams_queued_requests_and_partial_uploads(self):
        import http.client
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        import time
        entered = {name: threading.Event() for name in ('stream', 'queued', 'upload')}
        release = {name: threading.Event() for name in ('stream', 'queued')}
        failures = []

        class Runtime(BaseHTTPRequestHandler):
            def do_GET(self):
                name = self.path.strip('/')
                if name not in entered:
                    self.send_response(200)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                entered[name].set()
                if name == 'queued':
                    release[name].wait(10)
                self.send_response(200)
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'A')
                self.wfile.flush()
                if name == 'stream':
                    release[name].wait(10)
                self.wfile.write(b'B')

            def do_POST(self):
                entered['upload'].set()
                body = self.rfile.read(2)
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        runtime = ThreadingHTTPServer(('127.0.0.1', 0), Runtime)
        runtime.daemon_threads = True
        thread = threading.Thread(target=runtime.serve_forever, daemon=True)
        thread.start()
        task = subprocess.Popen(['sleep', '120'], start_new_session=True)
        directory = self.root / 'pods' / self.uid
        directory.mkdir()
        state = {'pod': self.pod, 'port_base': runtime.server_port, 'task': agent.owner(task),
                 'drain_started_at': time.time(), 'drain_seconds': agent.REQUEST_DRAIN_SECONDS}
        agent.atomic_json(directory / 'state.json', state)
        proxy = self.root / 'proxy'
        proxy.mkdir()
        for name in ('body', 'temp'):
            (proxy / name).mkdir()
        self.host.refresh_proxy()
        command = ['nginx', '-c', str(self.root / 'nginx.conf'), '-g',
                   'daemon off;' + (' user root;' if os.geteuid() == 0 else '')]
        log = (self.root / 'nginx.log').open('wb')
        process = subprocess.Popen(command, stdout=log, stderr=log)
        connections = []

        def connect():
            connection = http.client.HTTPConnection('127.0.0.1', 8889, timeout=10)
            connections.append(connection)
            return connection

        def queued_request():
            try:
                connection = connect()
                connection.request('GET', f'/alloc/{self.uid}/queued')
                self.assertEqual(connection.getresponse().read(), b'AB')
            except BaseException as error:
                failures.append(error)

        try:
            deadline = time.monotonic() + 5
            while not agent.health(8889, '/healthz') and time.monotonic() < deadline:
                self.assertIsNone(process.poll(), (self.root / 'nginx.log').read_text())
                time.sleep(.02)
            stream = connect()
            stream.request('GET', f'/alloc/{self.uid}/stream')
            stream_response = stream.getresponse()
            self.assertEqual(stream_response.read(1), b'A')
            queued = threading.Thread(target=queued_request)
            queued.start()
            self.assertTrue(entered['queued'].wait(2))
            upload = connect()
            upload.putrequest('POST', f'/alloc/{self.uid}/upload')
            upload.putheader('Content-Length', '2')
            upload.endheaders(b'A')
            self.assertTrue(entered['upload'].wait(2))
            agent.atomic_json(directory / 'state.json', {**state, 'draining': True})
            self.host.refresh_proxy()
            deadline = time.monotonic() + 5
            while not agent.health(8889, f'/_draining/{self.uid}') and time.monotonic() < deadline:
                time.sleep(.02)
            deadline = time.monotonic() + 5
            while True:
                rejected = connect()
                rejected.request('GET', f'/alloc/{self.uid}/new')
                response = rejected.getresponse()
                status = response.status
                response.read()
                rejected.close()
                if status == 503 or time.monotonic() >= deadline:
                    break
                time.sleep(.02)
            self.assertEqual(status, 503)
            self.assertFalse(self.host.proxy_drained(self.uid))
            restarted = agent.Agent(self.config, self.root)
            restarted.refresh_proxy()
            self.assertFalse(restarted.proxy_drained(self.uid))
            with patch.object(restarted, 'stop') as stop, \
                    patch.object(agent, 'pod_cgroup', return_value=self.root / 'no-cgroup'):
                draining = threading.Thread(target=restarted.drain, args=(self.uid,), daemon=True)
                draining.start()
                release['stream'].set()
                self.assertEqual(stream_response.read(), b'B')
                stop.assert_not_called()
                self.assertFalse(restarted.proxy_drained(self.uid))
                release['queued'].set()
                queued.join(2)
                self.assertFalse(queued.is_alive())
                self.assertEqual(failures, [])
                self.assertFalse(restarted.proxy_drained(self.uid))
                stop.assert_not_called()
                self.assertTrue((directory / 'state.json').exists())
                upload.send(b'B')
                self.assertEqual(upload.getresponse().read(), b'AB')
                draining.join(5)
                self.assertFalse(draining.is_alive())
                stop.assert_called_once()
                self.assertFalse((directory / 'state.json').exists())
        finally:
            for event in release.values():
                event.set()
            for connection in connections:
                connection.close()
            process.terminate()
            process.wait(timeout=5)
            log.close()
            runtime.shutdown()
            runtime.server_close()
            thread.join(2)
            task.terminate()
            task.wait(timeout=5)


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

    def prepare(self, profile, pods=(), files=lambda _repo, _revision: {'model.safetensors': (100, None), 'config.json': (1, None)}):
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
        listing = {'siblings': [{'rfilename': 'model.safetensors', 'size': 10, 'blobId': 'b' * 40,
                                 'lfs': {'sha256': 'c' * 64, 'size': 10}},
                                {'rfilename': 'pytorch_model.bin', 'size': 10},
                                {'rfilename': 'tokenizer.json', 'size': 1, 'blobId': 'd' * 40}]}
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(listing).encode()
        with patch.object(agent.urllib.request, 'urlopen', return_value=response):
            self.assertEqual(agent.hub_files('org/model', self.revision), {'model.safetensors': (10, 'c' * 64), 'tokenizer.json': (1, 'd' * 40)})

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
            return {'model.safetensors': (100, None), 'config.json': (1, None)}
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
                                  self.logs.append, lambda _repo, _revision: {'model.safetensors': (100, None), 'config.json': (1, None)}, self.usage)

        self.assertEqual(seen, [True])
        self.assertFalse(stale.exists())

    def test_blobs_cached_by_another_revision_are_not_counted_as_missing(self):
        model = self.cached('org/model', 101, 2)
        (model / 'blobs').mkdir()
        (model / 'blobs' / ('c' * 64)).write_bytes(b'x')
        stale = self.cached('org/stale', 150, 1)
        listing = lambda _repo, _revision: {'model.safetensors': (100, 'c' * 64), 'config.json': (1, 'd' * 40)}

        self.assertEqual(agent.missing_bytes(self.hub, 'org/model', 'e' * 40, listing(None, None)), 1)
        self.free = 1
        self.prepare(self.serving('org/model', 'e' * 40), files=listing)

        self.assertTrue(stale.exists())

    def shared_blob(self, blob, age=7200):
        path = self.hub / 'blobs' / blob[:2] / blob
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x')
        os.utime(path, (time.time() - age, time.time() - age))
        return path

    def link(self, directory, name, blob):
        link = directory / 'snapshots' / self.revision / name
        link.unlink(missing_ok=True)
        link.symlink_to(blob)

    @unittest.skipUnless(hasattr(agent, 'prune_shared_blobs'), 'the frozen recovery agent predates the shared blob store')
    def test_evicting_a_model_frees_its_blobs_in_the_shared_store(self):
        old = self.cached('org/old', 60, 1)
        kept = self.cached('org/kept', 60, 5)
        old_blob, kept_blob = self.shared_blob('a' * 64), self.shared_blob('b' * 64)
        self.link(old, 'model.safetensors', old_blob)
        self.link(kept, 'model.safetensors', kept_blob)
        downloading = self.shared_blob('c' * 64, age=10)
        incomplete = self.shared_blob('d' * 64 + '.incomplete')
        self.free = 50  # evicting org/old (60) is enough for the 101-byte pull

        self.prepare(self.serving('org/new'))

        self.assertFalse(old.exists())
        self.assertFalse(old_blob.exists())
        self.assertTrue(kept_blob.exists())
        self.assertTrue(downloading.exists())
        self.assertTrue(incomplete.exists())
        self.assertIn('Removed 1 unlinked shared blobs (1 bytes)', self.logs)

    @unittest.skipUnless(hasattr(agent, 'prune_shared_blobs'), 'the frozen recovery agent predates the shared blob store')
    def test_blob_in_the_shared_store_is_not_counted_as_missing(self):
        self.shared_blob('c' * 64)
        listing = {'model.safetensors': (100, 'c' * 64), 'config.json': (1, 'd' * 40)}

        self.assertEqual(agent.missing_bytes(self.hub, 'org/model', 'e' * 40, listing), 1)

    def test_profiles_without_pinned_weights_are_ignored(self):
        old = self.cached('org/old', 500, 1)

        self.prepare({'release': {'model_path': 'org/model', 'model_revision': 'main'}})
        self.prepare({'kind': 'training', 'recipe': {}})

        self.assertTrue(old.exists())

if __name__ == '__main__':
    unittest.main()
