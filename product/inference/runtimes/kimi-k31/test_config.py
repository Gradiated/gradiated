import importlib.util
import math
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('kimi_config', Path(__file__).with_name('config.py'))
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class Configuration(unittest.TestCase):
    def setUp(self):
        self.environment = {'GRADIATED_RUNTIME_ROOT': '/runtime',
                            'NVIDIA_VISIBLE_DEVICES': ','.join(f'GPU-{i}' for i in range(8)),
                            'RUNTIME_PORT': '18080', 'WARMUP_PORT': '18083'}

    def test_exact_checkpoint_and_bounded_admission(self):
        settings, backend, router = config.commands(self.environment)
        for flag, value in [('--model-path', config.MODEL), ('--revision', config.REVISION),
                            ('--tp-size', '8'), ('--reasoning-parser', 'kimi_k3'),
                            ('--tool-call-parser', 'kimi_k3'), ('--mem-fraction-static', '0.85'),
                            ('--max-running-requests', '5'), ('--cuda-graph-max-bs-decode', '5'),
                            ('--context-length', '1048576'), ('--chunked-prefill-size', '8192'),
                            ('--max-prefill-tokens', '8192'),
                            ('--mamba-full-memory-ratio', '0.45'), ('--prefill-decode-interval', '4'),
                            ('--prefill-decode-interval-min-bs', '1'),
                            ('--schedule-policy', 'shortest-prefill-first')]:
            self.assertEqual(backend[backend.index(flag) + 1], value)
        self.assertIn('--trust-remote-code', backend)
        self.assertNotIn('--dtype', backend)
        self.assertNotIn('--quantization', backend)
        self.assertEqual(backend[backend.index('--moe-runner-backend') + 1], 'flashinfer_mxfp4')
        self.assertEqual(backend[backend.index('--flashinfer-mxfp4-moe-precision') + 1], 'default')
        self.assertEqual(settings['active_requests'], 5)
        self.assertEqual(router[router.index('--max-concurrent-requests') + 1], '5')
        self.assertNotIn('--enable-cache-report', backend)
        self.assertNotIn('--disable-radix-cache', backend)
        self.assertNotIn('--enable-mixed-chunk', backend)
        self.assertEqual(settings['backend'], 18084)
        self.assertEqual(router[router.index('--queue-size') + 1], '0')
        self.assertIn('--disable-retries', router)

    def test_maximum_output_has_time_for_floor_rate_decode_and_prefill(self):
        _, _, router = config.commands(self.environment)
        timeout = int(router[router.index('--request-timeout-secs') + 1])
        self.assertGreaterEqual(timeout, math.ceil(config.MAX_OUTPUT_TOKENS / 80) + 600)

    def test_backend_caps_unlimited_requests_at_the_catalog_maximum(self):
        environment = config.backend_environment({'PATH': '/bin'})
        self.assertEqual(environment['SGLANG_MAX_NEW_TOKENS_LIMIT'], '131072')
        self.assertEqual(environment['PATH'], '/bin')

    def test_pinned_draft_and_sampling_correctness_geometry(self):
        _, backend, _ = config.commands(self.environment)
        for flag, value in [('--speculative-algorithm', 'DFLASH'),
                            ('--speculative-draft-model-path', '/runtime/models/kimi-dflash'),
                            ('--speculative-draft-model-revision', 'd0d8bc2e3c6d0a195d2e00a49017e71ca8d881f1'),
                            ('--speculative-draft-attention-backend', 'cutedsl_mla'),
                            ('--speculative-dflash-block-size', '5'), ('--mamba-ssm-dtype', 'float32')]:
            self.assertEqual(backend[backend.index(flag) + 1], value)
        self.assertIn('--disable-overlap-schedule', backend)
        self.assertIn('--enable-linear-replayssm-spec', backend)
        for unsafe in ['--enable-nvidia-megakernel', '--speculative-use-block-verification',
                       '--enable-symm-mem', '--enable-deterministic-inference', '--kv-cache-dtype',
                       '--dcp-size', '--ep-size', '--enable-int8-mamba-checkpoint',
                       '--speculative-draft-kv-cache-dtype']:
            self.assertNotIn(unsafe, backend)

    def test_yetalabs_abliterated_model_id_selects_pinned_open_checkpoint_and_tuned_profile(self):
        for model_id in (config.CYBER_MODEL_ID, config.ABLITERATED_MODEL_ID):
            with self.subTest(model_id=model_id):
                settings, backend, router = config.commands({**self.environment, 'MODEL_ID': model_id})
                self.assertEqual(settings['model_id'], model_id)
                self.assertEqual(settings['model'], 'yetalabs/Kimi-K3.1-Pro-abliterated')
                self.assertEqual(settings['revision'], '0911ef0765f49d26dfa25bb0d071f29463f8000b')
                self.assertEqual(settings['served_model_name'], 'yetalabs/Kimi-K3.1-Pro-abliterated')
                self.assertEqual(settings['active_requests'], 16)
                self.assertEqual(router[router.index('--max-concurrent-requests') + 1], '16')
                for flag, value in [('--model-path', 'yetalabs/Kimi-K3.1-Pro-abliterated'),
                                    ('--revision', '0911ef0765f49d26dfa25bb0d071f29463f8000b'),
                                    ('--served-model-name', 'yetalabs/Kimi-K3.1-Pro-abliterated'),
                                    ('--tp-size', '8'), ('--ep-size', '8'), ('--dcp-size', '8'),
                                    ('--max-running-requests', '16'), ('--cuda-graph-max-bs-decode', '16'),
                                    ('--mem-fraction-static', '0.88'), ('--mamba-full-memory-ratio', '1.5'),
                                    ('--chunked-prefill-size', '16384'), ('--max-prefill-tokens', '16384'),
                                    ('--speculative-draft-kv-cache-dtype', 'fp8_e4m3'),
                                    ('--speculative-dflash-block-size', '5'), ('--mamba-ssm-dtype', 'float32')]:
                    self.assertEqual(backend[backend.index(flag) + 1], value)
                self.assertIn('--enable-int8-mamba-checkpoint', backend)
                self.assertIn('--disable-overlap-schedule', backend)
                self.assertIn('--enable-linear-replayssm-spec', backend)
                for unsafe in ['--enable-nvidia-megakernel', '--speculative-use-block-verification',
                               '--enable-symm-mem', '--enable-deterministic-inference', '--kv-cache-dtype']:
                    self.assertNotIn(unsafe, backend)

    def test_invalid_allocations_fail_before_startup(self):
        for delta in [{'NVIDIA_VISIBLE_DEVICES': 'GPU-a,GPU-b'},
                      {'NVIDIA_VISIBLE_DEVICES': ','.join(['GPU-a'] * 8)},
                      {'TENSOR_PARALLEL_SIZE': '2'}, {'LORA_ENABLED': 'true'},
                      {'MODEL_ID': 'unknown/model'},
                      {'WARMUP_PORT': '18084'}, {'RUNTIME_PORT': '65532'},
                      {'MAX_QUEUED_REQUESTS': '4'}, {'GRADIATED_RUNTIME_ROOT': 'relative'}]:
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                config.commands({**self.environment, **delta})

    def test_entrypoint_sets_measured_cpu_budgets_before_mapping_and_launch(self):
        source = Path(__file__).resolve()
        entrypoint = next(path for path in [source.parents[1] / 'entrypoint',
            source.parents[2] / 'bundles/kimi-k31-pro/entrypoint'] if path.exists())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python = root / 'python/bin/python3'
            python.parent.mkdir(parents=True)
            python.write_text('''#!/bin/sh
[ "$OMP_NUM_THREADS" = 8 ] && [ "$MAX_JOBS" = 8 ] || exit 90
if [ "${2-}" = --cuda-visible-devices ]; then
  echo 0,1,2,3,4,5,6,7
else
  printf '{"omp":"%s","jobs":"%s","devices":"%s"}' "$OMP_NUM_THREADS" "$MAX_JOBS" "$CUDA_VISIBLE_DEVICES"
fi
''')
            python.chmod(0o755)
            environment = {**os.environ, **self.environment, 'GRADIATED_RUNTIME_ROOT': directory,
                           'XDG_CACHE_HOME': str(root / 'cache'), 'OMP_NUM_THREADS': '99', 'MAX_JOBS': '99'}
            result = subprocess.run(['bash', str(entrypoint)], env=environment,
                                    text=True, capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout),
                             {'omp': '8', 'jobs': '8', 'devices': '0,1,2,3,4,5,6,7'})

    def test_hardware_checks_every_assigned_gpu(self):
        for names, valid in [(['NVIDIA B300 SXM6 AC'] * 8, True),
                             (['NVIDIA B200'] * 8, False),
                             (['NVIDIA B300 SXM6 AC'] * 7, False)]:
            with patch.object(config.subprocess, 'run', return_value=SimpleNamespace(stdout='\n'.join(names))):
                if valid:
                    config.validate_hardware(self.environment)
                else:
                    with self.assertRaises(ValueError):
                        config.validate_hardware(self.environment)

    def test_cuda_indices_follow_assigned_uuid_order_not_inventory_order(self):
        inventory = '\n'.join(f'{7 - i}, GPU-{7 - i}' for i in range(8))
        with patch.object(config.subprocess, 'run', return_value=SimpleNamespace(stdout=inventory)) as query:
            self.assertEqual(config.cuda_visible_devices(self.environment), '0,1,2,3,4,5,6,7')
            reversed_devices = ','.join(f'GPU-{7 - i}' for i in range(8))
            self.assertEqual(config.cuda_visible_devices({**self.environment, 'NVIDIA_VISIBLE_DEVICES': reversed_devices}),
                             '7,6,5,4,3,2,1,0')
        self.assertIn('--query-gpu=index,uuid', query.call_args.args[0])

    def test_cuda_mapping_rejects_missing_duplicate_and_unassigned_inventory(self):
        valid = [f'{i}, GPU-{i}' for i in range(8)]
        for rows in [valid[:-1], valid[:-1] + ['0, GPU-7'], valid[:-1] + ['7, GPU-0'],
                     valid[:-1] + ['7, GPU-extra'], valid[:-1] + ['invalid, GPU-7']]:
            with self.subTest(rows=rows), patch.object(config.subprocess, 'run', return_value=SimpleNamespace(stdout='\n'.join(rows))):
                with self.assertRaises(ValueError):
                    config.cuda_visible_devices(self.environment)
        with self.assertRaises(ValueError):
            config.cuda_visible_devices({**self.environment, 'NVIDIA_VISIBLE_DEVICES': ','.join(['GPU-0'] * 8)})


if __name__ == '__main__':
    unittest.main()
