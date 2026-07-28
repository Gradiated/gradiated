from __future__ import annotations

import hashlib
import json
import io
import os
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from grad_research.lab_harness import (
    CodexAgentRunner,
    LabConfig,
    LabHarness,
    ModelRoute,
    codex_environment,
    main,
    run_reports_agent_service_unavailable,
    trace_reports_response_capacity_exhausted,
)


def pool_bench_spec() -> dict:
    return {
        "id": "gemma-h200-1",
        "provider": "nebius",
        "accelerator": "h200-sxm",
        "resource": {"instance_id": "instance-1"},
        "contents": {"model": "google/gemma-4-31b-it", "runtime": "sglang"},
        "lifecycle": {
            "watchdog": {"unit": "gpu-watchdog.service", "unit_manager": "user"},
            "deadline_utc": "2099-07-18T14:00:00Z",
        },
        "hourly_cost_usd": 2.65,
    }


class FakeRunner:
    def __init__(self, lab_dir: Path):
        self.lab_dir = lab_dir
        self.calls: list[dict] = []
        self._lock = threading.Lock()
        self._active_researchers = 0
        self.max_active_researchers = 0

    def run(self, prompt, *, role, route, thread_id, timeout_seconds, label):
        with self._lock:
            self.calls.append(
                {
                    "prompt": prompt,
                    "role": role,
                    "model": route.model,
                    "thread_id": thread_id,
                    "label": label,
                }
            )
            if role == "researcher":
                self._active_researchers += 1
                self.max_active_researchers = max(
                    self.max_active_researchers, self._active_researchers
                )
        if role == "director":
            for name, priority in (("kernel", 2), ("scheduler", 1)):
                project = self.lab_dir / "projects" / name
                project.mkdir(parents=True, exist_ok=True)
                if not (project / "PROJECT.md").exists():
                    (project / "PROJECT.md").write_text(f"# {name}\n")
                    (project / "STATUS.json").write_text(
                        json.dumps(
                            {
                                "status": "active",
                                "priority": priority,
                                "summary": "ready",
                                "next_action": "run the experiment",
                            }
                        )
                    )
        elif role == "researcher":
            time.sleep(0.04)
            project = self.lab_dir / "projects" / label
            with (project / "RESEARCH_LOG.md").open("a") as handle:
                handle.write("\nMeasured one experiment.\n")
            with self._lock:
                self._active_researchers -= 1
        elif role == "supervisor":
            with (self.lab_dir / "SUPERVISOR_LOG.md").open("a") as handle:
                handle.write("\nParallelism is healthy.\n")
        return {
            "thread_id": thread_id or f"thread-{role}-{label}",
            "returncode": 0,
            "timed_out": False,
            "duration_seconds": 0.04,
            "model": route.model,
            "reasoning_effort": route.reasoning_effort,
            "stdout_path": f"trace-{role}-{label}.jsonl",
            "stderr_path": f"trace-{role}-{label}.stderr.log",
        }


class SimpleLabHarnessTests(unittest.TestCase):
    def _config(self, root: Path) -> LabConfig:
        lab_dir = root / "lab"
        lab_dir.mkdir()
        (lab_dir / "CAMPAIGN.md").write_text("# Beat GLM-4.7 token cost\n")
        return LabConfig(
            repo_dir=root,
            lab_dir=lab_dir,
            cycle_interval_seconds=1,
            max_parallel_researchers=2,
            supervisor_every_cycles=1,
            director_timeout_seconds=60,
            researcher_timeout_seconds=60,
            supervisor_timeout_seconds=60,
            director=ModelRoute("gpt-sol", "high"),
            researcher=ModelRoute("gpt-terra", "medium"),
            researcher_routes=(
                ModelRoute("gpt-terra", "medium"),
                ModelRoute("gpt-luna", "medium"),
            ),
            deep_researcher=ModelRoute("gpt-sol", "high"),
            supervisor=ModelRoute("gpt-sol", "high"),
            tools=(root / "tools",),
        )

    def test_cycle_runs_director_parallel_researchers_and_process_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            (config.lab_dir / "DIRECTOR_LOG.md").write_text(
                "# Director log\n\n## Current decision\n"
                "The BF16 development control and frozen NLL ceilings are ready.\n"
            )

            status = harness.cycle()

            self.assertEqual(1, status["cycle_count"])
            self.assertEqual(2, runner.max_active_researchers)
            self.assertEqual(
                ["director", "researcher", "researcher", "supervisor"],
                [call["role"] for call in runner.calls],
            )
            self.assertEqual("gpt-sol", runner.calls[0]["model"])
            self.assertEqual("gpt-terra", runner.calls[1]["model"])
            self.assertEqual(
                {"gpt-terra", "gpt-luna"},
                {
                    call["model"]
                    for call in runner.calls
                    if call["role"] == "researcher"
                },
            )
            self.assertIn("$research-director", runner.calls[0]["prompt"])
            self.assertIn("$researcher", runner.calls[1]["prompt"])
            self.assertIn("$research-supervisor", runner.calls[-1]["prompt"])
            self.assertIn("Shared GPU bench inventory", runner.calls[0]["prompt"])
            self.assertIn("director owns allocation and teardown", runner.calls[0]["prompt"])
            self.assertIn("claim a compatible lab bench", runner.calls[1]["prompt"])
            self.assertIn("never create or tear down a provider GPU", runner.calls[1]["prompt"])
            self.assertIn("warm-bench reuse", runner.calls[-1]["prompt"])
            self.assertIn("provider resources that are absent from the inventory", runner.calls[-1]["prompt"])
            self.assertIn("do not infer a dead watchdog from probing the guest", runner.calls[-1]["prompt"])
            self.assertIn("mark the registered bench draining", runner.calls[-1]["prompt"])
            self.assertIn("Do not perform provider cleanup", runner.calls[-1]["prompt"])
            self.assertIn(
                "The model-specific objective and intervention scope",
                runner.calls[-1]["prompt"],
            )
            self.assertIn(
                "decision-relevant research progress per wall-clock hour",
                runner.calls[0]["prompt"],
            )
            self.assertIn("Current active portfolio:", runner.calls[0]["prompt"])
            self.assertIn("Latest director decision:", runner.calls[0]["prompt"])
            self.assertIn("Latest supervisor handoff:", runner.calls[0]["prompt"])
            self.assertIn("Do not leave a confirmed orphan merely documented", runner.calls[0]["prompt"])
            self.assertIn(
                "Do not begin by reading generated `STATUS.md`, full logs",
                runner.calls[0]["prompt"],
            )
            self.assertIn(
                "Do not wait, sleep, poll, monitor active work, or spawn internal subagents",
                runner.calls[0]["prompt"],
            )
            self.assertIn(
                "assign another researcher to prepare the best likely follow-up offline",
                runner.calls[0]["prompt"],
            )
            self.assertIn(
                "exclusive only for mutation of that bench",
                runner.calls[0]["prompt"],
            )
            self.assertIn("overall researcher-process cap of 2", runner.calls[0]["prompt"])
            self.assertIn(
                "keep the lab bench for in-place repair",
                runner.calls[0]["prompt"],
            )
            self.assertIn(
                "keep newly released reusable state through the next portfolio selection",
                runner.calls[0]["prompt"],
            )
            self.assertIn(
                "must follow the next portfolio selection in this same director turn",
                runner.calls[0]["prompt"],
            )
            self.assertIn(
                "do not drain in one cycle and reopen onto replacement hardware in the next",
                runner.calls[0]["prompt"],
            )
            self.assertIn(
                "mutable retained development environment",
                runner.calls[0]["prompt"],
            )
            self.assertIn("releasing never tears one down", runner.calls[0]["prompt"])
            self.assertIn("latency tradeoffs as authoritative", runner.calls[0]["prompt"])
            self.assertIn(
                "produce new decision-relevant evidence quickly",
                runner.calls[1]["prompt"],
            )
            self.assertIn("Researcher profile: execution", runner.calls[1]["prompt"])
            self.assertIn(
                "Current scheduled action from `STATUS.json`: run the experiment",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "do not substitute another readiness artifact",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "absence of project-local code is not a typed blocker",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "materialize the admitted bytes under this project before claiming",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "Do not resolve the shared path again after the claim",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "ordinary launcher, path, CLI/API, parser, numeric-guard, telemetry, comparator, archive, or retrieval defect is not scientific evidence",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "patch and retry only the invalidated operation inside the same claimed bench/session",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "Candidate CUDA execution or a pre-call `*_science_started` marker proves path entry",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "Judge consumption from evidence, not intent markers",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "A complete interpretable candidate result is a sample",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "may be amended and retried, even when some candidate bytes executed",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "do not count the retry as another independent sample",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "protects valid measurements and completed costly stages",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "claim, heartbeat, and final release in one bounded outer controller",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "must not unconditionally release the bench on a recoverable pre-invocation exit",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "preserve that producer artifact and patch only the consumer on the same retained bench",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "do not rerun training, conversion, calibration, or another scientific producer invocation",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "retrieve its compact terminal, hash, and manifest first",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "only when that transfer does not delay GPU progress",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "start it inside that durable claim owner before copying bytes",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "never retry an all-files overwrite against already-matched read-only files",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "retrieve its remote compact terminal",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "Never release first and later guess whether the arm was consumed",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "do not promote the attempt terminal to the project's scientific terminal or release the warm bench",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "write `REPAIR_READY.json` with the diagnostic and an absolute repair deadline",
                runner.calls[1]["prompt"],
            )
            self.assertIn("Latest director decision", runner.calls[1]["prompt"])
            self.assertIn(
                "The BF16 development control and frozen NLL ceilings are ready.",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "Before declaring a prerequisite missing",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "Keep documentation to a short handoff",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "check the listed shared tools once for an existing durable controller",
                runner.calls[1]["prompt"],
            )
            self.assertIn("Use that controller with absolute paths", runner.calls[1]["prompt"])
            self.assertIn("trade latency as allowed", runner.calls[1]["prompt"])
            self.assertTrue((config.lab_dir / "STATUS.md").is_file())
            self.assertTrue((config.lab_dir / "runtime" / "events.jsonl").is_file())
            self.assertTrue((config.lab_dir / "runtime" / "gpus.json").is_file())
            self.assertTrue((config.lab_dir / "projects" / "kernel" / "RESEARCH_LOG.md").is_file())
            self.assertTrue((config.lab_dir / "projects" / "kernel" / "artifacts").is_dir())
            self.assertTrue((config.lab_dir / "projects" / "scheduler" / "artifacts").is_dir())
            harness.close()

    def test_gpu_inventory_is_rendered_and_changes_wake_the_director(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            before = harness._director_observation_sha256()
            harness.gpu_pool.register(pool_bench_spec())
            after = harness._director_observation_sha256()

            status = harness.render_status()

            self.assertNotEqual(before, after)
            self.assertEqual("gemma-h200-1", status["gpu_pool"]["benches"][0]["id"])
            self.assertIn("## GPU benches", (config.lab_dir / "STATUS.md").read_text())
            harness.close()

    def test_supervisor_handoff_changes_wake_the_director(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            before = harness._director_observation_sha256()
            with (config.lab_dir / "SUPERVISOR_LOG.md").open("a") as handle:
                handle.write("\nOrphan bench needs director cleanup.\n")

            after = harness._director_observation_sha256()

            self.assertNotEqual(before, after)
            harness.close()

    def test_deep_profile_routes_causal_work_to_sol(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            for name, priority, profile in (
                ("kernel", 2, "deep"),
                ("scheduler", 1, "execution"),
            ):
                project = config.lab_dir / "projects" / name
                project.mkdir()
                (project / "PROJECT.md").write_text(f"# {name}\n")
                (project / "STATUS.json").write_text(
                    json.dumps(
                        {
                            "status": "active",
                            "priority": priority,
                            "summary": "ready",
                            "next_action": "continue",
                            "researcher_profile": profile,
                        }
                    )
                )

            harness._run_researchers()

            calls = {
                call["label"]: call
                for call in runner.calls
                if call["role"] == "researcher"
            }
            self.assertEqual("gpt-sol", calls["kernel"]["model"])
            self.assertIn("Researcher profile: deep", calls["kernel"]["prompt"])
            self.assertIn(calls["scheduler"]["model"], {"gpt-terra", "gpt-luna"})
            self.assertIn(
                "Researcher profile: execution", calls["scheduler"]["prompt"]
            )
            harness.close()

    def test_development_session_keeps_the_launching_researcher_route(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                unit_is_active=lambda unit, manager: (
                    unit == "retained.service" and manager == "user"
                ),
            )
            project = config.lab_dir / "projects" / "retained"
            project.mkdir()
            (project / "PROJECT.md").write_text("# retained\n")
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 10,
                        "researcher_profile": "execution",
                        "active_session": {
                            "mode": "development",
                            "unit": "retained.service",
                            "unit_manager": "user",
                        },
                    }
                )
            )
            harness.state["project_routes"]["retained"] = "gpt-sol"

            harness._run_researchers()

            call = next(
                call
                for call in runner.calls
                if call["role"] == "researcher" and call["label"] == "retained"
            )
            self.assertEqual("gpt-sol", call["model"])
            harness.close()

    def test_unchanged_development_session_waits_for_a_new_owner_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                unit_is_active=lambda unit, manager: (
                    unit == "retained.service" and manager == "user"
                ),
            )
            project = config.lab_dir / "projects" / "retained"
            artifact_root = project / "artifacts" / "session"
            artifact_root.mkdir(parents=True)
            events = artifact_root / "events.jsonl"
            events.write_text('{"event":"ssh_ready"}\n')
            (project / "PROJECT.md").write_text("# retained\n")
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 10,
                        "active_session": {
                            "mode": "development",
                            "unit": "retained.service",
                            "unit_manager": "user",
                            "artifact_root": "artifacts/session",
                        },
                    }
                )
            )

            harness._run_researchers()
            runner.calls.clear()
            events.write_text(
                '{"event":"ssh_ready"}\n'
                '{"event":"heartbeat","returncode":0}\n'
            )
            harness._run_researchers()

            self.assertFalse(
                any(call["role"] == "researcher" for call in runner.calls)
            )
            deferred = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_deferred"
                    and event.get("label") == "retained"
                    and event.get("reason") == "unchanged_development_session"
                    for event in deferred
                )
            )

            events.write_text(
                '{"event":"ssh_ready"}\n'
                '{"event":"repair_window_open"}\n'
            )
            harness._run_researchers()

            self.assertTrue(
                any(call["role"] == "researcher" for call in runner.calls)
            )
            harness.close()

    def test_changed_development_action_wakes_the_researcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                unit_is_active=lambda unit, manager: (
                    unit == "retained.service" and manager == "user"
                ),
            )
            project = config.lab_dir / "projects" / "retained"
            artifact_root = project / "artifacts" / "session"
            artifact_root.mkdir(parents=True)
            (artifact_root / "events.jsonl").write_text(
                '{"event":"transfer_active"}\n'
            )
            (project / "PROJECT.md").write_text("# retained\n")
            status_path = project / "STATUS.json"
            status = {
                "status": "active",
                "priority": 10,
                "next_action": "preserve healthy transfer",
                "active_session": {
                    "mode": "development",
                    "unit": "retained.service",
                    "unit_manager": "user",
                    "artifact_root": "artifacts/session",
                },
            }
            status_path.write_text(json.dumps(status))

            harness._run_researchers()
            runner.calls.clear()
            harness._run_researchers()
            self.assertFalse(
                any(call["role"] == "researcher" for call in runner.calls)
            )

            status["next_action"] = "stop redundant transfer and resume launch"
            status_path.write_text(json.dumps(status))
            harness._run_researchers()

            call = next(
                call
                for call in runner.calls
                if call["role"] == "researcher" and call["label"] == "retained"
            )
            self.assertIn("stop redundant transfer and resume launch", call["prompt"])
            harness.close()

    def test_threads_survive_restart_and_completed_projects_are_not_scheduled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            first_runner = FakeRunner(config.lab_dir)
            first = LabHarness(config, runner=first_runner)
            first.cycle()
            first.close()
            kernel = config.lab_dir / "projects" / "kernel" / "STATUS.json"
            status = json.loads(kernel.read_text())
            status["status"] = "complete"
            kernel.write_text(json.dumps(status))

            second_runner = FakeRunner(config.lab_dir)
            second = LabHarness(config, runner=second_runner)
            second.cycle()

            director_call = second_runner.calls[0]
            scheduler_call = next(
                call
                for call in second_runner.calls
                if call["role"] == "researcher" and call["label"] == "scheduler"
            )
            self.assertEqual("thread-director-director", director_call["thread_id"])
            self.assertEqual(
                "thread-researcher-scheduler", scheduler_call["thread_id"]
            )
            self.assertFalse(
                any(
                    call["role"] == "researcher" and call["label"] == "kernel"
                    for call in second_runner.calls
                )
            )
            second.close()

    def test_exhausted_researcher_thread_is_replaced_on_the_same_route(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            project = config.lab_dir / "projects" / "retained"
            project.mkdir()
            (project / "PROJECT.md").write_text("# retained\n")
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 10,
                        "summary": "ready",
                        "next_action": "implement the runner",
                    }
                )
            )
            trace = config.lab_dir / "runtime" / "traces" / "exhausted.jsonl"
            trace.parent.mkdir(parents=True, exist_ok=True)
            trace.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "agent_message",
                            "text": "I cannot continue in the remaining response capacity.",
                        },
                    }
                )
                + "\n"
            )
            harness.state["threads"]["projects"]["retained"] = "exhausted-thread"
            harness.state["project_routes"]["retained"] = "gpt-terra"
            harness.state["last_runs"]["researcher:retained"] = {
                "model": "gpt-terra",
                "stdout_path": str(trace),
            }

            harness._run_researchers()

            call = next(
                call
                for call in runner.calls
                if call["role"] == "researcher" and call["label"] == "retained"
            )
            self.assertIsNone(call["thread_id"])
            self.assertEqual("gpt-terra", call["model"])
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_thread_reset"
                    and event.get("label") == "retained"
                    and event.get("reason") == "response_capacity_exhausted"
                    for event in events
                )
            )
            harness.close()

    def test_turn_capacity_handoff_resets_the_researcher_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "turn-capacity.jsonl"
            trace.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "agent_message",
                            "text": "I couldn't complete the required runtime stack within this turn.",
                        },
                    }
                )
                + "\n"
            )

            self.assertTrue(trace_reports_response_capacity_exhausted(trace))

    def test_codex_child_environment_uses_saved_login_not_api_key(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "secret", "AZURE_OPENAI_API_KEY": "secret", "PATH": "/bin"},
            clear=True,
        ):
            environment = codex_environment()

        self.assertTrue(environment["PATH"].endswith("/bin"))
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("AZURE_OPENAI_API_KEY", environment)

    def test_codex_runner_isolates_and_removes_child_temporary_files(self):
        class CompletedProcess:
            def __init__(self):
                read_fd, write_fd = os.pipe()
                os.write(
                    write_fd,
                    b'{"type":"thread.started","thread_id":"thread-1"}\n',
                )
                os.close(write_fd)
                self.stdin = CapturingInput()
                self.stdout = os.fdopen(read_fd)
                self.pid = 123
                self.returncode = 0

            def poll(self):
                return 0

        class CapturingInput(io.StringIO):
            def close(self):
                self.closed_by_runner = True

        calls = []

        def popen(command, **kwargs):
            temporary_directory = Path(kwargs["env"]["TMPDIR"])
            self.assertTrue(temporary_directory.is_dir())
            process = CompletedProcess()
            calls.append((command, kwargs, process))
            return process

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace_dir = root / "traces"
            runner = CodexAgentRunner(root, trace_dir, popen=popen)

            result = runner.run(
                "prompt",
                role="supervisor",
                route=ModelRoute("model", "high"),
                thread_id=None,
                timeout_seconds=10,
                label="supervisor",
            )

            environment = calls[0][1]["env"]
            temporary_directory = Path(environment["TMPDIR"])
            self.assertEqual(environment["TMPDIR"], environment["TMP"])
            self.assertEqual(environment["TMPDIR"], environment["TEMP"])
            self.assertEqual(trace_dir / ".agent-tmp", temporary_directory.parent)
            self.assertFalse(temporary_directory.exists())
            self.assertEqual("-", calls[0][0][-1])
            self.assertNotIn("prompt", calls[0][0])
            self.assertEqual("prompt", calls[0][2].stdin.getvalue())
            self.assertFalse(result["timed_out"])

    def test_status_is_readable_while_the_live_harness_owns_the_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "repo_dir": str(config.repo_dir),
                        "lab_dir": str(config.lab_dir),
                    }
                )
            )
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))

            output = io.StringIO()
            with redirect_stdout(output):
                returncode = main(["--config", str(config_path), "--status"])

            self.assertEqual(0, returncode)
            self.assertEqual(0, json.loads(output.getvalue())["cycle_count"])
            harness.close()

    def test_source_change_requests_restart_only_at_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            source = root / "lab_harness.py"
            source.write_text("old source\n")
            harness._source_path = source
            harness._source_sha256 = harness._source_digest(source)
            source.write_text("new source\n")

            with self.assertRaises(SystemExit) as raised:
                harness._restart_if_source_changed()

            self.assertEqual(75, raised.exception.code)
            self.assertTrue(harness._lock_handle.closed)
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertEqual("harness_reload_requested", events[-1]["event"])

    def test_source_change_defers_restart_for_live_pid_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            source = root / "lab_harness.py"
            source.write_text("old source\n")
            harness._source_path = source
            harness._source_sha256 = harness._source_digest(source)
            stat = Path(f"/proc/{os.getpid()}/stat").read_text()
            fields = stat[stat.rfind(")") + 2 :].split()
            project = config.lab_dir / "projects" / "retained"
            project.mkdir()
            (project / "PROJECT.md").write_text("# retained\n")
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "active_session": {
                            "unit": str(project / "OWNER.json"),
                            "unit_manager": "pid",
                            "pid": os.getpid(),
                            "start_ticks": int(fields[19]),
                        },
                    }
                )
            )
            source.write_text("new source\n")

            harness._restart_if_source_changed()

            self.assertFalse(harness._lock_handle.closed)
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertEqual("harness_reload_deferred", events[-1]["event"])
            self.assertEqual(["retained"], events[-1]["live_pid_sessions"])
            harness.close()

    def test_pending_reload_rechecks_pid_sessions_after_agents_drain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            project = config.lab_dir / "projects" / "retained"
            project.mkdir(parents=True)
            (project / "PROJECT.md").write_text("# retained\n")
            status_path = project / "STATUS.json"
            status_path.write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 1,
                        "summary": "ready",
                        "next_action": "start a durable owner",
                    }
                )
            )
            researcher_started = threading.Event()
            register_owner = threading.Event()

            class RegisteringRunner(FakeRunner):
                def run(
                    self,
                    prompt,
                    *,
                    role,
                    route,
                    thread_id,
                    timeout_seconds,
                    label,
                ):
                    if role != "researcher":
                        return {
                            "thread_id": thread_id or f"thread-{role}-{label}",
                            "returncode": 0,
                            "timed_out": False,
                            "duration_seconds": 0.01,
                            "model": route.model,
                            "reasoning_effort": route.reasoning_effort,
                            "stdout_path": f"trace-{role}-{label}.jsonl",
                            "stderr_path": f"trace-{role}-{label}.stderr.log",
                        }
                    researcher_started.set()
                    register_owner.wait(3)
                    stat = Path(f"/proc/{os.getpid()}/stat").read_text()
                    fields = stat[stat.rfind(")") + 2 :].split()
                    status_path.write_text(
                        json.dumps(
                            {
                                "status": "active",
                                "priority": 1,
                                "summary": "owner active",
                                "next_action": "let the owner finish",
                                "active_session": {
                                    "unit": str(project / "OWNER.json"),
                                    "unit_manager": "pid",
                                    "pid": os.getpid(),
                                    "start_ticks": int(fields[19]),
                                },
                            }
                        )
                    )
                    return {
                        "thread_id": thread_id or f"thread-{role}-{label}",
                        "returncode": 0,
                        "timed_out": False,
                        "duration_seconds": 0.01,
                        "model": route.model,
                        "reasoning_effort": route.reasoning_effort,
                        "stdout_path": f"trace-{role}-{label}.jsonl",
                        "stderr_path": f"trace-{role}-{label}.stderr.log",
                    }

            harness = LabHarness(config, runner=RegisteringRunner(config.lab_dir))
            source = root / "lab_harness.py"
            source.write_text("old source\n")
            harness._source_path = source
            harness._source_sha256 = harness._source_digest(source)
            stop = threading.Event()
            errors: list[BaseException] = []

            def run_harness() -> None:
                try:
                    harness.run_forever(stop_event=stop)
                except BaseException as error:
                    errors.append(error)

            thread = threading.Thread(target=run_harness)
            thread.start()
            self.assertTrue(researcher_started.wait(3))
            source.write_text("new source\n")
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                events = [
                    json.loads(line)
                    for line in harness.events_path.read_text().splitlines()
                ]
                if any(
                    event["event"] == "harness_reload_requested"
                    for event in events
                ):
                    break
                time.sleep(0.02)
            else:
                self.fail("reload was not requested while the researcher ran")
            register_owner.set()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                events = [
                    json.loads(line)
                    for line in harness.events_path.read_text().splitlines()
                ]
                if any(
                    event["event"] == "harness_reload_deferred"
                    and event.get("disposition")
                    == "cancel_pending_reload_for_new_pid_sessions"
                    for event in events
                ):
                    break
                time.sleep(0.02)
            else:
                self.fail("pending reload was not canceled for the new owner")
            stop.set()
            thread.join(3)
            harness.close()

            self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
            self.assertTrue(
                any(
                    event.get("live_pid_sessions") == ["retained"]
                    for event in events
                    if event["event"] == "harness_reload_deferred"
                )
            )

    def test_researcher_prompt_does_not_poll_a_durable_active_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            project = config.lab_dir / "projects" / "retained"
            project.mkdir()
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "next_action": "Reconcile after terminal cleanup.",
                        "active_session": {
                            "unit": "retained.service",
                            "state": "runtime_bootstrap",
                            "launcher_deadline_utc": "2026-07-16T01:14:52Z",
                        },
                    }
                )
            )

            prompt = harness._researcher_prompt(project)

            self.assertIn("Durable active session from `STATUS.json`", prompt)
            self.assertIn("retained.service", prompt)
            self.assertIn("take one grouped snapshot", prompt)
            self.assertIn("do not sleep or poll", prompt)
            harness.close()

    def test_researcher_prompt_preserves_completed_stage_after_owner_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            project = config.lab_dir / "projects" / "retained"
            artifacts = project / "artifacts" / "run"
            control = artifacts / "retrieved" / "control"
            control.mkdir(parents=True)
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "next_action": "Run the whole control/candidate pair.",
                        "active_session": {
                            "artifact_root": "artifacts/run",
                            "unit": "retained.service",
                            "unit_manager": "user",
                        },
                    }
                )
            )
            (artifacts / "RECONCILED_TERMINAL.json").write_text(
                json.dumps(
                    {
                        "status": "terminal",
                        "pass": False,
                        "classification": "typed_external_or_owner_boundary",
                    }
                )
            )
            (artifacts / "REMOTE_WORKER_TERMINAL.json").write_text(
                json.dumps(
                    {
                        "status": "terminal",
                        "classification": "integration_failure",
                        "message": "control.validator_failed",
                    }
                )
            )
            (artifacts / "INVOCATION_STATE.json").write_text(
                json.dumps(
                    {
                        "control_science_started": True,
                        "candidate_science_started": False,
                    }
                )
            )
            (control / "TERMINAL.json").write_text(
                json.dumps({"arm": "control", "pass": True})
            )

            prompt = harness._researcher_prompt(project)

            self.assertIn(
                "Previous durable owner terminal after an integration failure", prompt
            )
            self.assertIn('"completed_passing_stages": ["control"]', prompt)
            self.assertIn('"candidate_science_started": false', prompt)
            self.assertIn("Preserve every completed stage listed above", prompt)
            self.assertIn("execute only stages", prompt)
            self.assertIn("Do not replay the whole scheduled pair", prompt)
            self.assertIn("same compatible warm bench", prompt)
            harness.close()

    def test_researcher_prompt_hands_off_a_new_durable_owner_immediately(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            project = config.lab_dir / "projects" / "launch"
            project.mkdir()
            (project / "STATUS.json").write_text(
                json.dumps({"next_action": "Launch the admitted durable GPU arm."})
            )

            prompt = harness._researcher_prompt(project)

            self.assertIn("An agent-turn boundary is not a scientific wall-clock budget", prompt)
            self.assertIn("deterministic local work", prompt)
            self.assertIn("Do not kill and restart correct local computation", prompt)
            self.assertIn("If you start a durable local computation", prompt)
            self.assertIn("STATUS.json.active_session", prompt)
            self.assertIn("canonical `unit` and `unit_manager` keys", prompt)
            self.assertIn("claimed GPU bench remains lab-owned", prompt)
            self.assertIn("director supplies a lab bench", prompt)
            harness.close()

    def test_director_prompt_uses_resource_budgets_not_agent_turn_deadlines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))

            prompt = harness._director_prompt()

            self.assertIn("never with an agent-turn boundary", prompt)
            self.assertIn("one bounded durable local owner", prompt)
            self.assertIn("keep provider creation gated", prompt)
            self.assertIn("kill/restart correct work", prompt)
            harness.close()

    def test_controller_unit_alias_is_deferred_without_using_a_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                unit_is_active=lambda unit, manager: (
                    unit == "aliased.service" and manager == "user"
                ),
            )
            project = config.lab_dir / "projects" / "aliased"
            project.mkdir(parents=True)
            (project / "PROJECT.md").write_text("# aliased\n")
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 10,
                        "active_session": {
                            "controller_unit": "aliased.service",
                            "controller_cgroup": "/user.slice/aliased.service",
                        },
                    }
                )
            )

            harness._run_researchers()

            self.assertFalse(
                any(call["role"] == "researcher" for call in runner.calls)
            )
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_deferred"
                    and event.get("unit") == "aliased.service"
                    and event.get("unit_manager") == "user"
                    for event in events
                )
            )
            harness.close()

    def test_systemd_user_manager_alias_is_deferred_without_using_a_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                unit_is_active=lambda unit, manager: (
                    unit == "aliased-manager.service" and manager == "user"
                ),
            )
            project = config.lab_dir / "projects" / "aliased-manager"
            project.mkdir(parents=True)
            (project / "PROJECT.md").write_text("# aliased manager\n")
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 10,
                        "active_session": {
                            "unit": "aliased-manager.service",
                            "unit_manager": "systemd --user",
                        },
                    }
                )
            )

            harness._run_researchers()

            self.assertFalse(
                any(call["role"] == "researcher" for call in runner.calls)
            )
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_deferred"
                    and event.get("unit") == "aliased-manager.service"
                    and event.get("unit_manager") == "user"
                    for event in events
                )
            )
            harness.close()

    def test_active_local_durable_session_is_deferred_without_using_a_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                unit_is_active=lambda unit, manager: (
                    unit == "retained.service" and manager == "system"
                ),
            )
            for name, priority, active_session in (
                (
                    "retained",
                    10,
                    {
                        "unit": "retained.service",
                        "unit_manager": "system",
                        "state": "runtime_bootstrap",
                    },
                ),
                ("ready", 9, None),
            ):
                project = config.lab_dir / "projects" / name
                project.mkdir()
                (project / "PROJECT.md").write_text(f"# {name}\n")
                (project / "STATUS.json").write_text(
                    json.dumps(
                        {
                            "status": "active",
                            "priority": priority,
                            "active_session": active_session,
                        }
                    )
                )

            harness._run_researchers()

            researcher_calls = [
                call for call in runner.calls if call["role"] == "researcher"
            ]
            self.assertEqual(["ready"], [call["label"] for call in researcher_calls])
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_deferred"
                    and event.get("label") == "retained"
                    and event.get("unit") == "retained.service"
                    and event.get("unit_manager") == "system"
                    for event in events
                )
            )
            harness.close()

    def test_active_batch_owner_wakes_for_bounded_repair_handshake(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                unit_is_active=lambda unit, manager: (
                    unit == "repair.service" and manager == "user"
                ),
            )
            project = config.lab_dir / "projects" / "repair"
            artifacts = project / "artifacts" / "run"
            artifacts.mkdir(parents=True)
            (project / "PROJECT.md").write_text("# repair\n")
            (artifacts / "REPAIR_READY.json").write_text(
                json.dumps({"repair_deadline_epoch": time.time() + 600})
            )
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 10,
                        "active_session": {
                            "unit": "repair.service",
                            "unit_manager": "user",
                            "artifact_root": "artifacts/run",
                        },
                    }
                )
            )

            harness._run_researchers()

            calls = [call for call in runner.calls if call["role"] == "researcher"]
            self.assertEqual(["repair"], [call["label"] for call in calls])
            self.assertIn("Durable repair handshake", calls[0]["prompt"])
            self.assertIn("REPAIR_REQUEST.json", calls[0]["prompt"])
            self.assertIn(
                "a repair request must resume at the invalidated operation",
                calls[0]["prompt"],
            )
            self.assertIn(
                "not blindly rerun a monolithic worker that reloads the model",
                calls[0]["prompt"],
            )
            self.assertIn(
                "atomically archive that partial root and give the unchanged retry a fresh output path",
                calls[0]["prompt"],
            )
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_woken"
                    and event.get("reason") == "durable_repair_ready"
                    for event in events
                )
            )
            harness.close()

    def test_pending_durable_repair_accepts_absolute_utc_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "REPAIR_READY.json").write_text(
                json.dumps(
                    {
                        "absolute_repair_deadline_utc": (
                            datetime.now(timezone.utc) + timedelta(minutes=10)
                        ).isoformat()
                    }
                )
            )

            repair_root = LabHarness._pending_durable_repair(
                project,
                {"artifact_root": "."},
            )

            self.assertEqual(project, repair_root)

    def test_pending_durable_repair_accepts_repair_utc_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "REPAIR_READY.json").write_text(
                json.dumps(
                    {
                        "repair_deadline_utc": (
                            datetime.now(timezone.utc) + timedelta(minutes=10)
                        ).isoformat()
                    }
                )
            )

            repair_root = LabHarness._pending_durable_repair(
                project,
                {"artifact_root": "."},
            )

            self.assertEqual(project, repair_root)

    def test_pending_durable_repair_finds_namespaced_shared_tool_handshake(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            artifact_root = project / "artifacts" / "run"
            repair_root = (
                artifact_root
                / "repair"
                / ".repair-handshakes"
                / "component-repair"
            )
            repair_root.mkdir(parents=True)
            (repair_root / "REPAIR_READY.json").write_text(
                json.dumps({"repair_deadline_epoch": time.time() + 600})
            )

            pending_root = LabHarness._pending_durable_repair(
                project,
                {"artifact_root": "artifacts/run"},
            )

            self.assertEqual(repair_root, pending_root)

    def test_pending_durable_repair_wakes_for_new_ready_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            deadline = (
                datetime.now(timezone.utc) + timedelta(minutes=10)
            ).isoformat()
            previous = {
                "repair_deadline_utc": deadline,
                "stage": "component_consumer",
            }
            current = {
                "repair_deadline_utc": deadline,
                "stage": "endpoint_consumer",
            }
            previous_sha256 = hashlib.sha256(
                (json.dumps(previous, indent=2, sort_keys=True) + "\n").encode()
            ).hexdigest()
            (project / "REPAIR_READY.json").write_text(
                json.dumps(current, indent=2, sort_keys=True) + "\n"
            )
            (project / "REPAIR_REQUEST.json").write_text(
                json.dumps({"ready_sha256": previous_sha256})
            )

            repair_root = LabHarness._pending_durable_repair(
                project,
                {"artifact_root": "."},
            )

            self.assertEqual(project, repair_root)

    def test_pending_durable_repair_falls_back_to_project_root(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            artifacts = project / "artifacts" / "run"
            artifacts.mkdir(parents=True)
            (project / "REPAIR_READY.json").write_text(
                json.dumps(
                    {
                        "absolute_deadline_utc": (
                            datetime.now(timezone.utc) + timedelta(minutes=10)
                        ).isoformat()
                    }
                )
            )

            repair_root = LabHarness._pending_durable_repair(
                project,
                {"artifact_root": str(artifacts)},
            )

            self.assertEqual(project, repair_root)

    def test_pending_durable_repair_ignores_marker_for_previous_artifact_root(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            current = project / "artifacts" / "current"
            previous = project / "artifacts" / "previous"
            current.mkdir(parents=True)
            previous.mkdir(parents=True)
            (project / "REPAIR_READY.json").write_text(
                json.dumps(
                    {
                        "artifact_root": str(previous),
                        "absolute_deadline_utc": (
                            datetime.now(timezone.utc) + timedelta(minutes=10)
                        ).isoformat(),
                    }
                )
            )

            repair_root = LabHarness._pending_durable_repair(
                project,
                {"artifact_root": str(current)},
            )

            self.assertIsNone(repair_root)

    def test_development_session_stays_attached_while_other_paid_work_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                unit_is_active=lambda unit, manager: (
                    unit == "development.service" and manager == "user"
                ),
            )
            for name, priority, spend, active_session in (
                (
                    "development",
                    30,
                    1.0,
                    {
                        "unit": "development.service",
                        "unit_manager": "user",
                        "mode": "development",
                        "state": "runtime_ready",
                    },
                ),
                ("other-paid", 20, 1.0, None),
                ("offline", 10, 0.0, None),
            ):
                project = config.lab_dir / "projects" / name
                project.mkdir()
                (project / "PROJECT.md").write_text(f"# {name}\n")
                (project / "STATUS.json").write_text(
                    json.dumps(
                        {
                            "status": "active",
                            "priority": priority,
                            "authorized_spend_usd": spend,
                            "active_session": active_session,
                        }
                    )
                )

            harness._run_researchers()

            researcher_calls = [
                call for call in runner.calls if call["role"] == "researcher"
            ]
            self.assertEqual(
                ["development", "other-paid"],
                [call["label"] for call in researcher_calls],
            )
            development_prompt = researcher_calls[0]["prompt"]
            self.assertIn("Mutable retained development session", development_prompt)
            self.assertIn(
                "Do not create a replacement resource for it", development_prompt
            )
            self.assertIn(
                "Other projects may own independent GPU sessions concurrently",
                development_prompt,
            )
            self.assertIn("patch the local or remote program", development_prompt)
            harness.close()

    def test_fresh_shared_bench_claim_defers_dependent_project_until_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                unit_is_active=lambda unit, manager: (
                    unit == "owner.service" and manager == "user"
                ),
            )
            owner = config.lab_dir / "projects" / "owner"
            owner.mkdir()
            (owner / "PROJECT.md").write_text("# owner\n")
            (owner / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 20,
                        "active_session": {
                            "unit": "owner.service",
                            "unit_manager": "user",
                        },
                    }
                )
            )
            dependent = config.lab_dir / "projects" / "dependent"
            dependent.mkdir()
            (dependent / "PROJECT.md").write_text("# dependent\n")
            (dependent / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 10,
                        "bench_id": "gemma-h200-1",
                        "next_action": "Wait for the current owner to release gemma-h200-1.",
                    }
                )
            )
            harness.gpu_pool.register(pool_bench_spec())
            harness.gpu_pool.claim("owner", bench_id="gemma-h200-1")
            harness.state["director_observation_sha256"] = (
                harness._director_observation_sha256()
            )

            can_defer, _, reason = harness._director_can_defer()
            harness._run_researchers()

            self.assertTrue(can_defer)
            self.assertEqual("unchanged_durable_sessions", reason)
            self.assertFalse(
                any(call["role"] == "researcher" for call in runner.calls)
            )
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_deferred"
                    and event.get("label") == "dependent"
                    and event.get("reason") == "shared_bench_claimed"
                    and event.get("owner_project") == "owner"
                    for event in events
                )
            )

            harness.gpu_pool.release("owner")
            can_defer, _, _ = harness._director_can_defer()
            harness._run_researchers()

            self.assertFalse(can_defer)
            self.assertEqual(
                ["dependent"],
                [
                    call["label"]
                    for call in runner.calls
                    if call["role"] == "researcher"
                ],
            )
            harness.close()

    def test_shared_bench_development_prompt_resumes_after_settled_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                unit_is_active=lambda unit, manager: (
                    unit == "development.service" and manager == "user"
                ),
            )
            project = config.lab_dir / "projects" / "development"
            project.mkdir()
            (project / "PROJECT.md").write_text("# development\n")
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 30,
                        "authorized_spend_usd": 1.0,
                        "active_session": {
                            "unit": "development.service",
                            "unit_manager": "user",
                            "mode": "development",
                            "bench_id": "bench-1",
                            "state": "runtime_repair",
                        },
                    }
                )
            )

            harness._run_researchers()

            prompt = next(
                call["prompt"]
                for call in runner.calls
                if call["role"] == "researcher"
            )
            self.assertIn("resume at the failed operation", prompt)
            self.assertIn("do not replay settled host bootstrap", prompt)
            self.assertIn("checkpoint transfer", prompt)
            self.assertIn("image pull", prompt)
            harness.close()

    def test_unchanged_durable_session_defers_director_but_runs_periodic_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                unit_is_active=lambda unit, manager: (
                    unit == "retained.service" and manager == "user"
                ),
            )
            project = config.lab_dir / "projects" / "retained"
            project.mkdir()
            (project / "PROJECT.md").write_text("# retained\n")
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 10,
                        "active_session": {
                            "unit": "retained.service",
                            "unit_manager": "user",
                        },
                    }
                )
            )
            harness.state["director_observation_sha256"] = (
                harness._director_observation_sha256()
            )
            harness.gpu_pool.register(pool_bench_spec())
            harness.gpu_pool.claim("retained", bench_id="gemma-h200-1")
            harness.state["director_observation_sha256"] = (
                harness._director_observation_sha256()
            )
            harness.gpu_pool.heartbeat("retained")

            status = harness.cycle()

            self.assertEqual(1, status["cycle_count"])
            self.assertEqual(["supervisor"], [call["role"] for call in runner.calls])
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "director_deferred"
                    and event.get("reason") == "unchanged_durable_sessions"
                    for event in events
                )
            )
            harness.close()

    def test_unchanged_empty_lab_runs_director_to_replenish_portfolio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.state["director_observation_sha256"] = (
                harness._director_observation_sha256()
            )

            harness.cycle()

            self.assertEqual("director", runner.calls[0]["role"])
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertFalse(
                any(event.get("event") == "director_deferred" for event in events)
            )
            harness.close()

    def test_unchanged_empty_spend_exhausted_lab_defers_director(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "spend_cap_usd": 1.0,
                    "spend_cap_starts_at": "2026-07-19T00:00:00Z",
                }
            )
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            spend_cap = json.loads(harness.spend_cap_path.read_text())
            spend_cap["reservations"]["completed"] = {
                "authorized_usd": 1.0,
                "reserved_at": "2026-07-19T00:01:00Z",
            }
            harness.spend_cap_path.write_text(json.dumps(spend_cap))
            harness.state["director_observation_sha256"] = (
                harness._director_observation_sha256()
            )

            harness.cycle()

            self.assertEqual(["supervisor"], [call["role"] for call in runner.calls])
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "director_deferred"
                    and event.get("reason") == "unchanged_quiescent_lab"
                    for event in events
                )
            )
            harness.close()

    def test_unchanged_empty_lab_below_opt_in_spend_floor_defers_director(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "spend_cap_usd": 1.0,
                    "spend_cap_starts_at": "2026-07-19T00:00:00Z",
                    "quiescent_spend_floor_usd": 0.75,
                }
            )
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            spend_cap = json.loads(harness.spend_cap_path.read_text())
            spend_cap["settled_spend_usd"] = 0.5
            harness.spend_cap_path.write_text(json.dumps(spend_cap))
            harness.state["director_observation_sha256"] = (
                harness._director_observation_sha256()
            )

            harness.cycle()

            self.assertEqual(["supervisor"], [call["role"] for call in runner.calls])
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "director_deferred"
                    and event.get("reason") == "unchanged_quiescent_lab"
                    for event in events
                )
            )
            harness.close()

    def test_empty_quiescent_lab_keeps_periodic_supervisor_safety_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.state["director_observation_sha256"] = (
                harness._director_observation_sha256()
            )
            harness.state["cycle_count"] = 5

            harness.cycle()

            roles = [call["role"] for call in runner.calls]
            self.assertEqual("director", roles[0])
            self.assertEqual("supervisor", roles[-1])
            harness.close()

    def test_quiescent_lab_with_live_bench_keeps_normal_supervisor_cadence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.gpu_pool.register(pool_bench_spec())
            harness.state["director_observation_sha256"] = (
                harness._director_observation_sha256()
            )

            harness.cycle()

            roles = [call["role"] for call in runner.calls]
            self.assertEqual("director", roles[0])
            self.assertEqual("supervisor", roles[-1])
            harness.close()

    def test_spend_cap_change_wakes_director_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "spend_cap_usd": 10.0,
                    "spend_cap_starts_at": "2026-07-19T00:00:00Z",
                }
            )
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            before = harness._director_observation_sha256()
            spend_cap = json.loads(harness.spend_cap_path.read_text())
            spend_cap["reservations"]["reopened"] = {
                "authorized_usd": 1.0,
                "reserved_at": "2026-07-19T00:01:00Z",
            }
            harness.spend_cap_path.write_text(json.dumps(spend_cap))

            after = harness._director_observation_sha256()

            self.assertNotEqual(before, after)
            harness.close()

    def test_new_typed_summary_wakes_director_for_live_durable_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                unit_is_active=lambda unit, manager: (
                    unit == "retained.service" and manager == "user"
                ),
            )
            project = config.lab_dir / "projects" / "retained"
            project.mkdir()
            (project / "PROJECT.md").write_text("# retained\n")
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 10,
                        "active_session": {
                            "unit": "retained.service",
                            "unit_manager": "user",
                        },
                    }
                )
            )
            harness.state["director_observation_sha256"] = (
                harness._director_observation_sha256()
            )
            summary = project / "artifacts" / "candidate" / "summary.json"
            summary.parent.mkdir(parents=True)
            summary.write_text(json.dumps({"outcome": "PASS"}))

            harness.cycle()

            self.assertEqual("director", runner.calls[0]["role"])
            harness.close()

    def test_multiple_provider_capable_projects_run_concurrently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            for name, priority, spend in (
                ("paid-primary", 30, 1.0),
                ("paid-secondary", 20, 0.75),
                ("offline", 10, 0.0),
            ):
                project = config.lab_dir / "projects" / name
                project.mkdir()
                (project / "PROJECT.md").write_text(f"# {name}\n")
                (project / "STATUS.json").write_text(
                    json.dumps(
                        {
                            "status": "active",
                            "priority": priority,
                            "authorized_spend_usd": spend,
                        }
                    )
                )

            harness._run_researchers()

            researcher_calls = [
                call for call in runner.calls if call["role"] == "researcher"
            ]
            self.assertEqual(
                ["paid-primary", "paid-secondary"],
                [call["label"] for call in researcher_calls],
            )
            harness.close()

    def test_remote_shell_project_continues_before_sibling_researcher_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            slow_finished = threading.Event()

            class CompletionRunner(FakeRunner):
                def __init__(self, lab_dir: Path):
                    super().__init__(lab_dir)
                    self.remote_calls = 0
                    self.continued_before_slow_finished = False

                def run(
                    self,
                    prompt,
                    *,
                    role,
                    route,
                    thread_id,
                    timeout_seconds,
                    label,
                ):
                    with self._lock:
                        self.calls.append(
                            {
                                "prompt": prompt,
                                "role": role,
                                "model": route.model,
                                "thread_id": thread_id,
                                "label": label,
                            }
                        )
                    if label == "slow":
                        time.sleep(0.3)
                        slow_finished.set()
                    elif label == "remote":
                        self.remote_calls += 1
                        status_path = self.lab_dir / "projects" / label / "STATUS.json"
                        status = json.loads(status_path.read_text())
                        if self.remote_calls == 1:
                            status["active_session"] = {
                                "unit": "/remote/OWNER.json",
                                "unit_manager": "remote-shell",
                                "bench_id": "gemma-h200-1",
                            }
                        else:
                            self.continued_before_slow_finished = (
                                not slow_finished.is_set()
                            )
                            status["status"] = "complete"
                            status["active_session"] = None
                        status_path.write_text(json.dumps(status))
                    return {
                        "thread_id": thread_id or f"thread-{label}",
                        "returncode": 0,
                        "timed_out": False,
                        "duration_seconds": 0.01,
                        "model": route.model,
                        "reasoning_effort": route.reasoning_effort,
                    }

            runner = CompletionRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.gpu_pool.register(pool_bench_spec())
            harness.gpu_pool.claim("remote", bench_id="gemma-h200-1")
            for name, priority in (("remote", 20), ("slow", 10)):
                project = config.lab_dir / "projects" / name
                project.mkdir()
                (project / "PROJECT.md").write_text(f"# {name}\n")
                (project / "STATUS.json").write_text(
                    json.dumps(
                        {
                            "status": "active",
                            "priority": priority,
                            "bench_id": (
                                "gemma-h200-1" if name == "remote" else None
                            ),
                        }
                    )
                )

            harness._run_researchers()

            self.assertEqual(2, runner.remote_calls)
            self.assertTrue(runner.continued_before_slow_finished)
            continuation = [
                call
                for call in runner.calls
                if call["label"] == "remote"
            ][1]
            self.assertIn("Take one current remote owner snapshot", continuation["prompt"])
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_woken"
                    and event.get("label") == "remote"
                    and event.get("reason") == "remote_shell_turn_continuation"
                    for event in events
                )
            )
            harness.close()

    def test_unchanged_remote_shell_session_does_not_get_duplicate_continuation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.gpu_pool.register(pool_bench_spec())
            harness.gpu_pool.claim("remote", bench_id="gemma-h200-1")
            project = config.lab_dir / "projects" / "remote"
            project.mkdir()
            (project / "PROJECT.md").write_text("# remote\n")
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 20,
                        "bench_id": "gemma-h200-1",
                        "active_session": {
                            "artifact_root": "artifacts/run-1",
                            "unit": "/remote/OWNER.json",
                            "unit_manager": "remote-shell",
                            "bench_id": "gemma-h200-1",
                            "pid": 1234,
                        },
                    }
                )
            )

            harness._run_researchers()

            remote_calls = [
                call for call in runner.calls if call["label"] == "remote"
            ]
            self.assertEqual(1, len(remote_calls))
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertFalse(
                any(
                    event.get("event") == "researcher_woken"
                    and event.get("label") == "remote"
                    and event.get("reason") == "remote_shell_turn_continuation"
                    for event in events
                )
            )
            harness.close()

    def test_live_pid_session_keeps_outer_controller_deferred(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            stat = Path(f"/proc/{os.getpid()}/stat").read_text()
            start_ticks = int(stat[stat.rfind(")") + 2 :].split()[19])
            project = config.lab_dir / "projects" / "durable"
            project.mkdir()
            (project / "PROJECT.md").write_text("# durable\n")
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 20,
                        "active_session": {
                            "artifact_root": "artifacts/run-1",
                            "unit": str(project / "artifacts/run-1/OWNER.json"),
                            "unit_manager": "pid",
                            "pid": os.getpid(),
                            "start_ticks": start_ticks,
                        },
                    }
                )
            )

            harness._run_researchers()

            self.assertEqual([], runner.calls)
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_deferred"
                    and event.get("label") == "durable"
                    and event.get("reason") == "durable_session_active"
                    and event.get("unit_manager") == "pid"
                    for event in events
                )
            )
            harness.close()

    def test_pid_owner_state_pointer_keeps_outer_controller_deferred(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            stat = Path(f"/proc/{os.getpid()}/stat").read_text()
            start_ticks = int(stat[stat.rfind(")") + 2 :].split()[19])
            project = config.lab_dir / "projects" / "durable-pointer"
            project.mkdir()
            (project / "PROJECT.md").write_text("# durable pointer\n")
            owner_state = project / "OWNER_STATE.json"
            owner_state.write_text(
                json.dumps(
                    {
                        "unit_manager": "pid",
                        "pid": os.getpid(),
                        "start_ticks": start_ticks,
                    }
                )
            )
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "active",
                        "priority": 20,
                        "active_session": {
                            "artifact_root": "artifacts/run-1",
                            "unit": str(owner_state),
                            "unit_manager": "pid",
                        },
                    }
                )
            )

            harness._run_researchers()

            self.assertEqual([], runner.calls)
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_deferred"
                    and event.get("label") == "durable-pointer"
                    and event.get("reason") == "durable_session_active"
                    and event.get("unit_manager") == "pid"
                    for event in events
                )
            )
            harness.close()

    def test_researcher_cap_limits_paid_projects_to_five(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "max_parallel_researchers": 5,
                }
            )
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            for index in range(6):
                name = f"paid-{index}"
                project = config.lab_dir / "projects" / name
                project.mkdir()
                (project / "PROJECT.md").write_text(f"# {name}\n")
                (project / "STATUS.json").write_text(
                    json.dumps(
                        {
                            "status": "active",
                            "priority": 100 - index,
                            "authorized_spend_usd": 1.0,
                        }
                    )
                )

            harness._run_researchers()

            researcher_calls = [
                call for call in runner.calls if call["role"] == "researcher"
            ]
            self.assertEqual(
                [f"paid-{index}" for index in range(5)],
                [call["label"] for call in researcher_calls],
            )
            harness.close()

    def test_campaign_spend_cap_reserves_projects_and_rejects_overcommit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "max_parallel_researchers": 5,
                    "spend_cap_usd": 2.0,
                    "spend_cap_starts_at": "2026-07-17T21:59:00Z",
                }
            )
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            for name, priority, spend in (
                ("paid-primary", 30, 1.5),
                ("paid-over-cap", 20, 1.0),
                ("offline", 10, 0.0),
            ):
                project = config.lab_dir / "projects" / name
                project.mkdir()
                (project / "PROJECT.md").write_text(f"# {name}\n")
                (project / "STATUS.json").write_text(
                    json.dumps(
                        {
                            "status": "active",
                            "priority": priority,
                            "authorized_spend_usd": spend,
                        }
                    )
                )

            harness._run_researchers()

            researcher_calls = [
                call for call in runner.calls if call["role"] == "researcher"
            ]
            self.assertEqual(
                ["paid-primary", "offline"],
                [call["label"] for call in researcher_calls],
            )
            self.assertIn(
                "cumulative provider-spend ceiling across all of its allocations",
                researcher_calls[0]["prompt"],
            )
            self.assertIn(
                "Paid provider mutation is forbidden",
                researcher_calls[1]["prompt"],
            )
            spend_cap = json.loads(harness.spend_cap_path.read_text())
            self.assertEqual(
                {"paid-primary"}, set(spend_cap["reservations"])
            )
            self.assertEqual(0.5, harness._spend_cap_snapshot()["available_usd"])
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_deferred"
                    and event.get("label") == "paid-over-cap"
                    and event.get("reason") == "spend_cap_exceeded"
                    for event in events
                )
            )
            harness.close()

    def test_campaign_spend_cap_cannot_be_reset_implicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            configured = LabConfig(
                **{
                    **base.__dict__,
                    "spend_cap_usd": 100.0,
                    "spend_cap_starts_at": "2026-07-17T21:59:00Z",
                }
            )
            first = LabHarness(configured, runner=FakeRunner(configured.lab_dir))
            first.close()
            changed = LabConfig(
                **{
                    **configured.__dict__,
                    "spend_cap_starts_at": "2026-07-18T00:00:00Z",
                }
            )
            with self.assertRaisesRegex(RuntimeError, "cannot be reset"):
                LabHarness(changed, runner=FakeRunner(changed.lab_dir))

    def test_settled_spend_and_reservation_epoch_release_historical_allowances(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "spend_cap_usd": 200.0,
                    "spend_cap_starts_at": "2026-07-17T21:59:00Z",
                }
            )
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            ledger = json.loads(harness.spend_cap_path.read_text())
            ledger["settled_spend_usd"] = 110.0
            ledger["reservation_epoch"] = "2026-07-22T21:30:00Z"
            ledger["reservations"]["historical"] = {
                "authorized_usd": 200.0,
                "reserved_at": "2026-07-18T00:00:00Z",
            }
            harness.spend_cap_path.write_text(json.dumps(ledger))
            row = {
                "id": "next-experiment",
                "authorized_spend_usd": 10.0,
            }

            self.assertEqual(90.0, harness._spend_cap_snapshot()["available_usd"])
            self.assertTrue(harness._reserve_project_spend(row))
            snapshot = harness._spend_cap_snapshot()
            self.assertEqual(80.0, snapshot["available_usd"])
            self.assertEqual({"next-experiment"}, set(snapshot["reservations"]))
            self.assertEqual(1, snapshot["historical_reservation_count"])
            harness.close()

    def test_terminal_project_actual_spend_settles_and_releases_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "spend_cap_usd": 20.0,
                    "spend_cap_starts_at": "2026-07-17T21:59:00Z",
                }
            )
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            project = config.lab_dir / "projects" / "measured"
            project.mkdir()
            (project / "PROJECT.md").write_text("# measured\n")
            status_path = project / "STATUS.json"
            status_path.write_text(
                json.dumps(
                    {
                        "status": "active",
                        "authorized_spend_usd": 10.0,
                    }
                )
            )
            row = harness._project_rows()[0]
            self.assertTrue(harness._reserve_project_spend(row))
            status_path.write_text(
                json.dumps(
                    {
                        "status": "terminal",
                        "authorized_spend_usd": 10.0,
                        "actual_spend_usd": 2.5,
                    }
                )
            )

            harness._settle_terminal_reservations()

            snapshot = harness._spend_cap_snapshot()
            self.assertEqual(2.5, snapshot["settled_spend_usd"])
            self.assertEqual(17.5, snapshot["available_usd"])
            self.assertEqual({}, snapshot["reservations"])
            harness.close()

    def test_live_gpu_exposure_keeps_terminal_project_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "spend_cap_usd": 20.0,
                    "spend_cap_starts_at": "2026-07-17T21:59:00Z",
                }
            )
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            project = config.lab_dir / "projects" / "measured"
            project.mkdir()
            (project / "PROJECT.md").write_text("# measured\n")
            status_path = project / "STATUS.json"
            status_path.write_text(
                json.dumps(
                    {
                        "status": "active",
                        "authorized_spend_usd": 10.0,
                    }
                )
            )
            self.assertTrue(
                harness._reserve_project_spend(harness._project_rows()[0])
            )
            status_path.write_text(
                json.dumps(
                    {
                        "status": "terminal",
                        "authorized_spend_usd": 10.0,
                        "actual_spend_usd": 0.0,
                    }
                )
            )
            spec = pool_bench_spec()
            spec["contents"]["project"] = "measured"
            harness.gpu_pool.register(spec)

            harness._settle_terminal_reservations()

            snapshot = harness._spend_cap_snapshot()
            self.assertEqual(0.0, snapshot["settled_spend_usd"])
            self.assertEqual({"measured"}, set(snapshot["reservations"]))
            self.assertEqual(10.0, snapshot["available_usd"])
            harness.close()

    def test_live_gpu_exposure_restores_early_released_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "spend_cap_usd": 20.0,
                    "spend_cap_starts_at": "2026-07-17T21:59:00Z",
                }
            )
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            project = config.lab_dir / "projects" / "measured"
            project.mkdir()
            (project / "PROJECT.md").write_text("# measured\n")
            status_path = project / "STATUS.json"
            status_path.write_text(
                json.dumps(
                    {
                        "status": "active",
                        "authorized_spend_usd": 10.0,
                    }
                )
            )
            self.assertTrue(
                harness._reserve_project_spend(harness._project_rows()[0])
            )
            status_path.write_text(
                json.dumps(
                    {
                        "status": "terminal",
                        "authorized_spend_usd": 10.0,
                        "actual_spend_usd": 0.0,
                    }
                )
            )
            harness._settle_terminal_reservations()
            self.assertEqual({}, harness._spend_cap_snapshot()["reservations"])
            spec = pool_bench_spec()
            spec["contents"]["project"] = "measured"
            harness.gpu_pool.register(spec)

            harness._settle_terminal_reservations()

            snapshot = harness._spend_cap_snapshot()
            self.assertEqual({"measured"}, set(snapshot["reservations"]))
            self.assertEqual(10.0, snapshot["available_usd"])
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "spend_reservation_restored"
                    and event.get("label") == "measured"
                    and event.get("authorized_spend_usd") == 10.0
                    for event in events
                )
            )
            harness.close()

    def test_late_provider_exposure_reconciles_after_zero_spend_settlement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "spend_cap_usd": 0.4,
                    "spend_cap_starts_at": "2026-07-17T21:59:00Z",
                }
            )
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            project = config.lab_dir / "projects" / "late-cleanup"
            project.mkdir()
            (project / "PROJECT.md").write_text("# late cleanup\n")
            status_path = project / "STATUS.json"
            status_path.write_text(
                json.dumps(
                    {
                        "status": "active",
                        "authorized_spend_usd": 0.4,
                    }
                )
            )
            self.assertTrue(
                harness._reserve_project_spend(harness._project_rows()[0])
            )
            status_path.write_text(
                json.dumps(
                    {
                        "status": "terminal",
                        "authorized_spend_usd": 0.4,
                        "actual_spend_usd": 0.0,
                    }
                )
            )
            harness._settle_terminal_reservations()
            status_path.write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "authorized_spend_usd": 0.4,
                        "actual_spend_usd": 0.435895,
                    }
                )
            )

            harness._settle_terminal_reservations()

            snapshot = harness._spend_cap_snapshot()
            self.assertEqual(0.435895, snapshot["settled_spend_usd"])
            self.assertEqual(-0.035895, snapshot["available_usd"])
            self.assertFalse(
                harness._reserve_project_spend(
                    {
                        "id": "successor",
                        "authorized_spend_usd": 0.01,
                    }
                )
            )
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "spend_reconciled"
                    and event.get("label") == "late-cleanup"
                    and event.get("incremental_actual_spend_usd") == 0.435895
                    for event in events
                )
            )
            harness.close()

    def test_active_researcher_keeps_transient_blocked_project_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "spend_cap_usd": 20.0,
                    "spend_cap_starts_at": "2026-07-17T21:59:00Z",
                }
            )
            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))
            project = config.lab_dir / "projects" / "repairing"
            project.mkdir()
            (project / "PROJECT.md").write_text("# repairing\n")
            status_path = project / "STATUS.json"
            status_path.write_text(
                json.dumps(
                    {
                        "status": "active",
                        "authorized_spend_usd": 8.0,
                    }
                )
            )
            self.assertTrue(
                harness._reserve_project_spend(harness._project_rows()[0])
            )
            status_path.write_text(
                json.dumps(
                    {
                        "status": "blocked",
                        "authorized_spend_usd": 8.0,
                        "actual_spend_usd": 0.25,
                    }
                )
            )

            harness._settle_terminal_reservations({"repairing"})
            snapshot = harness._spend_cap_snapshot()
            self.assertEqual(0.0, snapshot["settled_spend_usd"])
            self.assertEqual({"repairing"}, set(snapshot["reservations"]))

            harness._settle_terminal_reservations()
            snapshot = harness._spend_cap_snapshot()
            self.assertEqual(0.25, snapshot["settled_spend_usd"])
            self.assertEqual({}, snapshot["reservations"])
            harness.close()

    def test_event_loop_refills_fast_result_before_slow_sibling_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "cycle_interval_seconds": 10,
                    "supervisor_every_cycles": 100,
                }
            )
            stop = threading.Event()
            release_slow = threading.Event()
            slow_finished = threading.Event()

            class EventRunner(FakeRunner):
                def __init__(self, lab_dir: Path):
                    super().__init__(lab_dir)
                    self.director_calls = 0
                    self.second_director_before_slow = False
                    self.successor_before_slow = False

                def write_project(self, name: str, priority: int) -> None:
                    project = self.lab_dir / "projects" / name
                    project.mkdir(parents=True, exist_ok=True)
                    (project / "PROJECT.md").write_text(f"# {name}\n")
                    (project / "STATUS.json").write_text(
                        json.dumps(
                            {
                                "status": "active",
                                "priority": priority,
                                "summary": "ready",
                                "next_action": "run",
                            }
                        )
                    )

                def terminal(self, name: str) -> None:
                    project = self.lab_dir / "projects" / name
                    (project / "STATUS.json").write_text(
                        json.dumps(
                            {
                                "status": "complete",
                                "priority": 0,
                                "summary": "measured",
                                "next_action": "director",
                            }
                        )
                    )

                def run(
                    self,
                    prompt,
                    *,
                    role,
                    route,
                    thread_id,
                    timeout_seconds,
                    label,
                ):
                    with self._lock:
                        self.calls.append({"role": role, "label": label})
                        if role == "researcher":
                            self._active_researchers += 1
                            self.max_active_researchers = max(
                                self.max_active_researchers,
                                self._active_researchers,
                            )
                    try:
                        if role == "director":
                            self.director_calls += 1
                            if self.director_calls == 1:
                                self.write_project("fast", 20)
                                self.write_project("slow", 10)
                            elif self.director_calls == 2:
                                self.second_director_before_slow = (
                                    not slow_finished.is_set()
                                )
                                self.write_project("successor", 30)
                            elif self.director_calls >= 3:
                                release_slow.set()
                                stop.set()
                        elif role == "researcher":
                            if label == "slow":
                                release_slow.wait(5)
                                self.terminal(label)
                                slow_finished.set()
                            else:
                                if label == "successor":
                                    self.successor_before_slow = (
                                        not slow_finished.is_set()
                                    )
                                self.terminal(label)
                    finally:
                        if role == "researcher":
                            with self._lock:
                                self._active_researchers -= 1
                    return {
                        "thread_id": thread_id or f"thread-{role}-{label}",
                        "returncode": 0,
                        "timed_out": False,
                        "duration_seconds": 0.01,
                        "model": route.model,
                        "reasoning_effort": route.reasoning_effort,
                    }

            runner = EventRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.run_forever(stop_event=stop)

            self.assertTrue(runner.second_director_before_slow)
            self.assertTrue(runner.successor_before_slow)
            self.assertLessEqual(runner.max_active_researchers, 2)
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            dispatched = [
                event
                for event in events
                if event.get("event") == "director_wake_dispatched"
                and "researcher_completed" in event.get("reasons", [])
            ]
            self.assertTrue(dispatched)
            self.assertLess(
                dispatched[0]["oldest_wake_delay_seconds"], 1.0
            )
            harness.close()

    def test_director_completion_launches_admitted_work_before_queued_wake(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "cycle_interval_seconds": 10,
                    "max_parallel_researchers": 2,
                    "supervisor_every_cycles": 100,
                }
            )
            stop = threading.Event()
            release_slow = threading.Event()
            slow_finished = threading.Event()

            class AdmissionRunner(FakeRunner):
                def __init__(self, lab_dir: Path):
                    super().__init__(lab_dir)
                    self.director_calls = 0

                def write_project(self, name: str, priority: int) -> None:
                    project = self.lab_dir / "projects" / name
                    project.mkdir(parents=True, exist_ok=True)
                    (project / "PROJECT.md").write_text(f"# {name}\n")
                    (project / "STATUS.json").write_text(
                        json.dumps(
                            {
                                "status": "active",
                                "priority": priority,
                                "summary": "ready",
                                "next_action": "run",
                            }
                        )
                    )

                def terminal(self, name: str) -> None:
                    project = self.lab_dir / "projects" / name
                    (project / "STATUS.json").write_text(
                        json.dumps(
                            {
                                "status": "complete",
                                "priority": 0,
                                "summary": "measured",
                                "next_action": "director",
                            }
                        )
                    )

                def run(
                    self,
                    prompt,
                    *,
                    role,
                    route,
                    thread_id,
                    timeout_seconds,
                    label,
                ):
                    if role == "director":
                        self.director_calls += 1
                        if self.director_calls == 1:
                            self.write_project("fast", 20)
                            self.write_project("slow", 10)
                        elif self.director_calls == 2:
                            release_slow.set()
                            slow_finished.wait(5)
                            time.sleep(0.1)
                            self.write_project("admitted", 30)
                        else:
                            stop.set()
                    elif label == "slow":
                        release_slow.wait(5)
                        self.terminal(label)
                        slow_finished.set()
                    else:
                        self.terminal(label)
                    return {
                        "thread_id": thread_id or f"thread-{role}-{label}",
                        "returncode": 0,
                        "timed_out": False,
                        "duration_seconds": 0.01,
                        "model": route.model,
                        "reasoning_effort": route.reasoning_effort,
                    }

            runner = AdmissionRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.run_forever(stop_event=stop)

            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            admitted_slot = next(
                index
                for index, event in enumerate(events)
                if event.get("event") == "researcher_slot_filled"
                and event.get("label") == "admitted"
            )
            queued_wake = next(
                index
                for index, event in enumerate(events)
                if index > admitted_slot
                and event.get("event") == "director_wake_dispatched"
                and "researcher_completed" in event.get("reasons", [])
            )
            self.assertLess(admitted_slot, queued_wake)
            harness.close()

    def test_event_loop_wakes_durable_repair_while_director_is_running(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "cycle_interval_seconds": 10,
                    "max_parallel_researchers": 1,
                    "supervisor_every_cycles": 100,
                }
            )
            stop = threading.Event()
            director_started = threading.Event()
            director_finished = threading.Event()
            repair_started = threading.Event()

            class RepairRunner(FakeRunner):
                def __init__(self, lab_dir: Path):
                    super().__init__(lab_dir)
                    self.director_calls = 0
                    self.researcher_calls = 0
                    self.repair_started_while_director = False

                def run(
                    self,
                    prompt,
                    *,
                    role,
                    route,
                    thread_id,
                    timeout_seconds,
                    label,
                ):
                    if role == "director":
                        self.director_calls += 1
                        if self.director_calls == 1:
                            project = self.lab_dir / "projects" / "repair"
                            project.mkdir()
                            (project / "PROJECT.md").write_text("# repair\n")
                            (project / "STATUS.json").write_text(
                                json.dumps(
                                    {
                                        "status": "active",
                                        "priority": 1,
                                        "next_action": "run",
                                    }
                                )
                            )
                        else:
                            director_started.set()
                            repair_started.wait(5)
                            director_finished.set()
                            stop.set()
                    elif role == "researcher":
                        self.researcher_calls += 1
                        if self.researcher_calls == 1:
                            project = self.lab_dir / "projects" / label
                            artifacts = project / "artifacts" / "run"
                            artifacts.mkdir(parents=True)
                            (artifacts / "REPAIR_READY.json").write_text(
                                json.dumps(
                                    {
                                        "repair_deadline_epoch": (
                                            time.time() + 600
                                        )
                                    }
                                )
                            )
                            (project / "STATUS.json").write_text(
                                json.dumps(
                                    {
                                        "status": "active",
                                        "priority": 1,
                                        "active_session": {
                                            "unit": "repair.service",
                                            "unit_manager": "user",
                                            "artifact_root": "artifacts/run",
                                        },
                                    }
                                )
                            )
                        else:
                            self.repair_started_while_director = (
                                director_started.is_set()
                                and not director_finished.is_set()
                            )
                            repair_started.set()
                    return {
                        "thread_id": thread_id or f"thread-{role}-{label}",
                        "returncode": 0,
                        "timed_out": False,
                        "duration_seconds": 0.01,
                        "model": route.model,
                        "reasoning_effort": route.reasoning_effort,
                    }

            runner = RepairRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                unit_is_active=lambda unit, manager: (
                    unit == "repair.service" and manager == "user"
                ),
            )
            harness.run_forever(stop_event=stop)

            self.assertTrue(runner.repair_started_while_director)
            self.assertEqual(2, runner.researcher_calls)
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_woken"
                    and event.get("label") == "repair"
                    and event.get("reason") == "durable_repair_ready"
                    for event in events
                )
            )
            harness.close()

    def test_event_loop_supervisor_does_not_block_result_director(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "cycle_interval_seconds": 1,
                    "max_parallel_researchers": 1,
                    "supervisor_every_cycles": 1,
                }
            )
            stop = threading.Event()
            supervisor_started = threading.Event()
            release_supervisor = threading.Event()
            supervisor_finished = threading.Event()

            class IndependentRunner(FakeRunner):
                def __init__(self, lab_dir: Path):
                    super().__init__(lab_dir)
                    self.director_calls = 0
                    self.director_ran_while_supervisor_blocked = False

                def run(
                    self,
                    prompt,
                    *,
                    role,
                    route,
                    thread_id,
                    timeout_seconds,
                    label,
                ):
                    with self._lock:
                        self.calls.append({"role": role, "label": label})
                    if role == "director":
                        self.director_calls += 1
                        if self.director_calls == 1:
                            project = self.lab_dir / "projects" / "result"
                            project.mkdir()
                            (project / "PROJECT.md").write_text("# result\n")
                            (project / "STATUS.json").write_text(
                                json.dumps(
                                    {
                                        "status": "active",
                                        "priority": 1,
                                        "summary": "ready",
                                        "next_action": "run",
                                    }
                                )
                            )
                        else:
                            self.director_ran_while_supervisor_blocked = (
                                supervisor_started.is_set()
                                and not supervisor_finished.is_set()
                            )
                            release_supervisor.set()
                            stop.set()
                    elif role == "researcher":
                        supervisor_started.wait(4)
                        project = self.lab_dir / "projects" / label
                        (project / "STATUS.json").write_text(
                            json.dumps(
                                {
                                    "status": "complete",
                                    "summary": "measured",
                                    "next_action": "director",
                                }
                            )
                        )
                    elif role == "supervisor":
                        supervisor_started.set()
                        release_supervisor.wait(4)
                        supervisor_finished.set()
                    return {
                        "thread_id": thread_id or f"thread-{role}-{label}",
                        "returncode": 0,
                        "timed_out": False,
                        "duration_seconds": 0.01,
                        "model": route.model,
                        "reasoning_effort": route.reasoning_effort,
                    }

            runner = IndependentRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.run_forever(stop_event=stop)

            self.assertTrue(supervisor_started.is_set())
            self.assertTrue(runner.director_ran_while_supervisor_blocked)
            harness.close()

    def test_event_loop_director_completion_resets_fallback_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "cycle_interval_seconds": 1,
                    "supervisor_every_cycles": 100,
                }
            )
            stop = threading.Event()

            class CadenceRunner(FakeRunner):
                def __init__(self, lab_dir: Path):
                    super().__init__(lab_dir)
                    self.director_calls = 0
                    self.first_director_completed_at = None
                    self.second_director_started_at = None

                def run(
                    self,
                    prompt,
                    *,
                    role,
                    route,
                    thread_id,
                    timeout_seconds,
                    label,
                ):
                    if role == "director":
                        self.director_calls += 1
                        if self.director_calls == 1:
                            time.sleep(0.6)
                            self.first_director_completed_at = time.monotonic()
                        else:
                            self.second_director_started_at = time.monotonic()
                            stop.set()
                    return {
                        "thread_id": thread_id or f"thread-{role}-{label}",
                        "returncode": 0,
                        "timed_out": False,
                        "duration_seconds": 0.01,
                        "model": route.model,
                        "reasoning_effort": route.reasoning_effort,
                    }

            runner = CadenceRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.run_forever(stop_event=stop)

            self.assertEqual(2, runner.director_calls)
            self.assertIsNotNone(runner.first_director_completed_at)
            self.assertIsNotNone(runner.second_director_started_at)
            self.assertGreaterEqual(
                runner.second_director_started_at
                - runner.first_director_completed_at,
                0.8,
            )
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "director_wake_dispatched"
                    and event.get("reasons") == ["fallback"]
                    for event in events
                )
            )
            harness.close()

    def test_event_loop_fallback_does_not_interrupt_unchanged_researcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "cycle_interval_seconds": 1,
                    "max_parallel_researchers": 1,
                    "supervisor_every_cycles": 100,
                }
            )
            stop = threading.Event()

            class QuietRunner(FakeRunner):
                def __init__(self, lab_dir: Path):
                    super().__init__(lab_dir)
                    self.director_calls = 0
                    self.director_calls_during_research = None

                def run(
                    self,
                    prompt,
                    *,
                    role,
                    route,
                    thread_id,
                    timeout_seconds,
                    label,
                ):
                    if role == "director":
                        self.director_calls += 1
                        if self.director_calls == 1:
                            project = self.lab_dir / "projects" / "long"
                            project.mkdir()
                            (project / "PROJECT.md").write_text("# long\n")
                            (project / "STATUS.json").write_text(
                                json.dumps(
                                    {
                                        "status": "active",
                                        "priority": 1,
                                        "summary": "ready",
                                        "next_action": "run",
                                    }
                                )
                            )
                        else:
                            stop.set()
                    elif role == "researcher":
                        time.sleep(2.2)
                        self.director_calls_during_research = self.director_calls
                        project = self.lab_dir / "projects" / label
                        (project / "STATUS.json").write_text(
                            json.dumps(
                                {
                                    "status": "complete",
                                    "summary": "measured",
                                    "next_action": "director",
                                }
                            )
                        )
                    return {
                        "thread_id": thread_id or f"thread-{role}-{label}",
                        "returncode": 0,
                        "timed_out": False,
                        "duration_seconds": 0.01,
                        "model": route.model,
                        "reasoning_effort": route.reasoning_effort,
                    }

            runner = QuietRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.run_forever(stop_event=stop)

            self.assertEqual(1, runner.director_calls_during_research)
            self.assertEqual(2, runner.director_calls)
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "director_wake_deferred"
                    and event.get("reasons") == ["fallback"]
                    for event in events
                )
            )
            harness.close()

    def test_event_loop_unchanged_researcher_cannot_hot_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "cycle_interval_seconds": 5,
                    "max_parallel_researchers": 1,
                    "supervisor_every_cycles": 100,
                }
            )
            stop = threading.Event()

            class NoProgressRunner(FakeRunner):
                def __init__(self, lab_dir: Path):
                    super().__init__(lab_dir)
                    self.director_calls = 0
                    self.researcher_calls = 0
                    self.director_saw_last_run = False

                def run(
                    self,
                    prompt,
                    *,
                    role,
                    route,
                    thread_id,
                    timeout_seconds,
                    label,
                ):
                    if role == "director":
                        self.director_calls += 1
                        if self.director_calls == 1:
                            project = self.lab_dir / "projects" / "unchanged"
                            project.mkdir()
                            (project / "PROJECT.md").write_text("# unchanged\n")
                            (project / "STATUS.json").write_text(
                                json.dumps(
                                    {
                                        "status": "active",
                                        "priority": 1,
                                        "summary": "ready",
                                        "next_action": "run",
                                    }
                                )
                            )
                        else:
                            self.director_saw_last_run = (
                                '"last_researcher_run"' in prompt
                                and '"returncode": 0' in prompt
                            )
                            threading.Timer(0.2, stop.set).start()
                    elif role == "researcher":
                        self.researcher_calls += 1
                    return {
                        "thread_id": thread_id or f"thread-{role}-{label}",
                        "returncode": 0,
                        "timed_out": False,
                        "duration_seconds": 0.01,
                        "model": route.model,
                        "reasoning_effort": route.reasoning_effort,
                    }

            runner = NoProgressRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.run_forever(stop_event=stop)

            self.assertEqual(2, runner.director_calls)
            self.assertEqual(1, runner.researcher_calls)
            self.assertTrue(runner.director_saw_last_run)
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_no_progress"
                    and event.get("label") == "unchanged"
                    for event in events
                )
            )
            self.assertFalse(
                any(event.get("event") == "scheduler_failed" for event in events)
            )
            harness.close()

    def test_event_loop_agent_service_failure_starts_global_backoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "cycle_interval_seconds": 1,
                    "max_parallel_researchers": 1,
                    "supervisor_every_cycles": 100,
                }
            )
            stop = threading.Event()

            class UnavailableRunner(FakeRunner):
                def __init__(self, lab_dir: Path):
                    super().__init__(lab_dir)
                    self.director_calls = 0
                    self.researcher_calls = 0

                def run(
                    self,
                    prompt,
                    *,
                    role,
                    route,
                    thread_id,
                    timeout_seconds,
                    label,
                ):
                    if role == "director":
                        self.director_calls += 1
                        project = self.lab_dir / "projects" / "blocked"
                        project.mkdir()
                        (project / "PROJECT.md").write_text("# blocked\n")
                        (project / "STATUS.json").write_text(
                            json.dumps(
                                {
                                    "status": "active",
                                    "priority": 1,
                                    "summary": "ready",
                                    "next_action": "run",
                                }
                            )
                        )
                        return {
                            "thread_id": "thread-director",
                            "returncode": 0,
                            "timed_out": False,
                            "duration_seconds": 0.01,
                            "model": route.model,
                            "reasoning_effort": route.reasoning_effort,
                        }
                    self.researcher_calls += 1
                    trace = self.lab_dir / "runtime" / "service-error.jsonl"
                    trace.write_text(
                        '{"type":"error","message":'
                        '"biscuit_baker_service_me_circuit_open"}\n'
                    )
                    threading.Timer(1.2, stop.set).start()
                    return {
                        "thread_id": "thread-researcher",
                        "returncode": 1,
                        "timed_out": False,
                        "duration_seconds": 0.01,
                        "model": route.model,
                        "reasoning_effort": route.reasoning_effort,
                        "stdout_path": str(trace),
                    }

            runner = UnavailableRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.run_forever(stop_event=stop)

            self.assertEqual(1, runner.director_calls)
            self.assertEqual(1, runner.researcher_calls)
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "agent_service_backoff_started"
                    and event.get("role") == "researcher"
                    and event.get("retry_after_seconds") == 300
                    for event in events
                )
            )
            self.assertFalse(
                any(
                    event.get("event") == "researcher_no_progress"
                    for event in events
                )
            )
            harness.close()

    def test_agent_service_failure_requires_failed_run_and_known_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = root / "trace.jsonl"
            trace.write_text(
                '{"type":"error","message":'
                '"biscuit_baker_service_me_circuit_open"}\n'
            )
            self.assertTrue(
                run_reports_agent_service_unavailable(
                    {
                        "returncode": 1,
                        "timed_out": False,
                        "stdout_path": str(trace),
                    }
                )
            )
            trace.write_text(
                '{"type":"turn.failed","error":{"message":'
                '"You\'ve hit your usage limit. Try again later."}}\n'
            )
            self.assertTrue(
                run_reports_agent_service_unavailable(
                    {
                        "returncode": 1,
                        "timed_out": False,
                        "stdout_path": str(trace),
                    }
                )
            )
            self.assertFalse(
                run_reports_agent_service_unavailable(
                    {
                        "returncode": 0,
                        "timed_out": False,
                        "stdout_path": str(trace),
                    }
                )
            )
            trace.write_text('{"type":"error","message":"ordinary failure"}\n')
            self.assertFalse(
                run_reports_agent_service_unavailable(
                    {
                        "returncode": 1,
                        "timed_out": False,
                        "stdout_path": str(trace),
                    }
                )
            )

    def test_context_window_exhaustion_rotates_resumed_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = root / "context-exhausted.jsonl"
            trace.write_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": (
                            "Codex ran out of room in the model's context window. "
                            "Start a new thread or clear earlier history before retrying."
                        ),
                    }
                )
                + "\n"
            )

            class ContextExhaustedRunner(FakeRunner):
                def run(
                    self,
                    prompt,
                    *,
                    role,
                    route,
                    thread_id,
                    timeout_seconds,
                    label,
                ):
                    return {
                        "thread_id": thread_id,
                        "returncode": 1,
                        "timed_out": False,
                        "duration_seconds": 0.01,
                        "model": route.model,
                        "reasoning_effort": route.reasoning_effort,
                        "stdout_path": str(trace),
                    }

            harness = LabHarness(self._config(root), runner=ContextExhaustedRunner(root))
            harness.state["threads"]["director"] = "saturated-director-thread"
            harness._run_agent(
                role="director",
                label="director",
                prompt="continue",
                route=harness.config.director,
                thread_id="saturated-director-thread",
                timeout_seconds=60,
            )

            self.assertIsNone(harness.state["threads"]["director"])
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "agent_thread_rotated"
                    and event.get("reason") == "context_window_exhausted"
                    and event.get("previous_thread_id")
                    == "saturated-director-thread"
                    for event in events
                )
            )
            harness.close()

    def test_context_window_exhaustion_rotates_thread_after_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            trace = config.lab_dir / "runtime" / "context-exhausted.jsonl"
            trace.parent.mkdir(exist_ok=True)
            trace.write_text(
                json.dumps(
                    {
                        "type": "turn.failed",
                        "error": {
                            "message": (
                                "Codex ran out of room in the model's context window."
                            )
                        },
                    }
                )
                + "\n"
            )
            state = {
                "schema_version": 1,
                "cycle_count": 0,
                "threads": {
                    "director": "saturated-director-thread",
                    "supervisor": None,
                    "projects": {},
                },
                "project_routes": {},
                "director_observation_sha256": None,
                "development_observations": {},
                "active_agents": {},
                "last_runs": {
                    "director:director": {
                        "thread_id": "saturated-director-thread",
                        "returncode": 1,
                        "timed_out": False,
                        "stdout_path": str(trace),
                    }
                },
                "updated_at": "2026-07-25T20:45:33Z",
            }
            (config.lab_dir / "runtime" / "state.json").write_text(
                json.dumps(state)
            )

            harness = LabHarness(config, runner=FakeRunner(config.lab_dir))

            self.assertIsNone(harness.state["threads"]["director"])
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "agent_thread_rotated"
                    and event.get("reason")
                    == "context_window_exhausted_on_startup"
                    for event in events
                )
            )
            harness.close()

    def test_event_loop_retries_context_exhausted_researcher_without_director(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "cycle_interval_seconds": 10,
                    "max_parallel_researchers": 1,
                    "supervisor_every_cycles": 100,
                }
            )
            stop = threading.Event()
            trace = config.lab_dir / "runtime" / "context-exhausted.jsonl"
            trace.parent.mkdir(exist_ok=True)
            trace.write_text(
                json.dumps(
                    {
                        "type": "turn.failed",
                        "error": {
                            "message": (
                                "Codex ran out of room in the model's context window."
                            )
                        },
                    }
                )
                + "\n"
            )

            class ContextExhaustedResearcherRunner(FakeRunner):
                def __init__(self, lab_dir: Path):
                    super().__init__(lab_dir)
                    self.director_calls = 0
                    self.researcher_thread_ids = []

                def run(
                    self,
                    prompt,
                    *,
                    role,
                    route,
                    thread_id,
                    timeout_seconds,
                    label,
                ):
                    if role == "director":
                        self.director_calls += 1
                        project = self.lab_dir / "projects" / "retry"
                        project.mkdir(exist_ok=True)
                        (project / "PROJECT.md").write_text("# retry\n")
                        (project / "STATUS.json").write_text(
                            json.dumps(
                                {
                                    "status": "active",
                                    "priority": 1,
                                    "summary": "ready",
                                    "next_action": "run",
                                }
                            )
                        )
                        return {
                            "thread_id": "thread-director",
                            "returncode": 0,
                            "timed_out": False,
                            "duration_seconds": 0.01,
                            "model": route.model,
                            "reasoning_effort": route.reasoning_effort,
                        }
                    self.researcher_thread_ids.append(thread_id)
                    if len(self.researcher_thread_ids) == 1:
                        return {
                            "thread_id": "exhausted-researcher-thread",
                            "returncode": 1,
                            "timed_out": False,
                            "duration_seconds": 0.01,
                            "model": route.model,
                            "reasoning_effort": route.reasoning_effort,
                            "stdout_path": str(trace),
                        }
                    stop.set()
                    return {
                        "thread_id": "second-exhausted-researcher-thread",
                        "returncode": 1,
                        "timed_out": False,
                        "duration_seconds": 0.01,
                        "model": route.model,
                        "reasoning_effort": route.reasoning_effort,
                        "stdout_path": str(trace),
                    }

            runner = ContextExhaustedResearcherRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.run_forever(stop_event=stop)

            self.assertEqual(1, runner.director_calls)
            self.assertEqual([None, None], runner.researcher_thread_ids)
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_retry_queued"
                    and event.get("reason") == "context_window_exhausted"
                    for event in events
                )
            )
            self.assertFalse(
                any(
                    event.get("event") == "researcher_no_progress"
                    for event in events
                )
            )
            harness.close()

    def test_event_loop_simultaneous_results_publish_status_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self._config(root)
            config = LabConfig(
                **{
                    **base.__dict__,
                    "cycle_interval_seconds": 10,
                    "max_parallel_researchers": 5,
                    "supervisor_every_cycles": 100,
                }
            )
            stop = threading.Event()
            result_barrier = threading.Barrier(5)

            class SimultaneousRunner(FakeRunner):
                def __init__(self, lab_dir: Path):
                    super().__init__(lab_dir)
                    self.director_calls = 0

                def run(
                    self,
                    prompt,
                    *,
                    role,
                    route,
                    thread_id,
                    timeout_seconds,
                    label,
                ):
                    with self._lock:
                        if role == "researcher":
                            self._active_researchers += 1
                            self.max_active_researchers = max(
                                self.max_active_researchers,
                                self._active_researchers,
                            )
                    try:
                        if role == "director":
                            self.director_calls += 1
                            if self.director_calls == 1:
                                for index in range(5):
                                    project = (
                                        self.lab_dir
                                        / "projects"
                                        / f"result-{index}"
                                    )
                                    project.mkdir()
                                    (project / "PROJECT.md").write_text(
                                        f"# result-{index}\n"
                                    )
                                    (project / "STATUS.json").write_text(
                                        json.dumps(
                                            {
                                                "status": "active",
                                                "priority": 10 - index,
                                                "summary": "ready",
                                                "next_action": "run",
                                            }
                                        )
                                    )
                            else:
                                stop.set()
                        elif role == "researcher":
                            project = self.lab_dir / "projects" / label
                            (project / "STATUS.json").write_text(
                                json.dumps(
                                    {
                                        "status": "complete",
                                        "summary": "measured",
                                        "next_action": "director",
                                    }
                                )
                            )
                            result_barrier.wait(3)
                    finally:
                        if role == "researcher":
                            with self._lock:
                                self._active_researchers -= 1
                    return {
                        "thread_id": thread_id or f"thread-{role}-{label}",
                        "returncode": 0,
                        "timed_out": False,
                        "duration_seconds": 0.01,
                        "model": route.model,
                        "reasoning_effort": route.reasoning_effort,
                    }

            runner = SimultaneousRunner(config.lab_dir)
            harness = LabHarness(config, runner=runner)
            harness.run_forever(stop_event=stop)

            self.assertEqual(5, runner.max_active_researchers)
            json.loads(harness.status_json_path.read_text())
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertFalse(
                any(event.get("event") == "scheduler_failed" for event in events)
            )
            self.assertTrue(
                any(
                    event.get("event") == "director_wake_dispatched"
                    and "researcher_completed" in event.get("reasons", [])
                    for event in events
                )
            )
            harness.close()

    def test_activating_systemd_unit_counts_as_owned_but_failed_unit_does_not(self):
        with patch("grad_research.lab_harness.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "activating\n"
            self.assertTrue(
                LabHarness._systemd_unit_is_active("retained.service", "system")
            )
            self.assertIn("--system", run.call_args.args[0])

            run.return_value.stdout = "failed\n"
            self.assertFalse(
                LabHarness._systemd_unit_is_active("retained.service", "system")
            )

            self.assertFalse(
                LabHarness._systemd_unit_is_active("retained.service", "remote")
            )


if __name__ == "__main__":
    unittest.main()
