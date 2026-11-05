import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

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

    def test_h200_selects_hopper_attention_and_bounds_both_admission_layers(self):
        environment = {**self.environment, 'GLM_SGLANG_PROFILE': 'h200-tp2'}
        settings, backend, router = config.commands(environment)
        self.assertEqual(settings['gpu_product'], 'H200')
        for flag, value in [('--dsa-prefill-backend', 'flashmla_sparse'), ('--dsa-decode-backend', 'fa3'),
                            ('--max-running-requests', '4'), ('--cuda-graph-max-bs-decode', '4'),
                            ('--chunked-prefill-size', '4096'), ('--max-prefill-tokens', '4096'),
                            ('--page-size', '256'), ('--tp-size', '2'), ('--moe-runner-backend', 'marlin'),
                            ('--kv-cache-dtype', 'bfloat16')]:
            self.assertEqual(backend[backend.index(flag) + 1], value)
        self.assertNotIn('--enable-prefill-cp', backend)
        self.assertNotIn('--attn-cp-size', backend)
        self.assertEqual(router[router.index('--max-concurrent-requests') + 1], '4')
        self.assertEqual(router[router.index('--queue-size') + 1], '2')

    def test_b200_keeps_blackwell_attention_with_a_smaller_admission_limit(self):
        environment = {**self.environment, 'GLM_SGLANG_PROFILE': 'b200-pcp2'}
        settings, backend, router = config.commands(environment)
        _, b300, _ = config.commands(self.environment)
        self.assertEqual(settings['gpu_product'], 'B200')
        for flag, value in [('--dsa-prefill-backend', 'trtllm'), ('--dsa-decode-backend', 'trtllm'),
                            ('--max-running-requests', '8'), ('--cuda-graph-max-bs-decode', '8'),
                            ('--chunked-prefill-size', '16384'), ('--attn-cp-size', '2')]:
            self.assertEqual(backend[backend.index(flag) + 1], value)
        self.assertIn('--enable-prefill-cp', backend)
        self.assertNotIn('--page-size', backend)
        limits = {'--max-running-requests', '--cuda-graph-max-bs-decode'}
        strip = lambda args: [a for i, a in enumerate(args) if a not in limits and (i == 0 or args[i - 1] not in limits)]
        self.assertEqual(strip(backend), strip(b300))
        self.assertEqual(router[router.index('--max-concurrent-requests') + 1], '8')

    def test_profile_validation_does_not_silently_fall_back(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            config.commands({**self.environment, 'GLM_SGLANG_PROFILE': 'h200'})
        for names, profile, valid in [('NVIDIA H200\nNVIDIA H200\n', 'h200-tp2', True),
                                       ('NVIDIA B300\nNVIDIA B300\n', 'b300-pcp2', True),
                                       ('NVIDIA H200\nNVIDIA H200\n', 'b300-pcp2', False),
                                       ('NVIDIA B300\nNVIDIA B300\n', 'h200-tp2', False),
                                       ('NVIDIA GH200\nNVIDIA GH200\n', 'h200-tp2', False),
                                       ('NVIDIA B200\nNVIDIA B200\n', 'b200-pcp2', True),
                                       ('NVIDIA B200\nNVIDIA B200\n', 'b300-pcp2', False),
                                       ('NVIDIA B300\nNVIDIA B300\n', 'b200-pcp2', False),
                                       ('NVIDIA GB200\nNVIDIA GB200\n', 'b200-pcp2', False)]:
            with self.subTest(names=names, profile=profile), patch.object(config.subprocess, 'run', return_value=SimpleNamespace(stdout=names)) as run:
                environment = {**self.environment, 'GLM_SGLANG_PROFILE': profile}
                if valid:
                    config.validate_hardware(environment)
                else:
                    with self.assertRaisesRegex(ValueError, 'Assigned GPUs'):
                        config.validate_hardware(environment)
                self.assertIn('--id=GPU-a,GPU-b', run.call_args.args[0])

    def test_profile_is_detected_from_assigned_gpus_when_unset(self):
        for names, expected in [('NVIDIA H200\nNVIDIA H200\n', 'h200-tp2'), ('NVIDIA B300 SXM6 AC\nNVIDIA B300 SXM6 AC\n', 'b300-pcp2')]:
            with self.subTest(names=names), patch.object(config.subprocess, 'run', return_value=SimpleNamespace(stdout=names)):
                self.assertEqual(config.detect_profile(self.environment)['GLM_SGLANG_PROFILE'], expected)
        for names in ['NVIDIA GH200\nNVIDIA GH200\n', 'NVIDIA H200\nNVIDIA B300\n', '']:
            with self.subTest(names=names), patch.object(config.subprocess, 'run', return_value=SimpleNamespace(stdout=names)):
                with self.assertRaisesRegex(ValueError, 'hardware profile'):
                    config.detect_profile(self.environment)
        with patch.object(config.subprocess, 'run') as run:
            explicit = {**self.environment, 'GLM_SGLANG_PROFILE': 'h200-tp2'}
            self.assertIs(config.detect_profile(explicit), explicit)
            run.assert_not_called()

    def test_python_entrypoint_has_no_shell_or_external_router(self):
        _, backend, router = config.commands(self.environment)
        self.assertEqual(backend[:3], [str(self.root / 'python/bin/python3'), '-m', 'sglang.launch_server'])
        self.assertEqual(router[:3], [str(self.root / 'python/bin/python3'), '-m', 'smg.launch_router'])
        self.assertEqual(router[router.index('--host') + 1], '127.0.0.1')


if __name__ == '__main__':
    unittest.main()
