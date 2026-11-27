import argparse
import ast
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config

LORA = {'LORA_ENABLED': 'true', 'MODEL_ID': 'Qwen/Qwen3-8B', 'LORA_GPU_SLOTS': '8', 'LORA_CPU_SLOTS': '64',
        'LORA_MAX_RANK': '32', 'LORA_DISK_CACHE_BYTES': '1073741824',
        'LORA_DOWNLOAD_HOSTS': 'artifacts.s3.amazonaws.com'}


class Configuration(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.environment = {'GRADIATED_RUNTIME_ROOT': self.directory.name, 'RUNTIME_PORT': '18080',
                            'WARMUP_PORT': '18083', 'TENSOR_PARALLEL_SIZE': '1',
                            'NVIDIA_VISIBLE_DEVICES': 'GPU-a'}

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

    def test_tp1_with_qwen3_parsers_and_bounded_front(self):
        settings, backend, router = config.commands(self.environment)
        for flag, value in [('--model-path', config.MODEL), ('--revision', config.REVISION),
                            ('--served-model-name', config.MODEL), ('--tp-size', '1'),
                            ('--context-length', '40960'), ('--reasoning-parser', 'qwen3'),
                            ('--tool-call-parser', 'qwen25'), ('--port', '18084'),
                            ('--max-running-requests', str(config.ACTIVE_REQUESTS)),
                            ('--cuda-graph-max-bs-decode', str(config.ACTIVE_REQUESTS))]:
            self.assertEqual(backend[backend.index(flag) + 1], value)
        self.assertNotIn('--enable-lora', backend)
        self.assertNotIn('--trust-remote-code', backend)
        self.assertNotIn('--cartridge-pool-bytes', backend)
        for flag, value in [('--max-concurrent-requests', str(config.ACTIVE_REQUESTS)), ('--queue-size', '2'),
                            ('--worker-urls', 'http://127.0.0.1:18084'), ('--prometheus-port', '18085')]:
            self.assertEqual(router[router.index(flag) + 1], value)
        self.assertEqual((settings['tp'], settings['served_model_name'], settings['model_id']),
                         (1, config.MODEL, 'Qwen/Qwen3-8B'))

    def test_adapters_add_native_lora_flags_for_every_projection(self):
        settings, backend, _ = config.commands({**self.environment, **LORA})
        self.assertTrue(settings['lora'])
        for flag, value in [('--max-lora-rank', '32'), ('--max-loras-per-batch', '8'), ('--max-loaded-loras', '64')]:
            self.assertEqual(backend[backend.index(flag) + 1], value)
        start = backend.index('--lora-target-modules') + 1
        self.assertEqual(backend[start:], config.LORA_TARGETS)
        self.assertEqual(config.LORA_TARGETS,
                         ['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'])

    def test_build_verifier_preserves_model_for_base_and_adapter_commands(self):
        lora = {**self.environment, **LORA}
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

    def test_wrong_model_tp_devices_ports_cartridges_or_queue_contract_fail(self):
        for delta in [{'MODEL_ID': 'Qwen/Qwen3-32B'}, {'TENSOR_PARALLEL_SIZE': '2'},
                      {'NVIDIA_VISIBLE_DEVICES': 'GPU-a,GPU-b'}, {'NVIDIA_VISIBLE_DEVICES': '0'},
                      {'WARMUP_PORT': '18082'}, {'WARMUP_PORT': '18084'}, {'MAX_QUEUED_REQUESTS': '4'},
                      {'LORA_ENABLED': 'yes'}, {'QWEN3_SGLANG_PROFILE': 'h200-tp1'},
                      {'CARTRIDGE_POOL_BYTES': '1024'}]:
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                config.commands({**self.environment, **delta})

    def test_profile_comes_from_the_assigned_gpu(self):
        original = config.gpu_names
        try:
            config.gpu_names = lambda _: ['NVIDIA B300 SXM6 AC']
            detected = config.detect_profile(self.environment)
            self.assertEqual(detected['QWEN3_SGLANG_PROFILE'], 'b300-tp1')
            config.validate_hardware(detected)
            config.gpu_names = lambda _: ['NVIDIA L4']
            with self.assertRaises(ValueError):
                config.detect_profile(self.environment)
            config.gpu_names = lambda _: ['NVIDIA B300 SXM6 AC'] * 2
            with self.assertRaises(ValueError):
                config.validate_hardware(detected)
        finally:
            config.gpu_names = original


if __name__ == '__main__':
    unittest.main()
