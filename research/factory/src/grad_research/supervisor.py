from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Sequence

from .director import ResearchDirector
from .labd import LabDatabase, LeaseBusy
from .operations import resume_program
from .util import require_id, utc_now


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


@dataclass(frozen=True)
class ModelRoute:
    model: str
    reasoning_effort: str


@dataclass(frozen=True)
class SupervisorConfig:
    root: Path
    program_id: str
    repo_dir: Path
    campaign_dir: Path
    owner: str
    mode: str = "observe"
    cycle_interval_seconds: int = 60
    idle_backoff_seconds: int = 300
    coordinator_ttl_seconds: int = 900
    director_timeout_seconds: int = 900
    turn_timeout_seconds: int = 3600
    max_parallel_workers: int = 2
    max_worker_attempts: int = 2
    reuse_director_thread: bool = False
    provider_launcher: tuple[str, ...] = ()
    director: ModelRoute = ModelRoute("gpt-5.6-sol", "high")
    implementation: ModelRoute = ModelRoute("gpt-5.6-terra", "medium")
    mechanical: ModelRoute = ModelRoute("gpt-5.6-luna", "medium")

    @classmethod
    def load(cls, path: Path) -> "SupervisorConfig":
        raw = json.loads(path.read_text())
        routes = raw.get("routes", {})

        def route(name: str, default: ModelRoute) -> ModelRoute:
            value = routes.get(name, {})
            return ModelRoute(value.get("model", default.model), value.get("reasoning_effort", default.reasoning_effort))

        config = cls(
            root=Path(raw["root"]).expanduser().resolve(),
            program_id=require_id("program_id", raw["program_id"]),
            repo_dir=Path(raw["repo_dir"]).expanduser().resolve(),
            campaign_dir=Path(raw["campaign_dir"]).expanduser().resolve(),
            owner=require_id("owner", raw.get("owner", f"supervisor-{raw['program_id']}")),
            mode=raw.get("mode", "observe"),
            cycle_interval_seconds=int(raw.get("cycle_interval_seconds", 60)),
            idle_backoff_seconds=int(raw.get("idle_backoff_seconds", 300)),
            coordinator_ttl_seconds=int(raw.get("coordinator_ttl_seconds", 900)),
            director_timeout_seconds=int(raw.get("director_timeout_seconds", 900)),
            turn_timeout_seconds=int(raw.get("turn_timeout_seconds", 3600)),
            max_parallel_workers=int(raw.get("max_parallel_workers", 2)),
            max_worker_attempts=int(raw.get("max_worker_attempts", 2)),
            reuse_director_thread=bool(raw.get("reuse_director_thread", False)),
            provider_launcher=tuple(str(value) for value in raw.get("provider_launcher", [])),
            director=route("director", cls.director),
            implementation=route("implementation", cls.implementation),
            mechanical=route("mechanical", cls.mechanical),
        )
        if config.mode not in {"observe", "active"}:
            raise ValueError("mode must be observe or active")
        for name in (
            "cycle_interval_seconds",
            "idle_backoff_seconds",
            "coordinator_ttl_seconds",
            "director_timeout_seconds",
            "turn_timeout_seconds",
            "max_parallel_workers",
            "max_worker_attempts",
        ):
            if getattr(config, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if not config.repo_dir.is_dir() or not config.campaign_dir.is_dir():
            raise ValueError("repo_dir and campaign_dir must exist")
        return config

    def route(self, task_kind: str) -> ModelRoute:
        if task_kind in {"scientific_gate", "recovery", "director"}:
            return self.director
        if task_kind == "implementation":
            return self.implementation
        if task_kind == "mechanical":
            return self.mechanical
        raise ValueError(f"unknown task kind: {task_kind}")


class CodexRunner:
    def __init__(self, config: SupervisorConfig, runtime_dir: Path, *, popen: Callable[..., Any] = subprocess.Popen):
        self.config = config
        self.runtime_dir = runtime_dir
        self.popen = popen

    def _command(self, prompt: str, thread_id: str | None, route: ModelRoute) -> list[str]:
        common = [
            "--model", route.model,
            "-c", f'model_reasoning_effort="{route.reasoning_effort}"',
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
        ]
        if thread_id:
            return ["codex", "exec", "resume", *common, thread_id, prompt]
        return ["codex", "exec", *common, "-C", str(self.config.repo_dir), prompt]

    def run(
        self,
        prompt: str,
        *,
        thread_id: str | None,
        task_kind: str,
        heartbeat: Callable[[], None],
        timeout_seconds: int | None = None,
        trace_label: str = "director",
    ) -> dict[str, Any]:
        route = self.config.route(task_kind)
        started = time.time()
        stamp = datetime.fromtimestamp(started, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_label = "".join(character if character.isalnum() or character in "-_" else "_" for character in trace_label)
        stdout_path = self.runtime_dir / "codex" / f"{stamp}-{time.time_ns()}-{safe_label}.jsonl"
        stderr_path = self.runtime_dir / "codex" / f"{stamp}-{time.time_ns()}-{safe_label}.stderr.log"
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        command = self._command(prompt, thread_id, route)
        with stderr_path.open("w") as stderr:
            process = self.popen(
                command,
                cwd=self.config.repo_dir,
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            next_heartbeat = time.monotonic()
            timed_out = False
            discovered_thread = thread_id
            event_count = 0
            with stdout_path.open("w") as output:
                while process.poll() is None:
                    now = time.monotonic()
                    if now >= next_heartbeat:
                        heartbeat()
                        next_heartbeat = now + max(5, self.config.coordinator_ttl_seconds // 3)
                    limit = timeout_seconds or self.config.turn_timeout_seconds
                    if time.time() - started >= limit:
                        timed_out = True
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                        break
                    for key, _ in selector.select(timeout=1):
                        line = key.fileobj.readline()
                        if not line:
                            continue
                        output.write(line)
                        output.flush()
                        event_count += 1
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if event.get("type") == "thread.started":
                            discovered_thread = event.get("thread_id") or event.get("thread", {}).get("id") or discovered_thread
                for line in process.stdout:
                    output.write(line)
                    event_count += 1
        ended = time.time()
        return {
            "model": route.model,
            "reasoning_effort": route.reasoning_effort,
            "task_kind": task_kind,
            "thread_id": discovered_thread,
            "pid": process.pid,
            "returncode": process.returncode,
            "timed_out": timed_out,
            "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat().replace("+00:00", "Z"),
            "ended_at": datetime.fromtimestamp(ended, timezone.utc).isoformat().replace("+00:00", "Z"),
            "duration_seconds": round(ended - started, 3),
            "event_count": event_count,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "timeout_seconds": timeout_seconds or self.config.turn_timeout_seconds,
        }


class ResearchSupervisor:
    def __init__(
        self,
        config: SupervisorConfig,
        *,
        runner: CodexRunner | None = None,
        provider_popen: Callable[..., Any] = subprocess.Popen,
    ):
        self.config = config
        self.runtime_dir = config.root / "supervisor" / config.program_id
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.lab = LabDatabase(config.root / "lab.sqlite3")
        self.director = ResearchDirector(config.root, config.program_id)
        self.runner = runner or CodexRunner(config, self.runtime_dir)
        self.state_path = self.runtime_dir / "STATE.json"
        self.status_path = self.runtime_dir / "STATUS.json"
        self.events_path = self.runtime_dir / "events.jsonl"
        self._lock_handle: Any = None
        self._provider_processes: dict[str, Any] = {}
        self._provider_popen = provider_popen

    def close(self) -> None:
        self.lab.close()
        if self._lock_handle is not None:
            self._lock_handle.close()

    def acquire_process_lock(self) -> None:
        self._lock_handle = (self.runtime_dir / "supervisor.lock").open("w")
        try:
            fcntl.flock(self._lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"supervisor already running for {self.config.program_id}") from error
        self._lock_handle.write(str(os.getpid()))
        self._lock_handle.flush()

    def _saved_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"schema_version": 1, "thread_id": None, "cycle_count": 0, "no_progress_cycles": 0}
        return json.loads(self.state_path.read_text())

    def _write_status(self, status: dict[str, Any]) -> None:
        _atomic_json(self.status_path, status)
        lines = [
            f"# Research supervisor: {self.config.program_id}", "",
            f"- Updated: `{status['updated_at']}`",
            f"- Mode/status: `{status['mode']}` / `{status['status']}`",
            f"- Owner: `{self.config.owner}`",
            f"- Codex route: `{status.get('model', 'none')}` ({status.get('reasoning_effort', 'n/a')})",
            f"- Codex thread: `{status.get('thread_id') or 'not started'}`",
            f"- Event head: `{status.get('event_head_sha256') or 'none'}`",
            f"- Next action: {status.get('next_action') or 'none'}",
        ]
        provider_job = status.get("provider_job")
        if provider_job:
            lines.extend([
                "",
                "## Provider job",
                "",
                f"- Status: `{provider_job.get('status')}`; run `{provider_job.get('run_id')}`",
                f"- PID: `{provider_job.get('pid') or 'not started'}`",
                f"- Started: `{provider_job.get('started_at')}`",
                f"- Logs: `{provider_job.get('stdout_path')}` / `{provider_job.get('stderr_path')}`",
            ])
        if status.get("blocked_reason"):
            lines.append(f"- Blocked/waiting: {status['blocked_reason']}")
        if status.get("lease"):
            lease = status["lease"]
            lines.append(f"- Lease: `{lease.get('owner')}` epoch `{lease.get('epoch')}`, expires `{lease.get('expires_at')}`")
        if status.get("last_turn"):
            turn = status["last_turn"]
            lines.extend(["", "## Last Codex turn", "", f"- Result: return code `{turn['returncode']}`, timeout `{turn['timed_out']}`", f"- Duration/events: `{turn['duration_seconds']}s` / `{turn['event_count']}`", f"- Trace: `{turn['stdout_path']}`"])
        (self.runtime_dir / "STATUS.md").write_text("\n".join(lines) + "\n")

    def _base_status(self, state: dict[str, Any]) -> dict[str, Any]:
        projection = self.director.state()
        snapshot = self.lab.snapshot()
        lease = next((row for row in snapshot["leases"] if row["program_id"] == self.config.program_id), None)
        return {
            "schema_version": 1,
            "updated_at": utc_now(),
            "mode": self.config.mode,
            "status": "observing",
            "program_id": self.config.program_id,
            "owner": self.config.owner,
            "model": self.config.director.model,
            "reasoning_effort": self.config.director.reasoning_effort,
            "thread_id": state.get("thread_id"),
            "cycle_count": state.get("cycle_count", 0),
            "event_head_sha256": projection.get("event_head_sha256"),
            "next_action": projection.get("next_action"),
            "residual_bottleneck": projection.get("residual_bottleneck"),
            "lease": lease,
            "last_turn": state.get("last_turn"),
            "routes": {
                name: vars(self.config.route(name))
                for name in ("scientific_gate", "implementation", "mechanical")
            },
            "workers": state.get("workers", {}),
            "provider_job": state.get("provider_job"),
        }

    def _prompt(self, resume: dict[str, Any]) -> str:
        return f"""Run exactly one bounded research-director decision cycle for `{self.config.program_id}`. Finish within 10 minutes.

You are the scientific director. Work autonomously from durable repository and lab state, not chat memory. Start by reading:
- {resume['resume_path']}
- {resume['work_queue_path']}
- {self.director.store.program_dir / 'COORDINATOR.md'}
- {self.config.campaign_dir / 'CAMPAIGN_STATUS.json'}
- {self.runtime_dir / 'STATUS.json'} and any completed files below {self.runtime_dir / 'workers'}
- research/sol/AGENTS.md and the nearest campaign handoff/report.

Coordinator owner is `{self.config.owner}`. Re-run `grad_research resume` with this exact owner before any fenced mutation. Resolve P0 recovery and provider reconciliation before new work. Never create provider resources while `safe_to_start_new_provider_mutation` is false. Preserve the existing budget and every paid-run deadline; do not grant new budget authority. The deterministic supervisor owns provider-controller execution through its configured durable launcher; never launch or poll a long-running provider controller from this Codex turn. If a provider intent is admitted, leave it for the supervisor and stop after recording the state transition.

Make one material state transition: reconcile interrupted work, record a cheap offline falsifier, prepare one bounded worker packet, or make one scientific admission/stop decision. Attack the measured bottleneck. Do not spawn Codex subagents, use collaboration tools, or ask another agent to review your work; the local supervisor performs that delegation after you exit. Do not poll a long-running provider command or repeatedly inspect the same log. Do not launch a new paid provider process from this turn unless the durable factory contract requires an immediate fenced mutation; if it does, launch exactly one bounded command and stop, leaving the supervisor to observe the lifecycle on the next cycle. Prefer a cheap falsifier and leave explicit `parallel_offline` packets for routine analysis, fixture generation, packaging, and deterministic tests. Keep provider/setup-affine mutations serialized. Reserve your high reasoning for hypotheses, admission, interpretation, and stop/promotion decisions.

Every scored arm must retain identities, exact raw request/event data, quality/correctness, cost, low-overhead host/GPU telemetry, logs, and a hashed manifest. Deep profiling is diagnostic and observer-bracketed. Operational failures must not update scientific beliefs. Do not spend a turn merely narrating status: either advance durable state or record a concrete blocker/recovery artifact. Finish after one material transition so the supervisor can measure and reschedule the next cycle.
"""

    @staticmethod
    def _task_kind(resume: dict[str, Any]) -> str:
        actions = resume.get("actions", [])
        if any(action.get("priority") == "P0" for action in actions):
            return "recovery"
        packets = resume.get("work_packets", [])
        declared = {packet.get("task_kind") for packet in packets if packet.get("task_kind")}
        if len(declared) == 1 and declared <= {"implementation", "mechanical"}:
            return declared.pop()
        if packets and all(packet.get("lane") == "parallel_offline" and packet.get("command") for packet in packets):
            return "mechanical"
        return "scientific_gate"

    @staticmethod
    def _worker_task_kind(packet: dict[str, Any]) -> str:
        declared = packet.get("task_kind")
        if declared in {"implementation", "mechanical"}:
            return declared
        # A packet with an exact local command is mechanical execution. Packets
        # without commands are bounded analysis/preparation and use the same
        # fast route; the director remains responsible for scientific validity.
        return "mechanical"

    def _worker_prompt(self, packet: dict[str, Any], output_dir: Path) -> str:
        command = packet.get("command") or "No command is registered; perform only bounded local analysis or preparation."
        return f"""You are a bounded research-factory worker for packet `{packet['packet_id']}`.

The Sol/high director owns scientific judgment. You are routed here only for `{self._worker_task_kind(packet)}` work. Work on this packet alone and leave all other packets untouched. Use the durable repository and lab state as context, but do not make scientific promotion, stop, or budget decisions.

Packet contract:
- mechanism: {packet.get('mechanism', 'n/a')}
- changed variable: {packet.get('changed_variable', 'n/a')}
- falsifier: {packet.get('falsifier', 'n/a')}
- fidelity: {packet.get('fidelity', 'n/a')}
- timeout seconds: {packet.get('timeout_seconds', self.config.turn_timeout_seconds)}
- exact registered command, if any: {command}

Write all worker-specific logs and intermediate outputs below `{output_dir}`. Do not mutate provider resources, change budgets, or bypass factory admission/cleanup. If a command is present, execute that exact command with its declared bounds; do not invent a more expensive replacement. If the packet is preparation/analysis, produce a reproducible artifact and a concise result note. A worker result is not scientific evidence until the Sol director validates and records it through the factory event/artifact contracts.

Return a concise structured summary including status, files written, command exit status, and any blocker. Do not spend time narrating the broader campaign.
"""

    def _worker_heartbeat(self, lease: dict[str, Any]) -> None:
        # Codex workers run in threads, while LabDatabase's default connection
        # is deliberately single-threaded. Use a short-lived fenced connection
        # per heartbeat instead of weakening the SQLite thread-safety boundary.
        lab = LabDatabase(self.config.root / "lab.sqlite3")
        try:
            lab.heartbeat_coordinator(
                self.config.program_id,
                self.config.owner,
                lease["epoch"],
                ttl_seconds=self.config.coordinator_ttl_seconds,
                now=time.time(),
            )
        finally:
            lab.close()

    @staticmethod
    def _provider_action(resume: dict[str, Any]) -> dict[str, Any] | None:
        return next(
            (
                action
                for action in resume.get("actions", [])
                if action.get("action") == "reconcile_provider_intent"
            ),
            None,
        )

    def _provider_command(self, action: dict[str, Any], lease: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        if not self.config.provider_launcher:
            raise RuntimeError("provider intent requires configured provider_launcher")
        run_id = action["run_id"]
        state = self.director.state()
        run = state.get("runs", {}).get(run_id)
        if not run:
            raise RuntimeError(f"admitted provider run is missing from durable state: {run_id}")
        admission = run.get("admission") or {}
        spec = run.get("spec") or {}
        context = {
            "root": str(self.config.root),
            "repo_dir": str(self.config.repo_dir),
            "campaign_dir": str(self.config.campaign_dir),
            "run_id": run_id,
            "admission_sha256": admission.get("admission_sha256", ""),
            "reservation_id": admission.get("reservation_id", f"reservation:{run_id}"),
            "allocation_id": f"allocation:{run_id}",
            "absolute_deadline_utc": admission.get("absolute_deadline_utc", ""),
            "owner": self.config.owner,
            "lease_epoch": str(lease["epoch"]),
            "setup_key": spec.get("setup_key", ""),
            "output_dir": str(self.config.campaign_dir / "allocations" / run_id),
        }
        try:
            command = [part.format(**context) for part in self.config.provider_launcher]
        except KeyError as error:
            raise RuntimeError(f"provider_launcher uses unknown placeholder: {error.args[0]}") from error
        return command, context

    @staticmethod
    def _pid_alive(pid: int | None) -> bool:
        if not pid:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _provider_status(
        self,
        saved: dict[str, Any],
        lease: dict[str, Any],
        *,
        status_name: str,
        blocked_reason: str | None = None,
    ) -> dict[str, Any]:
        status = self._base_status(saved)
        status.update({
            "status": status_name,
            "blocked_reason": blocked_reason,
            "lease": lease,
            "provider_job": saved.get("provider_job"),
            "active_cycle": None,
            "active_worker_count": 0,
        })
        self._write_status(status)
        return status

    def _manage_provider_job(
        self,
        resume: dict[str, Any],
        lease: dict[str, Any],
        saved: dict[str, Any],
    ) -> dict[str, Any] | None:
        job = saved.get("provider_job")
        if job and job.get("status") == "running":
            process = self._provider_processes.get(job.get("run_id"))
            returncode = process.poll() if process is not None else None
            alive = returncode is None and self._pid_alive(job.get("pid"))
            if alive:
                self.lab.heartbeat_coordinator(
                    self.config.program_id,
                    self.config.owner,
                    lease["epoch"],
                    ttl_seconds=self.config.coordinator_ttl_seconds,
                    now=time.time(),
                )
                return self._provider_status(saved, lease, status_name="provider_running")
            job.update({
                "status": "exited",
                "returncode": returncode if returncode is not None else "unknown",
                "ended_at": utc_now(),
            })
            _atomic_json(self.state_path, saved)
            _append_jsonl(self.events_path, {
                "event": "provider_job_exited",
                "run_id": job.get("run_id"),
                "pid": job.get("pid"),
                "returncode": job.get("returncode"),
                "timestamp": utc_now(),
            })
            return self._provider_status(
                saved,
                lease,
                status_name="provider_exited",
                blocked_reason="provider controller exited; waiting for factory reconciliation",
            )

        action = self._provider_action(resume)
        if not action or (job and job.get("status") in {"exited", "failed"}):
            return None
        command, context = self._provider_command(action, lease)
        run_id = context["run_id"]
        provider_dir = self.runtime_dir / "provider"
        provider_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = provider_dir / f"{run_id}.stdout.log"
        stderr_path = provider_dir / f"{run_id}.stderr.log"
        job = {
            "status": "starting",
            "run_id": run_id,
            "reservation_id": context["reservation_id"],
            "allocation_id": context["allocation_id"],
            "started_at": utc_now(),
            "command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "deadline": context["absolute_deadline_utc"],
        }
        saved["provider_job"] = job
        _atomic_json(self.state_path, saved)
        try:
            with stdout_path.open("w") as stdout, stderr_path.open("w") as stderr:
                process = self._provider_popen(
                    command,
                    cwd=self.config.repo_dir,
                    stdout=stdout,
                    stderr=stderr,
                    text=True,
                    start_new_session=True,
                )
            job.update({"status": "running", "pid": process.pid})
            self._provider_processes[run_id] = process
            saved["provider_job"] = job
            _atomic_json(self.state_path, saved)
            _append_jsonl(self.events_path, {
                "event": "provider_job_started",
                "run_id": run_id,
                "pid": process.pid,
                "command_sha256": job["command_sha256"],
                "timestamp": utc_now(),
            })
            return self._provider_status(saved, lease, status_name="provider_started")
        except Exception as error:
            job.update({"status": "failed", "error": f"{type(error).__name__}: {error}", "ended_at": utc_now()})
            saved["provider_job"] = job
            _atomic_json(self.state_path, saved)
            _append_jsonl(self.events_path, {
                "event": "provider_job_failed",
                "run_id": run_id,
                "error": job["error"],
                "timestamp": utc_now(),
            })
            return self._provider_status(saved, lease, status_name="provider_launch_failed", blocked_reason=job["error"])

    def _dispatch_workers(
        self,
        resume: dict[str, Any],
        lease: dict[str, Any],
        saved: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if any(action.get("priority") == "P0" for action in resume.get("actions", [])):
            return []
        workers = saved.setdefault("workers", {})
        packets = [
            packet
            for packet in resume.get("work_packets", [])
            if packet.get("lane") == "parallel_offline"
            and workers.get(packet["packet_id"], {}).get("status") != "succeeded"
            and workers.get(packet["packet_id"], {}).get("attempts", 0) < self.config.max_worker_attempts
        ]
        packets = packets[: self.config.max_parallel_workers]
        if not packets:
            return []

        # Project the worker hand-off before starting Codex.  Previously the
        # durable status file remained `running_director` until every worker
        # completed, which made a healthy mechanical hand-off look like a
        # stalled Sol turn and hid the actual active work from operators.
        for packet in packets:
            packet_id = packet["packet_id"]
            record = workers.get(packet_id, {})
            record.update({
                "status": "running",
                "attempts": record.get("attempts", 0) + 1,
                "started_at": utc_now(),
            })
            workers[packet_id] = record
            _atomic_json(self.runtime_dir / "workers" / f"{packet_id.replace(':', '-')}.json", record)
        status = self._base_status(saved)
        status.update({
            "status": "dispatching_workers",
            "lease": lease,
            "workers": workers,
            "active_worker_count": len(packets),
        })
        self._write_status(status)

        def run_packet(packet: dict[str, Any]) -> dict[str, Any]:
            packet_id = packet["packet_id"]
            worker_dir = self.runtime_dir / "workers" / packet_id.replace(":", "-")
            worker_dir.mkdir(parents=True, exist_ok=True)
            record = workers.get(packet_id, {})
            try:
                result = self.runner.run(
                    self._worker_prompt(packet, worker_dir),
                    thread_id=record.get("thread_id"),
                    task_kind=self._worker_task_kind(packet),
                    heartbeat=lambda: self._worker_heartbeat(lease),
                    timeout_seconds=min(int(packet.get("timeout_seconds", self.config.turn_timeout_seconds)), self.config.turn_timeout_seconds),
                    trace_label=f"worker-{packet_id}",
                )
                result.update({"packet_id": packet_id, "output_dir": str(worker_dir)})
                result["status"] = "succeeded" if result.get("returncode") == 0 and not result.get("timed_out") else "failed"
                result["finished_at"] = utc_now()
                _atomic_json(worker_dir / "RESULT.json", result)
                return result
            except Exception as error:
                result = {"packet_id": packet_id, "status": "failed", "error": f"{type(error).__name__}: {error}", "finished_at": utc_now()}
                _atomic_json(worker_dir / "RESULT.json", result)
                return result

        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=len(packets), thread_name_prefix="research-worker") as executor:
            futures = [executor.submit(run_packet, packet) for packet in packets]
            for future in as_completed(futures):
                result = future.result()
                packet_id = result["packet_id"]
                current = workers.setdefault(packet_id, {})
                current.update(result)
                _atomic_json(self.runtime_dir / "workers" / f"{packet_id.replace(':', '-')}.json", current)
                status = self._base_status(saved)
                status.update({
                    "status": "dispatching_workers" if any(
                        item.get("status") == "running" for item in workers.values()
                    ) else "workers_complete",
                    "lease": lease,
                    "workers": workers,
                    "active_worker_count": sum(
                        item.get("status") == "running" for item in workers.values()
                    ),
                })
                self._write_status(status)
                results.append(result)
        return sorted(results, key=lambda result: result["packet_id"])

    def cycle(self) -> dict[str, Any]:
        saved = self._saved_state()
        status = self._base_status(saved)
        if self.config.mode == "observe":
            self._write_status(status)
            _append_jsonl(self.events_path, {"event": "observe", **status})
            return status
        try:
            resume = resume_program(
                self.director,
                self.lab,
                owner=self.config.owner,
                ttl_seconds=self.config.coordinator_ttl_seconds,
                now=datetime.now(timezone.utc),
                deep_artifact_audit=False,
            )
        except LeaseBusy as error:
            status.update({"status": "waiting_for_lease", "blocked_reason": str(error)})
            self._write_status(status)
            _append_jsonl(self.events_path, {"event": "lease_busy", **status})
            return status
        lease = resume["lease"]
        before_head = resume["event_head_sha256"]

        # Provider controllers are first-class supervisor jobs. They must not
        # be launched inside a Codex exec session: that session can end while
        # its child tool call remains unobservable to the 24/7 loop.
        provider_status = self._manage_provider_job(resume, lease, saved)
        if provider_status is not None:
            _append_jsonl(self.events_path, {"event": "provider_job_observed", **provider_status})
            return provider_status

        status.update({"status": "running_director", "blocked_reason": None, "lease": lease})
        status["active_cycle"] = {
            "stage": "director",
            "started_at": utc_now(),
            "task_kind": self._task_kind(resume),
            "timeout_seconds": self.config.director_timeout_seconds,
        }
        self._write_status(status)
        _append_jsonl(self.events_path, {"event": "cycle_started", "task_kind": self._task_kind(resume), **status})

        def heartbeat() -> None:
            self.lab.heartbeat_coordinator(
                self.config.program_id,
                self.config.owner,
                lease["epoch"],
                ttl_seconds=self.config.coordinator_ttl_seconds,
                now=time.time(),
            )

        turn = self.runner.run(
            self._prompt(resume),
            thread_id=saved.get("thread_id") if self.config.reuse_director_thread else None,
            task_kind=self._task_kind(resume),
            heartbeat=heartbeat,
            timeout_seconds=self.config.director_timeout_seconds,
            trace_label="director",
        )
        # The director may have registered or refreshed offline packets. Read
        # the queue again before dispatching; never dispatch a stale portfolio.
        refreshed = resume_program(
            self.director,
            self.lab,
            owner=self.config.owner,
            ttl_seconds=self.config.coordinator_ttl_seconds,
            now=datetime.now(timezone.utc),
            deep_artifact_audit=False,
        )
        worker_results = self._dispatch_workers(refreshed, lease, saved)
        after = self.director.state()
        progressed = after.get("event_head_sha256") != before_head
        saved.update(
            {
                "schema_version": 1,
                "thread_id": turn.get("thread_id") or saved.get("thread_id"),
                "cycle_count": saved.get("cycle_count", 0) + 1,
                "no_progress_cycles": 0 if progressed else saved.get("no_progress_cycles", 0) + 1,
                "last_turn": turn,
                "last_workers": worker_results,
                "last_event_head_sha256": after.get("event_head_sha256"),
                "updated_at": utc_now(),
            }
        )
        _atomic_json(self.state_path, saved)
        status = self._base_status(saved)
        status.update({
            "status": "progressed" if progressed else "idle_no_event_progress",
            "last_turn": turn,
            "last_workers": worker_results,
            "active_cycle": None,
            "active_worker_count": 0,
        })
        self._write_status(status)
        _append_jsonl(self.events_path, {"event": "cycle_completed", "progressed": progressed, **status})
        return status

    def run_forever(self, *, once: bool = False) -> None:
        self.acquire_process_lock()
        while True:
            try:
                status = self.cycle()
            except Exception as error:
                status = self._base_status(self._saved_state())
                status.update({"status": "error", "blocked_reason": f"{type(error).__name__}: {error}"})
                self._write_status(status)
                _append_jsonl(self.events_path, {"event": "cycle_error", **status})
            if once:
                return
            delay = self.config.idle_backoff_seconds if status["status"] in {"idle_no_event_progress", "error"} else self.config.cycle_interval_seconds
            time.sleep(delay)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persistent subscription-authenticated research supervisor")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    config = SupervisorConfig.load(args.config)
    supervisor = ResearchSupervisor(config)
    try:
        supervisor.run_forever(once=args.once)
    finally:
        supervisor.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
