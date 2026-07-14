from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from grad_research.labd import LabDatabase
from grad_research.supervisor import ModelRoute, ResearchSupervisor, SupervisorConfig


class FakeRunner:
    def __init__(self, supervisor: ResearchSupervisor | None = None):
        self.supervisor = supervisor
        self.calls = []

    def run(self, prompt, *, thread_id, task_kind, heartbeat, **kwargs):
        heartbeat()
        self.calls.append((prompt, thread_id, task_kind))
        return {
            "model": "sol",
            "reasoning_effort": "high",
            "task_kind": task_kind,
            "thread_id": thread_id or "thread-1",
            "pid": 1,
            "returncode": 0,
            "timed_out": False,
            "started_at": "2026-07-14T00:00:00Z",
            "ended_at": "2026-07-14T00:00:01Z",
            "duration_seconds": 1.0,
            "event_count": 2,
            "stdout_path": "trace.jsonl",
            "stderr_path": "stderr.log",
            "timeout_seconds": kwargs.get("timeout_seconds", 60),
        }


class FakeProviderProcess:
    def __init__(self):
        self.pid = __import__("os").getpid()

    def poll(self):
        return None


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.campaign = self.repo / "campaign"
        self.campaign.mkdir(parents=True)
        (self.campaign / "CAMPAIGN_STATUS.json").write_text("{}\n")
        self.config = SupervisorConfig(
            root=self.base / "lab",
            program_id="program-1",
            repo_dir=self.repo,
            campaign_dir=self.campaign,
            owner="supervisor-1",
            mode="observe",
            cycle_interval_seconds=1,
            idle_backoff_seconds=1,
            coordinator_ttl_seconds=60,
            director_timeout_seconds=60,
            turn_timeout_seconds=60,
            director=ModelRoute("sol", "high"),
            implementation=ModelRoute("terra", "medium"),
            mechanical=ModelRoute("luna", "low"),
            reuse_director_thread=False,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_model_routes_are_explicit(self):
        self.assertEqual(self.config.route("scientific_gate").model, "sol")
        self.assertEqual(self.config.route("implementation").model, "terra")
        self.assertEqual(self.config.route("mechanical").model, "luna")

    def test_director_defaults_to_fresh_bounded_turns(self):
        self.assertEqual(self.config.director_timeout_seconds, 60)
        self.assertFalse(self.config.reuse_director_thread)

    def test_task_routing_keeps_judgment_on_sol_and_commands_on_fast_worker(self):
        self.assertEqual(ResearchSupervisor._task_kind({"actions": [{"priority": "P0"}]}), "recovery")
        self.assertEqual(
            ResearchSupervisor._task_kind(
                {"work_packets": [{"lane": "parallel_offline", "command": ["true"]}]}
            ),
            "mechanical",
        )
        self.assertEqual(
            ResearchSupervisor._task_kind({"work_packets": [{"task_kind": "implementation"}]}),
            "implementation",
        )
        self.assertEqual(
            ResearchSupervisor._task_kind({"work_packets": [{"lane": "serialized_setup_affine"}]}),
            "scientific_gate",
        )

    def test_parallel_packets_use_fast_worker_route_and_durable_results(self):
        config = SupervisorConfig(**{**self.config.__dict__, "mode": "active", "max_parallel_workers": 2})
        runner = FakeRunner()
        supervisor = ResearchSupervisor(config, runner=runner)
        try:
            lease = supervisor.lab.acquire_coordinator(
                config.program_id,
                config.owner,
                ttl_seconds=60,
                now=time.time(),
            )
            results = supervisor._dispatch_workers(
                {
                    "actions": [],
                    "work_packets": [
                        {"packet_id": "cycle-1:offline-a", "lane": "parallel_offline", "command": ["true"], "timeout_seconds": 5},
                        {"packet_id": "cycle-1:offline-b", "lane": "parallel_offline", "fidelity": "simulation", "timeout_seconds": 5},
                    ],
                },
                lease,
                {"workers": {}},
            )
            self.assertEqual([result["status"] for result in results], ["succeeded", "succeeded"])
            self.assertEqual({call[2] for call in runner.calls}, {"mechanical"})
            self.assertTrue((supervisor.runtime_dir / "workers" / "cycle-1-offline-a" / "RESULT.json").exists())
            status = json.loads(supervisor.status_path.read_text())
            self.assertEqual(status["status"], "workers_complete")
            self.assertEqual(status["active_worker_count"], 0)
        finally:
            supervisor.close()

    def test_config_loads_without_credentials(self):
        path = self.base / "supervisor.json"
        path.write_text(
            json.dumps(
                {
                    "root": str(self.config.root),
                    "program_id": self.config.program_id,
                    "repo_dir": str(self.repo),
                    "campaign_dir": str(self.campaign),
                    "owner": self.config.owner,
                    "mode": "active",
                    "routes": {"mechanical": {"model": "fast", "reasoning_effort": "low"}},
                }
            )
        )
        loaded = SupervisorConfig.load(path)
        self.assertEqual(loaded.mode, "active")
        self.assertEqual(loaded.route("mechanical"), ModelRoute("fast", "low"))
        self.assertNotIn("api", path.read_text().lower())

    def test_admitted_provider_intent_is_started_as_durable_supervisor_job(self):
        config = SupervisorConfig(**{
            **self.config.__dict__,
            "mode": "active",
            "provider_launcher": ("python3", "{run_id}", "{admission_sha256}", "{output_dir}"),
        })
        calls = []

        def provider_popen(command, **kwargs):
            calls.append((command, kwargs))
            return FakeProviderProcess()

        supervisor = ResearchSupervisor(config, runner=FakeRunner(), provider_popen=provider_popen)
        try:
            lease = supervisor.lab.acquire_coordinator(
                config.program_id,
                config.owner,
                ttl_seconds=60,
                now=time.time(),
            )
            supervisor.director.state = lambda: {
                "runs": {
                    "run-1": {
                        "admission": {
                            "admission_sha256": "a" * 64,
                            "reservation_id": "reservation:run-1",
                            "absolute_deadline_utc": "2099-01-01T00:00:00Z",
                        },
                        "spec": {"setup_key": "provider:setup"},
                    }
                }
            }
            resume = {"actions": [{"action": "reconcile_provider_intent", "run_id": "run-1"}]}
            saved = {"workers": {}}
            status = supervisor._manage_provider_job(resume, lease, saved)
            self.assertEqual(status["status"], "provider_started")
            self.assertEqual(calls[0][0], ["python3", "run-1", "a" * 64, str(config.campaign_dir / "allocations" / "run-1")])
            self.assertEqual(saved["provider_job"]["status"], "running")
            observed = supervisor._manage_provider_job(resume, lease, saved)
            self.assertEqual(observed["status"], "provider_running")
            self.assertTrue((supervisor.runtime_dir / "provider" / "run-1.stdout.log").exists())
        finally:
            supervisor.close()

    def test_observe_mode_does_not_acquire_lease(self):
        supervisor = ResearchSupervisor(self.config)
        try:
            status = supervisor.cycle()
            self.assertEqual(status["status"], "observing")
            self.assertEqual(supervisor.lab.snapshot()["leases"], [])
            self.assertTrue((supervisor.runtime_dir / "STATUS.md").exists())
        finally:
            supervisor.close()

    def test_active_mode_waits_for_foreign_lease(self):
        config = SupervisorConfig(**{**self.config.__dict__, "mode": "active"})
        lab = LabDatabase(config.root / "lab.sqlite3")
        lab.acquire_coordinator(config.program_id, "other-owner", ttl_seconds=60, now=time.time())
        lab.close()
        supervisor = ResearchSupervisor(config, runner=FakeRunner())
        try:
            status = supervisor.cycle()
            self.assertEqual(status["status"], "waiting_for_lease")
            self.assertEqual(supervisor.runner.calls, [])
        finally:
            supervisor.close()

    def test_active_cycle_persists_thread_and_turn_metrics(self):
        config = SupervisorConfig(**{**self.config.__dict__, "mode": "active"})
        runner = FakeRunner()
        supervisor = ResearchSupervisor(config, runner=runner)
        try:
            status = supervisor.cycle()
            saved = json.loads(supervisor.state_path.read_text())
            self.assertEqual(saved["thread_id"], "thread-1")
            self.assertEqual(saved["cycle_count"], 1)
            self.assertEqual(status["last_turn"]["duration_seconds"], 1.0)
            self.assertIn("Run exactly one bounded research-director decision cycle", runner.calls[0][0])
        finally:
            supervisor.close()


if __name__ == "__main__":
    unittest.main()
