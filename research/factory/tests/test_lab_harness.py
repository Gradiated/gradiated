from __future__ import annotations

import json
import io
import os
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from grad_research.lab_harness import (
    LabConfig,
    LabHarness,
    ModelRoute,
    codex_environment,
    main,
)


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
            self.assertIn(
                "The model-specific objective and intervention scope",
                runner.calls[-1]["prompt"],
            )
            self.assertIn(
                "decision-relevant research progress per wall-clock hour",
                runner.calls[0]["prompt"],
            )
            self.assertIn(
                "exclusive for provider mutation and spend, not for offline scientific work",
                runner.calls[0]["prompt"],
            )
            self.assertIn(
                "preregister one adjacent conditional follow-up",
                runner.calls[0]["prompt"],
            )
            self.assertIn(
                "across already-ranked project boundaries",
                runner.calls[0]["prompt"],
            )
            self.assertIn("existing retained-session path", runner.calls[0]["prompt"])
            self.assertIn("one sequential owner/watchdog", runner.calls[0]["prompt"])
            self.assertIn("latency tradeoffs as authoritative", runner.calls[0]["prompt"])
            self.assertIn(
                "produce new decision-relevant evidence quickly",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "Current scheduled action from `STATUS.json`: run the experiment",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "do not substitute another readiness artifact",
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
            self.assertTrue((config.lab_dir / "projects" / "kernel" / "RESEARCH_LOG.md").is_file())
            self.assertTrue((config.lab_dir / "projects" / "kernel" / "artifacts").is_dir())
            self.assertTrue((config.lab_dir / "projects" / "scheduler" / "artifacts").is_dir())
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
            self.assertIn("keep every dependent provider create gated", prompt)
            self.assertIn("Do not kill and restart correct local computation", prompt)
            self.assertIn("If you start a durable local or provider experiment owner", prompt)
            self.assertIn("STATUS.json.active_session", prompt)
            self.assertIn("canonical `unit` and `unit_manager` keys", prompt)
            self.assertIn("return immediately", prompt)
            self.assertIn("Do not sleep, poll checkpoint transfer", prompt)
            self.assertIn("reschedule terminal reconciliation", prompt)
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

    def test_unchanged_durable_session_defers_director_and_supervisor(self):
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

            status = harness.cycle()

            self.assertEqual(1, status["cycle_count"])
            self.assertEqual([], runner.calls)
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

    def test_only_one_provider_capable_project_is_scheduled_per_cycle(self):
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
                ["paid-primary", "offline"],
                [call["label"] for call in researcher_calls],
            )
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_deferred"
                    and event.get("label") == "paid-secondary"
                    and event.get("reason") == "provider_lane_reserved"
                    for event in events
                )
            )
            harness.close()

    def test_undeclared_lab_owner_reserves_provider_lane(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            runner = FakeRunner(config.lab_dir)
            harness = LabHarness(
                config,
                runner=runner,
                lab_active_units=lambda: [
                    {"unit": "component.service", "unit_manager": "user"}
                ],
            )
            for name, priority, spend in (
                ("paid", 20, 1.0),
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
                ["offline"], [call["label"] for call in researcher_calls]
            )
            events = [
                json.loads(line)
                for line in harness.events_path.read_text().splitlines()
            ]
            self.assertTrue(
                any(
                    event.get("event") == "researcher_deferred"
                    and event.get("label") == "paid"
                    and event.get("reason") == "provider_lane_reserved"
                    and event.get("observed_active_units")
                    == [{"unit": "component.service", "unit_manager": "user"}]
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
