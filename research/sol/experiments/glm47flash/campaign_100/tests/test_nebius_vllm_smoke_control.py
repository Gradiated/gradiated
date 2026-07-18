import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nebius"))

from vllm_smoke_control import (  # noqa: E402
    ABSOLUTE_TIMEOUT_SECONDS,
    IMAGE,
    RUNTIME_IMAGE,
    allocation_has_harness_error,
    background_completion_pass,
    build_container_command,
    build_host_bootstrap,
    execution_outcome,
    hold_for_repair_decision,
    measured_phase,
    methodology_completion_pass,
    methodology_useful_gpu_seconds,
    validate_bf16_model,
    validate_methodology_contract,
    redact_provider_text,
    required_quality_files,
    resolve_created_instance,
    validate_scientific_owner,
    validate_frontier_concurrencies,
    validate_timeout_seconds,
    start_independent_watchdog,
    useful_gpu_seconds,
    write_create_diagnostic,
)


class NebiusVllmSmokeControlTests(unittest.TestCase):
    def test_scientific_phase_records_remote_failure_without_losing_artifact_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / "events.jsonl"
            with measured_phase(events, "scientific_workload") as phase:
                phase["outcome"] = "FAIL"
                phase["returncode"] = 2
            rows = [json.loads(line) for line in events.read_text().splitlines()]
        self.assertEqual(
            {
                "outcome": "FAIL",
                "returncode": 2,
            },
            {
                key: rows[-1][key]
                for key in ("outcome", "returncode")
            },
        )
        source = (ROOT / "nebius" / "vllm_smoke_control.py").read_text()
        retrieval = source.split('with measured_phase(events, "artifact_retrieval"):', 1)[1]
        self.assertLess(
            retrieval.index("verify_internal_manifest(archive)"),
            retrieval.index('extract_member(archive, "/allocation-result.json")'),
        )

    def test_background_contract_can_accept_a_verified_nonzero_remote_result(self):
        result = {
            "batch_pass": False,
            "semantic": {"pass": True},
            "quality": {"pass": True},
            "performance": {
                "profiles": [
                    {
                        "success_fraction": 1.0,
                        "exact_geometry_pass": True,
                        "wall_seconds": 109.803,
                        "requests": 64,
                        "rows": [{}] * 64,
                        "prefix_cache_disabled": True,
                        "prefix_cache_zero_delta": True,
                    }
                ]
            },
        }
        self.assertEqual(execution_outcome(1, result, 300), ("PASS", True))
        self.assertEqual(execution_outcome(1, result, 60), ("FAIL", False))
        source = (ROOT / "nebius" / "vllm_smoke_control.py").read_text()
        self.assertIn("retain_after_result = keep_instance_after_result and background_pass", source)

    def test_methodology_requires_every_mandatory_arm_before_background_override(self):
        rows = [
            {
                "prompt_sha256": str(index),
                "input_tokens_o200k": 10_000,
                "output_tokens_server": 1_500,
                "output_token_ids_complete": True,
                "end_to_end_ms": 20_000,
            }
            for index in range(7)
        ]
        phases = [
            {
                "concurrency": concurrency,
                "planned_phase_seconds": 180,
                "wall_seconds": 180.5,
                "geometry_pass": True,
                "success_fraction": 1.0,
                "requests_completed": concurrency,
            }
            for concurrency in (1, 2, 4, 8, 16, 32, 64)
        ]
        result = {
            "pass": True,
            "single_request": {"geometry_pass": True, "requests": 7, "rows": rows},
            "system_load": {"phases": phases},
        }
        self.assertTrue(methodology_completion_pass(result))
        self.assertEqual(methodology_useful_gpu_seconds(result), 1403.5)
        result["system_load"]["phases"] = phases[:-1]
        self.assertFalse(methodology_completion_pass(result))
        result["system_load"]["plateau"] = {
            "at_concurrency": 32,
            "rule": "two adjacent steps below 5% aggregate-throughput gain",
        }
        self.assertTrue(methodology_completion_pass(result))

    def test_methodology_mode_requires_the_exact_internal_c32_control(self):
        validate_methodology_contract("awq", "l40s-awq", 32, (32,), True)
        validate_methodology_contract("awq", "l40s-awq", 8, (1, 8), False)
        for values in (
            ("awq", "l40s-awq", 8, (1, 8), True),
            ("awq", "l40s-awq", 32, (1, 8), True),
            ("bf16-v2-quality", "h100-bf16", 1, (1,), True),
        ):
            with self.subTest(values=values), self.assertRaisesRegex(
                RuntimeError, "exact c32 internal control"
            ):
                validate_methodology_contract(*values)

    def test_frontier_validator_admits_the_direct_c16_c32_pair(self):
        self.assertEqual(validate_frontier_concurrencies((16, 32), 32), (16, 32))

    def test_frontier_validator_admits_the_stock_maxseq36_pairs(self):
        self.assertEqual(validate_frontier_concurrencies((32, 36), 36), (32, 36))
        self.assertEqual(validate_frontier_concurrencies((36,), 36), (36,))

    def test_frontier_validator_admits_only_the_ordered_scheduling_knee_bracket(self):
        self.assertEqual(validate_frontier_concurrencies((32, 24, 28, 30, 32), 32), (32, 24, 28, 30, 32))
        with self.assertRaisesRegex(RuntimeError, "frontier concurrencies"):
            validate_frontier_concurrencies((32, 24, 28, 32), 32)

    def test_cleanup_watchdog_is_an_independent_user_systemd_service(self):
        launched = CompletedProcess(["systemd-run"], 0, stdout="", stderr="")
        shown = CompletedProcess(
            ["systemctl"], 0,
            stdout="Id=glm-test-watchdog.service\nActiveState=active\nMainPID=123\nControlGroup=/user.slice/watchdog\n",
            stderr="",
        )
        with (
            patch.dict("vllm_smoke_control.os.environ", {"XDG_RUNTIME_DIR": "/run/user/0"}, clear=True),
            patch("vllm_smoke_control.subprocess.run", side_effect=[launched, shown]) as run,
        ):
            result = start_independent_watchdog("instance-1", "disk-1", 9999999999.0, "glm-test-watchdog")
        self.assertEqual(result["unit"], "glm-test-watchdog.service")
        self.assertEqual(result["main_pid"], 123)
        self.assertEqual(result["control_group"], "/user.slice/watchdog")
        self.assertEqual(result["unit_manager"], "user")
        self.assertIn("--user", run.call_args_list[0].args[0])
        self.assertIn("--user", run.call_args_list[1].args[0])

    def test_cleanup_watchdog_uses_system_manager_from_system_service(self):
        launched = CompletedProcess(["systemd-run"], 0, stdout="", stderr="")
        shown = CompletedProcess(
            ["systemctl"], 0,
            stdout="Id=glm-test-watchdog.service\nActiveState=active\nMainPID=456\nControlGroup=/system.slice/watchdog\n",
            stderr="",
        )
        with (
            patch.dict("vllm_smoke_control.os.environ", {}, clear=True),
            patch("vllm_smoke_control.subprocess.run", side_effect=[launched, shown]) as run,
        ):
            result = start_independent_watchdog("instance-1", "disk-1", 9999999999.0, "glm-test-watchdog")
        self.assertEqual(result["unit_manager"], "system")
        self.assertEqual(result["main_pid"], 456)
        self.assertIn("--system", run.call_args_list[0].args[0])
        self.assertIn("--system", run.call_args_list[1].args[0])

    def test_cleanup_watchdog_runtime_includes_provider_deletion_reserve(self):
        launched = CompletedProcess(["systemd-run"], 0, stdout="", stderr="")
        shown = CompletedProcess(
            ["systemctl"],
            0,
            stdout="Id=glm-test-watchdog.service\nActiveState=active\nMainPID=456\nControlGroup=/system.slice/watchdog\n",
            stderr="",
        )
        with (
            patch("vllm_smoke_control.time.time", return_value=1000.0),
            patch(
                "vllm_smoke_control.subprocess.run",
                side_effect=[launched, shown],
            ) as run,
        ):
            start_independent_watchdog(
                "instance-1", "disk-1", 2000.0, "glm-test-watchdog"
            )
        self.assertIn(
            "--property=RuntimeMaxSec=1600s",
            run.call_args_list[0].args[0],
        )

    def test_maxseq36_is_exposed_by_the_controller_cli(self):
        source = (ROOT / "nebius" / "vllm_smoke_control.py").read_text()
        self.assertIn('choices=(8, 16, 32, 36, 64)', source)

    def test_create_diagnostic_is_typed_and_redacted(self):
        result = CompletedProcess(
            ["nebius"],
            1,
            stdout="access_token=token-value",
            stderr="operation wait failed",
        )
        with tempfile.TemporaryDirectory() as tmp:
            write_create_diagnostic(Path(tmp), result)
            diagnostic = json.loads((Path(tmp) / "provider-create-diagnostic.json").read_text())
        self.assertEqual(diagnostic["stage"], "provider_create")
        self.assertEqual(diagnostic["returncode"], 1)
        self.assertNotIn("token-value", diagnostic["stdout_tail_redacted"])

    def test_create_reconciles_nonzero_cli_exit_with_created_named_instance(self):
        result = CompletedProcess(["nebius"], 1, stdout="", stderr="operation wait failed")
        with patch("vllm_smoke_control.find_named_instance", return_value="computeinstance-test"):
            self.assertEqual(
                resolve_created_instance(result, "glm-test"),
                ("computeinstance-test", True),
            )

    def test_create_failure_without_resource_remains_terminal(self):
        result = CompletedProcess(["nebius"], 1, stdout="", stderr="provider rejected request")
        with patch("vllm_smoke_control.find_named_instance", return_value=None):
            with self.assertRaises(RuntimeError):
                resolve_created_instance(result, "glm-test")

    def test_provider_diagnostic_redacts_credentials_and_private_keys(self):
        text = "access_token=token-value password=pw-value -----BEGIN PRIVATE KEY----- hidden -----END PRIVATE KEY-----"
        redacted = redact_provider_text(text)
        self.assertNotIn("token-value", redacted)
        self.assertNotIn("pw-value", redacted)
        self.assertNotIn("hidden", redacted)

    def test_typed_wrapper_does_not_hide_harness_errors(self):
        self.assertTrue(allocation_has_harness_error({"error": {"type": "BatchError"}}))
        self.assertTrue(allocation_has_harness_error({"quality": {"quality_error": {"type": "BatchError"}}}))
        self.assertFalse(allocation_has_harness_error({"semantic": {"pass": False}, "quality": None}))

    def test_background_completion_is_distinct_from_interactive_slo(self):
        result = {
            "batch_pass": False,
            "semantic": {"pass": True},
            "quality": {"pass": True},
            "performance": {
                "profiles": [
                    {
                        "success_fraction": 1.0,
                        "exact_geometry_pass": True,
                        "wall_seconds": 61.216,
                        "requests": 64,
                        "rows": [{}] * 64,
                        "prefix_cache_disabled": True,
                        "prefix_cache_zero_delta": True,
                    }
                ]
            },
        }
        self.assertTrue(background_completion_pass(result, 300.0))
        self.assertFalse(background_completion_pass(result, 60.0))
        result["performance"]["performance_error"] = {"type": "BatchError"}
        self.assertFalse(background_completion_pass(result, 300.0))
        self.assertFalse(background_completion_pass({"semantic": None, "quality": None}, 300.0))
        self.assertFalse(background_completion_pass({"semantic": {"pass": True}, "quality": {"pass": True}, "performance": None}, 300.0))

    def test_useful_gpu_seconds_sum_scored_profile_wall_time(self):
        result = {"performance": {"profiles": [{"wall_seconds": 10.5}, {"wall_seconds": 20.25}]}}
        self.assertEqual(useful_gpu_seconds(result), 30.75)
        self.assertIsNone(useful_gpu_seconds({"performance": {"profiles": []}}))

    def test_image_and_budget_are_pinned(self):
        self.assertEqual(
            IMAGE,
            "vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543",
        )
        self.assertEqual(ABSOLUTE_TIMEOUT_SECONDS, 4500)

    def test_frontier_timeout_is_bounded_to_project_limit(self):
        self.assertEqual(validate_timeout_seconds(4500), 4500)
        with self.assertRaises(RuntimeError):
            validate_timeout_seconds(4501)

    def test_bootstrap_pulls_vllm_not_sglang(self):
        script = build_host_bootstrap()
        self.assertIn(IMAGE, script)
        self.assertIn("1618d44b9295361607ec74d7be860ba886aac039", script)
        self.assertIn("rm -f /etc/ld.so.conf.d/00-cuda-compat.conf", script)
        self.assertNotIn("pip check", script)
        self.assertNotIn("lmsysorg/sglang", script)
        self.assertIn("org.gradiated.runtime-contract", script)
        self.assertIn("runtime_image_cache_hit=true", script)
        self.assertIn("for attempt in 1 2", script)

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

    def test_bf16_v2_mode_binds_long_v2_geometry_and_writable_mode(self):
        joined = " ".join(build_container_command("b" * 64, 1783990000, scientific_mode="bf16-v2-quality", max_num_batched_tokens=43008, max_num_seqs=1, max_model_len=43008, frontier_concurrencies=(1,)))
        self.assertIn("VLLM_SCIENTIFIC_MODE=bf16-v2-quality", joined)
        self.assertIn("VLLM_MAX_MODEL_LEN=43008", joined)
        self.assertIn("MODEL_MANIFEST_PATH=/workspace/model-bf16/model-files.sha256", joined)
        remote = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        self.assertIn("/workspace/bf16-v2-quality", remote)
        self.assertIn("--enforce-eager", remote)
        self.assertNotIn('python3 /input/remote_v2_capture.sh', remote)

    def test_provider_mutation_requires_durable_service_ownership(self):
        with self.assertRaisesRegex(RuntimeError, "durable service ownership"):
            validate_scientific_owner("bf16-v2-quality", {})
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "durable service ownership"):
                validate_scientific_owner("bf16-v2-quality")
        with self.assertRaisesRegex(RuntimeError, "durable service ownership"):
            validate_scientific_owner("bf16-v2-quality", {"INVOCATION_ID": "inherited-parent-unit", "SYSTEMD_EXEC_PID": "1"})
        with patch("vllm_smoke_control.os.getpid", return_value=123):
            validate_scientific_owner("bf16-v2-quality", {"INVOCATION_ID": "unit-invocation", "SYSTEMD_EXEC_PID": "123"})
            validate_scientific_owner("awq", {"INVOCATION_ID": "unit-invocation", "SYSTEMD_EXEC_PID": "123"})
        with self.assertRaisesRegex(RuntimeError, "durable service ownership"):
            validate_scientific_owner("awq", {})

    def test_bf16_runner_retains_seven_artifacts(self):
        source = (ROOT / "nebius" / "vllm_v2_quality_runner.py").read_text()
        for name in ("raw-response-bytes", "normalized-output-bytes", "transform-decisions", "responses.jsonl", "runtime-evidence.json", "identity-manifest.json", "capture-result.json"):
            self.assertIn(name, source)

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

    def test_l40s_arm_can_request_fp8_kv_cache_and_c32(self):
        joined = " ".join(build_container_command("k" * 64, 1783990000, max_num_seqs=32, frontier_concurrencies=(32,), kv_cache_dtype="fp8_e4m3"))
        self.assertIn("VLLM_MAX_NUM_SEQS=32", joined)
        self.assertIn("VLLM_FRONTIER_CONCURRENCIES=32", joined)
        self.assertIn("VLLM_KV_CACHE_DTYPE=fp8_e4m3", joined)
        script = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        self.assertIn('CMD+=(--kv-cache-dtype "$VLLM_KV_CACHE_DTYPE")', script)

    def test_ngram_prompt_lookup_is_pinned_to_the_candidate_only_l40s_c16_arm(self):
        stock = " ".join(build_container_command("n" * 64, 1783990000, max_num_seqs=16, frontier_concurrencies=(16,)))
        candidate = " ".join(build_container_command("n" * 64, 1783990000, max_num_seqs=16, frontier_concurrencies=(16,), ngram_prompt_lookup=True))
        self.assertIn("VLLM_NGRAM_PROMPT_LOOKUP=0", stock)
        self.assertNotIn("--speculative-config", stock)
        self.assertIn("VLLM_NGRAM_PROMPT_LOOKUP=1", candidate)
        remote = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        self.assertIn('{"method":"ngram","num_speculative_tokens":5,"prompt_lookup_min":5,"prompt_lookup_max":5}', remote)
        for kwargs in (
            {"scientific_mode": "bf16-v2-quality", "max_num_seqs": 16, "frontier_concurrencies": (16,)},
            {"max_num_seqs": 8, "frontier_concurrencies": (8,)},
            {"max_num_seqs": 16, "frontier_concurrencies": (16,), "native_mtp": True},
            {"max_num_seqs": 16, "frontier_concurrencies": (16,), "exit35_mode": True},
            {"max_num_seqs": 16, "frontier_concurrencies": (16,), "moe_top2_no_shared": True},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(RuntimeError, "ngram prompt lookup requires AWQ L40S c16 only"):
                build_container_command("n" * 64, 1783990000, ngram_prompt_lookup=True, **kwargs)

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

    def test_head_shared_w4_remote_binder_matches_the_staged_binder_basename(self):
        control = (ROOT / "nebius" / "vllm_smoke_control.py").read_text()
        script = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        binder = re.search(r'head_shared_binder = .* / "([^"]+)"', control)
        self.assertIsNotNone(binder)
        self.assertIn("shutil.copy2(head_shared_binder, staging / head_shared_binder.name)", control)
        self.assertIn(f"python3 /input/{binder.group(1)}", script)
        self.assertNotIn("python3 /input/head_shared_w4_bind.py", script)

    def test_isolated_selective_w4_scope_reaches_the_remote_contract(self):
        joined = " ".join(
            build_container_command(
                "a" * 64,
                1783990000,
                head_shared_w4=True,
                selective_w4_scope="shared_only",
            )
        )
        self.assertIn("GLM_HEAD_SHARED_W4=1", joined)
        self.assertIn("GLM_SELECTIVE_W4_SCOPE=shared_only", joined)

    def test_isolated_selective_w4_scope_requires_selective_w4_mode(self):
        with self.assertRaisesRegex(Exception, "isolated selective-W4 scope"):
            build_container_command(
                "a" * 64,
                1783990000,
                selective_w4_scope="head_only",
            )

    def test_remote_telemetry_uses_utc_timestamps(self):
        script = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        self.assertIn("TZ=UTC nvidia-smi --query-gpu=timestamp", script)

    def test_remote_embedded_python_blocks_compile(self):
        script = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        blocks = re.findall(r"python3 - <<'PY'\n(.*?)\nPY", script, re.DOTALL)
        self.assertTrue(blocks)
        for block in blocks:
            compile(block, "remote_vllm_awq_smoke.sh", "exec")

    def test_remote_identity_gate_binds_the_current_awq_tokenizer(self):
        script = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        self.assertIn("353a3ff93723c098ac93fb593d4d1b93faede916fe502b005cd503871023e012", script)
        self.assertIn("b6b807f7bfaf4fb4bd3952f58a70d61442620df8e5d8a904dcf4bc6ca7946940", script)

    def test_methodology_runner_is_explicit_opt_in_after_control(self):
        source = (ROOT / "nebius" / "vllm_smoke_control.py").read_text()
        remote = (ROOT / "nebius" / "remote_vllm_awq_smoke.sh").read_text()
        self.assertIn('methodology_runner = HERE / "vllm_methodology_runner.py"', source)
        self.assertIn('parser.add_argument("--run-methodology", action="store_true")', source)
        self.assertIn("VLLM_RUN_METHODOLOGY=0", " ".join(build_container_command("a" * 64, 1783990000)))
        self.assertIn("VLLM_RUN_METHODOLOGY=1", " ".join(build_container_command("a" * 64, 1783990000, max_num_seqs=32, frontier_concurrencies=(32,), run_methodology=True)))
        self.assertIn('VLLM_RUN_METHODOLOGY="${VLLM_RUN_METHODOLOGY:-0}"', remote)
        self.assertIn('if [ "$VLLM_RUN_METHODOLOGY" = "1" ]; then', remote)
        self.assertIn("vllm_methodology_runner.py", remote)

    def test_infrastructure_failures_do_not_idle_without_explicit_repair_window(self):
        emitted = []
        with tempfile.TemporaryDirectory() as tmp, patch(
            "vllm_smoke_control.emit",
            side_effect=lambda _path, event, **fields: emitted.append((event, fields)),
        ), patch("vllm_smoke_control.time.sleep", side_effect=AssertionError("must not wait")):
            hold_for_repair_decision(Path(tmp), Path(tmp) / "events.jsonl", 10**12)
        self.assertEqual(emitted, [("repair_window_skipped", {})])
        source = (ROOT / "nebius" / "vllm_smoke_control.py").read_text()
        self.assertIn("--repair-window-seconds", source)
        self.assertIn("min(maximum_seconds, 600)", source)
        self.assertIn("repair-decision.json", source)
        self.assertIn('decision.get("action") == "teardown"', source)

    def test_launcher_uses_resumable_staging_and_reserves_artifact_time(self):
        source = (ROOT / "nebius" / "vllm_smoke_control.py").read_text()
        self.assertIn("transfer_checkpoint(", source)
        self.assertIn("transfer_timeout_seconds", source)
        self.assertIn("science_deadline = deadline - ARTIFACT_RESERVE_SECONDS", source)
        self.assertIn('measured_phase(events, "checkpoint_transfer")', source)
        joined = " ".join(build_container_command("a" * 64, 1783990000, server_health_timeout_seconds=360))
        self.assertIn("VLLM_SERVER_HEALTH_TIMEOUT_SECONDS=360", joined)

    def test_moe_top2_no_shared_is_l40s_c16_only_and_binds_patch_identity(self):
        joined = " ".join(build_container_command("a" * 64, 1783990000, max_num_seqs=16, frontier_concurrencies=(16,), moe_top2_no_shared=True))
        self.assertIn("GLM_MOE_TOP2_NO_SHARED=1", joined)
        self.assertIn("GLM_MOE_TOP2_NO_SHARED_PATCH_SHA256=69f34087f816038a8ba7e9c3874b42fb6837d4f4df794a11f0d8c797820dfa7e", joined)
        with self.assertRaisesRegex(Exception, "moe top2/no-shared mode requires AWQ mode"):
            build_container_command("a" * 64, 1783990000, scientific_mode="bf16-v2-quality", moe_top2_no_shared=True)
        source = (ROOT / "nebius" / "vllm_smoke_control.py").read_text()
        self.assertIn('parser.add_argument("--moe-top2-no-shared", action="store_true")', source)
        self.assertIn("moe top2/no-shared mode requires l40s-awq c16 only", source)
        self.assertIn("moe_top2_no_shared_patch_sha256", source)

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
