import importlib.util
import io
import json
from pathlib import Path
import sys
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

    def test_missing_bad_pressure_never_becomes_zero(self):
        for text in ['', 'sglang:token_usage 0.5', 'sglang:full_token_usage NaN',
                     'sglang:full_token_usage 1.1', 'sglang:full_token_usage -0.1',
                     'sglang:full_token_usage{rank="0"} malformed']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                launch.full_kv_pressure(text)
        self.assertEqual(launch.full_kv_pressure('sglang:full_token_usage{model="a } b"} 0.25 123'), .25)

    def test_warmup_concurrency_bounded_by_front_active_capacity(self):
        self.assertEqual(max(launch.base.CONCURRENCIES), 16)
        supervisor = launch.base.Supervisor(['unused'], max_queued_requests=18)
        maximum = min(supervisor.max_queued_requests, 16)
        self.assertEqual(maximum, 16)
        self.assertEqual(launch.ACTIVE_REQUESTS, 16)

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
