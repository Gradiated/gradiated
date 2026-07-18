import sys
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nebius"))

from mla_microbench_control import (  # noqa: E402
    ABSOLUTE_TIMEOUT_SECONDS,
    DISK_GIB,
    DISK_HOURLY_RATE_USD,
    HOURLY_RATE_USD,
    IMAGE,
    PLATFORM,
    PRESET,
    build_container_command,
    build_host_bootstrap,
    conditional_trigger,
    hold_for_repair_decision,
    read_stage_terminal,
    repairable_work_deadline,
    retained_development_window,
    run_repairable_operation,
    validate_durable_owner,
)
from vllm_mla_microbench import (  # noqa: E402
    E2E_SHARE_STATUS,
    SOURCE_SHA256,
    UNSCOPED_MIXED_TRACE_KERNEL_DURATION_SHARE,
    Candidate,
    exact_shapes,
    generate_candidates,
    prospective_e2e_gain,
    select_promotable_candidate,
)


class NebiusMlaMicrobenchTests(unittest.TestCase):
    def test_exact_shapes_bind_runtime_and_model_geometry(self):
        shapes = exact_shapes()
        self.assertEqual({shape.batch_size for shape in shapes}, {1, 8})
        self.assertEqual(
            {shape.context_tokens for shape in shapes},
            {8193, 8449, 8705, 8961, 9215},
        )
        for shape in shapes:
            self.assertEqual(shape.query_heads, 20)
            self.assertEqual(shape.kv_heads, 1)
            self.assertEqual(shape.kv_lora_rank, 512)
            self.assertEqual(shape.qk_rope_head_dim, 64)
            self.assertEqual(shape.query_width, 576)
            self.assertEqual(shape.value_width, 512)
            self.assertEqual(shape.model_value_head_dim, 256)
            self.assertEqual(shape.page_size, 16)
            self.assertEqual(shape.stock_kv_splits, 4)

    def test_candidate_grid_is_bounded_and_contains_stock(self):
        candidates = generate_candidates()
        self.assertEqual(len(candidates), len(set(candidates)))
        self.assertIn(Candidate(16, 32, 4, 2, 4), candidates)
        self.assertLessEqual(len(candidates), 80)
        self.assertTrue(all(value.block_h in {8, 16, 32} for value in candidates))
        self.assertTrue(all(value.block_n in {16, 32, 64} for value in candidates))
        self.assertTrue(all(value.num_warps in {2, 4, 8} for value in candidates))
        self.assertTrue(all(value.num_stages in {1, 2, 3} for value in candidates))
        self.assertTrue(all(value.num_kv_splits in {1, 2, 4, 8, 16} for value in candidates))
        self.assertFalse(any(value.block_n == 64 and value.num_stages == 2 for value in candidates))

    def test_source_and_unscoped_trace_diagnostic_are_pinned(self):
        self.assertEqual(SOURCE_SHA256, "cf4debbbbdf2245355177dd7be91c4ac75730a9207a10cd7dab6306a5c3bdec4")
        self.assertAlmostEqual(UNSCOPED_MIXED_TRACE_KERNEL_DURATION_SHARE, 0.3738261181394841)
        self.assertEqual(E2E_SHARE_STATUS, "unavailable_until_phase_aware_c8_trace_or_empirical_ab")

    def test_promotion_requires_scope_matched_e2e_share_and_both_gates(self):
        self.assertIsNone(prospective_e2e_gain(0.10))
        self.assertAlmostEqual(prospective_e2e_gain(0.20, 0.30), 0.06)
        rows = [
            {
                "candidate": Candidate(8, 32, 4, 2, 4).as_dict(),
                "correctness_pass": True,
                "hardware_legal": True,
                "component_time_reduction": 0.12,
            },
            {
                "candidate": Candidate(8, 64, 4, 1, 4).as_dict(),
                "correctness_pass": True,
                "hardware_legal": True,
                "component_time_reduction": 0.15,
            },
        ]
        self.assertIsNone(select_promotable_candidate(rows))
        selected = select_promotable_candidate(rows, measured_e2e_share=0.40)
        self.assertEqual(selected["candidate"]["block_n"], 64)
        self.assertGreaterEqual(selected["prospective_e2e_gain"], 0.05)

    def test_incorrect_or_illegal_candidates_cannot_promote(self):
        rows = [
            {
                "candidate": Candidate(8, 64, 4, 1, 4).as_dict(),
                "correctness_pass": False,
                "hardware_legal": True,
                "component_time_reduction": 0.50,
            },
            {
                "candidate": Candidate(4, 64, 8, 2, 4).as_dict(),
                "correctness_pass": True,
                "hardware_legal": False,
                "component_time_reduction": 0.50,
            },
        ]
        self.assertIsNone(select_promotable_candidate(rows))

    def test_control_uses_cheapest_same_gpu_geometry_and_bounded_cost(self):
        self.assertEqual(PLATFORM, "gpu-l40s-a")
        self.assertEqual(PRESET, "1gpu-8vcpu-32gb")
        self.assertEqual(DISK_GIB, 100)
        self.assertAlmostEqual(HOURLY_RATE_USD, 0.7492)
        self.assertAlmostEqual(DISK_HOURLY_RATE_USD, 0.0097222)
        self.assertEqual(ABSOLUTE_TIMEOUT_SECONDS, 2700)
        self.assertLess((HOURLY_RATE_USD + DISK_HOURLY_RATE_USD) * ABSOLUTE_TIMEOUT_SECONDS / 3600, 0.60)

    def test_bootstrap_and_container_pin_exact_runtime_without_weights(self):
        bootstrap = build_host_bootstrap()
        self.assertIn(IMAGE, bootstrap)
        self.assertIn("rm -f /etc/ld.so.conf.d/00-cuda-compat.conf", bootstrap)
        self.assertIn("torch.cuda.get_device_name", bootstrap)
        command = " ".join(build_container_command("a" * 64, 1783990000))
        self.assertIn(IMAGE, command)
        self.assertIn("/input/vllm_mla_microbench.py", command)
        self.assertIn("EXPERIMENT_SPEC_SHA256=" + "a" * 64, command)
        self.assertNotIn("model-awq", command)

    def test_explicit_runtime_image_reaches_bootstrap_and_container(self):
        image = "docker.io/vllm/vllm-openai:gemma4@sha256:" + "b" * 64
        self.assertIn(image, build_host_bootstrap(image))
        command = " ".join(build_container_command("a" * 64, 1783990000, runtime_image=image))
        self.assertIn(image, command)
        self.assertIn("RUNTIME_IMAGE_IDENTITY=" + image, command)

    def test_remote_harness_captures_telemetry_and_content_addressed_artifact(self):
        source = (ROOT / "nebius" / "remote_mla_microbench.sh").read_text()
        self.assertIn("nvidia-smi --query-gpu=", source)
        self.assertIn("manifest.json", source)
        self.assertIn("sha256sum", source)
        self.assertIn("vllm_mla_microbench.py", source)
        self.assertIn("benchmark_sha256", source)

    def test_reference_masks_padding_on_nonmultiple_final_pages(self):
        source = (ROOT / "nebius" / "vllm_mla_microbench.py").read_text()
        self.assertIn("< sequence_lengths[:, None]", source)
        self.assertIn('masked_fill(~valid_tokens[:, None, :], float("-inf"))', source)

    def test_infrastructure_error_is_owned_by_verified_cleanup(self):
        source = (ROOT / "nebius" / "mla_microbench_control.py").read_text()
        self.assertIn('with VerifiedRetainedOwner(name, output_dir / "cleanup.json")', source)
        self.assertIn('emit(events, "experiment_error"', source)

    def test_create_path_persists_diagnostic_and_reconciles_before_watchdog(self):
        source = (ROOT / "nebius" / "mla_microbench_control.py").read_text()
        self.assertIn("write_create_diagnostic(output_dir, proc)", source)
        self.assertIn("resolve_created_instance(proc, name)", source)
        self.assertLess(
            source.index("write_create_diagnostic(output_dir, proc)"),
            source.index("start_independent_watchdog(instance_id"),
        )
        self.assertLess(
            source.index("retained.bind_instance(instance_id)"),
            source.index("start_independent_watchdog(instance_id"),
        )

    def test_owner_rejection(self):
        with self.assertRaisesRegex(RuntimeError, "durable service ownership"):
            validate_durable_owner({})

    def test_primary_artifact_preservation(self):
        terminal = {"stage": "primary", "pass": True, "all_actual_consumers_pass": True, "economic_both_envelopes_falsified": False}
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "primary.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                data = json.dumps(terminal).encode()
                member = tarfile.TarInfo("artifact/stage-terminal.json"); member.size = len(data)
                bundle.addfile(member, io.BytesIO(data))
            self.assertEqual(read_stage_terminal(archive), terminal)

    def test_true_branch_sequences_only_after_primary_terminal(self):
        self.assertTrue(conditional_trigger({"stage": "primary", "pass": True, "all_actual_consumers_pass": True, "economic_both_envelopes_falsified": False}))

    def test_false_trigger_cleanup_branch_is_not_eligible_for_conditional(self):
        self.assertFalse(conditional_trigger({"stage": "primary", "pass": True, "all_actual_consumers_pass": True, "economic_both_envelopes_falsified": True}))

    def test_error_contract_keeps_verified_owner_cleanup(self):
        source = (ROOT / "nebius" / "mla_microbench_control.py").read_text()
        self.assertIn('with VerifiedRetainedOwner(name, output_dir / "cleanup.json")', source)
        self.assertIn('except Exception as error:', source)
        self.assertIn('"cleanup_pass": cleanup', source)

    def test_development_error_holds_inside_owner_until_repair_decision(self):
        emitted = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "repair-decision.json").write_text(
                json.dumps({"action": "teardown"})
            )
            with patch(
                "mla_microbench_control.emit",
                side_effect=lambda _path, event, **fields: emitted.append(
                    (event, fields)
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "recoverable"):
                    with retained_development_window(
                        root, root / "events.jsonl", 10**12, 600
                    ):
                        raise RuntimeError("recoverable")
        self.assertEqual(
            ["repair_window_open", "repair_decision_received"],
            [event for event, _fields in emitted],
        )

    def test_development_work_deadline_reserves_the_repair_window(self):
        self.assertEqual(400, repairable_work_deadline(1000, 600))
        self.assertEqual(1000, repairable_work_deadline(1000, 0))
        with self.assertRaisesRegex(ValueError, "between zero and 600"):
            repairable_work_deadline(1000, 601)

    def test_active_repair_can_extend_retention_within_absolute_deadline(self):
        emitted = []
        now = [100.0]

        def advance(seconds):
            now[0] += seconds

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decision = root / "repair-decision.json"
            decision.write_text(
                json.dumps({"action": "retain", "until_epoch": 125.0})
            )
            with (
                patch("mla_microbench_control.time.time", side_effect=lambda: now[0]),
                patch("mla_microbench_control.time.sleep", side_effect=advance),
                patch(
                    "mla_microbench_control.emit",
                    side_effect=lambda _path, event, **fields: emitted.append(
                        (event, fields)
                    ),
                ),
            ):
                hold_for_repair_decision(
                    root, root / "events.jsonl", deadline=140.0, maximum_seconds=10
                )
            self.assertFalse(decision.exists())

        self.assertEqual(
            [
                "repair_window_open",
                "repair_decision_received",
                "repair_retention_extended",
                "repair_window_expired",
            ],
            [event for event, _fields in emitted],
        )
        self.assertEqual(
            125.0,
            dict(emitted[2][1])["retained_until_epoch"],
        )

    def test_repair_retry_reenters_the_operation_on_the_same_owner(self):
        emitted = []
        attempts = []

        def operation(attempt_number):
            attempts.append(attempt_number)
            if attempt_number == 1:
                raise RuntimeError("recoverable integration error")
            return "repaired-result"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decision = root / "repair-decision.json"
            decision.write_text(json.dumps({"action": "retry"}))
            with patch(
                "mla_microbench_control.emit",
                side_effect=lambda _path, event, **fields: emitted.append(
                    (event, fields)
                ),
            ):
                result = run_repairable_operation(
                    operation,
                    root,
                    root / "events.jsonl",
                    deadline=10**12,
                    maximum_seconds=600,
                )

            self.assertFalse(decision.exists())

        self.assertEqual("repaired-result", result)
        self.assertEqual([1, 2], attempts)
        self.assertEqual(
            [
                "repair_window_open",
                "repair_decision_received",
                "repair_retry_started",
            ],
            [event for event, _fields in emitted],
        )
        self.assertEqual(2, emitted[-1][1]["attempt_number"])


if __name__ == "__main__":
    unittest.main()
