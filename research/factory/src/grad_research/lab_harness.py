from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import selectors
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from .gpu_pool import GpuPool


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def trace_reports_response_capacity_exhausted(path: Path) -> bool:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return False
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str) and "remaining response capacity" in text.lower():
            return True
    return False


def codex_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    environment.pop("AZURE_OPENAI_API_KEY", None)
    codex_path = Path("/root/.codex/packages/standalone/current/codex-path")
    if codex_path.is_dir():
        environment["PATH"] = f"{codex_path}:{environment.get('PATH', '')}"
    return environment


@dataclass(frozen=True)
class ModelRoute:
    model: str
    reasoning_effort: str


@dataclass(frozen=True)
class LabConfig:
    repo_dir: Path
    lab_dir: Path
    cycle_interval_seconds: int = 60
    max_parallel_researchers: int = 5
    spend_cap_usd: float | None = None
    spend_cap_starts_at: str | None = None
    supervisor_every_cycles: int = 6
    director_timeout_seconds: int = 900
    researcher_timeout_seconds: int = 2700
    supervisor_timeout_seconds: int = 900
    director: ModelRoute = ModelRoute("gpt-5.6-sol", "high")
    researcher: ModelRoute = ModelRoute("gpt-5.6-terra", "medium")
    researcher_routes: tuple[ModelRoute, ...] = ()
    deep_researcher: ModelRoute = ModelRoute("gpt-5.6-sol", "high")
    supervisor: ModelRoute = ModelRoute("gpt-5.6-sol", "high")
    tools: tuple[Path, ...] = ()

    @classmethod
    def load(cls, path: Path) -> "LabConfig":
        raw = json.loads(path.read_text())
        routes = raw.get("routes", {})

        def route(name: str, default: ModelRoute) -> ModelRoute:
            value = routes.get(name, {})
            return ModelRoute(
                str(value.get("model", default.model)),
                str(value.get("reasoning_effort", default.reasoning_effort)),
            )

        researcher_routes = tuple(
            ModelRoute(
                str(value["model"]),
                str(value.get("reasoning_effort", cls.researcher.reasoning_effort)),
            )
            for value in routes.get("researchers", [])
        )

        config = cls(
            repo_dir=Path(raw["repo_dir"]).expanduser().resolve(),
            lab_dir=Path(raw["lab_dir"]).expanduser().resolve(),
            cycle_interval_seconds=int(raw.get("cycle_interval_seconds", 60)),
            max_parallel_researchers=int(raw.get("max_parallel_researchers", 5)),
            spend_cap_usd=(
                float(raw["spend_cap_usd"])
                if raw.get("spend_cap_usd") is not None
                else None
            ),
            spend_cap_starts_at=raw.get("spend_cap_starts_at"),
            supervisor_every_cycles=int(raw.get("supervisor_every_cycles", 6)),
            director_timeout_seconds=int(raw.get("director_timeout_seconds", 900)),
            researcher_timeout_seconds=int(raw.get("researcher_timeout_seconds", 2700)),
            supervisor_timeout_seconds=int(raw.get("supervisor_timeout_seconds", 900)),
            director=route("director", cls.director),
            researcher=route("researcher", cls.researcher),
            researcher_routes=researcher_routes,
            deep_researcher=route("deep_researcher", cls.deep_researcher),
            supervisor=route("supervisor", cls.supervisor),
            tools=tuple(Path(value).expanduser().resolve() for value in raw.get("tools", [])),
        )
        if not config.repo_dir.is_dir():
            raise ValueError("repo_dir must exist")
        if not config.lab_dir.is_dir() or not (config.lab_dir / "CAMPAIGN.md").is_file():
            raise ValueError("lab_dir must exist and contain CAMPAIGN.md")
        for name in (
            "cycle_interval_seconds",
            "max_parallel_researchers",
            "supervisor_every_cycles",
            "director_timeout_seconds",
            "researcher_timeout_seconds",
            "supervisor_timeout_seconds",
        ):
            if getattr(config, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if (config.spend_cap_usd is None) != (config.spend_cap_starts_at is None):
            raise ValueError("spend_cap_usd and spend_cap_starts_at must be set together")
        if config.spend_cap_usd is not None:
            if config.spend_cap_usd <= 0:
                raise ValueError("spend_cap_usd must be positive")
            try:
                datetime.fromisoformat(config.spend_cap_starts_at.replace("Z", "+00:00"))
            except (AttributeError, ValueError) as error:
                raise ValueError("spend_cap_starts_at must be RFC3339") from error
        return config


class CodexAgentRunner:
    def __init__(
        self,
        repo_dir: Path,
        trace_dir: Path,
        *,
        popen: Callable[..., Any] = subprocess.Popen,
    ):
        self.repo_dir = repo_dir
        self.trace_dir = trace_dir
        self.popen = popen

    def _command(
        self, prompt: str, route: ModelRoute, thread_id: str | None
    ) -> list[str]:
        options = [
            "--model",
            route.model,
            "-c",
            f'model_reasoning_effort="{route.reasoning_effort}"',
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
        ]
        if thread_id:
            return ["codex", "exec", "resume", *options, thread_id, prompt]
        return ["codex", "exec", *options, "-C", str(self.repo_dir), prompt]

    def run(
        self,
        prompt: str,
        *,
        role: str,
        route: ModelRoute,
        thread_id: str | None,
        timeout_seconds: int,
        label: str,
    ) -> dict[str, Any]:
        started = time.time()
        stamp = datetime.fromtimestamp(started, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_label = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in label
        )
        prefix = f"{stamp}-{time.time_ns()}-{role}-{safe_label}"
        stdout_path = self.trace_dir / f"{prefix}.jsonl"
        stderr_path = self.trace_dir / f"{prefix}.stderr.log"
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        command = self._command(prompt, route, thread_id)
        with stderr_path.open("w") as stderr:
            process = self.popen(
                command,
                cwd=self.repo_dir,
                env=codex_environment(),
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            if process.stdout is None:
                raise RuntimeError("Codex stdout pipe is unavailable")
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            discovered_thread = thread_id
            timed_out = False
            event_count = 0
            with stdout_path.open("w") as output:
                while process.poll() is None:
                    if time.time() - started >= timeout_seconds:
                        timed_out = True
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=10)
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
                            discovered_thread = (
                                event.get("thread_id")
                                or event.get("thread", {}).get("id")
                                or discovered_thread
                            )
                for line in process.stdout:
                    output.write(line)
                    event_count += 1
        ended = time.time()
        return {
            "role": role,
            "label": label,
            "model": route.model,
            "reasoning_effort": route.reasoning_effort,
            "thread_id": discovered_thread,
            "returncode": process.returncode,
            "timed_out": timed_out,
            "started_at": datetime.fromtimestamp(started, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "ended_at": datetime.fromtimestamp(ended, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "duration_seconds": round(ended - started, 3),
            "event_count": event_count,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }


class LabHarness:
    def __init__(
        self,
        config: LabConfig,
        *,
        runner: Any | None = None,
        unit_is_active: Callable[[str, str], bool] | None = None,
    ):
        self.config = config
        self._source_path = Path(__file__).resolve()
        self._source_sha256 = self._source_digest(self._source_path)
        self._unit_is_active = unit_is_active or self._systemd_unit_is_active
        self.runtime_dir = config.lab_dir / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        (config.lab_dir / "projects").mkdir(exist_ok=True)
        self._ensure_log(config.lab_dir / "DIRECTOR_LOG.md", "# Director log\n")
        self._ensure_log(config.lab_dir / "SUPERVISOR_LOG.md", "# Research supervisor log\n")
        self.state_path = self.runtime_dir / "state.json"
        self.events_path = self.runtime_dir / "events.jsonl"
        self.spend_cap_path = self.runtime_dir / "spend_cap.json"
        self.status_json_path = self.runtime_dir / "status.json"
        self.status_markdown_path = config.lab_dir / "STATUS.md"
        self.gpu_pool = GpuPool(config.lab_dir)
        self.runner = runner or CodexAgentRunner(
            config.repo_dir, self.runtime_dir / "traces"
        )
        self._mutex = threading.Lock()
        self._lock_handle = (self.runtime_dir / "harness.lock").open("w")
        try:
            fcntl.flock(self._lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self._lock_handle.close()
            raise RuntimeError("another research-lab harness owns this lab") from error
        self.state = self._load_state()
        try:
            self._ensure_spend_cap()
        except Exception:
            self.close()
            raise
        self.render_status()

    @staticmethod
    def _ensure_log(path: Path, heading: str) -> None:
        if not path.exists():
            path.write_text(heading)

    @staticmethod
    def _source_digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _systemd_unit_is_active(unit: str, unit_manager: str = "user") -> bool:
        if unit_manager not in {"system", "user"}:
            return False
        try:
            result = subprocess.run(
                [
                    "systemctl",
                    f"--{unit_manager}",
                    "show",
                    unit,
                    "--property=ActiveState",
                    "--value",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0 and result.stdout.strip() in {
            "active",
            "activating",
            "reloading",
            "deactivating",
        }

    def _restart_if_source_changed(self) -> None:
        try:
            current_sha256 = self._source_digest(self._source_path)
        except OSError:
            current_sha256 = "unavailable"
        if current_sha256 == self._source_sha256:
            return
        self._record(
            "harness_reload_requested",
            previous_source_sha256=self._source_sha256,
            current_source_sha256=current_sha256,
        )
        self.close()
        raise SystemExit(75)

    def close(self) -> None:
        if not self._lock_handle.closed:
            fcntl.flock(self._lock_handle, fcntl.LOCK_UN)
            self._lock_handle.close()

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.is_file():
            state = json.loads(self.state_path.read_text())
            state.setdefault("project_routes", {})
            state.setdefault("director_observation_sha256", None)
            state.setdefault("development_observations", {})
            return state
        return {
            "schema_version": 1,
            "cycle_count": 0,
            "threads": {"director": None, "supervisor": None, "projects": {}},
            "project_routes": {},
            "director_observation_sha256": None,
            "development_observations": {},
            "active_agents": {},
            "last_runs": {},
            "updated_at": utc_now(),
        }

    def _save_state(self) -> None:
        self.state["updated_at"] = utc_now()
        atomic_json(self.state_path, self.state)

    def _record(self, event: str, **fields: Any) -> None:
        append_jsonl(
            self.events_path,
            {"schema_version": 1, "timestamp": utc_now(), "event": event, **fields},
        )

    @staticmethod
    def _usd_micros(value: float) -> int:
        return int(round(float(value) * 1_000_000))

    def _ensure_spend_cap(self) -> None:
        if self.config.spend_cap_usd is None:
            return
        expected = {
            "schema_version": 1,
            "starts_at": self.config.spend_cap_starts_at,
            "cap_usd": self.config.spend_cap_usd,
            "reservations": {},
        }
        if not self.spend_cap_path.is_file():
            atomic_json(self.spend_cap_path, expected)
            return
        current = json.loads(self.spend_cap_path.read_text())
        if (
            current.get("starts_at") != expected["starts_at"]
            or self._usd_micros(current.get("cap_usd", 0))
            != self._usd_micros(expected["cap_usd"])
        ):
            raise RuntimeError("spend cap cannot be reset or changed implicitly")
        if not isinstance(current.get("reservations"), dict):
            raise RuntimeError("spend cap reservations must be an object")

    def _spend_cap_snapshot(self) -> dict[str, Any] | None:
        if self.config.spend_cap_usd is None:
            return None
        value = json.loads(self.spend_cap_path.read_text())
        reserved_micros = sum(
            self._usd_micros(reservation["authorized_usd"])
            for reservation in value["reservations"].values()
        )
        cap_micros = self._usd_micros(value["cap_usd"])
        return {
            **value,
            "reserved_usd": reserved_micros / 1_000_000,
            "available_usd": (cap_micros - reserved_micros) / 1_000_000,
        }

    def _reserve_project_spend(self, row: dict[str, Any]) -> bool:
        requested = float(row.get("authorized_spend_usd", 0))
        if requested <= 0 or self.config.spend_cap_usd is None:
            return True
        value = json.loads(self.spend_cap_path.read_text())
        reservations = value["reservations"]
        previous = reservations.get(row["id"], {})
        previous_micros = self._usd_micros(previous.get("authorized_usd", 0))
        requested_micros = self._usd_micros(requested)
        if requested_micros <= previous_micros:
            return True
        committed_micros = sum(
            self._usd_micros(reservation["authorized_usd"])
            for reservation in reservations.values()
        )
        cap_micros = self._usd_micros(value["cap_usd"])
        if committed_micros + requested_micros - previous_micros > cap_micros:
            return False
        reservations[row["id"]] = {
            "authorized_usd": requested,
            "reserved_at": previous.get("reserved_at", utc_now()),
            "updated_at": utc_now(),
        }
        atomic_json(self.spend_cap_path, value)
        self._record(
            "spend_reserved",
            label=row["id"],
            authorized_spend_usd=requested,
            cap_usd=value["cap_usd"],
        )
        return True

    def _tools_text(self) -> str:
        paths = [str(path) for path in self.config.tools if path.exists()]
        return "\n".join(f"- {path}" for path in paths) or "- Use relevant repository tools."

    def _latest_log_section(self, filename: str, fallback: str) -> str:
        path = self.config.lab_dir / filename
        try:
            lines = path.read_text().splitlines()
        except OSError:
            return fallback
        starts = [index for index, line in enumerate(lines) if line.startswith("## ")]
        if not starts:
            return fallback
        return "\n".join(lines[starts[-1] :]).strip()

    def _latest_director_decision(self) -> str:
        return self._latest_log_section(
            "DIRECTOR_LOG.md", "No director decision is available."
        )

    def _latest_supervisor_handoff(self) -> str:
        return self._latest_log_section(
            "SUPERVISOR_LOG.md", "No supervisor handoff is available."
        )

    def _active_portfolio_context(self) -> str:
        rows = [
            {
                key: row[key]
                for key in (
                    "id",
                    "status",
                    "priority",
                    "summary",
                    "next_action",
                    "researcher_profile",
                    "authorized_spend_usd",
                    "active_session",
                )
            }
            for row in self._project_rows()
            if row["status"] in {"active", "ready"}
        ]
        return json.dumps(rows, indent=2, sort_keys=True)

    def _spend_cap_context(self) -> str:
        snapshot = self._spend_cap_snapshot()
        if snapshot is None:
            return "No harness-level spend cap is configured."
        return json.dumps(snapshot, indent=2, sort_keys=True)

    def _gpu_pool_context(self) -> str:
        return json.dumps(self.gpu_pool.snapshot(), indent=2, sort_keys=True)

    def _director_prompt(self) -> str:
        return f"""Use `$research-director` as the Sol research director for this lab.

Lab: {self.config.lab_dir}
Read `CAMPAIGN.md`. Use the compact active portfolio and latest handoffs below as orientation. Do not begin by reading generated `STATUS.md`, full logs, every project brief, or closed project directories. Inspect only the specific active project artifacts and historical evidence needed for this decision. Use your best judgment.

Current active portfolio:
{self._active_portfolio_context()}

Latest director decision:
{self._latest_director_decision()}

Latest supervisor handoff:
{self._latest_supervisor_handoff()}

Experiment spend cap from its fixed start timestamp:
{self._spend_cap_context()}

Shared GPU bench inventory:
{self._gpu_pool_context()}

Maximize decision-relevant research progress per wall-clock hour. Treat the campaign's economic target, workload, quality requirement, and latency tradeoffs as authoritative. Review the evidence, improve the portfolio, and delegate or update independent projects under `projects/`. Keep useful work parallel, redirect lines that are stuck, and keep the log to a short decision handoff. Do not execute the delegated projects yourself.

Make one decision from the current snapshot and return. Do not wait, sleep, poll, monitor active work, or spawn internal subagents. The harness owns scheduling and will invoke you again after material state changes.

Provider lifecycle is the one mechanical operation you own: create/register or drain/clean/retire a bench when this portfolio decision requires it, then return without waiting for setup or running the experiment.
Treat an actionable GPU safety finding in the latest supervisor handoff as lifecycle work: verify the named provider resources once, clean and retire them when the finding is confirmed, or correct the inventory when it is not. Do not leave a confirmed orphan merely documented.

Mark `STATUS.json` with `researcher_profile: deep` only when a project's next result requires mechanism-level causal reasoning across source, model geometry, and accelerator behavior. Use `execution` for routine implementation, provider operations, and sweeps; switching profiles is a model-routing decision, not an experiment gate.

The director owns allocation and teardown of shared provider GPUs. Before creating one, inspect the inventory with `PYTHONPATH=research/factory/src python3 -m grad_research.gpu_pool --lab {self.config.lab_dir} list`. Register a new bench once with its provider resource, accelerator, hourly cost, absolute watchdog/deadline, and concise description of resident model, checkpoint, image, runtime, caches, and server state. Researchers claim and release benches; releasing never tears one down. Keep useful benches warm across projects. Drain and externally clean a bench only when no compatible queued work justifies its idle cost, the deadline or spend authority requires it, or the environment/hardware must change; then retire it with verified cleanup. The director owns allocation and teardown, while the harness enforces only the overall researcher-process cap of {self.config.max_parallel_researchers}.

Independent projects may use independent claimed benches concurrently. A claim is exclusive only for mutation of that bench, never for the provider or lab. Use a mutable retained development environment across ordinary import, path, permission, runtime-context, API, benchmark, and telemetry repairs. Do not create repair/audit/successor projects unless the scientific question changes.

Budget projects with explicit wall-clock, compute, storage, and spend limits, never with an agent-turn boundary. “Same researcher turn” may prohibit a support successor, but it must not force deterministic checkpoint materialization, compilation, or an actual quality-consumer run to fit inside one model response. When required local work can outlive a response, require one bounded durable local owner in the same project and keep provider creation gated until its typed terminal passes; do not make the researcher kill/restart correct work or weaken a pre-create gate to satisfy turn cadence.

When setup, bootstrap, checkpoint staging, compilation, or model load materially exceed scored GPU time, keep the lab bench for in-place repair and compatible projects by default. Size or replace its watchdog for a short portfolio itinerary rather than one project's turn or terminal, while staying inside the campaign spend cap. Compare idle cost with measured cold-setup cost and lost wall time; retain while compatible reuse within that break-even window is plausible. If the campaign remains open, keep newly released reusable state through the next portfolio selection: choose the next experiment and hardware before deciding the warm bench has no compatible work. Preserve resident state and record each attempted program and result. A project terminal, empty claim, recoverable integration failure, or failed conditional trigger does not itself require teardown.

If cold setup is likely to exceed a compatible follow-up arm, assign another researcher to prepare the best likely follow-up offline while the bench bootstraps. Run it sequentially on the resident bench only if it becomes ready and remains useful; never delay the primary or wait in the director turn.

Shared tools available to all agents:
{self._tools_text()}
"""

    def _researcher_prompt(self, project: Path) -> str:
        try:
            status = json.loads((project / "STATUS.json").read_text())
            next_action = str(status.get("next_action", "")).strip()
        except (OSError, ValueError, TypeError):
            status = {}
            next_action = ""
        scheduled_action = next_action or "choose the fastest in-scope evidence path"
        researcher_profile = str(status.get("researcher_profile", "execution"))
        active_session = status.get("active_session")
        if isinstance(active_session, dict) and active_session:
            session_mode = str(active_session.get("mode", "batch"))
            shared_bench = active_session.get("bench_id")
            if session_mode == "development":
                if shared_bench:
                    session_guidance = f"""
Legacy development owner imported as shared bench `{shared_bench}`: {json.dumps(active_session, sort_keys=True)}
This project owns the experiment process, not provider lifecycle. Attach and repair the experiment in place, but do not invoke provider cleanup or end the watchdog. Update and release the bench through the pool when the experiment reaches a terminal; the director decides whether it remains warm or drains.
"""
                else:
                    session_guidance = f"""
Mutable retained development session from `STATUS.json`: {json.dumps(active_session, sort_keys=True)}
This project still owns this allocation or session. Do not create a replacement resource for it. Other projects may own independent GPU sessions concurrently. Inspect current progress once. If setup is progressing normally, preserve it and return. If a recoverable integration error is visible, attach to the existing exact environment, inspect the full diagnostic, patch the local or remote program, and rerun in place. Keep the image, checkpoint, model, and caches when valid. End the session only for a scientific decision, required hardware/image change, unsafe or unintelligible state, budget/deadline, or a judgment that another route is better.
"""
            else:
                session_guidance = f"""
Durable active session from `STATUS.json`: {json.dumps(active_session, sort_keys=True)}
If its independent owner is still active and forward progress is visible, take one grouped snapshot, record ownership, and return; do not sleep or poll. If it is terminal, reconcile artifacts, spend, and cleanup.
"""
        else:
            session_guidance = ""
        spend_snapshot = self._spend_cap_snapshot()
        if spend_snapshot is None:
            spend_guidance = ""
        else:
            reservation = spend_snapshot["reservations"].get(project.name)
            if reservation is None:
                spend_guidance = """
Paid provider mutation is forbidden for this project because it has no reservation in the campaign spend cap. Continue only with zero-cost work unless the director gives the project a positive authorized spend that the harness can reserve.
"""
            else:
                spend_guidance = f"""
This project's cumulative provider-spend ceiling across all of its allocations is reserved under the campaign cap: {json.dumps(reservation, sort_keys=True)}. Subtract every prior measured or conservatively derived project cost before launching more work. Never exceed that cumulative reservation; unused reservation is not authority for another project.
"""
        return f"""Use `$researcher` to continue the project at `{project}`.

Current scheduled action from `STATUS.json`: {scheduled_action}
Researcher profile: {researcher_profile}
Treat it as this turn's default execution contract. If it calls for integration and measurement, do not substitute another readiness artifact: continue to the measured result or a typed in-scope external blocker. Deviate only when new evidence invalidates the action, and record that evidence.
If that action needs a runner, adapter, or experiment script that is not present yet, implement the narrow in-scope version now and continue; absence of project-local code is not a typed blocker.
{session_guidance}
{spend_guidance}

Shared GPU bench inventory:
{self._gpu_pool_context()}

For GPU work, claim a compatible lab bench atomically before touching it:
`PYTHONPATH=research/factory/src python3 -m grad_research.gpu_pool --lab {self.config.lab_dir} claim --project {project.name} [--bench ID | --accelerator TYPE | --model MODEL]`.
Claims are idempotent for this project. Heartbeat long work, update the concise resident `contents`, and release the bench when this experiment is done. Release with `--condition maintenance` when the environment needs director attention; otherwise release it ready for the next researcher; never create or tear down a provider GPU, disk, watchdog, or lab bench. If no compatible bench is available, record the exact need in `STATUS.json` for the director and continue useful offline work or return; do not create a project-owned allocation. A project spend reservation is not authority to bypass the pool. Using an already-claimed shared bench is not new provider mutation.

An agent-turn boundary is not a scientific wall-clock budget. If required deterministic local work such as checkpoint materialization, compilation, or an actual quality-consumer run can outlive this response, start it once as a bounded durable service in the same project and record its deadline, artifact root, expected typed terminal, and canonical `unit` and `unit_manager` keys in `STATUS.json.active_session`. Do not kill and restart correct local computation merely to return. Local preparation does not authorize provider creation; the director supplies a lab bench when it is ready.

If you start a durable local computation, record its PID/cgroup, deadline, artifact root, and forward progress in `STATUS.json.active_session`. A claimed GPU bench remains lab-owned and is recorded in `runtime/gpus.json`, not as a project-owned provider session. Do not repeatedly poll normal setup, but do not abandon the first real invocation without a durable experiment process or result artifact.

Latest director decision:
{self._latest_director_decision()}
Treat it as the current cross-project dependency state. Before declaring a prerequisite missing, check the named project or artifact once instead of relying on older project-local history.

Read its `PROJECT.md`, `STATUS.json`, and only the useful recent parts of `RESEARCH_LOG.md`, plus the campaign's economic target and relevant code, telemetry, and artifacts. Use your best judgment to produce new decision-relevant evidence quickly. Respect the workload and quality requirements, but trade latency as allowed by `CAMPAIGN.md`. Spend the turn on experiments, simulations, falsification, or a working intervention; treat setup and validation as means to that end. If the route is stuck, change strategy instead of circling. Keep documentation to a short handoff, update `STATUS.json`, and stay within scope.

Before constructing a provider, background-process, or systemd wrapper, check the listed shared tools once for an existing durable controller that accepts the experiment's script or inputs. Use that controller with absolute paths; a custom component benchmark is not a reason to create a custom lifecycle owner.

Shared tools available to all agents:
{self._tools_text()}
"""

    def _supervisor_prompt(self) -> str:
        return f"""Use `$research-supervisor` to review and improve the research process at `{self.config.lab_dir}`.

Read `CAMPAIGN.md`, `STATUS.md`, director and project logs, `runtime/events.jsonl`, recent agent traces, experiment timings, and GPU outcomes. The model-specific objective and intervention scope in `CAMPAIGN.md` define research progress; generic activity and process cleanliness do not. Use your best judgment to find the real bottleneck to reaching that objective. Make a small safe improvement to the skills, shared tools, or harness when warranted, and append the evidence and expected effect to `SUPERVISOR_LOG.md`. Do not take over the scientific portfolio or disrupt active experiments.

Start with a short GPU safety audit. Compare `runtime/gpus.json` with one grouped listing from each configured provider whose authenticated interface is already available. Check provider resources that are absent from the inventory, inventory records whose provider resources no longer exist, inactive lifecycle owners or watchdogs, stale claims, passed deadlines, and available benches whose idle cost is no longer justified by compatible queued work. Do not research provider setup or repeatedly poll. If a registered bench has objectively lost its owner/watchdog, passed its deadline, or become unsafe, mark the registered bench draining and give the director its exact resource IDs; for idle-cost judgments, recommend drain or reuse. Do not perform provider cleanup or retire inventory records: the director owns those actions. Record actionable mismatches in `SUPERVISOR_LOG.md`; if the audit is healthy and no process change is warranted, leave the log untouched and return quickly.

Review `runtime/gpu_events.jsonl` for warm-bench reuse, claim duration, idle time, repeated setup, and teardown decisions. Treat teardown and cold restart after a recoverable integration error as waste. Prefer a claimed mutable bench in which the researcher patches and reruns against resident state. Do not answer this failure mode with more static validation or more projects.

Shared tools:
{self._tools_text()}
"""

    def _project_rows(self) -> list[dict[str, Any]]:
        rows = []
        for project in sorted((self.config.lab_dir / "projects").iterdir()):
            if not project.is_dir() or not (project / "PROJECT.md").is_file():
                continue
            status_path = project / "STATUS.json"
            try:
                status = json.loads(status_path.read_text()) if status_path.is_file() else {}
            except json.JSONDecodeError:
                status = {"status": "blocked", "summary": "STATUS.json is invalid"}
            priority = status.get("priority", 0)
            if not isinstance(priority, (int, float)):
                priority = 0
            authorized_spend_usd = status.get("authorized_spend_usd", 0)
            if not isinstance(authorized_spend_usd, (int, float)):
                authorized_spend_usd = 0
            rows.append(
                {
                    "id": project.name,
                    "path": str(project),
                    "status": str(status.get("status", "active")),
                    "priority": priority,
                    "summary": str(status.get("summary", "")),
                    "next_action": str(status.get("next_action", "")),
                    "researcher_profile": str(
                        status.get("researcher_profile", "execution")
                    ),
                    "active_session": status.get("active_session"),
                    "authorized_spend_usd": authorized_spend_usd,
                }
            )
        return sorted(rows, key=lambda row: (-row["priority"], row["id"]))

    def _durable_session_owner(self, row: dict[str, Any]) -> tuple[str, str] | None:
        active_session = row.get("active_session")
        if not isinstance(active_session, dict):
            return None
        unit = active_session.get("unit") or active_session.get("controller_unit")
        if not isinstance(unit, str) or not unit.strip():
            return None
        unit_manager = active_session.get("unit_manager", "user")
        if unit_manager == "systemd --user":
            unit_manager = "user"
        if unit_manager not in {"system", "user"}:
            return None
        return unit, unit_manager

    def _durable_session_is_running(self, row: dict[str, Any]) -> bool:
        owner = self._durable_session_owner(row)
        if owner is None:
            return False
        unit, unit_manager = owner
        try:
            return self._unit_is_active(unit, unit_manager)
        except Exception:
            return False

    @staticmethod
    def _durable_session_mode(row: dict[str, Any]) -> str:
        active_session = row.get("active_session")
        if not isinstance(active_session, dict):
            return "batch"
        return "development" if active_session.get("mode") == "development" else "batch"

    @staticmethod
    def _development_observation_sha256(row: dict[str, Any]) -> str:
        active_session = row.get("active_session")
        if not isinstance(active_session, dict):
            active_session = {}
        stable_session = {
            key: value
            for key, value in active_session.items()
            if key != "forward_progress"
        }
        artifacts = []
        artifact_root = active_session.get("artifact_root")
        if isinstance(artifact_root, str) and artifact_root:
            root = Path(artifact_root)
            project_path = row.get("path")
            if (
                not root.is_absolute()
                and isinstance(project_path, str)
                and project_path
            ):
                root = Path(project_path) / root
            try:
                paths = sorted(root.rglob("*")) if root.is_dir() else []
            except OSError:
                paths = []
            for path in paths:
                if not path.is_file() or not (
                    path.suffix in {".json", ".jsonl"}
                    or path.name.endswith(".sha256")
                    or path.name.endswith(".tar.gz")
                ):
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                artifacts.append(
                    {
                        "path": str(path.relative_to(root)),
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                    }
                )
        encoded = json.dumps(
            {"active_session": stable_session, "artifacts": artifacts},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode()).hexdigest()

    def _director_observation_sha256(self) -> str:
        observations = []
        for row in self._project_rows():
            project = Path(row["path"])
            status_path = project / "STATUS.json"
            try:
                status_sha256 = hashlib.sha256(status_path.read_bytes()).hexdigest()
            except OSError:
                status_sha256 = "unavailable"
            summaries = []
            artifacts = project / "artifacts"
            if artifacts.is_dir():
                for summary_path in sorted(artifacts.rglob("summary.json")):
                    try:
                        summary_sha256 = hashlib.sha256(summary_path.read_bytes()).hexdigest()
                    except OSError:
                        summary_sha256 = "unavailable"
                    summaries.append(
                        {
                            "path": str(summary_path.relative_to(project)),
                            "sha256": summary_sha256,
                        }
                    )
            observations.append(
                {
                    "id": row["id"],
                    "status_sha256": status_sha256,
                    "summaries": summaries,
                }
            )
        try:
            gpu_inventory_sha256 = hashlib.sha256(
                self.gpu_pool.inventory_path.read_bytes()
            ).hexdigest()
        except OSError:
            gpu_inventory_sha256 = "unavailable"
        try:
            supervisor_log_sha256 = hashlib.sha256(
                (self.config.lab_dir / "SUPERVISOR_LOG.md").read_bytes()
            ).hexdigest()
        except OSError:
            supervisor_log_sha256 = "unavailable"
        encoded = json.dumps(
            {
                "projects": observations,
                "gpu_inventory_sha256": gpu_inventory_sha256,
                "supervisor_log_sha256": supervisor_log_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode()).hexdigest()

    def _director_can_defer(self) -> tuple[bool, str]:
        runnable = [
            row
            for row in self._project_rows()
            if row["status"] in {"active", "ready"}
        ]
        observation_sha256 = self._director_observation_sha256()
        now = datetime.now(timezone.utc)
        urgent_gpu_state = any(
            (bench.get("claim") or {}).get("stale", False)
            or datetime.fromisoformat(
                bench["lifecycle"]["deadline_utc"].replace("Z", "+00:00")
            )
            <= now
            for bench in self.gpu_pool.snapshot()["benches"]
        )
        if urgent_gpu_state:
            return False, observation_sha256
        if not runnable or not all(
            self._durable_session_is_running(row) for row in runnable
        ):
            return False, observation_sha256
        return (
            self.state.get("director_observation_sha256") == observation_sha256,
            observation_sha256,
        )

    def _run_agent(
        self,
        *,
        role: str,
        label: str,
        prompt: str,
        route: ModelRoute,
        thread_id: str | None,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        agent_id = f"{role}:{label}"
        with self._mutex:
            self.state["active_agents"][agent_id] = {
                "role": role,
                "label": label,
                "model": route.model,
                "started_at": utc_now(),
            }
            self._save_state()
            self.render_status()
            self._record(
                "agent_started",
                role=role,
                label=label,
                model=route.model,
                reasoning_effort=route.reasoning_effort,
                prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            )
        try:
            result = self.runner.run(
                prompt,
                role=role,
                route=route,
                thread_id=thread_id,
                timeout_seconds=timeout_seconds,
                label=label,
            )
        except Exception as error:
            result = {
                "role": role,
                "label": label,
                "model": route.model,
                "reasoning_effort": route.reasoning_effort,
                "thread_id": thread_id,
                "returncode": None,
                "timed_out": False,
                "duration_seconds": 0,
                "error": f"{type(error).__name__}: {error}",
            }
        with self._mutex:
            self.state["active_agents"].pop(agent_id, None)
            self.state["last_runs"][agent_id] = result
            if role == "director":
                self.state["threads"]["director"] = result.get("thread_id")
            elif role == "supervisor":
                self.state["threads"]["supervisor"] = result.get("thread_id")
            else:
                self.state["threads"]["projects"][label] = result.get("thread_id")
            self._save_state()
            self.render_status()
            self._record(
                "agent_completed",
                role=role,
                label=label,
                model=result.get("model", route.model),
                reasoning_effort=result.get("reasoning_effort", route.reasoning_effort),
                returncode=result.get("returncode"),
                timed_out=result.get("timed_out", False),
                duration_seconds=result.get("duration_seconds", 0),
                error=result.get("error"),
                stdout_path=result.get("stdout_path"),
                stderr_path=result.get("stderr_path"),
            )
        return result

    def _run_researchers(self) -> list[dict[str, Any]]:
        rows = [
            row
            for row in self._project_rows()
            if row["status"] in {"active", "ready"}
        ]
        running_owners = {
            row["id"]: self._durable_session_owner(row)
            for row in rows
            if self._durable_session_is_running(row)
        }
        active = []
        for row in rows:
            owner = running_owners.get(row["id"])
            owns_development_session = (
                owner is not None
                and self._durable_session_mode(row) == "development"
            )
            if owns_development_session:
                observation_sha256 = self._development_observation_sha256(row)
                if (
                    self.state["development_observations"].get(row["id"])
                    == observation_sha256
                ):
                    unit, unit_manager = owner
                    self._record(
                        "researcher_deferred",
                        label=row["id"],
                        reason="unchanged_development_session",
                        unit=unit,
                        unit_manager=unit_manager,
                        observation_sha256=observation_sha256,
                    )
                    continue
                self.state["development_observations"][row["id"]] = (
                    observation_sha256
                )
            if owner is not None and not owns_development_session:
                unit, unit_manager = owner
                self._record(
                    "researcher_deferred",
                    label=row["id"],
                    reason="durable_session_active",
                    unit=unit,
                    unit_manager=unit_manager,
                )
                continue
            if not self._reserve_project_spend(row):
                self._record(
                    "researcher_deferred",
                    label=row["id"],
                    reason="spend_cap_exceeded",
                    authorized_spend_usd=row["authorized_spend_usd"],
                    spend_cap=self._spend_cap_snapshot(),
                )
                continue
            active.append(row)
            if len(active) >= self.config.max_parallel_researchers:
                break
        if not active:
            return []
        routes = self.config.researcher_routes or (self.config.researcher,)
        routes_by_model = {route.model: route for route in routes}
        all_routes_by_model = {
            route.model: route for route in (*routes, self.config.deep_researcher)
        }
        route_counts = {route.model: 0 for route in routes}
        assignments = []
        for row in active:
            previous_model = self.state["project_routes"].get(row["id"])
            if (
                self._durable_session_mode(row) == "development"
                and previous_model in all_routes_by_model
            ):
                route = all_routes_by_model[previous_model]
                if route.model in route_counts:
                    route_counts[route.model] += 1
            elif row["researcher_profile"] == "deep":
                route = self.config.deep_researcher
            else:
                model = previous_model
                if model not in routes_by_model:
                    model = min(route_counts, key=lambda name: route_counts[name])
                route = routes_by_model[model]
                route_counts[model] += 1
            self.state["project_routes"][row["id"]] = route.model
            assignments.append((row, route))
        self._save_state()
        results = []
        with ThreadPoolExecutor(
            max_workers=len(active), thread_name_prefix="lab-researcher"
        ) as executor:
            futures = {}
            for row, route in assignments:
                project = Path(row["path"])
                (project / "artifacts").mkdir(parents=True, exist_ok=True)
                previous = self.state["last_runs"].get(f"researcher:{row['id']}", {})
                thread_id = self.state["threads"]["projects"].get(row["id"])
                previous_trace = previous.get("stdout_path")
                if (
                    thread_id
                    and isinstance(previous_trace, str)
                    and trace_reports_response_capacity_exhausted(Path(previous_trace))
                ):
                    self.state["threads"]["projects"][row["id"]] = None
                    self._record(
                        "researcher_thread_reset",
                        label=row["id"],
                        reason="response_capacity_exhausted",
                        model=route.model,
                    )
                    thread_id = None
                if previous.get("model") not in {None, route.model}:
                    thread_id = None
                future = executor.submit(
                    self._run_agent,
                    role="researcher",
                    label=row["id"],
                    prompt=self._researcher_prompt(project),
                    route=route,
                    thread_id=thread_id,
                    timeout_seconds=self.config.researcher_timeout_seconds,
                )
                futures[future] = row["id"]
            for future in as_completed(futures):
                results.append(future.result())
        return results

    def render_status(self) -> dict[str, Any]:
        status = {
            "schema_version": 1,
            "updated_at": utc_now(),
            "cycle_count": self.state["cycle_count"],
            "active_agents": self.state["active_agents"],
            "projects": self._project_rows(),
            "last_runs": self.state["last_runs"],
            "spend_cap": self._spend_cap_snapshot(),
            "gpu_pool": self.gpu_pool.snapshot(),
        }
        atomic_json(self.status_json_path, status)
        lines = [
            "# Research lab status",
            "",
            f"Updated: {status['updated_at']}",
            f"Cycle: {status['cycle_count']}",
            f"Active agents: {len(status['active_agents'])}",
            "",
            "## Projects",
            "",
        ]
        if status["projects"]:
            lines.extend(
                [
                    "| Project | Status | Summary | Next action |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for row in status["projects"]:
                values = [
                    row["id"],
                    row["status"],
                    row["summary"].replace("|", "/"),
                    row["next_action"].replace("|", "/"),
                ]
                lines.append("| " + " | ".join(values) + " |")
        else:
            lines.append("No research projects have been delegated yet.")
        lines.extend(["", "## GPU benches", ""])
        if status["gpu_pool"]["benches"]:
            lines.extend(
                [
                    "| Bench | Status | Accelerator | Project | Resident state |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for bench in status["gpu_pool"]["benches"]:
                claim = bench.get("claim") or {}
                contents = bench.get("contents") or {}
                resident = ", ".join(
                    str(contents.get(key))
                    for key in ("model", "runtime", "server")
                    if contents.get(key)
                )
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(bench.get("id", "")),
                            str(bench.get("status", "")),
                            str(bench.get("accelerator", "")),
                            str(claim.get("project", "")),
                            resident.replace("|", "/"),
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("No shared GPU benches are registered.")
        lines.extend(["", "## Last agent runs", ""])
        if status["last_runs"]:
            for agent_id, run in sorted(status["last_runs"].items()):
                outcome = "timed out" if run.get("timed_out") else f"exit {run.get('returncode')}"
                lines.append(
                    f"- {agent_id}: {outcome}, {run.get('duration_seconds', 0)}s on {run.get('model', 'unknown')}"
                )
        else:
            lines.append("No agent turns have completed yet.")
        self.status_markdown_path.write_text("\n".join(lines) + "\n")
        return status

    def cycle(self) -> dict[str, Any]:
        self.render_status()
        director_deferred, observation_sha256 = self._director_can_defer()
        if director_deferred:
            self._record(
                "director_deferred",
                reason="unchanged_durable_sessions",
                observation_sha256=observation_sha256,
            )
        else:
            self._run_agent(
                role="director",
                label="director",
                prompt=self._director_prompt(),
                route=self.config.director,
                thread_id=self.state["threads"]["director"],
                timeout_seconds=self.config.director_timeout_seconds,
            )
            self.state["director_observation_sha256"] = (
                self._director_observation_sha256()
            )
            self._save_state()
        self._run_researchers()
        next_cycle = self.state["cycle_count"] + 1
        if next_cycle % self.config.supervisor_every_cycles == 0:
            self._run_agent(
                role="supervisor",
                label="supervisor",
                prompt=self._supervisor_prompt(),
                route=self.config.supervisor,
                thread_id=self.state["threads"]["supervisor"],
                timeout_seconds=self.config.supervisor_timeout_seconds,
            )
        self.state["cycle_count"] = next_cycle
        self._save_state()
        self._record("cycle_completed", cycle_count=next_cycle)
        return self.render_status()

    def run_forever(self, *, once: bool = False) -> None:
        while True:
            if not once:
                self._restart_if_source_changed()
            try:
                self.cycle()
            except Exception as error:
                self._record(
                    "cycle_failed", error=f"{type(error).__name__}: {error}"
                )
                self.render_status()
            if once:
                return
            self._restart_if_source_changed()
            time.sleep(self.config.cycle_interval_seconds)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Simple subscription-authenticated multi-agent research lab"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    config = LabConfig.load(args.config)
    if args.status:
        status_path = config.lab_dir / "runtime" / "status.json"
        if not status_path.is_file():
            raise SystemExit("the research lab has not written status yet")
        print(json.dumps(json.loads(status_path.read_text()), indent=2, sort_keys=True))
        return 0
    harness = LabHarness(config)
    try:
        harness.run_forever(once=args.once)
    finally:
        harness.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
