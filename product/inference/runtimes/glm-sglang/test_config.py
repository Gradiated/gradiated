import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config


class Configuration(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        candidate = HERE.parents[1] / 'bundles/glm-5-3-flash-sglang/model-config.json'
        if not candidate.is_file():
            candidate = HERE.parents[0] / 'model-config.json'
        (self.root / 'model-config.json').write_bytes(candidate.read_bytes())
        self.environment = {'GRADIATED_RUNTIME_ROOT': str(self.root), 'NVIDIA_VISIBLE_DEVICES': 'GPU-a,GPU-b',
                            'RUNTIME_PORT': '18080', 'WARMUP_PORT': '18083', 'TENSOR_PARALLEL_SIZE': '2'}

    def tearDown(self):
        self.directory.cleanup()

    def test_measured_pcp_marlin_and_native_front(self):
        settings, backend, router = config.commands(self.environment)
        for key, value in [('--tp-size', '2'), ('--attn-cp-size', '2'), ('--moe-runner-backend', 'marlin'),
                           ('--max-running-requests', '16'), ('--chunked-prefill-size', '16384'),
                           ('--max-prefill-tokens', '16384'), ('--prefill-decode-interval', '64'),
                           ('--speculative-num-steps', '2'), ('--speculative-num-draft-tokens', '3'),
                           ('--revision', config.REVISION), ('--schedule-policy', 'shortest-prefill-first')]:
            self.assertEqual(backend[backend.index(key) + 1], value)
        self.assertNotIn('--max-queued-requests', backend)
        self.assertNotIn('--disable-radix-cache', backend)
        self.assertNotIn('--disaggregation-mode', backend)
        self.assertNotIn('--disable-flashinfer-autotune', backend)
        for key, value in [('--max-concurrent-requests', '16'), ('--queue-size', '2'),
                           ('--queue-timeout-secs', '60'), ('--rate-limit-tokens-per-second', '0')]:
            self.assertEqual(router[router.index(key) + 1], value)
        self.assertIn('--disable-retries', router)
        self.assertEqual(settings['backend'], 18084)
        self.assertEqual(settings['metrics'], 18085)
        self.assertEqual(router[router.index('--worker-urls') + 1], 'http://127.0.0.1:18084')

    def test_invalid_devices_tp_adapters_and_port_collisions_fail(self):
        for delta in [{'NVIDIA_VISIBLE_DEVICES': 'GPU-a'}, {'NVIDIA_VISIBLE_DEVICES': 'GPU-a,GPU-a'},
                      {'TENSOR_PARALLEL_SIZE': '1'}, {'LORA_ENABLED': 'true'}, {'WARMUP_PORT': '18081'},
                      {'WARMUP_PORT': '18084'}, {'RUNTIME_PORT': '65532'}, {'MAX_QUEUED_REQUESTS': '6'}, {'MAX_QUEUED_TOKENS': '1000'}]:
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                config.commands({**self.environment, **delta})

    def test_python_entrypoint_has_no_shell_or_external_router(self):
        _, backend, router = config.commands(self.environment)
        self.assertEqual(backend[:3], [str(self.root / 'python/bin/python3'), '-m', 'sglang.launch_server'])
        self.assertEqual(router[:3], [str(self.root / 'python/bin/python3'), '-m', 'smg.launch_router'])
        self.assertEqual(router[router.index('--host') + 1], '127.0.0.1')


if __name__ == '__main__':
    unittest.main()
