import importlib.util
import os
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
                           ('--max-running-requests', '12'), ('--chunked-prefill-size', '16384'),
                           ('--max-prefill-tokens', '16384'), ('--prefill-decode-interval', '64'),
                           ('--speculative-num-steps', '2'), ('--speculative-num-draft-tokens', '3'),
                           ('--revision', config.REVISION), ('--mem-fraction-static', '0.85'),
                           ('--schedule-policy', 'shortest-prefill-first')]:
            self.assertEqual(backend[backend.index(key) + 1], value)
        self.assertNotIn('--max-queued-requests', backend)
        self.assertNotIn('--disable-radix-cache', backend)
        self.assertNotIn('--disaggregation-mode', backend)
        self.assertNotIn('--disable-flashinfer-autotune', backend)
        for key, value in [('--max-concurrent-requests', '12'), ('--queue-size', '2'),
                           ('--queue-timeout-secs', '10'), ('--rate-limit-tokens-per-second', '0')]:
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

    def test_plain_glm_serves_the_nvfp4_export_with_native_adapters(self):
        environment = {**self.environment, 'MODEL_ID': 'z-ai/glm-5.3-flash', 'LORA_ENABLED': 'true',
                       'LORA_GPU_SLOTS': '8', 'LORA_CPU_SLOTS': '64', 'LORA_MAX_RANK': '8',
                       'LORA_DISK_CACHE_BYTES': '274877906944', 'LORA_DOWNLOAD_HOSTS': 'artifacts.s3.amazonaws.com'}
        settings, backend, router = config.commands(environment)
        model = config.MODELS['z-ai/glm-5.3-flash']
        for flag, value in [('--model-path', model['model']), ('--revision', model['revision']),
                            ('--served-model-name', 'zai-org/GLM-5.3-Flash'), ('--quantization', 'modelopt_fp4'),
                            ('--moe-runner-backend', model['moe_runner']), ('--max-lora-rank', '8'),
                            ('--max-loras-per-batch', '8'), ('--max-loaded-loras', '64')]:
            self.assertEqual(backend[backend.index(flag) + 1], value)
        self.assertNotIn('--json-model-override-args', backend)
        self.assertNotIn('--attn-cp-size', backend)
        self.assertEqual(backend[backend.index('--page-size') + 1], '256')
        targets = backend[backend.index('--lora-target-modules') + 1:]
        targets = targets[:next((i for i, a in enumerate(targets) if a.startswith('--')), len(targets))]
        self.assertEqual(targets, model['lora_targets'])
        self.assertTrue(settings['lora'])
        _, plain, _ = config.commands({**environment, 'LORA_ENABLED': 'false'})
        self.assertNotIn('--enable-lora', plain)

    def test_uncensored_default_never_enables_adapters_or_unknown_models(self):
        settings, backend, _ = config.commands(self.environment)
        self.assertEqual(settings['served_model_name'], config.MODEL)
        self.assertNotIn('--enable-lora', backend)
        for delta in [{'MODEL_ID': 'dealignai/glm-5.3-flash-uncensored', 'LORA_ENABLED': 'true'},
                      {'MODEL_ID': 'z-ai/glm-5'}, {'MODEL_ID': 'z-ai/glm-5.3-flash', 'LORA_ENABLED': 'yes'}]:
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                config.commands({**self.environment, **delta})

    def test_h200_selects_hopper_attention_and_bounds_both_admission_layers(self):
        environment = {**self.environment, 'GLM_SGLANG_PROFILE': 'h200-tp2'}
        settings, backend, router = config.commands(environment)
        self.assertEqual(settings['gpu_product'], 'H200')
        for flag, value in [('--dsa-prefill-backend', 'flashmla_sparse_q8'), ('--dsa-decode-backend', 'tilelang'),
                            ('--max-running-requests', '3'), ('--cuda-graph-max-bs-decode', '3'),
                            ('--chunked-prefill-size', '4096'), ('--max-prefill-tokens', '4096'),
                            ('--page-size', '256'), ('--tp-size', '2'), ('--moe-runner-backend', 'marlin'),
                            ('--kv-cache-dtype', 'fp8_e4m3'), ('--speculative-num-steps', '3'),
                            ('--speculative-num-draft-tokens', '4'), ('--speculative-algorithm', 'EAGLE'),
                            ('--mem-fraction-static', '0.9'), ('--mamba-full-memory-ratio', '1.8')]:
            self.assertEqual(backend[backend.index(flag) + 1], value)
        self.assertNotIn('--enable-prefill-cp', backend)
        self.assertNotIn('--attn-cp-size', backend)
        self.assertEqual(router[router.index('--max-concurrent-requests') + 1], '3')
        self.assertEqual(router[router.index('--queue-size') + 1], '2')

    def test_b200_keeps_blackwell_attention_with_a_smaller_admission_limit(self):
        environment = {**self.environment, 'GLM_SGLANG_PROFILE': 'b200-pcp2'}
        settings, backend, router = config.commands(environment)
        _, b300, _ = config.commands(self.environment)
        self.assertEqual(settings['gpu_product'], 'B200')
        for flag, value in [('--dsa-prefill-backend', 'trtllm'), ('--dsa-decode-backend', 'trtllm'),
                            ('--max-running-requests', '6'), ('--cuda-graph-max-bs-decode', '6'),
                            ('--chunked-prefill-size', '16384'), ('--attn-cp-size', '2')]:
            self.assertEqual(backend[backend.index(flag) + 1], value)
        self.assertIn('--enable-prefill-cp', backend)
        self.assertNotIn('--page-size', backend)
        limits = {'--max-running-requests', '--cuda-graph-max-bs-decode', '--hicache-size', '--hicache-write-policy'}
        strip = lambda args: [a for i, a in enumerate(args) if a not in limits and (i == 0 or args[i - 1] not in limits)]
        self.assertEqual(strip(backend), [a for a in strip(b300) if a != '--enable-hierarchical-cache'])
        self.assertEqual(router[router.index('--max-concurrent-requests') + 1], '6')

    def test_b300_hicache_spills_to_a_per_identity_per_gpu_file_tier(self):
        bundle = self.root / 'bundle'
        bundle.mkdir()
        environment = {**self.environment, 'XDG_CACHE_HOME': '/home/runtime/.cache'}
        _, backend, _ = config.commands(environment, bundle)
        self.assertIn('--enable-hierarchical-cache', backend)
        self.assertEqual(backend[backend.index('--hicache-size') + 1], '48')
        self.assertEqual(backend[backend.index('--hicache-write-policy') + 1], 'write_through')
        self.assertNotIn('--hicache-storage-backend', backend)
        self.assertNotIn('--hicache-storage-key-scheme', backend)

        (bundle / '.bundle-sha256').write_text('a' * 64 + '\n')
        settings, backend, _ = config.commands(environment, bundle)
        self.assertEqual(backend[backend.index('--hicache-storage-backend') + 1], 'file')
        extra = json.loads(backend[backend.index('--hicache-storage-backend-extra-config') + 1])
        self.assertEqual(extra, {'file_storage_path': str(config.hicache_directory(environment, settings, bundle)),
                                 'max_size': '100G', 'min_free_space': '100G'})
        directory = Path(extra['file_storage_path'])
        self.assertEqual(directory.parent.parent, Path('/home/runtime/.cache/glm-sglang/hicache'))
        self.assertEqual(directory.name, 'GPU-a_GPU-b')

        moved = {**environment, 'RUNTIME_PORT': '28080', 'WARMUP_PORT': '28083', 'GRADIATED_RUNTIME_ROOT': str(self.root)}
        self.assertEqual(config.hicache_directory(moved, config.settings(moved), bundle), directory)
        other_gpus = {**environment, 'NVIDIA_VISIBLE_DEVICES': 'GPU-c,GPU-d'}
        self.assertEqual(config.hicache_directory(other_gpus, config.settings(other_gpus), bundle).parent, directory.parent)
        self.assertNotEqual(config.hicache_directory(other_gpus, config.settings(other_gpus), bundle), directory)
        self.assertNotEqual(config.hicache_directory(environment, {**settings, 'active_requests': 11}, bundle).parent, directory.parent)
        (bundle / '.bundle-sha256').write_text('b' * 64 + '\n')
        self.assertNotEqual(config.hicache_directory(environment, settings, bundle).parent, directory.parent)

        for profile in ['b200-pcp2', 'h200-tp2']:
            _, other, _ = config.commands({**environment, 'GLM_SGLANG_PROFILE': profile}, bundle)
            self.assertFalse([a for a in other if a.startswith('--hicache') or a == '--enable-hierarchical-cache'], profile)
        for lora in ['true', 'false']:
            plain = {**environment, 'MODEL_ID': 'z-ai/glm-5.3-flash', 'LORA_ENABLED': lora,
                     'LORA_GPU_SLOTS': '8', 'LORA_CPU_SLOTS': '64', 'LORA_MAX_RANK': '8',
                     'LORA_DISK_CACHE_BYTES': '274877906944', 'LORA_DOWNLOAD_HOSTS': 'artifacts.s3.amazonaws.com'}
            self.assertFalse(config.settings(plain)['hicache'])
            _, other, _ = config.commands(plain, bundle)
            self.assertFalse([a for a in other if a.startswith('--hicache') or a == '--enable-hierarchical-cache'], lora)

    def test_mamba_prompt_end_checkpoint_follows_hicache(self):
        flag = 'GRADIATED_MAMBA_PROMPT_END_CHECKPOINT'
        inherited = {**self.environment, flag: '1'}
        for profile in config.PROFILES:
            settings = config.settings({**self.environment, 'GLM_SGLANG_PROFILE': profile})
            expected = '1' if settings.get('hicache') else '0'
            self.assertEqual(config.backend_environment(inherited, settings)[flag], expected, profile)
        settings = config.settings(self.environment)
        self.assertTrue(settings['hicache'])
        enabled = config.backend_environment(self.environment, settings)
        self.assertEqual(enabled[flag], '1')
        self.assertEqual(enabled['NVIDIA_VISIBLE_DEVICES'], 'GPU-a,GPU-b')
        self.assertEqual(config.backend_environment(inherited, {**settings, 'hicache': False})[flag], '0')

    def test_prune_removes_only_week_idle_hicache_leaves(self):
        environment = {**self.environment, 'XDG_CACHE_HOME': str(self.root / 'cache')}
        base = self.root / 'cache/glm-sglang/hicache'
        keep, live, stale = base / 'x/GPU-a_GPU-b', base / 'y/GPU-c_GPU-d', base / 'z/GPU-c_GPU-d'
        for leaf in [keep, live, stale]:
            leaf.mkdir(parents=True)
            (leaf / 'page.bin').write_bytes(b'0')
        old = config.time.time() - 8 * 86400
        for path in [stale / 'page.bin', stale, keep / 'page.bin', keep]:
            os.utime(path, (old, old))
        held = base / 'w/GPU-g_GPU-h'
        held.mkdir(parents=True)
        os.utime(held, (old, old))
        lock = config.hold_hicache(held)
        config.prune_hicache(environment, keep)
        lock.close()
        self.assertTrue(keep.is_dir() and live.is_dir() and held.is_dir())
        self.assertFalse(stale.exists())

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
        for names, expected in [('NVIDIA H200\nNVIDIA H200\n', 'h200-tp2'), ('NVIDIA B300 SXM6 AC\nNVIDIA B300 SXM6 AC\n', 'b300-pcp2'),
                                ('NVIDIA B200\nNVIDIA B200\n', 'b200-pcp2')]:
            with self.subTest(names=names), patch.object(config.subprocess, 'run', return_value=SimpleNamespace(stdout=names)):
                self.assertEqual(config.detect_profile(self.environment)['GLM_SGLANG_PROFILE'], expected)
        for names in ['NVIDIA GH200\nNVIDIA GH200\n', 'NVIDIA H200\nNVIDIA B300\n', 'NVIDIA GB200\nNVIDIA GB200\n',
                      'NVIDIA B200\nNVIDIA B300\n', '']:
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
