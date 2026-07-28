from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import selectors
import signal
import subprocess
import tempfile
import threading
import time
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ThreadPoolExecutor,
    as_completed,
    wait,
)
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


def canonical_json_sha256(value: Any) -> str:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    return hashlib.sha256(payload).hexdigest()


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
        if isinstance(text, str):
            lowered = text.lower()
            if "remaining response capacity" in lowered:
                return True
            if "within this turn" in lowered and any(
                phrase in lowered
                for phrase in ("unable to complete", "couldn't complete", "cannot complete")
            ):
                return True
    return False


def run_reports_agent_service_unavailable(run: dict[str, Any]) -> bool:
    if run.get("returncode") in {None, 0} or run.get("timed_out"):
        return False
    markers = (
        "biscuit_baker_service_me_circuit_open",
        "too many concurrent requests",
        "currently experiencing high demand",
        "no_biscuit_no_service",
        "you've hit your usage limit",
    )
    for key in ("stdout_path", "stderr_path"):
        value = run.get(key)
        if not isinstance(value, str):
            continue
        try:
            with Path(value).open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - 262_144))
                text = handle.read().decode(errors="replace").lower()
        except OSError:
            continue
        if any(marker in text for marker in markers):
            return True
    return False


def run_reports_context_window_exhausted(run: dict[str, Any]) -> bool:
    if run.get("returncode") in {None, 0} or run.get("timed_out"):
        return False
    marker = "ran out of room in the model's context window"
    for key in ("stdout_path", "stderr_path"):
        value = run.get(key)
        if not isinstance(value, str):
            continue
        try:
            with Path(value).open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - 262_144))
                text = handle.read().decode(errors="replace").lower()
        except OSError:
            continue
        if marker in text:
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
    quiescent_spend_floor_usd: float = 0.0
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
            quiescent_spend_floor_usd=float(
                raw.get("quiescent_spend_floor_usd", 0.0)
            ),
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
            if config.quiescent_spend_floor_usd > config.spend_cap_usd:
                raise ValueError(
                    "quiescent_spend_floor_usd cannot exceed spend_cap_usd"
                )
        if config.quiescent_spend_floor_usd < 0:
            raise ValueError("quiescent_spend_floor_usd cannot be negative")
        if config.quiescent_spend_floor_usd > 0 and config.spend_cap_usd is None:
            raise ValueError(
                "quiescent_spend_floor_usd requires a configured spend cap"
            )
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

    def _command(self, route: ModelRoute, thread_id: str | None) -> list[str]:
        options = [
            "--model",
            route.model,
            "-c",
            f'model_reasoning_effort="{route.reasoning_effort}"',
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
        ]
        if thread_id:
            return ["codex", "exec", "resume", *options, thread_id, "-"]
        return ["codex", "exec", *options, "-C", str(self.repo_dir), "-"]

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
        temporary_root = self.trace_dir / ".agent-tmp"
        temporary_root.mkdir(exist_ok=True)
        command = self._command(route, thread_id)
        with (
            tempfile.TemporaryDirectory(
                prefix=f"{prefix}-",
                dir=temporary_root,
                ignore_cleanup_errors=True,
            ) as temporary_directory,
            stderr_path.open("w") as stderr,
        ):
            environment = codex_environment()
            environment["TMPDIR"] = temporary_directory
            environment["TMP"] = temporary_directory
            environment["TEMP"] = temporary_directory
            process = self.popen(
                command,
                cwd=self.repo_dir,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            if process.stdin is None:
                raise RuntimeError("Codex stdin pipe is unavailable")
            try:
                process.stdin.write(prompt)
            except BrokenPipeError:
                pass
            finally:
                process.stdin.close()
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
        self._mutex = threading.RLock()
        self._lock_handle = (self.runtime_dir / "harness.lock").open("w")
        try:
            fcntl.flock(self._lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self._lock_handle.close()
            raise RuntimeError("another research-lab harness owns this lab") from error
        self.state = self._load_state()
        self._rotate_exhausted_threads_from_last_runs()
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
        live_pid_sessions = self._live_pid_session_labels()
        if live_pid_sessions:
            self._record(
                "harness_reload_deferred",
                previous_source_sha256=self._source_sha256,
                current_source_sha256=current_sha256,
                live_pid_sessions=live_pid_sessions,
                disposition="preserve_pid_managed_sessions",
            )
            return
        self._record(
            "harness_reload_requested",
            previous_source_sha256=self._source_sha256,
            current_source_sha256=current_sha256,
        )
        self.close()
        raise SystemExit(75)

    def _live_pid_session_labels(self) -> list[str]:
        return sorted(
            row["id"]
            for row in self._project_rows()
            if row.get("status") in {"active", "ready"}
            and isinstance(row.get("active_session"), dict)
            and row["active_session"].get("unit_manager") == "pid"
            and self._pid_session_is_running(row["active_session"], row.get("path"))
        )

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

    def _rotate_exhausted_threads_from_last_runs(self) -> None:
        for agent_id, run in self.state["last_runs"].items():
            if not run_reports_context_window_exhausted(run):
                continue
            role, _, label = agent_id.partition(":")
            if role == "director":
                current = self.state["threads"]["director"]
                self.state["threads"]["director"] = None
            elif role == "supervisor":
                current = self.state["threads"]["supervisor"]
                self.state["threads"]["supervisor"] = None
            elif role == "researcher":
                current = self.state["threads"]["projects"].get(label)
                self.state["threads"]["projects"][label] = None
            else:
                continue
            if current is None:
                continue
            self._record(
                "agent_thread_rotated",
                role=role,
                label=label,
                reason="context_window_exhausted_on_startup",
                previous_thread_id=current,
            )
        self._save_state()

    def _save_state(self) -> None:
        with self._mutex:
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
            "settled_spend_usd": 0.0,
            "reservation_epoch": self.config.spend_cap_starts_at,
            "reservations": {},
            "settlements": {},
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
        if not isinstance(current.get("settlements", {}), dict):
            raise RuntimeError("spend cap settlements must be an object")
        settled = float(current.get("settled_spend_usd", 0))
        if settled < 0:
            raise RuntimeError("settled spend must be nonnegative")
        try:
            datetime.fromisoformat(
                current.get("reservation_epoch", current["starts_at"]).replace(
                    "Z", "+00:00"
                )
            )
        except (AttributeError, ValueError) as error:
            raise RuntimeError("reservation epoch must be RFC3339") from error

    @staticmethod
    def _current_reservations(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
        epoch = datetime.fromisoformat(
            value.get("reservation_epoch", value["starts_at"]).replace("Z", "+00:00")
        )
        current = {}
        for project, reservation in value["reservations"].items():
            try:
                reserved_at = datetime.fromisoformat(
                    reservation["reserved_at"].replace("Z", "+00:00")
                )
            except (KeyError, AttributeError, ValueError):
                continue
            if reserved_at >= epoch:
                current[project] = reservation
        return current

    def _spend_cap_snapshot(self) -> dict[str, Any] | None:
        if self.config.spend_cap_usd is None:
            return None
        value = json.loads(self.spend_cap_path.read_text())
        reservations = self._current_reservations(value)
        reserved_micros = sum(
            self._usd_micros(reservation["authorized_usd"])
            for reservation in reservations.values()
        )
        settled_micros = self._usd_micros(value.get("settled_spend_usd", 0))
        cap_micros = self._usd_micros(value["cap_usd"])
        return {
            "schema_version": value.get("schema_version", 1),
            "starts_at": value["starts_at"],
            "cap_usd": value["cap_usd"],
            "reservation_epoch": value.get("reservation_epoch", value["starts_at"]),
            "settled_spend_usd": settled_micros / 1_000_000,
            "reservations": reservations,
            "historical_reservation_count": len(value["reservations"]) - len(reservations),
            "reserved_usd": reserved_micros / 1_000_000,
            "available_usd": (
                cap_micros - settled_micros - reserved_micros
            ) / 1_000_000,
        }

    def _reserve_project_spend(self, row: dict[str, Any]) -> bool:
        requested = float(row.get("authorized_spend_usd", 0))
        if requested <= 0 or self.config.spend_cap_usd is None:
            return True
        value = json.loads(self.spend_cap_path.read_text())
        reservations = value["reservations"]
        current_reservations = self._current_reservations(value)
        previous = current_reservations.get(row["id"], {})
        previous_micros = self._usd_micros(previous.get("authorized_usd", 0))
        requested_micros = self._usd_micros(requested)
        if requested_micros <= previous_micros:
            return True
        committed_micros = sum(
            self._usd_micros(reservation["authorized_usd"])
            for reservation in current_reservations.values()
        )
        settled_micros = self._usd_micros(value.get("settled_spend_usd", 0))
        cap_micros = self._usd_micros(value["cap_usd"])
        if (
            settled_micros + committed_micros + requested_micros - previous_micros
            > cap_micros
        ):
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

    def _projects_with_live_gpu_exposure(self) -> set[str]:
        projects = set()
        for bench in self.gpu_pool.snapshot()["benches"]:
            claim = bench.get("claim")
            contents = bench.get("contents")
            for project in (
                claim.get("project") if isinstance(claim, dict) else None,
                contents.get("project") if isinstance(contents, dict) else None,
            ):
                if isinstance(project, str) and project:
                    projects.add(project)
        return projects

    def _settle_terminal_reservations(
        self, active_projects: set[str] | None = None
    ) -> None:
        if self.config.spend_cap_usd is None:
            return
        active_projects = active_projects or set()
        live_gpu_projects = self._projects_with_live_gpu_exposure()
        value = json.loads(self.spend_cap_path.read_text())
        reservations = self._current_reservations(value)
        rows = {row["id"]: row for row in self._project_rows()}
        accounted = {}
        for settlement in value.get("settlements", {}).values():
            project = settlement.get("project")
            actual = settlement.get("actual_spend_usd")
            if (
                isinstance(project, str)
                and isinstance(actual, (int, float))
                and not isinstance(actual, bool)
                and actual >= 0
            ):
                accounted[project] = max(accounted.get(project, 0.0), float(actual))
        restored = []
        for project in sorted(live_gpu_projects - reservations.keys()):
            row = rows.get(project)
            if row is None:
                continue
            authorized = row.get("authorized_spend_usd")
            if (
                not isinstance(authorized, (int, float))
                or isinstance(authorized, bool)
                or authorized <= 0
            ):
                continue
            remaining = max(0.0, float(authorized) - accounted.get(project, 0.0))
            if self._usd_micros(remaining) <= 0:
                continue
            timestamp = utc_now()
            reservation = {
                "authorized_usd": remaining,
                "reserved_at": timestamp,
                "updated_at": timestamp,
            }
            value["reservations"][project] = reservation
            reservations[project] = reservation
            restored.append(project)
            self._record(
                "spend_reservation_restored",
                label=project,
                authorized_spend_usd=remaining,
                reason="non_retired_gpu_exposure",
            )
        settled = []
        for project, reservation in reservations.items():
            row = rows.get(project)
            if (
                row is None
                or project in active_projects
                or project in live_gpu_projects
                or row.get("status") in {"active", "ready"}
            ):
                continue
            actual = row.get("actual_spend_usd")
            if not isinstance(actual, (int, float)) or isinstance(actual, bool) or actual < 0:
                continue
            settled.append((project, reservation, float(actual)))
        value.setdefault("settlements", {})
        total = float(value.get("settled_spend_usd", 0))
        for project, reservation, actual in settled:
            incremental = max(0.0, actual - accounted.get(project, 0.0))
            total += incremental
            value["settlements"][f"{project}:{utc_now()}"] = {
                "project": project,
                "actual_spend_usd": actual,
                "incremental_actual_spend_usd": incremental,
                "authorized_usd": reservation["authorized_usd"],
                "settled_at": utc_now(),
            }
            accounted[project] = max(accounted.get(project, 0.0), actual)
            del value["reservations"][project]
            self._record(
                "spend_settled",
                label=project,
                actual_spend_usd=actual,
                incremental_actual_spend_usd=incremental,
                authorized_spend_usd=reservation["authorized_usd"],
            )
        active_statuses = {"active", "ready"}
        for project, row in rows.items():
            if (
                project in active_projects
                or project in live_gpu_projects
                or row.get("status") in active_statuses
            ):
                continue
            actual = row.get("actual_spend_usd")
            if (
                not isinstance(actual, (int, float))
                or isinstance(actual, bool)
                or actual < 0
            ):
                continue
            actual = float(actual)
            prior = accounted.get(project, 0.0)
            incremental = actual - prior
            if self._usd_micros(incremental) <= 0:
                continue
            total += incremental
            value["settlements"][f"{project}:{utc_now()}"] = {
                "project": project,
                "actual_spend_usd": actual,
                "incremental_actual_spend_usd": incremental,
                "authorized_usd": float(row.get("authorized_spend_usd", 0)),
                "reconciled_after_reservation_release": True,
                "settled_at": utc_now(),
            }
            accounted[project] = actual
            self._record(
                "spend_reconciled",
                label=project,
                actual_spend_usd=actual,
                incremental_actual_spend_usd=incremental,
            )
        if (
            not settled
            and not restored
            and self._usd_micros(total)
            == self._usd_micros(value.get("settled_spend_usd", 0))
        ):
            return
        value["settled_spend_usd"] = total
        atomic_json(self.spend_cap_path, value)

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

    def _supervisor_handoff_sha256(self) -> str:
        try:
            content = (self.config.lab_dir / "SUPERVISOR_LOG.md").read_bytes()
        except OSError:
            return "unavailable"
        return hashlib.sha256(content).hexdigest()

    def _active_portfolio_context(self) -> str:
        with self._mutex:
            last_runs = dict(self.state["last_runs"])
        rows = [
            {
                **{
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
                },
                "last_researcher_run": {
                    key: value
                    for key in (
                        "returncode",
                        "timed_out",
                        "duration_seconds",
                        "error",
                        "ended_at",
                    )
                    if (value := last_runs.get(
                        f"researcher:{row['id']}", {}
                    ).get(key))
                    is not None
                },
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
Researchers in the active portfolio may still be running concurrently. Consume completed results and fill free capacity, but do not rewrite an in-flight project's scientific contract merely because another project finished.

Provider lifecycle is the one mechanical operation you own: create/register or drain/clean/retire a bench when this portfolio decision requires it, then return without waiting for setup or running the experiment. A requested or planned spend reservation is not authority: before any paid provider create, the exact project reservation must already appear in the spend-cap snapshot above and its remaining amount must cover the conservative lifecycle. If it does not, admit or update the project without provider mutation, let the harness reserve it, and create only on a later director turn after the durable reservation is visible.
Treat an actionable GPU safety finding in the latest supervisor handoff as lifecycle work: verify the named provider resources once, clean and retire them when the finding is confirmed, or correct the inventory when it is not. Do not leave a confirmed orphan merely documented.

Mark `STATUS.json` with `researcher_profile: deep` only when a project's next result requires mechanism-level causal reasoning across source, model geometry, and accelerator behavior. Use `execution` for routine implementation, provider operations, and sweeps; switching profiles is a model-routing decision, not an experiment gate.

The director owns allocation and teardown of shared provider GPUs. Before creating one, inspect the inventory with `PYTHONPATH=research/factory/src python3 -m grad_research.gpu_pool --lab {self.config.lab_dir} list`. Register a new bench once with its provider resource, accelerator, hourly cost, absolute watchdog/deadline, and concise description of resident model, checkpoint, image, runtime, caches, and server state. Researchers claim and release benches; releasing never tears one down. Keep useful benches warm across projects. Drain and externally clean a bench only when no compatible queued work justifies its idle cost, the deadline or spend authority requires it, or the environment/hardware must change; then retire it with verified cleanup. The director owns allocation and teardown, while the harness enforces only the overall researcher-process cap of {self.config.max_parallel_researchers}.

Independent projects may use independent claimed benches concurrently. A claim is exclusive only for mutation of that bench, never for the provider or lab. Use a mutable retained development environment across ordinary import, path, permission, runtime-context, API, benchmark, and telemetry repairs. Do not create repair/audit/successor projects unless the scientific question changes.

Budget projects with explicit wall-clock, compute, storage, and spend limits, never with an agent-turn boundary. “Same researcher turn” may prohibit a support successor, but it must not force deterministic checkpoint materialization, compilation, or an actual quality-consumer run to fit inside one model response. When required local work can outlive a response, require one bounded durable local owner in the same project and keep provider creation gated until its typed terminal passes; do not make the researcher kill/restart correct work or weaken a pre-create gate to satisfy turn cadence.

When setup, bootstrap, checkpoint staging, compilation, or model load materially exceed scored GPU time, keep the lab bench for in-place repair and compatible projects by default. Size or replace its watchdog for a short portfolio itinerary rather than one project's turn or terminal, while staying inside the campaign spend cap. Compare idle cost with measured cold-setup cost and lost wall time; retain while compatible reuse within that break-even window is plausible. If the campaign remains open, keep newly released reusable state through the next portfolio selection: choose the next experiment and hardware before deciding the warm bench has no compatible work. Preserve resident state and record each attempted program and result. A project terminal, empty claim, recoverable integration failure, or failed conditional trigger does not itself require teardown.
A drain justified by no compatible work or campaign termination must follow the next portfolio selection in this same director turn. If that selection would create the same compatible accelerator or environment, retain and assign the existing bench instead; do not drain in one cycle and reopen onto replacement hardware in the next.

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
On attachment, resume at the failed operation; do not replay settled host bootstrap, checkpoint transfer, image pull, or model preparation while their resident identity is unchanged. Inspect resident state once and repeat only the invalidated operation. A replacement controller on the same bench must consume the existing remote workspace rather than treating it as a cold allocation.
"""
                else:
                    session_guidance = f"""
Mutable retained development session from `STATUS.json`: {json.dumps(active_session, sort_keys=True)}
This project still owns this allocation or session. Do not create a replacement resource for it. Other projects may own independent GPU sessions concurrently. Inspect current progress once. If setup is progressing normally, preserve it and return. If a recoverable integration error is visible, attach to the existing exact environment, inspect the full diagnostic, patch the local or remote program, and rerun in place. Keep the image, checkpoint, model, and caches when valid. End the session only for a scientific decision, required hardware/image change, unsafe or unintelligible state, budget/deadline, or a judgment that another route is better.
"""
            else:
                repair_root = self._pending_durable_repair(project, active_session)
                if repair_root is not None:
                    session_guidance = f"""
Durable repair handshake from `STATUS.json`: {json.dumps(active_session, sort_keys=True)}
The independent owner is still active and retains the claim, but `{repair_root / 'REPAIR_READY.json'}` requests bounded in-place repair. Inspect the decision-bearing failure diagnostic once, patch only the recoverable integration defect in the existing environment, and write the owner's documented `REPAIR_REQUEST.json` before its recorded deadline. Do not stop, replace, release, or cold-restart the owner, and do not replay a consumed scientific stage.
Before signaling the owner, inspect its retry entrypoint: a repair request must resume at the invalidated operation, not blindly rerun a monolithic worker that reloads the model or replays passing setup, smoke, or path stages. Reuse a still-healthy server. If a failed pre-request consumer left a zero-request partial output root, atomically archive that partial root and give the unchanged retry a fresh output path; preserve its hashes and never delete or overwrite decision-bearing rows.
"""
                else:
                    terminal_repair = self._terminal_durable_repair(
                        project, active_session
                    )
                    if terminal_repair is not None:
                        session_guidance = f"""
Previous durable owner terminal after an integration failure: {json.dumps(terminal_repair, sort_keys=True)}
Before following the possibly stale scheduled action, inspect the persisted stage terminals and failure diagnostic. Preserve every completed stage listed above with a passing terminal; repair only the invalidated validator, consumer, or ordinary integration operation, then execute only stages that the invocation state and artifacts prove unstarted. Do not replay the whole scheduled pair merely because `STATUS.json.next_action` still names it. Reclaim and reuse the same compatible warm bench when available. If the diagnostic instead proves a scientific incompatibility or no safe in-scope repair exists, reconcile that terminal without replay.
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
If a GPU invocation consumes a hash-bound file from another project or shared mutable path, materialize the admitted bytes under this project before claiming the bench and transfer that immutable project-local snapshot. Do not resolve the shared path again after the claim.
During discovery, an ordinary launcher, path, CLI/API, parser, numeric-guard, telemetry, comparator, archive, or retrieval defect is not scientific evidence. If no interpretable candidate result persisted, record the attempt and causal amendment, then patch and retry only the invalidated operation inside the same claimed bench/session when that remains the best research choice. Candidate CUDA execution or a pre-call `*_science_started` marker proves path entry, not by itself a consumed scientific sample.
Judge consumption from evidence, not intent markers. A complete interpretable candidate result is a sample and must not be silently replayed. A crash, corrupt observer, missing comparator, or partial request with no decision-bearing result is an invalid attempt that may be amended and retried, even when some candidate bytes executed. Preserve the failed artifact and do not count the retry as another independent sample. A project no-retry rule protects valid measurements and completed costly stages; it does not convert harness defects into scientific conclusions.
In a multi-stage experiment, a completed and persisted producer stage remains consumed exactly once. If a later consumer fails from an ordinary configuration, import, path, API, numeric-guard, or harness defect, preserve that producer artifact and patch only the consumer on the same retained bench; do not rerun training, conversion, calibration, or another scientific producer invocation. Treat the consumer defect as decision-bearing only when the project preregisters that exact incompatibility or the resident state is unsafe. When the large producer artifact is already content-addressed and durable on the protected bench, retrieve its compact terminal, hash, and manifest first; repair and consume the remote artifact in place, then copy the bulk bytes after the final terminal or concurrently only when that transfer does not delay GPU progress.
For a mutable GPU session, keep claim, heartbeat, and final release in one bounded outer controller that spans those repair attempts. Per-attempt workers must not unconditionally release the bench on a recoverable pre-invocation exit. Release when the scientific terminal or a nonrecoverable typed boundary is recorded, or when the absolute deadline requires director disposition.
If that outer controller can outlive this turn, the controller itself must be durable; detaching only its guest worker is insufficient because claim heartbeats and terminal retrieval stop when the foreground controller exits. Launch the controller-host process through shared `detached-owner --unit-manager pid`, then record its absolute owner-state path as `unit` plus the emitted `pid`, `start_ticks`, and `unit_manager: pid` in `STATUS.json.active_session`. Do not label a foreground process as a durable controller.
If a remote worker fails while its bench is claimed, retrieve its remote compact terminal, raw stdout/stderr, and a marker showing whether the candidate CUDA or scientific invocation began before releasing the claim. Treat missing retrieval as a recoverable retrieval defect and repair that retrieval under the same claim. Release to maintenance without those artifacts only when the guest is unsafe or unreachable, or the absolute deadline requires director handoff. Never release first and later guess whether the arm was consumed.
If that evidence proves an ordinary integration or consumer defect, do not promote the attempt terminal to the project's scientific terminal or release the warm bench. The bounded outer owner should write `REPAIR_READY.json` with the diagnostic and an absolute repair deadline, keep the claim heartbeating, and wait for `REPAIR_REQUEST.json`; patch and repeat only the invalidated operation under the same owner. Finalize and release after a scientific result, a genuinely informative incompatibility, an unsafe or unreachable guest, or the absolute deadline. The handshake does not authorize a silent change to the scientific question.
When checkpoint or other large immutable staging can outlive the turn, start it inside that durable claim owner before copying bytes. Reconcile the remote size-and-hash manifest first, preserve matched files, transfer only missing or mismatched files to temporary paths, verify them, and atomically finalize their immutable names; never retry an all-files overwrite against already-matched read-only files.
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

Before setting a paid project terminal, put its conservative cumulative provider exposure in `STATUS.json.actual_spend_usd`, including failed attempts and any shared-bench idle exposure explicitly assigned by the director. This is the one number the harness uses to settle the reservation; do not substitute the authorized maximum or omit known setup/cleanup exposure. Compare it with the retired bench's `provider_exposure`: when the director registered `lifecycle.provider_started_at_utc`, that record covers provider start through cleanup verification and terminal spend must not be lower than the portion assigned to this project. A registration-based record is explicitly partial, so reconcile the omitted pre-registration creation interval before settlement rather than treating it as the full cost.

Shared tools available to all agents:
{self._tools_text()}
"""

    def _supervisor_prompt(self) -> str:
        return f"""Use `$research-supervisor` to review and improve the research process at `{self.config.lab_dir}`.

Read `CAMPAIGN.md`, `STATUS.md`, director and project logs, `runtime/events.jsonl`, recent agent traces, experiment timings, and GPU outcomes. The model-specific objective and intervention scope in `CAMPAIGN.md` define research progress; generic activity and process cleanliness do not. Use your best judgment to find the real bottleneck to reaching that objective. Make a small safe improvement to the skills, shared tools, or harness when warranted, and append the evidence and expected effect to `SUPERVISOR_LOG.md`. Do not take over the scientific portfolio or disrupt active experiments.

Start with a short GPU safety audit. Compare `runtime/gpus.json` with one grouped listing from each configured provider whose authenticated interface is already available. Check provider resources that are absent from the inventory, inventory records whose provider resources no longer exist, inactive lifecycle owners or watchdogs, stale claims, passed deadlines, and available benches whose idle cost is no longer justified by compatible queued work. Do not research provider setup or repeatedly poll. Resolve lifecycle processes in the namespace recorded by their metadata: a controller `control_group` and `unit_manager` refer to the controller host unless the record explicitly identifies a remote host; do not infer a dead watchdog from probing the guest's systemd manager. If a registered bench has objectively lost its owner/watchdog, passed its deadline, or become unsafe, mark the registered bench draining and give the director its exact resource IDs; for idle-cost judgments, recommend drain or reuse. Do not perform provider cleanup or retire inventory records: the director owns those actions. Record actionable mismatches in `SUPERVISOR_LOG.md`; if the audit is healthy and no process change is warranted, leave the log untouched and return quickly.

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
            actual_spend_usd = status.get("actual_spend_usd")
            if not isinstance(actual_spend_usd, (int, float)) or isinstance(
                actual_spend_usd, bool
            ):
                actual_spend_usd = None
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
                    "external_dependency": status.get("external_dependency"),
                    "bench_id": status.get("bench_id"),
                    "authorized_spend_usd": authorized_spend_usd,
                    "actual_spend_usd": actual_spend_usd,
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
        if unit_manager not in {"system", "user", "pid"}:
            return None
        return unit, unit_manager

    @staticmethod
    def _pid_session_is_running(
        active_session: object, project_path: object = None
    ) -> bool:
        if not isinstance(active_session, dict):
            return False
        try:
            identity = active_session
            if "pid" not in identity or "start_ticks" not in identity:
                unit = identity.get("unit") or identity.get("controller_unit")
                if not isinstance(unit, str) or not unit:
                    return False
                state_path = Path(unit)
                if not state_path.is_absolute():
                    if not isinstance(project_path, str) or not project_path:
                        return False
                    state_path = Path(project_path) / state_path
                loaded = json.loads(state_path.read_text())
                if not isinstance(loaded, dict):
                    return False
                identity = loaded
            pid = int(identity["pid"])
            expected_start_ticks = int(identity["start_ticks"])
            stat = Path(f"/proc/{pid}/stat").read_text()
            fields = stat[stat.rfind(")") + 2 :].split()
            return fields[0] != "Z" and int(fields[19]) == expected_start_ticks
        except (json.JSONDecodeError, KeyError, OSError, ValueError, IndexError):
            return False

    def _durable_session_is_running(self, row: dict[str, Any]) -> bool:
        owner = self._durable_session_owner(row)
        if owner is None:
            return False
        unit, unit_manager = owner
        if unit_manager == "pid":
            return self._pid_session_is_running(
                row.get("active_session"), row.get("path")
            )
        try:
            return self._unit_is_active(unit, unit_manager)
        except Exception:
            return False

    @staticmethod
    def _pending_durable_repair(project: Path, active_session: object) -> Path | None:
        if not isinstance(active_session, dict):
            return None
        artifact_root = active_session.get("artifact_root")
        if not isinstance(artifact_root, str) or not artifact_root:
            return None
        declared_root = Path(artifact_root)
        if not declared_root.is_absolute():
            declared_root = project / declared_root
        roots = (declared_root,) if declared_root == project else (declared_root, project)
        for root in roots:
            ready_paths = [root / "REPAIR_READY.json"]
            ready_paths.extend(
                sorted((root / ".repair-handshakes").glob("*/REPAIR_READY.json"))
            )
            ready_paths.extend(
                sorted(root.glob("*/.repair-handshakes/*/REPAIR_READY.json"))
            )
            for ready in ready_paths:
                if (
                    not ready.is_file()
                    or (root / "TERMINAL.json").exists()
                    or (ready.parent / "TERMINAL.json").exists()
                ):
                    continue
                try:
                    repair = json.loads(ready.read_text())
                    request_path = ready.with_name("REPAIR_REQUEST.json")
                    if request_path.is_file():
                        request = json.loads(request_path.read_text())
                        if request.get("ready_sha256") == canonical_json_sha256(
                            repair
                        ):
                            continue
                    repair_artifact_root = repair.get("artifact_root")
                    if isinstance(repair_artifact_root, str) and repair_artifact_root:
                        bound_root = Path(repair_artifact_root)
                        if not bound_root.is_absolute():
                            bound_root = project / bound_root
                        if bound_root.resolve() != declared_root.resolve():
                            continue
                    deadline_value = repair.get("repair_deadline_epoch")
                    if deadline_value is None:
                        deadline_utc = (
                            repair.get("repair_deadline_utc")
                            or repair.get("absolute_repair_deadline_utc")
                            or repair["absolute_deadline_utc"]
                        )
                        if not isinstance(deadline_utc, str):
                            continue
                        deadline = datetime.fromisoformat(
                            deadline_utc.replace("Z", "+00:00")
                        ).timestamp()
                    else:
                        deadline = float(deadline_value)
                except (
                    OSError,
                    ValueError,
                    TypeError,
                    KeyError,
                    json.JSONDecodeError,
                ):
                    continue
                if deadline > time.time():
                    return ready.parent
        return None

    @staticmethod
    def _terminal_durable_repair(
        project: Path, active_session: object
    ) -> dict[str, Any] | None:
        if not isinstance(active_session, dict):
            return None
        artifact_root = active_session.get("artifact_root")
        if not isinstance(artifact_root, str) or not artifact_root:
            return None
        root = Path(artifact_root)
        if not root.is_absolute():
            root = project / root

        def read_json(*paths: Path) -> dict[str, Any] | None:
            for path in paths:
                try:
                    value = json.loads(path.read_text())
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict):
                    return value
            return None

        reconciled = read_json(root / "RECONCILED_TERMINAL.json")
        worker = read_json(
            root / "REMOTE_WORKER_TERMINAL.json",
            root / "retrieved" / "WORKER_TERMINAL.json",
        )
        if (
            not isinstance(reconciled, dict)
            or reconciled.get("status") != "terminal"
            or reconciled.get("pass") is not False
            or not isinstance(worker, dict)
            or worker.get("classification") != "integration_failure"
        ):
            return None

        invocation_state = read_json(
            root / "INVOCATION_STATE.json",
            root / "retrieved" / "INVOCATION_STATE.json",
        )
        completed_stages = []
        for terminal_path in sorted((root / "retrieved").glob("*/TERMINAL.json")):
            terminal = read_json(terminal_path)
            if isinstance(terminal, dict) and terminal.get("pass") is True:
                completed_stages.append(terminal_path.parent.name)
        return {
            "artifact_root": str(root),
            "completed_passing_stages": completed_stages,
            "invocation_state": invocation_state or {},
            "worker_failure": {
                "classification": worker.get("classification"),
                "message": worker.get("message"),
            },
        }

    def _durable_session_needs_repair(self, row: dict[str, Any]) -> bool:
        return self._pending_durable_repair(Path(row["path"]), row.get("active_session")) is not None

    @staticmethod
    def _fresh_shared_bench_owner(
        row: dict[str, Any], benches: list[dict[str, Any]]
    ) -> tuple[str, dict[str, Any]] | None:
        dependency = row.get("external_dependency")
        structured_wait = (
            isinstance(dependency, dict)
            and dependency.get("type") == "shared_bench_claimed"
        )
        explicit_wait = str(row.get("next_action", "")).strip().casefold().startswith(
            "wait "
        )
        if not structured_wait and not explicit_wait:
            return None
        dependency_bench_id = (
            dependency.get("bench_id") if isinstance(dependency, dict) else None
        )
        bench_id = dependency_bench_id or row.get("bench_id")
        if not isinstance(bench_id, str) or not bench_id:
            return None
        bench = next(
            (candidate for candidate in benches if candidate.get("id") == bench_id),
            None,
        )
        if not isinstance(bench, dict) or bench.get("status") != "claimed":
            return None
        claim = bench.get("claim")
        if not isinstance(claim, dict) or claim.get("stale", False):
            return None
        owner_project = claim.get("project")
        if (
            not isinstance(owner_project, str)
            or not owner_project
            or owner_project == row.get("id")
        ):
            return None
        return owner_project, bench

    @staticmethod
    def _durable_session_mode(row: dict[str, Any]) -> str:
        active_session = row.get("active_session")
        if not isinstance(active_session, dict):
            return "batch"
        return "development" if active_session.get("mode") == "development" else "batch"

    @staticmethod
    def _remote_shell_session_identity(active_session: object) -> str | None:
        if (
            not isinstance(active_session, dict)
            or active_session.get("unit_manager") != "remote-shell"
        ):
            return None
        stable_session = {
            key: active_session.get(key)
            for key in (
                "artifact_root",
                "bench_id",
                "pid",
                "unit",
                "controller_unit",
                "unit_manager",
            )
            if active_session.get(key) is not None
        }
        return json.dumps(stable_session, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _material_jsonl_identity(path: Path) -> dict[str, Any]:
        digest = hashlib.sha256()
        material_lines = 0
        with path.open("rb") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    event = None
                if (
                    isinstance(event, dict)
                    and event.get("event") in {"heartbeat", "claim_heartbeat"}
                    and event.get("returncode") in {None, 0}
                ):
                    continue
                digest.update(line)
                material_lines += 1
        return {
            "material_lines": material_lines,
            "material_sha256": digest.hexdigest(),
        }

    @classmethod
    def _development_observation_sha256(
        cls, row: dict[str, Any]
    ) -> str:
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
                artifact = {"path": str(path.relative_to(root))}
                if path.suffix == ".jsonl":
                    try:
                        artifact.update(cls._material_jsonl_identity(path))
                    except OSError:
                        artifact["material_sha256"] = "unavailable"
                else:
                    artifact.update(
                        {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
                    )
                artifacts.append(artifact)
        encoded = json.dumps(
            {
                "active_session": stable_session,
                "next_action": row.get("next_action", ""),
                "artifacts": artifacts,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode()).hexdigest()

    @classmethod
    def _project_observation_sha256(cls, row: dict[str, Any]) -> str:
        try:
            status_sha256 = hashlib.sha256(
                (Path(row["path"]) / "STATUS.json").read_bytes()
            ).hexdigest()
        except (KeyError, OSError):
            status_sha256 = "unavailable"
        encoded = json.dumps(
            {
                "status_sha256": status_sha256,
                "development_sha256": cls._development_observation_sha256(row),
            },
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
            gpu_inventory = json.loads(self.gpu_pool.inventory_path.read_text())
            gpu_inventory.pop("updated_at", None)
            benches = gpu_inventory.get("benches")
            if isinstance(benches, dict):
                for bench in benches.values():
                    if not isinstance(bench, dict):
                        continue
                    bench.pop("updated_at", None)
                    claim = bench.get("claim")
                    if isinstance(claim, dict):
                        claim.pop("heartbeat_at", None)
                        claim.pop("lease_until_utc", None)
            gpu_inventory_sha256 = hashlib.sha256(
                json.dumps(
                    gpu_inventory, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
        except (OSError, json.JSONDecodeError):
            gpu_inventory_sha256 = "unavailable"
        try:
            supervisor_log_sha256 = hashlib.sha256(
                (self.config.lab_dir / "SUPERVISOR_LOG.md").read_bytes()
            ).hexdigest()
        except OSError:
            supervisor_log_sha256 = "unavailable"
        try:
            campaign_sha256 = hashlib.sha256(
                (self.config.lab_dir / "CAMPAIGN.md").read_bytes()
            ).hexdigest()
        except OSError:
            campaign_sha256 = "unavailable"
        try:
            spend_cap_sha256 = hashlib.sha256(
                self.spend_cap_path.read_bytes()
            ).hexdigest()
        except OSError:
            spend_cap_sha256 = "unavailable"
        encoded = json.dumps(
            {
                "projects": observations,
                "campaign_sha256": campaign_sha256,
                "gpu_inventory_sha256": gpu_inventory_sha256,
                "spend_cap_sha256": spend_cap_sha256,
                "supervisor_log_sha256": supervisor_log_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode()).hexdigest()

    def _director_can_defer(
        self, active_project_ids: set[str] | None = None
    ) -> tuple[bool, str, str]:
        active_project_ids = active_project_ids or set()
        runnable = [
            row
            for row in self._project_rows()
            if row["status"] in {"active", "ready"}
        ]
        observation_sha256 = self._director_observation_sha256()
        now = datetime.now(timezone.utc)
        benches = self.gpu_pool.snapshot()["benches"]
        urgent_gpu_state = any(
            (bench.get("claim") or {}).get("stale", False)
            or datetime.fromisoformat(
                bench["lifecycle"]["deadline_utc"].replace("Z", "+00:00")
            )
            <= now
            for bench in benches
        )
        if urgent_gpu_state:
            return False, observation_sha256, ""
        if not runnable:
            spend = self._spend_cap_snapshot()
            exhausted_quiescent_lab = (
                not benches
                and spend is not None
                and (
                    spend["available_usd"] <= 0
                    or (
                        self.config.quiescent_spend_floor_usd > 0
                        and spend["available_usd"]
                        < self.config.quiescent_spend_floor_usd
                    )
                )
            )
            if not exhausted_quiescent_lab:
                return False, observation_sha256, ""
            return (
                self.state.get("director_observation_sha256")
                == observation_sha256,
                observation_sha256,
                "unchanged_quiescent_lab",
            )
        if not all(
            row["id"] in active_project_ids
            or self._durable_session_is_running(row)
            or self._fresh_shared_bench_owner(row, benches) is not None
            for row in runnable
        ):
            return False, observation_sha256, ""
        return (
            self.state.get("director_observation_sha256") == observation_sha256,
            observation_sha256,
            "unchanged_durable_sessions",
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
            context_window_exhausted = run_reports_context_window_exhausted(result)
            resumed_thread_id = (
                None if context_window_exhausted else result.get("thread_id")
            )
            if role == "director":
                self.state["threads"]["director"] = resumed_thread_id
            elif role == "supervisor":
                self.state["threads"]["supervisor"] = resumed_thread_id
            else:
                self.state["threads"]["projects"][label] = resumed_thread_id
            if context_window_exhausted:
                self._record(
                    "agent_thread_rotated",
                    role=role,
                    label=label,
                    reason="context_window_exhausted",
                    previous_thread_id=thread_id,
                )
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

    def _researcher_assignments(
        self,
        *,
        excluded_labels: set[str] | None = None,
        limit: int | None = None,
        durable_repairs_only: bool = False,
    ) -> list[tuple[dict[str, Any], ModelRoute]]:
        excluded_labels = excluded_labels or set()
        selection_limit = min(
            self.config.max_parallel_researchers,
            self.config.max_parallel_researchers if limit is None else max(0, limit),
        )
        if selection_limit == 0:
            return []
        rows = [
            row
            for row in self._project_rows()
            if row["status"] in {"active", "ready"}
            and row["id"] not in excluded_labels
        ]
        benches = self.gpu_pool.snapshot()["benches"]
        running_owners = {
            row["id"]: self._durable_session_owner(row)
            for row in rows
            if self._durable_session_is_running(row)
        }
        active = []
        for row in rows:
            shared_owner = self._fresh_shared_bench_owner(row, benches)
            if shared_owner is not None:
                owner_project, bench = shared_owner
                claim = bench["claim"]
                self._record(
                    "researcher_deferred",
                    label=row["id"],
                    reason="shared_bench_claimed",
                    bench_id=bench["id"],
                    owner_project=owner_project,
                    heartbeat_at=claim.get("heartbeat_at"),
                    lease_until_utc=claim.get("lease_until_utc"),
                )
                continue
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
                with self._mutex:
                    self.state["development_observations"][row["id"]] = (
                        observation_sha256
                    )
            needs_repair = owner is not None and self._durable_session_needs_repair(row)
            if durable_repairs_only and not needs_repair:
                continue
            if needs_repair:
                self._record("researcher_woken", label=row["id"], reason="durable_repair_ready")
            if owner is not None and not owns_development_session and not needs_repair:
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
            if len(active) >= selection_limit:
                break
        if not active:
            return []
        routes = self.config.researcher_routes or (self.config.researcher,)
        routes_by_model = {route.model: route for route in routes}
        all_routes_by_model = {
            route.model: route for route in (*routes, self.config.deep_researcher)
        }
        with self._mutex:
            route_counts = {
                route.model: sum(
                    1
                    for label in excluded_labels
                    if self.state["project_routes"].get(label) == route.model
                )
                for route in routes
            }
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
                        model = min(
                            route_counts, key=lambda name: route_counts[name]
                        )
                    route = routes_by_model[model]
                    route_counts[route.model] += 1
                self.state["project_routes"][row["id"]] = route.model
                assignments.append((row, route))
            self._save_state()
        return assignments

    def _submit_researcher(
        self,
        executor: ThreadPoolExecutor,
        row: dict[str, Any],
        route: ModelRoute,
        *,
        prompt: str | None = None,
    ) -> Future:
        project = Path(row["path"])
        (project / "artifacts").mkdir(parents=True, exist_ok=True)
        with self._mutex:
            previous = self.state["last_runs"].get(
                f"researcher:{row['id']}", {}
            )
            thread_id = self.state["threads"]["projects"].get(row["id"])
            previous_trace = previous.get("stdout_path")
            if (
                thread_id
                and isinstance(previous_trace, str)
                and trace_reports_response_capacity_exhausted(
                    Path(previous_trace)
                )
            ):
                self.state["threads"]["projects"][row["id"]] = None
                self._record(
                    "researcher_thread_reset",
                    label=row["id"],
                    reason="response_capacity_exhausted",
                    model=route.model,
                )
                self._save_state()
                thread_id = None
            if previous.get("model") not in {None, route.model}:
                thread_id = None
        return executor.submit(
            self._run_agent,
            role="researcher",
            label=row["id"],
            prompt=prompt or self._researcher_prompt(project),
            route=route,
            thread_id=thread_id,
            timeout_seconds=self.config.researcher_timeout_seconds,
        )

    def _remote_continuation_prompt(self, project: Path) -> str:
        return (
            "The prior turn returned while this project still owned a "
            "remote-shell session and claimed bench. Take one current "
            "remote owner snapshot without sleeping or polling. If the "
            "owner is live and advancing, record accurate durable state "
            "and return. If it is dead or terminal, retrieve and reconcile "
            "the evidence now, preserving every completed stage and "
            "releasing or fencing the bench according to the existing "
            "contract.\n\n"
            + self._researcher_prompt(project)
        )

    def _run_researchers(self) -> list[dict[str, Any]]:
        assignments = self._researcher_assignments()
        if not assignments:
            return []
        active = [row for row, _ in assignments]
        initial_remote_sessions = {
            row["id"]: self._remote_shell_session_identity(row.get("active_session"))
            for row, _ in assignments
        }
        results = []
        continuations = set()
        with ThreadPoolExecutor(
            max_workers=len(active), thread_name_prefix="lab-researcher"
        ) as executor:
            futures = {}
            for row, route in assignments:
                future = self._submit_researcher(executor, row, route)
                futures[future] = row["id"]
            for future in as_completed(futures):
                results.append(future.result())
                label = futures[future]
                row = next(
                    (
                        candidate
                        for candidate in self._project_rows()
                        if candidate["id"] == label
                    ),
                    None,
                )
                active_session = row.get("active_session") if row else None
                remote_session = self._remote_shell_session_identity(active_session)
                if (
                    label in continuations
                    or row is None
                    or row["status"] not in {"active", "ready"}
                    or remote_session is None
                    or remote_session == initial_remote_sessions.get(label)
                ):
                    continue
                bench_id = active_session.get("bench_id") or row.get("bench_id")
                bench = next(
                    (
                        candidate
                        for candidate in self.gpu_pool.snapshot()["benches"]
                        if candidate["id"] == bench_id
                    ),
                    None,
                )
                claim = bench.get("claim") if bench else None
                if (
                    not isinstance(claim, dict)
                    or claim.get("project") != label
                    or claim.get("stale", False)
                ):
                    continue
                continuations.add(label)
                route = next(
                    assignment_route
                    for assignment_row, assignment_route in assignments
                    if assignment_row["id"] == label
                )
                self._record(
                    "researcher_woken",
                    label=label,
                    reason="remote_shell_turn_continuation",
                    bench_id=bench_id,
                )
                continuation_prompt = self._remote_continuation_prompt(
                    Path(row["path"])
                )
                results.append(
                    self._run_agent(
                        role="researcher",
                        label=label,
                        prompt=continuation_prompt,
                        route=route,
                        thread_id=self.state["threads"]["projects"].get(label),
                        timeout_seconds=self.config.researcher_timeout_seconds,
                    )
                )
        return results

    def render_status(self) -> dict[str, Any]:
        with self._mutex:
            return self._render_status_unlocked()

    def _render_status_unlocked(self) -> dict[str, Any]:
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
        self._settle_terminal_reservations()
        self.render_status()
        director_deferred, observation_sha256, defer_reason = (
            self._director_can_defer()
        )
        if director_deferred:
            self._record(
                "director_deferred",
                reason=defer_reason,
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

    def _run_event_loop(self, stop_event: threading.Event | None = None) -> None:
        stop_event = stop_event or threading.Event()
        fallback_interval = max(1, self.config.cycle_interval_seconds)
        supervisor_interval = max(
            fallback_interval,
            fallback_interval * max(1, self.config.supervisor_every_cycles),
        )
        next_fallback = time.monotonic() + fallback_interval
        next_supervisor = time.monotonic() + supervisor_interval
        reload_requested = False
        reload_deferred_sha256: str | None = None
        pending_director_wakes: list[dict[str, Any]] = []
        researcher_futures: dict[Future, dict[str, Any]] = {}
        researcher_cooldowns: dict[str, dict[str, Any]] = {}
        director_future: Future | None = None
        supervisor_future: Future | None = None
        supervisor_observation_sha256: str | None = None
        agent_service_backoff_until = 0.0

        def start_agent_service_backoff(
            run: dict[str, Any], *, role: str, label: str
        ) -> bool:
            nonlocal agent_service_backoff_until
            if not run_reports_agent_service_unavailable(run):
                return False
            retry_after_seconds = max(300, fallback_interval * 5)
            agent_service_backoff_until = max(
                agent_service_backoff_until,
                time.monotonic() + retry_after_seconds,
            )
            self._record(
                "agent_service_backoff_started",
                role=role,
                label=label,
                retry_after_seconds=retry_after_seconds,
                returncode=run.get("returncode"),
            )
            return True

        def request_director(reason: str, label: str | None = None) -> None:
            key = (reason, label)
            if any(
                (wake["reason"], wake.get("label")) == key
                for wake in pending_director_wakes
            ):
                return
            pending_director_wakes.append(
                {
                    "reason": reason,
                    "label": label,
                    "requested_at": utc_now(),
                    "requested_monotonic": time.monotonic(),
                }
            )
            self._record(
                "director_wake_requested",
                reason=reason,
                label=label,
                director_running=director_future is not None,
            )

        def active_researcher_labels() -> set[str]:
            return {
                str(metadata["label"])
                for metadata in researcher_futures.values()
            }

        def fill_researcher_slots(
            *,
            allow_pending_director_wakes: bool = False,
            durable_repairs_only: bool = False,
        ) -> None:
            if (
                reload_requested
                or stop_event.is_set()
                or (director_future is not None and not durable_repairs_only)
                or (
                    pending_director_wakes
                    and not allow_pending_director_wakes
                    and not durable_repairs_only
                )
                or time.monotonic() < agent_service_backoff_until
            ):
                return
            active_labels = active_researcher_labels()
            rows_by_id = {
                row["id"]: row
                for row in self._project_rows()
                if row["status"] in {"active", "ready"}
            }
            now = time.monotonic()
            for label, cooldown in list(researcher_cooldowns.items()):
                row = rows_by_id.get(label)
                if (
                    row is None
                    or now >= cooldown["until_monotonic"]
                    or self._project_observation_sha256(row)
                    != cooldown["project_observation_sha256"]
                ):
                    researcher_cooldowns.pop(label, None)
            excluded_labels = active_labels | set(researcher_cooldowns)
            slots = self.config.max_parallel_researchers - len(active_labels)
            for row, route in self._researcher_assignments(
                excluded_labels=excluded_labels,
                limit=slots,
                durable_repairs_only=durable_repairs_only,
            ):
                future = self._submit_researcher(
                    researcher_executor, row, route
                )
                researcher_futures[future] = {
                    "label": row["id"],
                    "route": route,
                    "initial_remote_session": self._remote_shell_session_identity(
                        row.get("active_session")
                    ),
                    "initial_project_observation": (
                        self._project_observation_sha256(row)
                    ),
                    "continuation": False,
                }
                active_labels.add(row["id"])
                self._record(
                    "researcher_slot_filled",
                    label=row["id"],
                    active_researchers=len(active_labels),
                    max_parallel_researchers=self.config.max_parallel_researchers,
                )

        def schedule_remote_continuation(metadata: dict[str, Any]) -> bool:
            if metadata.get("continuation"):
                return False
            label = str(metadata["label"])
            row = next(
                (
                    candidate
                    for candidate in self._project_rows()
                    if candidate["id"] == label
                ),
                None,
            )
            if row is None or row["status"] not in {"active", "ready"}:
                return False
            active_session = row.get("active_session")
            remote_session = self._remote_shell_session_identity(active_session)
            if (
                remote_session is None
                or remote_session == metadata.get("initial_remote_session")
            ):
                return False
            bench_id = active_session.get("bench_id") or row.get("bench_id")
            bench = next(
                (
                    candidate
                    for candidate in self.gpu_pool.snapshot()["benches"]
                    if candidate["id"] == bench_id
                ),
                None,
            )
            claim = bench.get("claim") if bench else None
            if (
                not isinstance(claim, dict)
                or claim.get("project") != label
                or claim.get("stale", False)
            ):
                return False
            route = metadata["route"]
            self._record(
                "researcher_woken",
                label=label,
                reason="remote_shell_turn_continuation",
                bench_id=bench_id,
            )
            future = self._submit_researcher(
                researcher_executor,
                row,
                route,
                prompt=self._remote_continuation_prompt(Path(row["path"])),
            )
            researcher_futures[future] = {
                "label": label,
                "route": route,
                "initial_remote_session": remote_session,
                "initial_project_observation": (
                    self._project_observation_sha256(row)
                ),
                "continuation": True,
            }
            return True

        request_director("startup")
        with (
            ThreadPoolExecutor(
                max_workers=self.config.max_parallel_researchers,
                thread_name_prefix="lab-researcher",
            ) as researcher_executor,
            ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="lab-director"
            ) as director_executor,
            ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="lab-supervisor"
            ) as supervisor_executor,
        ):
            try:
                while True:
                    now = time.monotonic()
                    stopping = stop_event.is_set() or reload_requested
                    if not reload_requested:
                        try:
                            current_sha256 = self._source_digest(self._source_path)
                        except OSError:
                            current_sha256 = "unavailable"
                        if current_sha256 != self._source_sha256:
                            live_pid_sessions = self._live_pid_session_labels()
                            if live_pid_sessions:
                                if reload_deferred_sha256 != current_sha256:
                                    self._record(
                                        "harness_reload_deferred",
                                        previous_source_sha256=self._source_sha256,
                                        current_source_sha256=current_sha256,
                                        live_pid_sessions=live_pid_sessions,
                                        disposition="preserve_pid_managed_sessions",
                                    )
                                    reload_deferred_sha256 = current_sha256
                            else:
                                reload_requested = True
                                stopping = True
                                self._record(
                                    "harness_reload_requested",
                                    previous_source_sha256=self._source_sha256,
                                    current_source_sha256=current_sha256,
                                    active_researchers=len(
                                        active_researcher_labels()
                                    ),
                                    director_running=director_future is not None,
                                    supervisor_running=(
                                        supervisor_future is not None
                                    ),
                                    disposition=(
                                        "drain_active_agent_turns_then_reload"
                                    ),
                                )

                    if (
                        not stopping
                        and supervisor_future is None
                        and now >= next_supervisor
                        and now >= agent_service_backoff_until
                    ):
                        supervisor_observation_sha256 = (
                            self._supervisor_handoff_sha256()
                        )
                        supervisor_future = supervisor_executor.submit(
                            self._run_agent,
                            role="supervisor",
                            label="supervisor",
                            prompt=self._supervisor_prompt(),
                            route=self.config.supervisor,
                            thread_id=self.state["threads"]["supervisor"],
                            timeout_seconds=self.config.supervisor_timeout_seconds,
                        )
                        next_supervisor = float("inf")

                    if (
                        not stopping
                        and director_future is None
                        and pending_director_wakes
                        and now >= agent_service_backoff_until
                    ):
                        active_labels = active_researcher_labels()
                        self._settle_terminal_reservations(active_labels)
                        wake_batch = list(pending_director_wakes)
                        pending_director_wakes.clear()
                        force_director = any(
                            wake["reason"]
                            in {
                                "researcher_completed",
                                "researcher_no_progress",
                                "supervisor_changed",
                            }
                            for wake in wake_batch
                        )
                        if force_director:
                            director_deferred = False
                            observation_sha256 = (
                                self._director_observation_sha256()
                            )
                            defer_reason = ""
                        else:
                            (
                                director_deferred,
                                observation_sha256,
                                defer_reason,
                            ) = self._director_can_defer(active_labels)
                        oldest_delay = max(
                            0.0,
                            time.monotonic()
                            - min(
                                wake["requested_monotonic"]
                                for wake in wake_batch
                            ),
                        )
                        reasons = sorted(
                            {str(wake["reason"]) for wake in wake_batch}
                        )
                        if director_deferred:
                            self._record(
                                "director_deferred",
                                reason=defer_reason,
                                observation_sha256=observation_sha256,
                            )
                            self._record(
                                "director_wake_deferred",
                                reasons=reasons,
                                wake_count=len(wake_batch),
                                oldest_wake_delay_seconds=round(
                                    oldest_delay, 6
                                ),
                            )
                        else:
                            self._record(
                                "director_wake_dispatched",
                                reasons=reasons,
                                wake_count=len(wake_batch),
                                oldest_wake_delay_seconds=round(
                                    oldest_delay, 6
                                ),
                                active_researchers=len(active_labels),
                            )
                            director_future = director_executor.submit(
                                self._run_agent,
                                role="director",
                                label="director",
                                prompt=self._director_prompt(),
                                route=self.config.director,
                                thread_id=self.state["threads"]["director"],
                                timeout_seconds=self.config.director_timeout_seconds,
                            )

                    if not stopping:
                        fill_researcher_slots(
                            durable_repairs_only=director_future is not None
                        )

                    all_futures = set(researcher_futures)
                    if director_future is not None:
                        all_futures.add(director_future)
                    if supervisor_future is not None:
                        all_futures.add(supervisor_future)
                    if stopping and not all_futures:
                        if reload_requested:
                            live_pid_sessions = self._live_pid_session_labels()
                            if live_pid_sessions:
                                try:
                                    current_sha256 = self._source_digest(
                                        self._source_path
                                    )
                                except OSError:
                                    current_sha256 = "unavailable"
                                self._record(
                                    "harness_reload_deferred",
                                    previous_source_sha256=self._source_sha256,
                                    current_source_sha256=current_sha256,
                                    live_pid_sessions=live_pid_sessions,
                                    disposition=(
                                        "cancel_pending_reload_for_new_pid_sessions"
                                    ),
                                )
                                reload_deferred_sha256 = current_sha256
                                reload_requested = False
                                stopping = False
                                next_fallback = (
                                    time.monotonic() + fallback_interval
                                )
                                next_supervisor = (
                                    time.monotonic() + supervisor_interval
                                )
                                request_director(
                                    "reload_deferred_live_pid_session"
                                )
                                continue
                        break

                    now = time.monotonic()
                    if (
                        not stopping
                        and now >= next_fallback
                        and director_future is None
                        and not pending_director_wakes
                    ):
                        request_director("fallback")
                        next_fallback = now + fallback_interval
                        continue
                    if not stopping and now >= next_fallback:
                        next_fallback = now + fallback_interval

                    timeout_candidates = [float(fallback_interval)]
                    if not stopping:
                        timeout_candidates.extend(
                            [
                                max(0.0, next_fallback - now),
                                max(
                                    0.0,
                                    max(
                                        next_supervisor,
                                        agent_service_backoff_until,
                                    )
                                    - now,
                                ),
                            ]
                        )
                    timeout = min(timeout_candidates)
                    if not all_futures:
                        stop_event.wait(timeout)
                        continue
                    done, _ = wait(
                        all_futures,
                        timeout=timeout,
                        return_when=FIRST_COMPLETED,
                    )
                    if not done:
                        continue

                    completed_researchers = [
                        future
                        for future in done
                        if future in researcher_futures
                    ]
                    for future in completed_researchers:
                        metadata = researcher_futures.pop(future)
                        run = future.result()
                        if stopping:
                            continue
                        label = str(metadata["label"])
                        if start_agent_service_backoff(
                            run, role="researcher", label=label
                        ):
                            current_row = next(
                                (
                                    candidate
                                    for candidate in self._project_rows()
                                    if candidate["id"] == label
                                ),
                                None,
                            )
                            researcher_cooldowns[label] = {
                                "until_monotonic": agent_service_backoff_until,
                                "project_observation_sha256": (
                                    self._project_observation_sha256(current_row)
                                    if current_row is not None
                                    else "project-removed"
                                ),
                            }
                            continue
                        if run_reports_context_window_exhausted(run):
                            self._record(
                                "researcher_retry_queued",
                                label=label,
                                reason="context_window_exhausted",
                            )
                            continue
                        if schedule_remote_continuation(metadata):
                            continue
                        row = next(
                            (
                                candidate
                                for candidate in self._project_rows()
                                if candidate["id"] == label
                            ),
                            None,
                        )
                        current_observation = (
                            self._project_observation_sha256(row)
                            if row is not None
                            else "project-removed"
                        )
                        if (
                            current_observation
                            == metadata.get("initial_project_observation")
                        ):
                            researcher_cooldowns[label] = {
                                "until_monotonic": (
                                    time.monotonic() + fallback_interval
                                ),
                                "project_observation_sha256": (
                                    current_observation
                                ),
                            }
                            self._record(
                                "researcher_no_progress",
                                label=label,
                                retry_after_seconds=fallback_interval,
                            )
                            request_director(
                                "researcher_no_progress", label
                            )
                        else:
                            request_director(
                                "researcher_completed", label
                            )

                    if supervisor_future is not None and supervisor_future in done:
                        run = supervisor_future.result()
                        start_agent_service_backoff(
                            run, role="supervisor", label="supervisor"
                        )
                        supervisor_future = None
                        next_supervisor = time.monotonic() + supervisor_interval
                        if not stopping:
                            current_observation = (
                                self._supervisor_handoff_sha256()
                            )
                            if (
                                current_observation
                                != supervisor_observation_sha256
                            ):
                                request_director("supervisor_changed")
                        supervisor_observation_sha256 = None

                    if director_future is not None and director_future in done:
                        run = director_future.result()
                        start_agent_service_backoff(
                            run, role="director", label="director"
                        )
                        director_future = None
                        next_fallback = time.monotonic() + fallback_interval
                        current_observation_sha256 = (
                            self._director_observation_sha256()
                            if not pending_director_wakes
                            else None
                        )
                        with self._mutex:
                            if current_observation_sha256 is not None:
                                self.state["director_observation_sha256"] = (
                                    current_observation_sha256
                                )
                            next_cycle = self.state["cycle_count"] + 1
                            self.state["cycle_count"] = next_cycle
                            self._save_state()
                        self._record(
                            "cycle_completed", cycle_count=next_cycle
                        )
                        self.render_status()
                        if not stopping:
                            fill_researcher_slots(
                                allow_pending_director_wakes=True
                            )
            except Exception as error:
                self._record(
                    "scheduler_failed",
                    error=f"{type(error).__name__}: {error}",
                )
                self.render_status()
                raise
        if reload_requested:
            self.close()
            raise SystemExit(75)

    def run_forever(
        self,
        *,
        once: bool = False,
        stop_event: threading.Event | None = None,
    ) -> None:
        if once:
            try:
                self.cycle()
            except Exception as error:
                self._record(
                    "cycle_failed", error=f"{type(error).__name__}: {error}"
                )
                self.render_status()
            return
        self._run_event_loop(stop_event)


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
