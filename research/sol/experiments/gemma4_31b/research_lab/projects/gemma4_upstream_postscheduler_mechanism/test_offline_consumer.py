import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("run_offline_consumer.py")
SPEC = importlib.util.spec_from_file_location("run_offline_consumer", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class OfflineConsumerTests(unittest.TestCase):
    def test_selected_consumer_exact_method_body(self):
        source = """
_MAX_PREFILL_CUDA_GRAPH_PADDING_FACTOR = 2
class PrefillCudaGraphRunner:
    def can_run_graph(self, forward_batch):
        if self._is_full_backend and forward_batch.batch_size > self._capture_req_slots:
            return False
        if forward_batch.input_embeds is not None:
            return False
        if forward_batch.replace_embeds is not None:
            return False
        if self._has_unsupported_mha_prefix(forward_batch):
            return False
        if forward_batch.forward_mode.is_target_verify():
            return False
        if forward_batch.capture_hidden_mode != self.capture_hidden_mode:
            return False
        if self._has_inactive_dp_rank(forward_batch):
            return False
        if forward_batch.global_num_tokens_cpu is not None and not forward_batch.can_run_dp_breakable_cuda_graph:
            return False
        num_tokens = len(forward_batch.input_ids)
        if forward_batch.return_logprob and not isinstance(self.backend, BreakableCudaGraphBackend):
            return False
        if num_tokens > self.max_num_tokens:
            return False
        padded_num_tokens = self._pad_to_bucket(num_tokens, self.capture_num_tokens)
        if padded_num_tokens > num_tokens * _MAX_PREFILL_CUDA_GRAPH_PADDING_FACTOR:
            return False
        return True
"""
        runner_class, factor, backend_class = MODULE.extract_method(
            source, "PrefillCudaGraphRunner", "can_run_graph"
        )
        self.assertEqual(factor, 2)
        runner = MODULE.make_runner(runner_class, backend_class, [3072, 8192])
        self.assertFalse(MODULE.run_guard_case(runner, 3208))
        self.assertTrue(MODULE.run_guard_case(runner, 4096))

    def test_rejected_source_contracts_fail_closed(self):
        with self.assertRaises(RuntimeError):
            MODULE.check_source_contracts("missing", "missing")


if __name__ == "__main__":
    unittest.main()
