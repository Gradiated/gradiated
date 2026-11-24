import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import service

spec = importlib.util.spec_from_file_location('sglang_launch', HERE / 'launch.py')
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


class Lifecycle(unittest.TestCase):
    def test_router_liveness_does_not_open_warmup_before_worker_readiness(self):
        supervisor = launch.Supervisor(['unused'], runtime_url='http://127.0.0.1:18080')
        supervisor.child = FakeChild(None)
        with patch.object(launch.urllib.request, 'urlopen', return_value=Response(b'')) as get:
            self.assertTrue(supervisor.health())
            self.assertEqual(get.call_args.args[0], 'http://127.0.0.1:18080/readiness')
        class Unready(Response):
            status = 503
        with patch.object(launch.urllib.request, 'urlopen', return_value=Unready(b'')):
            self.assertFalse(supervisor.health())
            supervisor.qualified.set()
            self.assertFalse(supervisor.ready())

    def test_native_metrics_namespaces_and_real_pressure_alias(self):
        backend = b'# HELP process_cpu_seconds_total duplicate\nprocess_cpu_seconds_total 9\n# TYPE sglang:full_token_usage gauge\nsglang:full_token_usage{rank="0"} 0.2\nsglang:full_token_usage{rank="1"} 0.7\nsglang:token_usage 0.9\nsglang:mamba_usage 0.9\n'
        front = b'# HELP process_cpu_seconds_total duplicate\nprocess_cpu_seconds_total 7\n# TYPE smg_http_requests_total counter\nsmg_http_requests_total 3\n'
        with patch.object(launch.urllib.request, 'urlopen', side_effect=[Response(backend), Response(front)]):
            result = launch.metrics({'backend': 18084, 'metrics': 18085}).decode()
        self.assertNotIn('process_cpu_seconds_total', result)
        self.assertIn('sglang:mamba_usage 0.9', result)
        self.assertIn('smg_http_requests_total 3', result)
        self.assertIn('vllm:kv_cache_usage_perc 0.7', result)
        self.assertIn('Compatibility alias:', result)
        self.assertIn('gradiated_runtime_waiting_request_limit 2', result)

    def test_metrics_report_startup_qualification_mode(self):
        backend = b'sglang:full_token_usage{rank="0"} 0.2\n'
        for mode in (None, 'full', 'short', 'short_to_full'):
            with self.subTest(mode=mode), patch.object(launch.urllib.request, 'urlopen',
                                                       side_effect=[Response(backend), Response(b'')]):
                result = launch.metrics({'backend': 18084, 'metrics': 18085}, mode).decode()
                if mode is None:
                    self.assertNotIn('gradiated_runtime_startup_qualification', result)
                else:
                    self.assertIn(f'gradiated_runtime_startup_qualification{{mode="{mode}"}} 1', result)

    def test_qualification_identity_and_record_directory(self):
        config = {'root': Path('/pods/a'), 'front': 18080, 'warmup': 18083, 'backend': 18084, 'metrics': 18085,
                  'profile': 'b300-pcp2', 'active_requests': 12}
        moved = {**config, 'root': Path('/pods/b'), 'front': 28080, 'warmup': 28083, 'backend': 28084, 'metrics': 28085}
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            self.assertIsNone(launch.qualification_identity(config, bundle))
            (bundle / '.bundle-sha256').write_text('not-a-digest\n')
            self.assertIsNone(launch.qualification_identity(config, bundle))
            (bundle / '.bundle-sha256').write_text('a' * 64 + '\n')
            identity = launch.qualification_identity(config, bundle)
            self.assertEqual(identity, {'bundle': 'a' * 64, 'config': {'profile': 'b300-pcp2', 'active_requests': 12}})
            self.assertEqual(launch.qualification_identity(moved, bundle), identity)
            json.dumps(identity)
        self.assertEqual(launch.qualification_records({'XDG_CACHE_HOME': '/home/runtime/.cache'}),
                         Path('/home/runtime/.cache/glm-sglang/qualification'))
        self.assertEqual(launch.qualification_records({'HOME': '/tmp/h'}), Path('/tmp/h/.cache/glm-sglang/qualification'))

    def test_missing_bad_pressure_never_becomes_zero(self):
        for text in ['', 'sglang:token_usage 0.5', 'sglang:full_token_usage NaN',
                     'sglang:full_token_usage 1.1', 'sglang:full_token_usage -0.1',
                     'sglang:full_token_usage{rank="0"} malformed']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                launch.full_kv_pressure(text)
        self.assertEqual(launch.full_kv_pressure('sglang:full_token_usage{model="a } b"} 0.25 123'), .25)

    def test_h200_metrics_report_the_h200_admission_limit(self):
        with patch.object(launch.urllib.request, 'urlopen', side_effect=[
                Response(b'sglang:full_token_usage 0.3\n'), Response(b'smg_http_requests_total 1\n')]):
            result = launch.metrics({'backend': 18084, 'metrics': 18085, 'active_requests': 4}).decode()
        self.assertIn('gradiated_runtime_active_request_limit 4', result)

    def test_wrong_hardware_never_starts_a_backend(self):
        with patch.object(service, 'commands', return_value=({}, [], [])), \
             patch.object(service, 'detect_profile', side_effect=lambda environment: environment), \
             patch.object(service, 'validate_hardware', side_effect=ValueError('Assigned GPUs')), \
             patch.object(service.subprocess, 'Popen') as start:
            with self.assertRaisesRegex(ValueError, 'Assigned GPUs'):
                service.run({})
        start.assert_not_called()

    def test_warmup_concurrency_bounded_by_front_active_capacity(self):
        self.assertEqual(max(launch.base.CONCURRENCIES), 16)
        supervisor = launch.base.Supervisor(['unused'], max_queued_requests=18)
        maximum = min(supervisor.max_queued_requests, 16)
        self.assertEqual(maximum, 16)
        self.assertEqual(launch.ACTIVE_REQUESTS, 12)

    def test_stop_closes_readiness_then_signals_owned_process_group(self):
        supervisor = launch.base.Supervisor(['unused'])
        supervisor.qualified.set()
        child = type('Child', (), {'pid': 1234})()
        supervisor.child = child
        with patch.object(launch.base.os, 'killpg') as kill:
            supervisor.stop()
        self.assertFalse(supervisor.qualified.is_set())
        self.assertTrue(supervisor.stopping.is_set())
        kill.assert_called_once_with(1234, launch.base.signal.SIGTERM)

    def test_failed_component_terminates_other_owned_child(self):
        children = [FakeChild(0), FakeChild(None)]
        service.stop_children(children)
        self.assertFalse(children[0].terminated)
        self.assertTrue(children[1].terminated)
        self.assertTrue(all(child.waited for child in children))

    def test_handler_uses_saved_base_without_recursive_patch(self):
        supervisor = launch.base.Supervisor(['unused'])
        cls = launch.handler(supervisor, {'backend': 18084, 'metrics': 18085})
        self.assertTrue(issubclass(cls, launch.base.http.server.BaseHTTPRequestHandler))


class LiveTuning(unittest.TestCase):
    def config(self, root):
        return {'root': Path(root), 'backend': 18084, 'profile': 'b300-pcp2'}

    def test_live_tuning_is_off_unless_asked(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(service.livetune({}, self.config(root)), (None, {}))
            with self.assertRaisesRegex(ValueError, 'LIVETUNE_MODE'):
                service.livetune({'LIVETUNE_MODE': 'on'}, self.config(root))

    def test_a_canary_ends_replayed_stops_and_records_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            command, environment = service.livetune({'LIVETUNE_MODE': 'canary', 'XDG_CACHE_HOME': '/c'}, self.config(root))
        self.assertIsNone(command)
        # Live variants on, as in production, so the canary measures production's scope.
        self.assertEqual(environment, {'LIVETUNE_REPLAY_STOPS': '1', 'LIVETUNE_LIVE_VARIANTS': '1',
                                       'LIVETUNE_VARIANTS_DIR': '/c/glm-sglang/livetune/variants'})

    def test_a_profile_without_a_policy_records_traffic_and_runs_no_controller(self):
        with tempfile.TemporaryDirectory() as root:
            command, environment = service.livetune({'LIVETUNE_MODE': 'act', 'XDG_CACHE_HOME': '/c'}, self.config(root))
        self.assertIsNone(command)
        self.assertEqual(environment, {'LIVETUNE_TRACE_DIR': '/c/glm-sglang/livetune/trace', 'LIVETUNE_LIVE_VARIANTS': '1',
                                       'LIVETUNE_VARIANTS_DIR': '/c/glm-sglang/livetune/variants'})

    def test_the_bundled_policy_for_the_profile_drives_the_controller(self):
        with tempfile.TemporaryDirectory() as root:
            policy = Path(root, 'glm-sglang/livetune/b300-pcp2.json')
            policy.parent.mkdir(parents=True)
            policy.write_text('{}')
            command, environment = service.livetune({'LIVETUNE_MODE': 'observe', 'HOME': '/h'}, self.config(root))
        self.assertEqual(command[1:5], ['-m', 'livetune.cli', 'control', '--url'])
        self.assertEqual(command[command.index('--policy') + 1], str(policy))
        self.assertEqual(command[command.index('--mode') + 1], 'observe')
        self.assertEqual(environment['LIVETUNE_TRACE_DIR'], '/h/.cache/glm-sglang/livetune/trace')
        # The controller registers the policy's variants where the server resolves them.
        self.assertEqual(command[command.index('--variants-dir') + 1], environment['LIVETUNE_VARIANTS_DIR'])

    def test_a_dying_controller_is_restarted_with_backoff_and_never_stops_serving(self):
        now, started = [0.0], []

        def start(command):
            started.append(now[0])
            return FakeChild(None)

        controller = service.Controller(['livetune'], clock=lambda: now[0], start=start)
        controller.tick()
        for _ in range(4):
            controller.child.code = 1  # exits soon after starting
            now[0] += 1
            controller.tick()
            self.assertIsNone(controller.child)
            now[0] = controller.restart_at
            controller.tick()
        gaps = [b - a for a, b in zip(started, started[1:])]
        self.assertEqual(gaps, [31, 61, 121, 241])
        controller.child.code = 1
        now[0] += 3600  # ran for an hour: a fresh failure, short backoff
        controller.tick()
        self.assertEqual(controller.restart_at - now[0], 30)
        controller.restart_at = now[0]
        controller.tick()
        controller.child.code = 78  # refused its policy: not restarted
        controller.tick()
        now[0] += 10_000
        controller.tick()
        self.assertEqual((controller.child, controller.children()), (None, []))
        def broken(command):
            raise OSError('No such file or directory')

        failing = service.Controller(['livetune'], clock=lambda: now[0], start=broken)
        failing.tick()  # does not raise: serving goes on
        self.assertEqual((failing.child, failing.restart_at - now[0]), (None, 30))
        idle = service.Controller(None, start=start)
        idle.tick()
        self.assertEqual(idle.children(), [])


class Response:
    status = 200
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, limit): return self.body[:limit]


class FakeChild:
    def __init__(self, code): self.code = code; self.terminated = False; self.waited = False
    def poll(self): return self.code
    def terminate(self): self.terminated = True; self.code = 0
    def wait(self, timeout): self.waited = True; return self.code


if __name__ == '__main__':
    unittest.main()
