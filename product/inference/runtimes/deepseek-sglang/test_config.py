import argparse
import ast
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config


class Configuration(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.environment = {'GRADIATED_RUNTIME_ROOT': self.directory.name, 'RUNTIME_PORT': '18080',
                            'WARMUP_PORT': '18083', 'TENSOR_PARALLEL_SIZE': '4',
                            'NVIDIA_VISIBLE_DEVICES': 'GPU-a,GPU-b,GPU-c,GPU-d'}

    def tearDown(self):
        self.directory.cleanup()

    def test_qualification_identity_ignores_placement_but_tracks_runtime_settings(self):
        bundle = Path(self.directory.name)
        settings = config.settings(self.environment)
        self.assertIsNone(config.qualification_identity(settings, bundle))
        (bundle / '.bundle-sha256').write_text('invalid')
        self.assertIsNone(config.qualification_identity(settings, bundle))
        (bundle / '.bundle-sha256').write_text('a' * 64)
        identity = config.qualification_identity(settings, bundle)
        moved = {**settings, 'root': Path('/another/bundle'), 'front': 28080,
                 'warmup': 28083, 'backend': 28084, 'metrics': 28085}
        self.assertEqual(config.qualification_identity(moved, bundle), identity)
        self.assertNotEqual(config.qualification_identity({**settings, 'lora': True}, bundle), identity)
        self.assertEqual(identity['bundle'], 'a' * 64)

    def test_backend_environment_preserves_deepseek_settings(self):
        environment = {**self.environment, 'CUDA_VISIBLE_DEVICES': '4,5,6,7'}
        self.assertEqual(config.backend_environment(environment, config.settings(environment)), environment)
        self.assertIsNot(config.backend_environment(environment, config.settings(environment)), environment)

    def test_tp4_dspark_with_native_parsers_and_bounded_front(self):
        settings, backend, router = config.commands(self.environment)
        for flag, value in [('--model-path', config.MODEL), ('--revision', config.REVISION),
                            ('--served-model-name', config.MODEL), ('--tp-size', '4'), ('--ep-size', '4'),
                            ('--speculative-algorithm', 'DSPARK'), ('--reasoning-parser', 'deepseek-v41'),
                            ('--tool-call-parser', 'deepseekv41'), ('--port', '18084'),
                            ('--max-running-requests', str(config.ACTIVE_REQUESTS))]:
            self.assertEqual(backend[backend.index(flag) + 1], value)
        self.assertNotIn('--enable-lora', backend)
        self.assertNotIn('--trust-remote-code', backend)
        for flag, value in [('--max-concurrent-requests', str(config.ACTIVE_REQUESTS)), ('--queue-size', '2'),
                            ('--worker-urls', 'http://127.0.0.1:18084'), ('--prometheus-port', '18085')]:
            self.assertEqual(router[router.index(flag) + 1], value)
        self.assertEqual((settings['tp'], settings['served_model_name']), (4, config.MODEL))

    def test_adapters_add_native_lora_flags(self):
        environment = {**self.environment, 'LORA_ENABLED': 'true', 'MODEL_ID': config.MODEL_ID,
                       'LORA_GPU_SLOTS': '8', 'LORA_CPU_SLOTS': '64', 'LORA_MAX_RANK': '8',
                       'LORA_DISK_CACHE_BYTES': '1073741824', 'LORA_DOWNLOAD_HOSTS': 'artifacts.s3.amazonaws.com'}
        settings, backend, _ = config.commands(environment)
        self.assertTrue(settings['lora'])
        for flag, value in [('--max-lora-rank', '8'), ('--max-loras-per-batch', '8'), ('--max-loaded-loras', '64')]:
            self.assertEqual(backend[backend.index(flag) + 1], value)
        self.assertEqual(backend[backend.index('--lora-target-modules') + 1:], config.LORA_TARGETS)

    def test_build_verifier_preserves_model_for_base_and_adapter_commands(self):
        lora = {**self.environment, 'LORA_ENABLED': 'true', 'MODEL_ID': config.MODEL_ID,
                'LORA_GPU_SLOTS': '8', 'LORA_CPU_SLOTS': '64', 'LORA_MAX_RANK': '8',
                'LORA_DISK_CACHE_BYTES': '1073741824', 'LORA_DOWNLOAD_HOSTS': 'artifacts.s3.amazonaws.com'}
        namespace = {'backend': config.commands(self.environment)[1],
                     'adapted_backend': config.commands(lora)[1], 'commands': config.commands, 'lora': lora}
        # Exercise the verifier's CLI extraction without loading its CUDA dependencies.
        tree = ast.parse((HERE / 'verify-build.py').read_text())
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == 'parse_args']
        self.assertGreaterEqual(len(calls), 2)
        parser = argparse.ArgumentParser()
        parser.add_argument('--model-path', required=True)
        for call in calls:
            with self.subTest(line=call.lineno):
                arguments = eval(compile(ast.Expression(call.args[0]), 'build-verifier-arguments', 'eval'), namespace)
                parsed, _ = parser.parse_known_args(arguments)
                self.assertEqual(parsed.model_path, config.MODEL)
        self.assertEqual(config.LORA_TARGETS, ['wq_a', 'wq_b', 'wkv', 'wo_a', 'wo_b',
                                              'w1', 'w2', 'w3', 'lm_head'])

    def test_wrong_model_tp_devices_ports_or_queue_contract_fail(self):
        for delta in [{'MODEL_ID': 'deepseek/deepseek-v4.1-flash'}, {'TENSOR_PARALLEL_SIZE': '8'},
                      {'NVIDIA_VISIBLE_DEVICES': 'GPU-a,GPU-b'}, {'NVIDIA_VISIBLE_DEVICES': 'GPU-a,GPU-a,GPU-b,GPU-c'},
                      {'WARMUP_PORT': '18082'}, {'WARMUP_PORT': '18084'}, {'MAX_QUEUED_REQUESTS': '4'},
                      {'LORA_ENABLED': 'yes'}, {'DEEPSEEK_SGLANG_PROFILE': 'h200-tp4'}]:
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                config.commands({**self.environment, **delta})

    def test_assigned_uuids_become_physical_indices_in_assignment_order(self):
        inventory = 'GPU-a, 2\n'
        rows = '3, GPU-d\n0, GPU-a\n2, GPU-c\n1, GPU-b\n'
        with patch.object(config.subprocess, 'run', return_value=type('R', (), {'stdout': rows})()):
            self.assertEqual(config.cuda_visible_devices(self.environment), '0,1,2,3')
        for bad in ['0, GPU-a\n0, GPU-b\n2, GPU-c\n3, GPU-d\n', '0, GPU-a\n1, GPU-b\n2, GPU-c\n', inventory,
                    'x, GPU-a\n1, GPU-b\n2, GPU-c\n3, GPU-d\n']:
            with self.subTest(bad=bad), self.assertRaises(ValueError), \
                    patch.object(config.subprocess, 'run', return_value=type('R', (), {'stdout': bad})()):
                config.cuda_visible_devices(self.environment)

    def test_profile_comes_from_the_assigned_gpus(self):
        original = config.gpu_names
        try:
            config.gpu_names = lambda _: ['NVIDIA B300 SXM6 AC'] * 4
            self.assertEqual(config.detect_profile(self.environment)['DEEPSEEK_SGLANG_PROFILE'], 'b300-tp4')
            config.validate_hardware(config.detect_profile(self.environment))
            config.gpu_names = lambda _: ['NVIDIA H200'] * 4
            with self.assertRaises(ValueError):
                config.detect_profile(self.environment)
        finally:
            config.gpu_names = original


if __name__ == '__main__':
    unittest.main()
