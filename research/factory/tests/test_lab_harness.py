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
            self.assertIn("latency tradeoffs as authoritative", runner.calls[0]["prompt"])
            self.assertIn(
                "produce new decision-relevant evidence quickly",
                runner.calls[1]["prompt"],
            )
            self.assertIn(
                "Keep documentation to a short handoff",
                runner.calls[1]["prompt"],
            )
            self.assertIn("trade latency as allowed", runner.calls[1]["prompt"])
            self.assertTrue((config.lab_dir / "STATUS.md").is_file())
            self.assertTrue((config.lab_dir / "runtime" / "events.jsonl").is_file())
            self.assertTrue((config.lab_dir / "projects" / "kernel" / "RESEARCH_LOG.md").is_file())
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


if __name__ == "__main__":
    unittest.main()
