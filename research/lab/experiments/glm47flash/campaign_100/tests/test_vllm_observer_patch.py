import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "nebius" / "vllm_observer_patch.py"
spec = importlib.util.spec_from_file_location("vllm_observer_patch", SOURCE)
vllm_observer_patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vllm_observer_patch)


SCHEDULER_FIXTURE = """import itertools
import time

logger = init_logger(__name__)


class Scheduler(SchedulerInterface):
        with record_function_or_nullcontext(\"schedule: update_after_schedule\"):
            self._update_after_schedule(scheduler_output)
        return scheduler_output

    def _preempt_request(self):
        pass
"""

RUNNER_FIXTURE = """import functools
import gc
import itertools

class GPUModelRunner(
            record_function_or_nullcontext(\"gpu_model_runner: forward\"),
            self.maybe_get_kv_connector_output(scheduler_output) as kv_connector_output,
"""


class VllmObserverPatchTests(unittest.TestCase):
    def test_scheduler_patch_emits_exact_iteration_identity_and_is_idempotent(self):
        patched = vllm_observer_patch.patch_scheduler_text(SCHEDULER_FIXTURE)
        self.assertIn("GRAD_RESEARCH_OBSERVER_V1", patched)
        self.assertIn("GRAD_RESEARCH_SCHEDULER_EVENTS", patched)
        self.assertIn("num_scheduled_tokens", patched)
        self.assertEqual(patched, vllm_observer_patch.patch_scheduler_text(patched))

    def test_runner_patch_wraps_forward_with_matching_nvtx_identity(self):
        patched = vllm_observer_patch.patch_runner_text(RUNNER_FIXTURE)
        self.assertIn("GRAD_RESEARCH_OBSERVER_V1", patched)
        self.assertIn("torch.cuda.nvtx.range", patched)
        self.assertIn("scheduler_output.num_scheduled_tokens", patched)
        self.assertEqual(patched, vllm_observer_patch.patch_runner_text(patched))

    def test_full_file_hash_mismatch_fails_closed(self):
        with self.assertRaisesRegex(vllm_observer_patch.ObserverPatchError, "source hash"):
            vllm_observer_patch.verify_source_hash(b"changed", "0" * 64, "scheduler")

    def test_pinned_vllm_source_hashes_are_explicit(self):
        self.assertEqual(
            "96f7360982899fffdbd627f51e3daf8afbe7a79fad5dc17d6dc0eb093aa516a0",
            vllm_observer_patch.SCHEDULER_SHA256,
        )
        self.assertEqual(
            "e8a73e1ccbfff37b880cd47ba9c115db572aef3c9d4d9eee50b18b729117f9bb",
            vllm_observer_patch.RUNNER_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
