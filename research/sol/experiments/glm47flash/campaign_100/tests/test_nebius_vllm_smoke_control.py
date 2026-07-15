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
    validate_timeout_seconds,
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

    def test_frontier_timeout_is_bounded_to_project_limit(self):
        self.assertEqual(validate_timeout_seconds(3600), 3600)
        with self.assertRaises(RuntimeError):
            validate_timeout_seconds(3601)

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

    def test_frontier_arm_can_raise_sequence_limit_and_request_c16_ladder(self):
        joined = " ".join(build_container_command("g" * 64, 1783990000, max_num_seqs=16, frontier_concurrencies=(1, 8, 16)))
        self.assertIn("VLLM_MAX_NUM_SEQS=16", joined)
        self.assertIn("VLLM_FRONTIER_CONCURRENCIES=1,8,16", joined)
        script = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        self.assertIn('--max-num-seqs "$VLLM_MAX_NUM_SEQS"', script)
        self.assertIn('--concurrencies "$VLLM_FRONTIER_CONCURRENCIES"', script)

    def test_retained_arm_can_change_glm_mla_decode_tile(self):
        joined = " ".join(build_container_command("e" * 64, 1783990000, decode_block_n=64, decode_num_stages=1))
        self.assertIn("VLLM_DECODE_BLOCK_N=64", joined)
        self.assertIn("VLLM_DECODE_NUM_STAGES=1", joined)
        patcher = (ROOT / "nebius" / "vllm_decode_kernel_patch.py").read_text()
        self.assertIn("cf4debbbbdf2245355177dd7be91c4ac75730a9207a10cd7dab6306a5c3bdec4", patcher)
        self.assertIn("function.count(old) != 1", patcher)

    def test_retained_arm_can_change_only_non_batch_invariant_mla_splits(self):
        joined = " ".join(build_container_command("f" * 64, 1783990000, num_kv_splits=8))
        self.assertIn("VLLM_NUM_KV_SPLITS=8", joined)
        patcher = (ROOT / "nebius" / "vllm_decode_kernel_patch.py").read_text()
        self.assertIn("647a6d5f4c46f3057fdedce04cc2ee3b15ade713b1d7752df00e347efbd62ef6", patcher)
        self.assertIn("expected exactly one non-batch-invariant KV split assignment", patcher)

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

    def test_profiler_capture_is_true_fixed_geometry_batch_eight(self):
        runner = (ROOT / "nebius" / "vllm_batched_runner.py").read_text()
        self.assertIn('"fixed_8k_128_c8"', runner)
        self.assertIn("threading.Barrier(concurrency)", runner)
        self.assertIn("max_tokens=128", runner)
        self.assertIn('row["input_tokens"] == 8192 and row["output_tokens"] == 128', runner)
        self.assertIn("observer_only_after_fixed_slo", runner)
        self.assertNotIn('quality.get("pass") and performance.get', runner)

    def test_remote_reuses_content_addressed_checkpoint_verification_marker(self):
        script = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        self.assertIn(".campaign-integrity-v1", script)
        self.assertIn("manifest_sha256=$MANIFEST_SHA", script)
        self.assertIn("metadata_sha256=$METADATA_SHA", script)
        self.assertIn("marker_reused=true", script)

    def test_remote_telemetry_uses_utc_timestamps(self):
        script = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        self.assertIn("TZ=UTC nvidia-smi --query-gpu=timestamp", script)

    def test_infrastructure_failures_open_bounded_repair_window(self):
        source = (ROOT / "nebius" / "vllm_smoke_control.py").read_text()
        self.assertIn("time.time() + 600", source)
        self.assertIn("repair-decision.json", source)
        self.assertIn('decision.get("action") == "teardown"', source)

    def test_primary_session_can_retain_verified_runtime_and_checkpoint(self):
        source = (ROOT / "nebius" / "vllm_smoke_control.py").read_text()
        self.assertIn("--keep-instance-after-result", source)
        self.assertIn('"instance_retained_for_next_preregistered_experiment"', source)
        self.assertIn("cleanup or retain_after_result", source)

    def test_recovery_failures_also_open_bounded_repair_window(self):
        source = (ROOT / "nebius" / "vllm_recover_existing.py").read_text()
        self.assertIn("hold_for_repair_decision", source)
        self.assertIn("allocation_result is None", source)
        self.assertIn("--reuse-staged-runtime-and-checkpoint", source)
        self.assertIn("--keep-instance-after-result", source)
        self.assertIn("--session-deadline-epoch", source)
        self.assertIn("deadline = min", source)


if __name__ == "__main__":
    unittest.main()
