import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nebius"))

from vllm_smoke_control import (  # noqa: E402
    ABSOLUTE_TIMEOUT_SECONDS,
    IMAGE,
    RUNTIME_IMAGE,
    allocation_has_harness_error,
    build_container_command,
    build_host_bootstrap,
    required_quality_files,
)


class NebiusVllmSmokeControlTests(unittest.TestCase):
    def test_typed_wrapper_does_not_hide_harness_errors(self):
        self.assertTrue(allocation_has_harness_error({"error": {"type": "BatchError"}}))
        self.assertTrue(allocation_has_harness_error({"quality": {"quality_error": {"type": "BatchError"}}}))
        self.assertFalse(allocation_has_harness_error({"semantic": {"pass": False}, "quality": None}))

    def test_image_and_budget_are_pinned(self):
        self.assertEqual(
            IMAGE,
            "vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543",
        )
        self.assertEqual(ABSOLUTE_TIMEOUT_SECONDS, 4500)

    def test_bootstrap_pulls_vllm_not_sglang(self):
        script = build_host_bootstrap()
        self.assertIn(IMAGE, script)
        self.assertIn("1618d44b9295361607ec74d7be860ba886aac039", script)
        self.assertIn("rm -f /etc/ld.so.conf.d/00-cuda-compat.conf", script)
        self.assertNotIn("pip check", script)
        self.assertNotIn("lmsysorg/sglang", script)

    def test_preflight_targets_runtime_compatibility(self):
        source = (ROOT / "nebius" / "vllm_preflight.py").read_text()
        self.assertIn("import vllm", source)
        self.assertIn("vllm.model_executor.models.glm4_moe_lite", source)
        self.assertIn('transformers.__version__ != "5.3.0.dev0"', source)

    def test_container_is_stock_vllm_and_local_checkpoint(self):
        joined = " ".join(build_container_command("b" * 64, 1783990000))
        self.assertIn(RUNTIME_IMAGE, joined)
        self.assertIn("ldconfig", joined)
        self.assertIn("--entrypoint bash", joined)
        self.assertIn("/input/remote_vllm_awq_smoke.sh", joined)
        self.assertIn("MODEL_MANIFEST_PATH=/workspace/model-awq/model-files.sha256", joined)
        self.assertNotIn("patch_sglang", joined)

    def test_retained_arm_can_change_only_activation_dtype(self):
        joined = " ".join(build_container_command("c" * 64, 1783990000, dtype="float16"))
        self.assertIn("VLLM_DTYPE=float16", joined)
        script = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        self.assertIn('VLLM_DTYPE="${VLLM_DTYPE:-bfloat16}"', script)
        self.assertIn('--dtype "$VLLM_DTYPE"', script)

    def test_retained_arm_can_change_scheduler_token_budget(self):
        joined = " ".join(build_container_command("d" * 64, 1783990000, max_num_batched_tokens=65536))
        self.assertIn("VLLM_MAX_NUM_BATCHED_TOKENS=65536", joined)
        script = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        self.assertIn('--max-num-batched-tokens "$VLLM_MAX_NUM_BATCHED_TOKENS"', script)

    def test_retained_arm_can_change_glm_mla_decode_tile(self):
        joined = " ".join(build_container_command("e" * 64, 1783990000, decode_block_n=64, decode_num_stages=1))
        self.assertIn("VLLM_DECODE_BLOCK_N=64", joined)
        self.assertIn("VLLM_DECODE_NUM_STAGES=1", joined)
        patcher = (ROOT / "nebius" / "vllm_decode_kernel_patch.py").read_text()
        self.assertIn("cf4debbbbdf2245355177dd7be91c4ac75730a9207a10cd7dab6306a5c3bdec4", patcher)
        self.assertIn("function.count(old) != 1", patcher)

    def test_remote_gate_requires_semantic_json_and_determinism(self):
        runner = (ROOT / "nebius" / "vllm_batched_runner.py").read_text()
        self.assertIn('{"alpha": 17, "beta": "smoke"}', runner)
        self.assertIn("exact_normalized_identity", runner)
        self.assertIn("semantic_json_pass", runner)
        self.assertIn("performance_batch", runner)

    def test_all_frozen_quality_files_are_staged(self):
        quality = ROOT / "quality"
        manifest = __import__("json").loads((quality / "FROZEN_MANIFEST.json").read_text())
        expected = set(manifest["files"]) | {"FROZEN_MANIFEST.json"}
        self.assertEqual({path.name for path in required_quality_files(quality)}, expected)

    def test_stock_comparator_disables_prefix_cache_and_bounds_profiler(self):
        script = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        self.assertIn("--no-enable-prefix-caching", script)
        self.assertIn('"max_iterations":256', script)
        self.assertIn('printf "%.0f\\n",s', script)
        self.assertIn('exit "$RUNNER_RC"', script)

    def test_infrastructure_failures_open_bounded_repair_window(self):
        source = (ROOT / "nebius" / "vllm_smoke_control.py").read_text()
        self.assertIn("time.time() + 600", source)
        self.assertIn("repair-decision.json", source)
        self.assertIn('decision.get("action") == "teardown"', source)

    def test_recovery_failures_also_open_bounded_repair_window(self):
        source = (ROOT / "nebius" / "vllm_recover_existing.py").read_text()
        self.assertIn("hold_for_repair_decision", source)
        self.assertIn("allocation_result is None", source)
        self.assertIn("--reuse-staged-runtime-and-checkpoint", source)
        self.assertIn("--keep-instance-after-result", source)


if __name__ == "__main__":
    unittest.main()
