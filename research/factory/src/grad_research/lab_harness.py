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
    max_parallel_researchers: int = 3
    supervisor_every_cycles: int = 6
    director_timeout_seconds: int = 900
    researcher_timeout_seconds: int = 2700
    supervisor_timeout_seconds: int = 900
    director: ModelRoute = ModelRoute("gpt-5.6-sol", "high")
    researcher: ModelRoute = ModelRoute("gpt-5.6-terra", "medium")
    researcher_routes: tuple[ModelRoute, ...] = ()
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
            max_parallel_researchers=int(raw.get("max_parallel_researchers", 3)),
            supervisor_every_cycles=int(raw.get("supervisor_every_cycles", 6)),
            director_timeout_seconds=int(raw.get("director_timeout_seconds", 900)),
            researcher_timeout_seconds=int(raw.get("researcher_timeout_seconds", 2700)),
            supervisor_timeout_seconds=int(raw.get("supervisor_timeout_seconds", 900)),
            director=route("director", cls.director),
            researcher=route("researcher", cls.researcher),
            researcher_routes=researcher_routes,
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
    def __init__(self, config: LabConfig, *, runner: Any | None = None):
        self.config = config
        self.runtime_dir = config.lab_dir / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        (config.lab_dir / "projects").mkdir(exist_ok=True)
        self._ensure_log(config.lab_dir / "DIRECTOR_LOG.md", "# Director log\n")
        self._ensure_log(config.lab_dir / "SUPERVISOR_LOG.md", "# Research supervisor log\n")
        self.state_path = self.runtime_dir / "state.json"
        self.events_path = self.runtime_dir / "events.jsonl"
        self.status_json_path = self.runtime_dir / "status.json"
        self.status_markdown_path = config.lab_dir / "STATUS.md"
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
        self.render_status()

    @staticmethod
    def _ensure_log(path: Path, heading: str) -> None:
        if not path.exists():
            path.write_text(heading)

    def close(self) -> None:
        if not self._lock_handle.closed:
            fcntl.flock(self._lock_handle, fcntl.LOCK_UN)
            self._lock_handle.close()

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.is_file():
            state = json.loads(self.state_path.read_text())
            state.setdefault("project_routes", {})
            return state
        return {
            "schema_version": 1,
            "cycle_count": 0,
            "threads": {"director": None, "supervisor": None, "projects": {}},
            "project_routes": {},
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

    def _tools_text(self) -> str:
        paths = [str(path) for path in self.config.tools if path.exists()]
        return "\n".join(f"- {path}" for path in paths) or "- Use relevant repository tools."

    def _director_prompt(self) -> str:
        return f"""Use `$research-director` as the Sol research director for this lab.

Lab: {self.config.lab_dir}
Read `CAMPAIGN.md`, `STATUS.md`, `DIRECTOR_LOG.md`, `SUPERVISOR_LOG.md`, the project briefs and the useful recent parts of their research logs. Inspect current telemetry and experiment artifacts when they matter. Use your best judgment.

Maximize decision-relevant research progress per wall-clock hour. Treat the campaign's economic target, workload, quality requirement, and latency tradeoffs as authoritative. Review the evidence, improve the portfolio, and delegate or update independent projects under `projects/`. Keep useful work parallel, redirect lines that are stuck, and keep the log to a short decision handoff. Do not execute the delegated projects yourself.

Shared tools available to all agents:
{self._tools_text()}
"""

    def _researcher_prompt(self, project: Path) -> str:
        return f"""Use `$researcher` to continue the project at `{project}`.

Read its `PROJECT.md`, `STATUS.json`, and only the useful recent parts of `RESEARCH_LOG.md`, plus the campaign's economic target and relevant code, telemetry, and artifacts. Use your best judgment to produce new decision-relevant evidence quickly. Respect the workload and quality requirements, but trade latency as allowed by `CAMPAIGN.md`. Spend the turn on experiments, simulations, falsification, or a working intervention; treat setup and validation as means to that end. If the route is stuck, change strategy instead of circling. Keep documentation to a short handoff, update `STATUS.json`, and stay within scope.

Shared tools available to all agents:
{self._tools_text()}
"""

    def _supervisor_prompt(self) -> str:
        return f"""Use `$research-supervisor` to review and improve the research process at `{self.config.lab_dir}`.

Read `CAMPAIGN.md`, `STATUS.md`, director and project logs, `runtime/events.jsonl`, recent agent traces, experiment timings, and GPU outcomes. The model-specific objective and intervention scope in `CAMPAIGN.md` define research progress; generic activity and process cleanliness do not. Use your best judgment to find the real bottleneck to reaching that objective. Make a small safe improvement to the skills, shared tools, or harness when warranted, and append the evidence and expected effect to `SUPERVISOR_LOG.md`. Do not take over the scientific portfolio or disrupt active experiments.

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
            rows.append(
                {
                    "id": project.name,
                    "path": str(project),
                    "status": str(status.get("status", "active")),
                    "priority": priority,
                    "summary": str(status.get("summary", "")),
                    "next_action": str(status.get("next_action", "")),
                }
            )
        return sorted(rows, key=lambda row: (-row["priority"], row["id"]))

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
        active = [
            row for row in self._project_rows() if row["status"] in {"active", "ready"}
        ][: self.config.max_parallel_researchers]
        if not active:
            return []
        routes = self.config.researcher_routes or (self.config.researcher,)
        routes_by_model = {route.model: route for route in routes}
        route_counts = {route.model: 0 for route in routes}
        assignments = []
        for row in active:
            model = self.state["project_routes"].get(row["id"])
            if model not in routes_by_model:
                model = min(route_counts, key=lambda name: route_counts[name])
                self.state["project_routes"][row["id"]] = model
            route_counts[model] += 1
            assignments.append((row, routes_by_model[model]))
        self._save_state()
        results = []
        with ThreadPoolExecutor(
            max_workers=len(active), thread_name_prefix="lab-researcher"
        ) as executor:
            futures = {}
            for row, route in assignments:
                previous = self.state["last_runs"].get(f"researcher:{row['id']}", {})
                thread_id = self.state["threads"]["projects"].get(row["id"])
                if previous.get("model") not in {None, route.model}:
                    thread_id = None
                future = executor.submit(
                    self._run_agent,
                    role="researcher",
                    label=row["id"],
                    prompt=self._researcher_prompt(Path(row["path"])),
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
        self._run_agent(
            role="director",
            label="director",
            prompt=self._director_prompt(),
            route=self.config.director,
            thread_id=self.state["threads"]["director"],
            timeout_seconds=self.config.director_timeout_seconds,
        )
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
            try:
                self.cycle()
            except Exception as error:
                self._record(
                    "cycle_failed", error=f"{type(error).__name__}: {error}"
                )
                self.render_status()
            if once:
                return
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
