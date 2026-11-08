"""The SGLang code the live-tuning plugin hooks into, checked against the installed (patched) SGLang.

A renamed method would leave a hook silently unattached: telemetry would stop recording or a knob would
stop applying while the server kept serving. The bundle build runs this with GRADIATED_REQUIRE_SGLANG=1.
"""
import dataclasses
import importlib
import inspect
import os
import unittest
from unittest import mock


def installed():
    try:
        from sglang.srt.plugins import hook_registry
        import livetune.sglang_plugin  # noqa: F401
    except ImportError:
        if os.environ.get('GRADIATED_REQUIRE_SGLANG') == '1':
            raise
        return None
    return hook_registry


class LivetuneContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        hook_registry = installed()
        if hook_registry is None:
            raise unittest.SkipTest('Run with the pinned installed SGLang package and livetune')
        from livetune import sglang_plugin

        cls.targets = []
        with mock.patch.object(hook_registry.HookRegistry, 'register',
                               side_effect=lambda target, hook, kind: cls.targets.append(target)):
            sglang_plugin.register()

    def method(self, target):
        module, owner, name = target.rsplit('.', 2)
        return getattr(getattr(importlib.import_module(module), owner), name)

    def parameters(self, target):
        return list(inspect.signature(self.method(target)).parameters)

    def test_every_hook_target_exists(self):
        self.assertEqual(len(self.targets), 9)
        for target in self.targets:
            with self.subTest(target=target):
                self.assertTrue(callable(self.method(target)))

    def test_hooks_receive_the_arguments_they_read(self):
        by_name = {target.rsplit('.', 1)[1]: target for target in self.targets}
        self.assertIn('req', self.parameters(by_name['_maybe_log_time_stats']))
        self.assertEqual(self.parameters(by_name['process_batch_result'])[:3], ['self', 'batch', 'result'])
        self.assertEqual(self.parameters(by_name['set_wait_queue_entry_time'])[0], 'self')

    def test_request_timing_fields_the_records_read(self):
        from sglang.srt.observability.req_time_stats import SchedulerReqTimeStats

        names = {field.name for field in dataclasses.fields(SchedulerReqTimeStats)}
        for name in ('wait_queue_entry_time', 'forward_entry_time', 'prefill_finished_time', 'completion_time',
                     'queue_duration_s'):
            self.assertIn(name, names)

    def test_update_handlers_and_graph_recapture_keep_their_interfaces(self):
        from sglang.srt.managers.scheduler_components import internal_state
        from sglang.srt.model_executor.model_runner_components import cuda_graph_setup

        self.assertTrue(issubclass(internal_state.UpdateRejected, Exception))
        self.assertTrue(callable(internal_state._UpdateHandler))
        drop = inspect.signature(cuda_graph_setup.drop_elastic_cuda_graph_state).parameters
        self.assertTrue({'decode_runner', 'eager_runner'} <= set(drop))
        self.assertIn('model_runner', inspect.signature(cuda_graph_setup.recapture_elastic_cuda_graph).parameters)

    def test_replay_stops_finish_requests_the_way_sglang_does(self):
        from sglang.srt.managers import schedule_batch
        from sglang.srt.sampling import sampling_params

        self.assertIn('new_accepted_len', inspect.signature(schedule_batch.Req.update_finish_state).parameters)
        self.assertIn('length', inspect.signature(schedule_batch.FINISH_LENGTH).parameters)
        self.assertIn('custom_params', inspect.signature(sampling_params.SamplingParams).parameters)

    def test_scheduler_and_model_runner_attributes_the_plugin_reads(self):
        import re
        from pathlib import Path

        import sglang

        srt = Path(sglang.__file__).parent / 'srt'

        def assigned(directory, name):
            # Assigned directly, by tuple unpacking or on another object; a rename removes the name.
            pattern = re.compile(rf'\.{name}\b')
            return any(pattern.search(path.read_text()) for path in (srt / directory).rglob('*.py'))

        scheduler = ('tp_worker', 'page_size', 'max_running_requests', 'chunked_prefill_size', 'max_prefill_tokens',
                     'schedule_policy', 'policy', 'max_queued_requests', 'max_total_num_tokens', 'tree_cache',
                     'enable_hierarchical_cache', 'enable_priority_scheduling', 'schedule_low_priority_values_first',
                     'new_token_ratio_tracker', 'forward_ct', 'tp_cpu_group', 'spec_algorithm', 'waiting_queue',
                     'running_batch', 'chunked_req')
        for name in scheduler:
            with self.subTest(scheduler=name):
                self.assertTrue(assigned('managers', name), name)
        for name in ('decode_cuda_graph_runner', 'prefill_cuda_graph_runner', 'eager_runner', 'graph_shared_output',
                     '_kernel_warmed_up', 'model'):
            with self.subTest(model_runner=name):
                self.assertTrue(assigned('model_executor', name), name)


if __name__ == '__main__':
    unittest.main()
