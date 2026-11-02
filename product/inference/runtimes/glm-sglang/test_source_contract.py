import ast
from enum import Enum
from http import HTTPStatus
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest


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


if __name__ == '__main__':
    unittest.main()
