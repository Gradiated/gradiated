import ast
from contextlib import nullcontext
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from test_source_contract import source_root


class Layer:
    def __init__(self, forward):
        self.hidden_size = 4096
        self.config = SimpleNamespace(hc_mult=4)
        self.hc_attn_fn = SimpleNamespace(is_cuda=True, device='cuda:0')
        self.input_layernorm = SimpleNamespace(weight=SimpleNamespace(data=object()), variance_epsilon=1e-6)
        self.hc_attn_pre = forward


class MhcPrewarm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = source_root()
        if root is None:
            raise unittest.SkipTest('Pinned SGLang source is required')
        tree = ast.parse((root / 'srt/models/glm5_next.py').read_text())
        cls.model = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                         and node.name == 'Glm5NextForConditionalGeneration')
        cls.method = next(node for node in cls.model.body if isinstance(node, ast.FunctionDef)
                          and node.name == '_prewarm_mhc_kernels')

    def setUp(self):
        self.events = []
        self.enabled = True
        self.schedule = SimpleNamespace(chunked_prefill_size=16384, max_prefill_tokens=8192)
        self.layer = Layer(self.forward)
        self.state = SimpleNamespace(config=SimpleNamespace(mhc=True), encoder_only=False,
                                     model=SimpleNamespace(layers=[self.layer], decoder=self.layer))
        modules = {}
        for name in ['sglang', 'sglang.kernels', 'sglang.kernels.ops', 'sglang.kernels.ops.layernorm',
                     'sglang.kernels.ops.layernorm.mhc', 'sglang.srt', 'sglang.srt.runtime_context']:
            modules[name] = ModuleType(name)
            modules[name].__path__ = []
        modules['sglang.kernels.ops.layernorm.mhc'].get_mhc_pre_token_count_representatives = self.buckets
        modules['sglang.srt.runtime_context'].get_schedule = lambda: self.schedule
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        torch = SimpleNamespace(inference_mode=nullcontext, bfloat16='bf16', zeros=self.zeros,
                                cuda=SimpleNamespace(synchronize=lambda: self.events.append('sync'),
                                                     empty_cache=lambda: self.events.append('empty')))
        namespace = {'torch': torch, 'Glm5NextDecoderLayer': Layer,
                     'envs': SimpleNamespace(SGLANG_OPT_USE_TILELANG_MHC_PRE=SimpleNamespace(get=lambda: self.enabled)),
                     'get_parallel': lambda: SimpleNamespace(tp_group=SimpleNamespace(barrier=lambda: self.events.append('barrier'))),
                     'logger': SimpleNamespace(info=lambda *args: None)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[self.method], type_ignores=[])),
                     'installed-glm-mhc-prewarm', 'exec'), namespace)
        self.run_prewarm = lambda **kwargs: namespace['_prewarm_mhc_kernels'](self.state, **kwargs)

    def buckets(self, maximum, width):
        self.events.append(('buckets', maximum, width))
        return (128, 512, maximum)

    def zeros(self, shape, **kwargs):
        value = SimpleNamespace(shape=shape, **kwargs)
        self.events.append(('zeros', shape, kwargs))
        return value

    def forward(self, residual, weight, epsilon):
        self.assertIs(weight, self.layer.input_layernorm.weight.data)
        self.assertEqual(epsilon, 1e-6)
        self.events.append(('forward', residual.shape))

    def test_native_bucket_shapes_use_real_glm_boundary_and_release_before_pool_sizing(self):
        self.run_prewarm()
        self.assertEqual(self.events[0], ('buckets', 16384, 16384))
        self.assertEqual([event[1] for event in self.events if isinstance(event, tuple) and event[0] == 'forward'],
                         [(128, 16384), (512, 16384), (16384, 16384)])
        for event in self.events:
            if isinstance(event, tuple) and event[0] == 'zeros':
                self.assertEqual(event[2], {'dtype': 'bf16', 'device': 'cuda:0'})
        self.assertEqual(self.events[-3:], ['sync', 'empty', 'barrier'])
        self.assertTrue(self.state._mhc_prewarmed_at_load)
        before = list(self.events)
        self.run_prewarm()
        self.assertEqual(self.events, before)

    def test_mtp_decoder_does_not_need_to_inherit_the_target_class(self):
        del self.state.model.layers
        self.run_prewarm(is_nextn=True)
        self.assertTrue(self.state._mhc_prewarmed_at_load)

    def test_both_weight_load_paths_call_target_helper_explicitly_for_mtp_wrapper(self):
        for name in ['load_weights', 'post_load_weights']:
            method = next(node for node in self.model.body if isinstance(node, ast.FunctionDef) and node.name == name)
            calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute) and node.func.attr == '_prewarm_mhc_kernels']
            self.assertEqual(len(calls), 1)
            self.assertIsInstance(calls[0].func.value, ast.Name)
            self.assertEqual(calls[0].func.value.id, 'Glm5NextForConditionalGeneration')

    def test_encoder_non_mhc_non_cuda_and_disabled_paths_do_no_gpu_work(self):
        for setting in ['encoder', 'non_mhc', 'cpu', 'disabled']:
            with self.subTest(setting=setting):
                self.state.encoder_only = setting == 'encoder'
                self.state.config.mhc = setting != 'non_mhc'
                self.layer.hc_attn_fn.is_cuda = setting != 'cpu'
                self.enabled = setting != 'disabled'
                self.run_prewarm()
                self.assertEqual(self.events, [])
                self.assertFalse(getattr(self.state, '_mhc_prewarmed_at_load', False))

    def test_pipeline_placeholder_layer_does_not_touch_cuda(self):
        self.state.model.layers = [object()]
        self.run_prewarm()
        self.assertEqual(self.events, [])

    def test_disabled_chunking_uses_native_prefill_budget(self):
        for size in [None, 0]:
            with self.subTest(size=size):
                self.events.clear()
                self.state._mhc_prewarmed_at_load = False
                self.schedule.chunked_prefill_size = size
                self.run_prewarm()
                self.assertEqual(self.events[0], ('buckets', 8192, 16384))

    def test_kernel_failure_propagates_without_claiming_warmup_or_crossing_barrier(self):
        self.layer.hc_attn_pre = lambda *args: (_ for _ in ()).throw(RuntimeError('compile failed'))
        with self.assertRaisesRegex(RuntimeError, 'compile failed'):
            self.run_prewarm()
        self.assertFalse(getattr(self.state, '_mhc_prewarmed_at_load', False))
        self.assertNotIn('barrier', self.events)


if __name__ == '__main__':
    unittest.main()
