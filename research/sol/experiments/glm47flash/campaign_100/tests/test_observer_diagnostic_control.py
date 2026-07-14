import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEBIUS = ROOT / "nebius"
sys.path.insert(0, str(NEBIUS))

from observer_diagnostic_control import (  # noqa: E402
    ABSOLUTE_TIMEOUT_SECONDS,
    CLEANUP_RESERVE_SECONDS,
    COMBINED_HOURLY_RATE_USD,
    FACTORY_CLEANUP_RESERVE_USD,
    MAX_COST_USD,
    NSYS_PACKAGE_VERSION,
    build_container_command,
    build_factory_command,
    build_host_bootstrap,
    cleanup_verification_sha256,
    repair_window_seconds,
    session_labels,
    should_run_fallback,
)
from placement_control import build_create_command  # noqa: E402


class ObserverDiagnosticControlTests(unittest.TestCase):
    def test_l40s_session_cap_includes_disk_and_cleanup(self):
        self.assertEqual(ABSOLUTE_TIMEOUT_SECONDS, 2000)
        self.assertEqual(MAX_COST_USD, 0.55)
        self.assertEqual(FACTORY_CLEANUP_RESERVE_USD, 0.07)
        self.assertGreaterEqual(CLEANUP_RESERVE_SECONDS, 240)
        self.assertLessEqual(
            COMBINED_HOURLY_RATE_USD * ABSOLUTE_TIMEOUT_SECONDS / 3600
            + FACTORY_CLEANUP_RESERVE_USD,
            MAX_COST_USD,
        )

    def test_nsys_release_and_all_required_collectors_are_preflighted(self):
        bootstrap = build_host_bootstrap()
        self.assertEqual(NSYS_PACKAGE_VERSION, "2026.3.1.157")
        self.assertIn(f"nsight-systems-cli={NSYS_PACKAGE_VERSION}", bootstrap)
        self.assertIn("AE09FE4BBD223A84B2CCFCE3F60F4B3D7FA2AF80", bootstrap)
        self.assertIn("devtools/repos/ubuntu2204/amd64", bootstrap)
        self.assertNotIn("3bf863cc.pub", bootstrap)
        self.assertIn("nsys status -e", bootstrap)
        self.assertIn("CPU Profiling Environment (process-tree): OK", bootstrap)
        self.assertNotIn("Sampling Environment: OK", bootstrap)
        self.assertIn("--cuda-graph-trace=node", bootstrap)
        self.assertIn("--sample=process-tree", bootstrap)
        self.assertIn("--cpuctxsw=process-tree", bootstrap)
        self.assertNotIn("--gpu-metrics-devices=all", bootstrap)
        self.assertNotIn("--gpu-metrics-frequency=", bootstrap)
        self.assertIn("gpu_metrics_collector=unsupported_on_l40s", bootstrap)
        self.assertIn("torch.cuda.CUDAGraph", bootstrap)

    def test_container_exposes_only_required_profiler_capabilities(self):
        command = build_container_command("a" * 64, 1_900_000_000, 1_899_999_760)
        joined = " ".join(command)
        for capability in ("SYS_NICE", "SYS_ADMIN", "SYS_PTRACE", "PERFMON"):
            self.assertIn(capability, joined)
        self.assertIn("--pid=host", joined)
        self.assertIn("/input/remote_observer_diagnostic.sh", joined)
        self.assertIn("MODEL_MANIFEST_PATH=/workspace/model-awq/model-files.sha256", joined)
        self.assertNotIn("RUNPOD_API_KEY", joined)
        self.assertNotIn("NEBIUS", joined)
        self.assertNotIn("HF_TOKEN", joined)

    def test_fallback_is_only_admitted_after_breach_with_time_and_cost(self):
        self.assertFalse(should_run_fallback(observer_pass=True, remaining_seconds=900))
        self.assertFalse(should_run_fallback(observer_pass=False, remaining_seconds=719))
        self.assertTrue(should_run_fallback(observer_pass=False, remaining_seconds=720))
        self.assertFalse(
            should_run_fallback(
                observer_pass=False,
                remaining_seconds=720,
                remaining_cost_usd=0.079,
            )
        )

    def test_repair_window_requires_a_tested_action_starting_within_ten_minutes(self):
        self.assertEqual(
            repair_window_seconds(
                next_action_tested=False,
                estimated_start_seconds=30,
                seconds_until_deadline=1000,
            ),
            0,
        )
        self.assertEqual(
            repair_window_seconds(
                next_action_tested=True,
                estimated_start_seconds=601,
                seconds_until_deadline=1000,
            ),
            0,
        )
        self.assertEqual(
            repair_window_seconds(
                next_action_tested=True,
                estimated_start_seconds=240,
                seconds_until_deadline=700,
            ),
            240,
        )

    def test_remote_contract_has_exact_bracket_and_conditional_fallback(self):
        source = (NEBIUS / "remote_observer_diagnostic.sh").read_text()
        a1 = source.index("run_arm A1 off")
        b1 = source.index("run_arm B1 nsys-full")
        a2 = source.index("run_arm A2 off")
        self.assertLess(a1, b1)
        self.assertLess(b1, a2)
        self.assertIn('if [ "$RUN_FALLBACK" = true ]; then', source)
        self.assertIn("run_arm B2 nsys-lite", source)
        self.assertNotIn("--gpu-metrics-devices", source)
        self.assertIn("sample_mode=process-tree", source)
        self.assertIn("context_switch_mode=process-tree", source)
        self.assertIn('local sample_mode=none', source)
        self.assertIn('local context_switch_mode=none', source)
        self.assertIn("run_arm A3 off", source)
        self.assertIn("from analyze_nsys_observer import observer_effect", source)
        self.assertIn("python3 /input/observer_workload.py", source)
        self.assertIn("python3 /input/vllm_observer_patch.py", source)

    def test_each_arm_excludes_exact_c8_8192_by_16_warmup_from_measurement(self):
        source = (NEBIUS / "remote_observer_diagnostic.sh").read_text()
        warmup = source.index('run_warmup "$arm"')
        metrics = source.index('metrics > "$arm_dir/metrics-before.txt"', warmup)
        nsys_start = source.index('nsys start --session="$session"', metrics)
        measured = source.index("python3 /input/observer_workload.py", nsys_start)
        self.assertLess(warmup, metrics)
        self.assertLess(metrics, nsys_start)
        self.assertLess(nsys_start, measured)
        self.assertIn('"max_tokens": 16', source)
        self.assertIn('row["input_tokens"] != 8192', source)
        self.assertIn('row["output_tokens"] != 16', source)
        self.assertIn('warmup.json', source)

    def test_result_does_not_promote_raw_nsys_sqlite_to_normalized_route(self):
        source = (NEBIUS / "remote_observer_diagnostic.sh").read_text()
        self.assertIn('"normalized_dependency_analysis_produced": False', source)
        self.assertIn('"route_decision": None', source)
        self.assertIn('"raw_nsys_export_only": True', source)

    def test_remote_verifies_retained_checkpoint_once_and_hashes_every_arm(self):
        source = (NEBIUS / "remote_observer_diagnostic.sh").read_text()
        self.assertEqual(source.count('sha256sum -c "$MODEL_MANIFEST_PATH"'), 1)
        self.assertIn(".campaign-integrity-v1", source)
        self.assertIn("marker_reused=true", source)
        self.assertIn("arm-artifact.tar.gz.sha256", source)
        self.assertIn("observer-diagnostic.tar.gz.sha256", source)
        self.assertIn("TZ=UTC nvidia-smi --query-gpu=timestamp", source)

    def test_controller_orders_preflight_before_large_transfer_and_evidence_before_delete(self):
        source = (NEBIUS / "observer_diagnostic_control.py").read_text()
        self.assertLess(source.index('"nsys_preflight_passed"'), source.index("transfer_local_model(ip, key, model_dir)"))
        self.assertLess(source.index("scp_from(ip, key, REMOTE_ARCHIVE"), source.index("delete_instance(instance_id)"))
        self.assertIn("start_new_session=True", source)
        self.assertIn("wait_absent(instance_id", source)
        self.assertIn("final_instance_count", source)
        self.assertIn("final_disk_count", source)

    def test_factory_lifecycle_commands_bind_exact_provider_resource(self):
        common = {
            "root": Path("/tmp/lab"),
            "program": "glm-4.7-flash",
            "owner": "observer-owner",
            "allocation_id": "observer-allocation-v1",
        }
        register = build_factory_command(
            "register-allocation",
            **common,
            reservation_id="observer-reservation-v1",
            setup_key="l40s:vllm:glm47:observer",
            provider_resource_id="computeinstance-example",
            absolute_deadline="2026-07-14T12:33:20Z",
        )
        request = build_factory_command("request-cleanup", **common)
        verification = cleanup_verification_sha256(
            allocation_id=common["allocation_id"],
            provider_resource_id="computeinstance-example",
            get_absent=True,
            inventory_absent=True,
        )
        marked = build_factory_command(
            "mark-cleanup-verified",
            **common,
            verification_sha256=verification,
            get_absent=True,
            inventory_absent=True,
        )
        register_joined = " ".join(register)
        self.assertIn("grad_research register-allocation", register_joined)
        self.assertIn("--provider nebius", register_joined)
        self.assertIn("--provider-resource-id computeinstance-example", register_joined)
        self.assertIn("--reservation-id observer-reservation-v1", register_joined)
        self.assertIn("--setup-key l40s:vllm:glm47:observer", register_joined)
        self.assertIn("grad_research request-cleanup", " ".join(request))
        marked_joined = " ".join(marked)
        self.assertIn("grad_research mark-cleanup-verified", marked_joined)
        self.assertIn("--get-absent", marked_joined)
        self.assertIn("--inventory-absent", marked_joined)

    def test_factory_registration_and_cleanup_wrap_provider_mutation(self):
        source = (NEBIUS / "observer_diagnostic_control.py").read_text()
        create = source.index("instance_id = extract_instance_id")
        watchdog = source.index("subprocess.Popen(", create)
        register = source.index('_run_factory_action("register-allocation"', watchdog)
        request = source.index('_run_factory_action("request-cleanup"')
        delete = source.index("delete_instance(instance_id)", request)
        verified = source.index('_run_factory_action("mark-cleanup-verified"', delete)
        self.assertLess(create, watchdog)
        self.assertLess(watchdog, register)
        self.assertLess(request, delete)
        self.assertLess(delete, verified)

    def test_provider_resources_are_durably_labeled_for_recovery(self):
        labels = session_labels(
            program="glm-4.7-flash",
            campaign="glm47-nebius-25",
            run_id="glm47-observer-diagnostic-l40s-v4",
        )
        command = build_create_command(
            name="observer-v1",
            disk_name="observer-v1-boot",
            cloud_init="#cloud-config\n",
            labels=labels,
        )
        joined = " ".join(command)
        self.assertIn("--labels", joined)
        self.assertIn("--boot-disk-managed-disk-labels", joined)
        self.assertIn("glm-4.7-flash", joined)
        self.assertIn("glm47-nebius-25", joined)
        self.assertIn("glm47-observer-diagnostic-l40s-v4", joined)

    def test_provider_commands_are_not_executed_by_tests(self):
        # This suite only inspects pure builders and source. Provider lifecycle is
        # exercised by the paid preregistered session, never as a unit-test side effect.
        self.assertNotIn("run", globals())
        self.assertNotIn("delete_instance", globals())

    def test_remote_shell_is_syntactically_valid_and_contains_no_secret_names(self):
        script = NEBIUS / "remote_observer_diagnostic.sh"
        checked = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        source = script.read_text()
        for secret in ("RUNPOD_API_KEY", "NEBIUS_IAM_TOKEN", "HF_TOKEN", "SECRET_KEY"):
            self.assertNotIn(secret, source)


if __name__ == "__main__":
    unittest.main()
