import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
NEBIUS = ROOT / "nebius"
sys.path.insert(0, str(NEBIUS))

import observer_diagnostic_control as observer_control  # noqa: E402
from observer_diagnostic_control import (  # noqa: E402
    ABSOLUTE_TIMEOUT_SECONDS,
    CLEANUP_RESERVE_SECONDS,
    COMBINED_HOURLY_RATE_USD,
    FACTORY_CLEANUP_RESERVE_USD,
    FACTORY_CAMPAIGN,
    FACTORY_RUN_ID,
    MAX_COST_USD,
    NSYS_PACKAGE_VERSION,
    NSYS_LAUNCH_REQUIRED_FLAGS,
    OPERATIONAL_STARTUP_ISOLATION,
    build_container_command,
    build_factory_command,
    build_host_bootstrap,
    cleanup_verification_sha256,
    nsys_launch_semantic_diff,
    normalize_nsys_launch_help,
    validate_nsys_launch_help,
    validate_nsys_start_help,
    validate_nsys_observer_argv,
    repair_window_seconds,
    session_labels,
    should_run_fallback,
    run as observer_run,
    valid_factory_run_id,
)
from launcher_retention import launcher_record  # noqa: E402
from placement_control import build_create_command  # noqa: E402


class ObserverDiagnosticControlTests(unittest.TestCase):
    def test_host_bootstrap_quote_boundary_repair_is_syntax_only(self):
        bootstrap = build_host_bootstrap()
        self.assertEqual(subprocess.run(
            ["bash", "-n"], input=bootstrap, text=True,
            capture_output=True, check=False,
        ).returncode, 0)
        expected = "unrecognised option " + "'" + '"' + "'" + '"' + "'--output"
        self.assertIn(expected, bootstrap)
        self.assertNotIn("unrecognised option '--output", bootstrap)

    def test_host_bootstrap_quote_boundary_preserves_probe_argument(self):
        bootstrap = build_host_bootstrap()
        expected = "grep -F -- " + '"' + "unrecognised option " + "'" + '"' + "'" + '"' + "'--output" + '"'
        self.assertIn(expected, bootstrap)
        self.assertEqual(bootstrap.count("nsys launch --session-new="), 4)

    def test_nsys_help_normalization_accepts_only_presentation_drift(self):
        fixture = (NEBIUS / "fixtures" / "nsys-launch-help-2026.3.1.157.txt").read_bytes()
        fixture = b"\n" + fixture + b"\n\n"
        drifted = fixture.replace(b"\n", b"\r\n")
        drifted = drifted.replace(b"\n\n", b"\n\n\n")
        drifted = drifted.replace(b"\t--trace=", b"    --trace=")
        self.assertEqual("", nsys_launch_semantic_diff(fixture, drifted))
        validate_nsys_launch_help(fixture, drifted)
        self.assertEqual(normalize_nsys_launch_help(fixture), normalize_nsys_launch_help(drifted))

    def test_nsys_help_boundary_blank_line_cases_are_separate(self):
        fixture = (NEBIUS / "fixtures" / "nsys-launch-help-2026.3.1.157.txt").read_bytes()
        cases = {
            "leading_one": b"\n" + fixture,
            "leading_many": b"\n\n\n" + fixture,
            "trailing_one": fixture + b"\n",
            "trailing_many": fixture + b"\n\n\n",
            "both": b"\n\n" + fixture + b"\n\n\n",
        }
        for name, observed in cases.items():
            with self.subTest(name=name):
                validate_nsys_launch_help(fixture, observed)
                self.assertEqual("", nsys_launch_semantic_diff(fixture, observed))

    def test_nsys_help_fail_closed_controls(self):
        fixture = (NEBIUS / "fixtures" / "nsys-launch-help-2026.3.1.157.txt").read_bytes()
        controls = {
            "option_rename": fixture.replace(b"--cuda-event-trace=", b"--cuda-event-events="),
            "option_value_syntax": fixture.replace(b"--cuda-event-trace=", b"--cuda-event-trace"),
            "forbidden_force_overwrite": fixture + b"\n--force-overwrite=true\n",
            "version_drift": b"NVIDIA Nsight Systems version 2026.3.1.158\n" + fixture,
        }
        for flag in NSYS_LAUNCH_REQUIRED_FLAGS:
            controls[f"missing_{flag.removeprefix('--')}"] = fixture.replace(
                flag.encode() + b"=", b"", 1
            )
        for name, observed in controls.items():
            with self.subTest(name=name):
                with self.assertRaises(observer_control.ObserverDiagnosticError):
                    validate_nsys_launch_help(fixture, observed)

    def test_nsys_help_required_flag_rename_fails_closed(self):
        fixture = (NEBIUS / "fixtures" / "nsys-launch-help-2026.3.1.157.txt").read_bytes()
        renamed = fixture.replace(b"--cuda-event-trace=", b"--cuda-event-events=")
        with self.assertRaises(observer_control.ObserverDiagnosticError):
            validate_nsys_launch_help(fixture, renamed)

    def test_nsys_help_required_flags_are_exact_tokens(self):
        fixture = (NEBIUS / "fixtures" / "nsys-launch-help-2026.3.1.157.txt").read_bytes()
        self.assertEqual(set(NSYS_LAUNCH_REQUIRED_FLAGS), {
            "--session-new", "--trace", "--cuda-graph-trace", "--cuda-event-trace",
            "--sample", "--cpuctxsw",
        })
        renamed = fixture.replace(b"--trace=", b"--trace-fork=")
        with self.assertRaises(observer_control.ObserverDiagnosticError):
            validate_nsys_launch_help(fixture, renamed)

    def test_backtrace_is_start_owned_and_omitted_from_constructed_argv(self):
        source = (NEBIUS / "remote_observer_diagnostic.sh").read_text()
        argv = validate_nsys_observer_argv(source)
        self.assertNotIn("--backtrace", argv["launch"])
        self.assertNotIn("--backtrace", argv["start"])
        self.assertIn("not supported by the launch command", build_host_bootstrap())
        self.assertIn("nsys launch unexpectedly accepted --backtrace=none", build_host_bootstrap())

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
        self.assertGreaterEqual(bootstrap.count("rm -f /etc/ld.so.conf.d/00-cuda-compat.conf"), 2)
        compat_cleanup = bootstrap.rindex("rm -f /etc/ld.so.conf.d/00-cuda-compat.conf")
        self.assertLess(compat_cleanup, bootstrap.index("nsys profile --force-overwrite=true"))
        self.assertIn("torch.cuda.CUDAGraph", bootstrap)
        self.assertIn("-v /home/glmrunner/input:/input:ro", bootstrap)

    def test_v8_preflights_exact_nsys_launch_cli_and_omits_unsupported_option(self):
        bootstrap = build_host_bootstrap()
        self.assertIn("-lc \"$(cat <<'REMOTE_SCRIPT'", bootstrap)
        self.assertIn("REMOTE_SCRIPT\n)\"", bootstrap)
        self.assertIn("nsys launch --help", bootstrap)
        self.assertIn("nsys-launch-help-2026.3.1.157.txt", bootstrap)
        self.assertIn("test -s /input/nsys-launch-help-2026.3.1.157.txt", bootstrap)
        self.assertIn("sha256sum /input/nsys-launch-help-2026.3.1.157.txt", bootstrap)
        fixture = NEBIUS / "fixtures" / "nsys-launch-help-2026.3.1.157.txt"
        fixture_text = fixture.read_text()
        self.assertGreater(len(fixture_text.splitlines()), 100)
        self.assertIn("usage: nsys launch [<args>] [application] [<application args>]", fixture_text)
        self.assertNotIn("Usage: nsys launch [options] application [application options]", fixture_text)
        for flag in (
            "session-new",
            "trace",
            "cuda-graph-trace",
            "cuda-event-trace",
            "sample",
            "cpuctxsw",
        ):
            self.assertIn(f'--{flag}', bootstrap)
        self.assertLess(
            bootstrap.index(f'grep -F "{NSYS_PACKAGE_VERSION}"'),
            bootstrap.index("nsys launch --help"),
        )

        source = (NEBIUS / "remote_observer_diagnostic.sh").read_text()
        launch = source[source.index("nsys launch ") : source.index("SERVER=$!", source.index("nsys launch "))]
        self.assertIn('--session-new="$session"', launch)
        self.assertNotIn("--force-overwrite", launch)

    def test_v8_controller_transfers_fixture_and_preflights_before_model_transfer(self):
        calls = []
        bootstrap = build_host_bootstrap()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            model = root / "model"
            tokenizer = root / "tokenizer"
            model.mkdir()
            tokenizer.mkdir()
            (model / "config.json").write_text("{}\n")
            for name in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja"):
                (tokenizer / name).write_text("fixture\n")
            key = root / "key"
            public_key = root / "key.pub"
            key.write_text("key\n")
            public_key.write_text("ssh-ed25519 fixture\n")

            def fake_scp(_ip, _key, sources, destination):
                calls.append(("scp", [Path(source).name for source in sources], destination))

            def fake_ssh(_ip, _key, command, **kwargs):
                if kwargs.get("input_text") == bootstrap:
                    calls.append(("bootstrap", kwargs["input_text"]))
                else:
                    calls.append(("ssh", command))
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            def fake_transfer(*_args):
                calls.append(("model-transfer",))

            create_result = SimpleNamespace(returncode=0, stdout='{"id":"computeinstance-v8-test"}\n', stderr="")
            launcher = root / "host-bootstrap-launcher.sh"
            launcher.write_bytes(observer_control.build_host_bootstrap().encode("utf-8"))
            (root / "host-bootstrap-launcher.sh.json").write_text(
                json.dumps(launcher_record(launcher.read_bytes()))
            )
            with mock.patch.object(observer_control, "validate_local_model", return_value={"model": "fixture"}), \
                mock.patch.object(observer_control, "list_items", return_value=[]), \
                mock.patch.object(observer_control, "find_named_instance", return_value=None), \
                mock.patch.object(observer_control, "build_create_command", return_value=["provider-create"]), \
                mock.patch.object(observer_control.subprocess, "run", return_value=create_result), \
                mock.patch.object(observer_control.subprocess, "Popen"), \
                mock.patch.object(observer_control, "_run_factory_action"), \
                mock.patch.object(observer_control, "get_instance", return_value={"public_ip_address": {"address": "8.8.8.8"}}), \
                mock.patch.object(observer_control, "wait_ssh"), \
                mock.patch.object(observer_control, "run_ssh", side_effect=fake_ssh), \
                mock.patch.object(observer_control, "scp_to", side_effect=fake_scp), \
                mock.patch.object(observer_control, "probe_transfer", return_value="probe"), \
                mock.patch.object(observer_control, "transfer_local_model", side_effect=fake_transfer), \
                mock.patch.object(observer_control, "retrieve_observer_artifact", side_effect=observer_control.ObserverDiagnosticError("test boundary")), \
                mock.patch.object(observer_control, "delete_instance"), \
                mock.patch.object(observer_control, "delete_disk"), \
                mock.patch.object(observer_control, "wait_absent", return_value=True):
                result = observer_control.run(
                    output,
                    "observer-v8-test",
                    key,
                    public_key,
                    model,
                    tokenizer,
                    "a" * 64,
                    factory_root=root / "factory",
                    factory_program=observer_control.FACTORY_PROGRAM,
                    factory_campaign=FACTORY_CAMPAIGN,
                    factory_run_id=observer_control.FACTORY_RUN_ID,
                    factory_owner="supervisor-test",
                    factory_reservation_id="reservation-test",
                    factory_allocation_id="allocation-test",
                    factory_setup_key=observer_control.FACTORY_SETUP_KEY,
                    factory_absolute_deadline="2099-01-01T00:00:00Z",
                    host_bootstrap_launcher=launcher,
                )

            self.assertEqual(result, 1)
            fixture_transfer = next(
                index for index, call in enumerate(calls)
                if call[0] == "scp" and "nsys-launch-help-2026.3.1.157.txt" in call[1]
            )
            bootstrap_call = next(index for index, call in enumerate(calls) if call[0] == "bootstrap")
            model_transfer = next(index for index, call in enumerate(calls) if call[0] == "model-transfer")
            self.assertLess(fixture_transfer, bootstrap_call)
            self.assertLess(bootstrap_call, model_transfer)
            self.assertLess(bootstrap.index("-v /home/glmrunner/input:/input:ro"), bootstrap.index("test -s /input/nsys-launch-help-2026.3.1.157.txt"))
            self.assertLess(bootstrap.index("sha256sum /input/nsys-launch-help-2026.3.1.157.txt"), bootstrap.index("nsys launch --help"))
            self.assertLess(bootstrap.index("nsys launch capability semantic mismatch"), bootstrap.index("nsys profile --force-overwrite=true"))
            readiness = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
            readiness_names = [row["event"] for row in readiness]
            self.assertLess(readiness_names.index("public_ip_ready"), readiness_names.index("ssh_cloud_init_probe_started"))
            self.assertLess(readiness_names.index("ssh_cloud_init_probe_started"), readiness_names.index("ssh_ready"))
            self.assertEqual(readiness[readiness_names.index("public_ip_ready")]["attempt_number"], 1)
            self.assertEqual(readiness[readiness_names.index("ssh_cloud_init_probe_started")]["attempt_number"], 1)
            self.assertIn("absolute_deadline_epoch", readiness[readiness_names.index("ssh_cloud_init_probe_started")])
            self.assertTrue((output / "events.jsonl").is_file())

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

    def test_v8_runs_excluded_unpatched_startup_probe_before_patch_and_scored_arms(self):
        source = (NEBIUS / "remote_observer_diagnostic.sh").read_text()
        self.assertEqual(FACTORY_RUN_ID, "glm47-observer-diagnostic-l40s-v17")
        self.assertTrue(valid_factory_run_id("glm47-observer-diagnostic-l40s-v17"))
        self.assertTrue(valid_factory_run_id("glm47-observer-diagnostic-l40s-v18"))
        self.assertTrue(valid_factory_run_id("glm47-observer-diagnostic-l40s-v27"))
        self.assertFalse(valid_factory_run_id(""))
        self.assertFalse(valid_factory_run_id("glm47-observer-diagnostic-l40s-v17\n"))
        self.assertFalse(valid_factory_run_id("glm47-observer-diagnostic-l40s-v17-extra"))
        self.assertFalse(valid_factory_run_id("glm47-observer-diagnostic-l40s-v17 "))
        self.assertFalse(valid_factory_run_id("glm47-observer-diagnostic-l40s-v16"))
        self.assertFalse(valid_factory_run_id("glm47-observer-diagnostic-l40s-v13"))
        self.assertFalse(valid_factory_run_id("glm47-observer-diagnostic-l40s-v0"))
        self.assertFalse(valid_factory_run_id("other-campaign-v11"))
        self.assertFalse(valid_factory_run_id("glm47-observer-diagnostic-l40s-v12-extra"))
        stock_probe_definition = source.index("run_stock_startup_probe()")
        stock_probe = source.index("\nrun_stock_startup_probe\n", stock_probe_definition)
        patch = source.index("phase observer_patch begin", stock_probe)
        first_scored_arm = source.index("run_arm A1 off", patch)
        self.assertLess(stock_probe, patch)
        self.assertLess(patch, first_scored_arm)

        probe = source[stock_probe_definition:stock_probe]
        self.assertIn('CURRENT_ARM="STOCK_STARTUP"', probe)
        self.assertIn('CURRENT_MODE="stock-unpatched"', probe)
        self.assertIn('wait_healthy "$CURRENT_ARM"', probe)
        self.assertIn("stop_server", probe)
        self.assertIn('"excluded_from_measurement":true', probe)
        self.assertIn('"scored_requests":0', probe)
        self.assertNotIn("observer_workload.py", probe)
        self.assertNotIn("run_warmup", probe)
        self.assertNotIn("vllm_observer_patch.py", probe)

    def test_controller_rejects_retired_identity_before_provider_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(observer_control.ObserverDiagnosticError):
                observer_run(
                    Path(directory),
                    "observer-v12-test",
                    Path(directory) / "key",
                    Path(directory) / "key.pub",
                    Path(directory) / "model",
                    Path(directory) / "tokenizer",
                    "a" * 64,
                    factory_root=Path(directory) / "factory",
                    factory_program=observer_control.FACTORY_PROGRAM,
                    factory_campaign=FACTORY_CAMPAIGN,
                    factory_run_id="glm47-observer-diagnostic-l40s-v11",
                    factory_owner="supervisor-test",
                    factory_reservation_id="reservation-test",
                    factory_allocation_id="allocation-test",
                    factory_setup_key=observer_control.FACTORY_SETUP_KEY,
                    factory_absolute_deadline="2099-01-01T00:00:00Z",
                )

    def test_stock_probe_uses_existing_readiness_limit_and_is_in_failure_archives(self):
        source = (NEBIUS / "remote_observer_diagnostic.sh").read_text()
        wait_healthy = source[source.index("wait_healthy()") : source.index("archive_arm()")]
        self.assertIn("for attempt in $(seq 1 180)", wait_healthy)
        self.assertIn("sleep 2", wait_healthy)
        partial = source[source.index("refresh_partial_archive()") : source.index("stop_server()")]
        self.assertIn("probe.json", partial)
        self.assertIn("server-status.json", partial)
        self.assertIn("server.stdout.log", partial)
        self.assertIn("server.stderr.log", partial)
        self.assertIn("health-attempts.jsonl", partial)
        self.assertIn("nvidia-smi-loaded.txt", partial)

    def test_stock_probe_stop_is_bounded_and_proves_absence_before_patch(self):
        source = (NEBIUS / "remote_observer_diagnostic.sh").read_text()
        stop = source[source.index("stop_server()") : source.index("package_session()")]
        probe_start = source.index("run_stock_startup_probe()")
        probe_call = source.index("\nrun_stock_startup_probe\n", probe_start)
        probe = source[probe_start:probe_call]
        self.assertIn("for _ in $(seq 1 30)", stop)
        self.assertIn("pkill -KILL", stop)
        self.assertIn("kill -KILL", stop)
        self.assertIn("pgrep -f 'vllm serve /workspace/model-awq'", stop)
        self.assertIn("stop_failed", stop)
        self.assertIn("stopped_and_absent", stop)
        self.assertLess(probe.index("wait_healthy"), probe.index("stop_server"))
        self.assertEqual(OPERATIONAL_STARTUP_ISOLATION["term_timeout_seconds"], 30)
        self.assertEqual(OPERATIONAL_STARTUP_ISOLATION["requests"], 0)

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

    def test_nsight_session_output_is_started_at_start_boundary(self):
        source = (NEBIUS / "remote_observer_diagnostic.sh").read_text()
        launch_start = source.index("    nsys launch --session-new=\"$session\"")
        launch_end = source.index('      > "$arm_dir/server.stdout.log"', launch_start)
        launch = source[launch_start:launch_end]
        self.assertNotIn("--output=", launch)
        start = source.index('nsys start --session="$session"')
        self.assertIn(' --output="$arm_dir/trace"', source[start:source.index("\n", start)])

    def test_generated_preflight_avoids_nested_shell_awk_positional_expansion(self):
        bootstrap = observer_control.build_host_bootstrap()
        self.assertIn('sha256sum /tmp/nsys-start-help-2026.3.1.157.txt | cut -d " " -f1', bootstrap)
        self.assertNotIn("awk '{{print $1}}'", bootstrap)

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

    def test_remote_keeps_atomic_hashed_partial_failure_evidence(self):
        source = (NEBIUS / "remote_observer_diagnostic.sh").read_text()
        self.assertIn("observer-diagnostic-partial.tar.gz.tmp", source)
        self.assertIn("observer-diagnostic-partial.tar.gz.sha256.tmp", source)
        self.assertIn('(root / "manifest.json")', source)
        self.assertIn('server-status.json', source)
        self.assertIn('server.stdout.log', source)
        self.assertIn('server.stderr.log', source)
        self.assertIn('health-attempts.jsonl', source)
        self.assertIn('phases.jsonl', source)
        self.assertLess(
            source.index("refresh_partial_archive", source.index("finish()")),
            source.index("package_session", source.index("finish()")),
        )

    def test_partial_failure_evidence_keeps_completed_arm_raw_scoring_files(self):
        source = (NEBIUS / "remote_observer_diagnostic.sh").read_text()
        partial = source[source.index("refresh_partial_archive()") : source.index("stop_server()")]
        for name in (
            "workload.json",
            "workload.stdout.log",
            "workload.stderr.log",
            "gate.json",
            "scheduler-events.jsonl",
        ):
            self.assertIn(name, partial)

    def test_readiness_failure_is_recorded_before_returning(self):
        source = (NEBIUS / "remote_observer_diagnostic.sh").read_text()
        wait_healthy = source[source.index("wait_healthy()") : source.index("archive_arm()")]
        self.assertIn('health-attempts.jsonl', wait_healthy)
        self.assertIn('record_server_status "$arm" "$CURRENT_MODE" exited "$server_rc"', wait_healthy)
        self.assertIn('record_server_status "$arm" "$CURRENT_MODE" readiness_failed null', wait_healthy)
        self.assertGreaterEqual(wait_healthy.count("refresh_partial_archive"), 2)

        run_arm = source[source.index("run_arm()") : source.index("# The exact same retained image")]
        running = run_arm.index('record_server_status "$arm" "$mode" running null')
        refresh = run_arm.index("refresh_partial_archive", running)
        readiness = run_arm.index('wait_healthy "$arm"', refresh)
        self.assertLess(running, refresh)
        self.assertLess(refresh, readiness)

    def test_controller_orders_preflight_before_large_transfer_and_evidence_before_delete(self):
        source = (NEBIUS / "observer_diagnostic_control.py").read_text()
        self.assertIn('"operational_startup_isolation": OPERATIONAL_STARTUP_ISOLATION', source)
        self.assertLess(source.index('"nsys_preflight_passed"'), source.index("transfer_local_model(ip, key, model_dir)"))
        self.assertLess(source.index("scp_from(ip, key, REMOTE_ARCHIVE"), source.index("delete_instance(instance_id)"))
        self.assertIn("start_new_session=True", source)
        self.assertIn("wait_absent(instance_id", source)
        self.assertIn("final_instance_count", source)
        self.assertIn("final_disk_count", source)

    def test_controller_falls_back_to_verified_partial_artifact_without_scoring_it(self):
        source = (NEBIUS / "observer_diagnostic_control.py").read_text()
        self.assertIn("REMOTE_PARTIAL_ARCHIVE", source)
        self.assertIn("observer-diagnostic-partial.tar.gz", source)
        retrieve = source[source.index("def retrieve_observer_artifact") : source.index("def session_labels")]
        self.assertLess(retrieve.index("REMOTE_ARCHIVE"), retrieve.index("REMOTE_PARTIAL_ARCHIVE"))
        self.assertEqual(retrieve.count("verify_internal_manifest"), 2)
        self.assertIn('return "partial"', retrieve)
        self.assertIn('outcome = "FAIL"', source[source.index("artifact_kind =") :])
        remote_segment = source[source.index("remote = None") : source.index("allocation_result = json.loads")]
        self.assertLess(remote_segment.index("except Exception as error"), remote_segment.index("retrieve_observer_artifact"))

    def test_partial_retrieval_verifies_outer_hash_and_internal_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_root = root / "campaign-100-observer-partial"
            bundle_root.mkdir()
            payload = b'{"complete":false}\n'
            (bundle_root / "partial-metadata.json").write_bytes(payload)
            manifest = [{
                "path": "partial-metadata.json",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }]
            (bundle_root / "manifest.json").write_text(json.dumps(manifest))
            remote_archive = root / "remote-partial.tar.gz"
            with tarfile.open(remote_archive, "w:gz") as bundle:
                bundle.add(bundle_root, arcname=bundle_root.name)
            remote_hash = hashlib.sha256(remote_archive.read_bytes()).hexdigest()

            def fake_scp(_ip, _key, source, destination):
                if source == observer_control.REMOTE_ARCHIVE:
                    raise FileNotFoundError(source)
                if source == observer_control.REMOTE_PARTIAL_ARCHIVE:
                    shutil.copy2(remote_archive, destination)
                    return
                if source == observer_control.REMOTE_PARTIAL_SIDECAR:
                    destination.write_text(remote_hash + "  observer-diagnostic-partial.tar.gz\n")
                    return
                raise AssertionError(source)

            output = root / "output"
            output.mkdir()
            with mock.patch.object(observer_control, "scp_from", side_effect=fake_scp):
                kind, archive, digest, count = observer_control.retrieve_observer_artifact(
                    "192.0.2.1", Path("/unused/key"), output
                )
            self.assertEqual(kind, "partial")
            self.assertEqual(archive.name, "observer-diagnostic-partial.tar.gz")
            self.assertEqual(digest, remote_hash)
            self.assertEqual(count, 1)

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
            run_id="glm47-observer-diagnostic-l40s-v9",
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
        self.assertIn("glm47-observer-diagnostic-l40s-v9", joined)

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
