import ast
from enum import Enum
from http import HTTPStatus
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


def source_root():
    if os.environ.get('SGLANG_TEST_SOURCE'):
        return Path(os.environ['SGLANG_TEST_SOURCE'])
    spec = importlib.util.find_spec('sglang')
    if spec and spec.origin:
        return Path(spec.origin).parent
    if os.environ.get('GRADIATED_REQUIRE_SGLANG') == '1':
        raise RuntimeError('Installed SGLang source is required')
    return None


class SourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = source_root()
        if cls.root is None:
            raise unittest.SkipTest('Run source checks with the pinned installed SGLang package')
        tree = ast.parse((cls.root / 'srt/managers/scheduler.py').read_text())
        methods = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                   and node.name in ['_abort_on_queued_limit', '_add_request_to_queue']]
        module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0),
                                 *methods], type_ignores=[])
        namespace = {'HTTPStatus': HTTPStatus,
                     'DisaggregationMode': SimpleNamespace(NULL='null', PREFILL='prefill', DECODE='decode'),
                     '_make_abort_req': lambda req, **kwargs: SimpleNamespace(rid=req.rid, **kwargs)}
        exec(compile(ast.fix_missing_locations(module), 'pinned-scheduler-methods', 'exec'), namespace)
        cls.methods = namespace

    def scheduler(self, running):
        state = SimpleNamespace(max_queued_requests=2, waiting_queue=[], running_batch=[None] * running,
                                enable_priority_scheduling=False, disaggregation_mode='null',
                                uocr_doc_hooks=None, processed_tokens_counter=0, sent=[])
        state.send_abort_output = lambda out, req: state.sent.append(out)
        state._set_or_validate_priority = lambda req: True
        state._release_aborted_request = lambda req: None
        state._prefetch_kvcache = lambda req: None
        state._abort_on_queued_limit = lambda req: self.methods['_abort_on_queued_limit'](state, req)
        return state

    def enqueue(self, state, name):
        req = SimpleNamespace(rid=name, time_stats=SimpleNamespace(
            trace_ctx=SimpleNamespace(abort=lambda **kwargs: None), set_wait_queue_entry_time=lambda: None))
        self.methods['_add_request_to_queue'](state, req)

    def test_native_queue_two_excludes_active_prefill_and_decode(self):
        state = self.scheduler(16)
        for name in ['a', 'b', 'c']:
            self.enqueue(state, name)
        self.assertEqual([req.rid for req in state.waiting_queue], ['a', 'b'])
        self.assertEqual(len(state.sent), 1)
        self.assertEqual(state.sent[0].finished_reason['status_code'], HTTPStatus.SERVICE_UNAVAILABLE)

    def test_native_queue_two_rejects_idle_intake_burst(self):
        state = self.scheduler(0)
        for index in range(16):
            self.enqueue(state, str(index))
        self.assertEqual(len(state.waiting_queue), 2)
        self.assertEqual(len(state.sent), 14)

    def test_source_pressure_is_non_evictable_full_kv_ratio(self):
        text = (self.root / 'srt/managers/scheduler_components/pool_stats_observer.py').read_text()
        self.assertIn('full_num_used = full_capacity - (full_available_size + full_evictable_size)', text)
        self.assertIn('full_token_usage = full_num_used / full_capacity', text)
        self.assertIn('stats.full_token_usage = self.full_token_usage', text)

    def test_native_hopper_fp8_backend_resolution_accepts_the_h200_profile(self):
        tree = ast.parse((self.root / 'srt/arg_groups/overrides.py').read_text())
        methods = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name in ['_dsa_split_backend_resolution', '_check_dsa_backend_constraints']]
        for node in methods:
            node.decorator_list = []
        module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0),
                                 *methods], type_ignores=[])
        model = SimpleNamespace(architectures=['Glm5NextForConditionalGeneration'])
        namespace = {'model_config_of': lambda view: SimpleNamespace(
                         hf_config=model, kv_lora_rank=512, qk_rope_head_dim=0),
                     '_DEEPSEEK_FAMILY_ARCHS': {model.architectures[0]},
                     'get_platform': lambda: SimpleNamespace(is_npu=False, is_xpu=False, is_hip=False),
                     'logger': SimpleNamespace(warning=lambda *args: None)}
        exec(compile(ast.fix_missing_locations(module), 'pinned-hopper-resolution', 'exec'), namespace)
        model_config = ModuleType('sglang.srt.configs.model_config')
        model_config.is_deepseek_dsa = lambda config: True
        config_tree = ast.parse((self.root / 'srt/configs/model_config.py').read_text())
        helper = next(node for node in config_tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == 'is_q8_raw_fp8_nope_layout')
        helper_module = ast.Module(body=[
            ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0),
            helper], type_ignores=[])
        helpers = {}
        exec(compile(ast.fix_missing_locations(helper_module), 'pinned-raw-fp8-layout', 'exec'), helpers)
        model_config.is_q8_raw_fp8_nope_layout = helpers['is_q8_raw_fp8_nope_layout']
        torch = ModuleType('torch')
        torch.cuda = SimpleNamespace(get_device_capability=lambda: (9, 0))
        view = SimpleNamespace(kv_cache_dtype='fp8_e4m3', dsa_prefill_backend=None,
                               dsa_decode_backend=None, enable_hisparse=False)
        with patch.dict(sys.modules, {'sglang.srt.configs.model_config': model_config, 'torch': torch}):
            resolved = namespace['_dsa_split_backend_resolution'](view)
            self.assertEqual(resolved, {'dsa_prefill_backend': 'flashmla_kv', 'dsa_decode_backend': 'flashmla_kv'})
            view.dsa_prefill_backend = view.dsa_decode_backend = 'flashmla_kv'
            self.assertEqual(namespace['_dsa_split_backend_resolution'](view), {})
            view.dsa_prefill_backend = 'flashmla_sparse_q8'
            view.dsa_decode_backend = 'tilelang'
            self.assertEqual(namespace['_dsa_split_backend_resolution'](view), {})
            view.dcp_size = 2
            with self.assertRaisesRegex(ValueError, 'dcp-size'):
                namespace['_dsa_split_backend_resolution'](view)
            view.dcp_size = 1
            torch.cuda.get_device_capability = lambda: (10, 0)
            with self.assertRaisesRegex(ValueError, 'SM90'):
                namespace['_dsa_split_backend_resolution'](view)



if __name__ == '__main__':
    unittest.main()
