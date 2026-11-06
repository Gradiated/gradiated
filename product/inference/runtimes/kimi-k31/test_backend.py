import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config


@unittest.skipUnless(importlib.util.find_spec('sglang'), 'Packaged SGLang is required')
class NativeMxfp4Dispatch(unittest.TestCase):
    def test_uuid_assignment_reaches_actual_custom_allreduce_index_parser(self):
        import torch
        from sglang.srt.distributed.device_communicators import custom_all_reduce_utils as consumer
        environment = {'NVIDIA_VISIBLE_DEVICES': ','.join(f'GPU-{i}' for i in range(8))}
        inventory = '\n'.join(f'{i}, GPU-{i}' for i in range(8))
        with patch.object(config.subprocess, 'run', return_value=SimpleNamespace(stdout=inventory)):
            visible = config.cuda_visible_devices(environment)

        def gather(tensors, local, group):
            for index, tensor in enumerate(tensors):
                tensor.fill_(index)

        with patch.dict(os.environ, {'CUDA_VISIBLE_DEVICES': visible}), \
                patch.object(consumer.dist, 'get_backend', return_value='gloo'), \
                patch.object(consumer.dist, 'get_rank', return_value=0), \
                patch.object(consumer.dist, 'get_world_size', return_value=8), \
                patch.object(consumer.dist, 'all_gather', side_effect=gather), \
                patch.object(consumer, 'in_the_same_node_as', return_value=[True] * 8), \
                patch.object(consumer, 'is_full_nvlink', return_value=True) as nvlink, \
                patch.object(consumer, 'can_p2p', return_value=True):
            self.assertTrue(consumer.can_use_custom_all_reduce_with_nvlink(
                object(), torch.device('cuda:0'), [8], 'CustomAllReduceV2'))
            nvlink.assert_called_once_with(list(range(8)), 8)

    def test_launcher_selects_mxfp8_blackwell_mxfp4_method_and_runner(self):
        from sglang.srt.layers.moe.utils import MoeA2ABackend, MoeRunnerBackend
        from sglang.srt.layers.quantization import mxfp4
        environment = {'GRADIATED_RUNTIME_ROOT': '/runtime',
                       'NVIDIA_VISIBLE_DEVICES': ','.join(f'GPU-{i}' for i in range(8)),
                       'RUNTIME_PORT': '18080', 'WARMUP_PORT': '18083'}
        _, command, _ = config.commands(environment)
        backend = MoeRunnerBackend(command[command.index('--moe-runner-backend') + 1])
        precision = command[command.index('--flashinfer-mxfp4-moe-precision') + 1]
        execution = SimpleNamespace(moe=SimpleNamespace(flashinfer_mxfp4_moe_precision=precision))
        with patch.object(mxfp4, 'get_moe_runner_backend', return_value=backend), \
                patch.object(mxfp4, 'get_moe_a2a_backend', return_value=MoeA2ABackend.NONE), \
                patch.object(mxfp4, 'get_exec', return_value=execution), \
                patch.object(mxfp4, 'get_platform', return_value=SimpleNamespace(is_sm100=True)), \
                patch.object(mxfp4, 'MoeRunner') as runner:
            method = mxfp4.Mxfp4MoEMethod('test')
            self.assertEqual(method._fi_kernel, 'trtllm_sm100')
            self.assertEqual(method.flashinfer_mxfp4_moe_precision, 'default')
            method.create_moe_runner(SimpleNamespace(), SimpleNamespace())
            runner.assert_called_once_with(backend, method.moe_runner_config)


if __name__ == '__main__':
    unittest.main()
