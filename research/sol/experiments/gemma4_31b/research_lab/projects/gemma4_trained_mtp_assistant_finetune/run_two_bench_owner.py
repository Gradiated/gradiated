#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from grad_research.gpu_pool import GpuPool


PROJECT_ID = "gemma4_trained_mtp_assistant_finetune"
REQUIRED_ACCELERATOR = "nvidia-h200-sxm"
LAB = Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / PROJECT_ID
STATUS = PROJECT / "STATUS.json"
OFFLINE_RESULT = PROJECT / "TRAINED_MTP_OWNER_OFFLINE_RESULT.json"
REPAIR_TOOL = Path("/root/workspace/research/factory/tools/repair-handshake")


class OwnerError(RuntimeError):
    pass


class ExactClaimSession:
    def __init__(
        self,
        pool: GpuPool,
        project: str,
        bench_id: str,
        *,
        lease_seconds: int,
        heartbeat_seconds: float,
        release_condition: str,
        release_contents: Mapping[str, Any],
    ):
        self.pool = pool
        self.project = project
        self.bench_id = bench_id
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.release_condition = release_condition
        self.release_contents = dict(release_contents)
        self.claimed_at: str | None = None
        self._released = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._heartbeat_error: BaseException | None = None

    def __enter__(self) -> ExactClaimSession:
        bench = self.pool.claim(
            self.project,
            bench_id=self.bench_id,
            lease_seconds=self.lease_seconds,
        )
        claim = bench.get("claim")
        if (
            bench.get("id") != self.bench_id
            or not isinstance(claim, dict)
            or claim.get("project") != self.project
            or not isinstance(claim.get("claimed_at"), str)
        ):
            raise OwnerError(f"invalid exact claim for {self.bench_id}")
        self.claimed_at = claim["claimed_at"]
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"heartbeat-{self.bench_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            try:
                bench = self.pool.heartbeat(self.project, bench_id=self.bench_id)
                claim = bench.get("claim")
                if not isinstance(claim, dict) or claim.get("claimed_at") != self.claimed_at:
                    raise OwnerError(f"claim generation changed for {self.bench_id}")
            except BaseException as error:
                self._heartbeat_error = error
                self._stop.set()
                return

    def check(self) -> None:
        if self._heartbeat_error is not None:
            raise OwnerError(f"heartbeat failed for {self.bench_id}") from self._heartbeat_error

    def release(
        self,
        *,
        condition: str | None = None,
        contents: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.claimed_at is None or self._released:
            raise OwnerError(f"claim for {self.bench_id} cannot be released")
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        result = self.pool.release(
            self.project,
            bench_id=self.bench_id,
            expected_claimed_at=self.claimed_at,
            condition=condition or self.release_condition,
            contents=dict(contents) if contents is not None else self.release_contents,
        )
        self._released = True
        return result

    def __exit__(self, exc_type, exc_value, traceback_value) -> bool:
        if not self._released and self.claimed_at is not None:
            self.release()
        return False


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def utc_text(value: dt.datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise OwnerError(f"{path} must contain a JSON object")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def wait_for_detached_state(path: Path) -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            return load_json(path)
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(0.05)
    raise OwnerError("detached-owner state was not published")


def check_binding(binding: dict[str, Any], binding_path: Path) -> None:
    if binding.get("schema_version") != 1:
        raise OwnerError("binding schema_version must be 1")
    if binding.get("project_id") != PROJECT_ID:
        raise OwnerError("binding project_id mismatch")
    if binding.get("offline_result_sha256") != sha256(OFFLINE_RESULT):
        raise OwnerError("binding does not consume the current offline owner result")
    benches = binding.get("benches")
    if not isinstance(benches, dict) or set(benches) != {"target", "trainer"}:
        raise OwnerError("binding must name target and trainer benches")
    ids = []
    total_rate = 0.0
    for role in ("target", "trainer"):
        row = benches[role]
        if not isinstance(row, dict):
            raise OwnerError(f"binding bench {role} must be an object")
        if row.get("accelerator") != REQUIRED_ACCELERATOR:
            raise OwnerError(f"binding bench {role} is not an H200 SXM")
        bench_id = row.get("id")
        rate = row.get("hourly_cost_usd")
        if not isinstance(bench_id, str) or not bench_id:
            raise OwnerError(f"binding bench {role} has no id")
        if not isinstance(rate, (int, float)) or rate <= 0:
            raise OwnerError(f"binding bench {role} has invalid hourly rate")
        ids.append(bench_id)
        total_rate += float(rate)
    if len(set(ids)) != 2:
        raise OwnerError("target and trainer bench IDs must be different")

    reservation = binding.get("reservation")
    if not isinstance(reservation, dict):
        raise OwnerError("binding reservation is missing")
    authorized = float(reservation.get("authorized_usd", -1))
    prior_spend = float(reservation.get("prior_spend_usd", -1))
    cleanup_reserve = float(reservation.get("cleanup_reserve_usd", -1))
    if authorized != 20.0 or prior_spend < 0 or cleanup_reserve < 0.5:
        raise OwnerError("binding reservation or cleanup reserve is invalid")
    remaining = authorized - prior_spend - cleanup_reserve
    if remaining <= 0:
        raise OwnerError("no provider budget remains after cleanup reserve")
    budget_deadline = utc_now() + dt.timedelta(hours=remaining / total_rate)
    lifecycle_deadline = parse_utc(str(binding.get("deadline_utc")))
    if lifecycle_deadline > budget_deadline + dt.timedelta(seconds=5):
        raise OwnerError("binding deadline exceeds the cumulative spend fence")
    if lifecycle_deadline <= utc_now() + dt.timedelta(minutes=10):
        raise OwnerError("binding leaves less than ten minutes for execution")

    pipeline = binding.get("pipeline")
    if not isinstance(pipeline, dict):
        raise OwnerError("pipeline binding is missing")
    command = pipeline.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise OwnerError("pipeline command must be a nonempty argv array")
    repair_command = pipeline.get("repair_command")
    if (
        not isinstance(repair_command, list)
        or not repair_command
        or not all(isinstance(part, str) and part for part in repair_command)
    ):
        raise OwnerError("pipeline repair_command must be a nonempty argv array")
    cwd = Path(str(pipeline.get("cwd", "")))
    terminal = Path(str(pipeline.get("terminal_path", "")))
    if not cwd.is_absolute() or not terminal.is_absolute():
        raise OwnerError("pipeline cwd and terminal_path must be absolute")
    if PROJECT not in terminal.parents:
        raise OwnerError("pipeline terminal must be project-local")
    binding_sha = sha256(binding_path)
    if pipeline.get("binding_sha256") not in (None, binding_sha):
        raise OwnerError("pipeline binding_sha256 mismatch")


def update_status(active_session: dict[str, Any] | None, summary: str, spend: float) -> None:
    status = load_json(STATUS)
    status["active_session"] = active_session
    status["summary"] = summary
    status["actual_spend_usd"] = round(spend, 6)
    atomic_json(STATUS, status)


def write_state(path: Path, **values: Any) -> None:
    current = load_json(path) if path.exists() else {"schema_version": 1}
    current.update(values)
    current["updated_at_utc"] = utc_text()
    atomic_json(path, current)


def run_pipeline(
    binding: dict[str, Any],
    artifact_root: Path,
    deadline: dt.datetime,
    state_path: Path,
) -> dict[str, Any]:
    pipeline = binding["pipeline"]
    command = list(pipeline["command"])
    cwd = Path(pipeline["cwd"])
    environment = os.environ.copy()
    configured_env = pipeline.get("env", {})
    if not isinstance(configured_env, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in configured_env.items()
    ):
        raise OwnerError("pipeline env must map strings to strings")
    environment.update(configured_env)
    environment["TRAINED_MTP_ABSOLUTE_DEADLINE_UTC"] = utc_text(deadline)
    stdout_path = artifact_root / "pipeline.stdout.log"
    stderr_path = artifact_root / "pipeline.stderr.log"
    write_state(state_path, phase="pipeline_start", command=command)
    remaining = (deadline - utc_now()).total_seconds()
    if remaining <= 300:
        raise OwnerError("insufficient lifecycle margin to start pipeline")
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            timeout=remaining - 180,
            check=False,
        )
    write_state(
        state_path,
        phase="pipeline_exit",
        pipeline_exit_code=completed.returncode,
        stdout_sha256=sha256(stdout_path),
        stderr_sha256=sha256(stderr_path),
    )
    terminal_path = Path(pipeline["terminal_path"])
    if completed.returncode != 0:
        raise OwnerError(f"pipeline exited {completed.returncode}")
    if not terminal_path.is_file():
        raise OwnerError("pipeline exited successfully without its terminal")
    terminal = load_json(terminal_path)
    if terminal.get("classification") not in {
        "trained_checkpoint_and_holdout_terminal",
        "bounded_training_negative_terminal",
        "informative_runtime_incompatibility_terminal",
    }:
        raise OwnerError("pipeline terminal classification is not decision-bearing")
    if terminal.get("decision_bearing") is not True:
        raise OwnerError("pipeline terminal is not decision-bearing")
    required = pipeline.get("required_artifacts", [])
    if not isinstance(required, list):
        raise OwnerError("required_artifacts must be a list")
    for entry in required:
        path = Path(entry["path"])
        if not path.is_file() or sha256(path) != entry["sha256"]:
            raise OwnerError(f"required artifact missing or changed: {path}")
    return terminal


def repair_wait(
    artifact_root: Path,
    deadline: dt.datetime,
    diagnostic: Path,
    repair_id: str,
    retry_scope: str,
) -> dict[str, Any]:
    command = [
        str(REPAIR_TOOL),
        "hold",
        "--root",
        str(artifact_root),
        "--deadline",
        utc_text(deadline),
        "--failure-kind",
        "integration",
        "--diagnostic",
        str(diagnostic),
        "--retry-scope",
        retry_scope,
        "--repair-id",
        repair_id,
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise OwnerError(
            f"repair handshake failed: {completed.stderr[-2000:]}"
        )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise OwnerError("repair handshake returned a non-object")
    return value


def consume_repair_request(
    binding: dict[str, Any],
    state: dict[str, Any],
    artifact_root: Path,
    deadline: dt.datetime,
) -> None:
    request_value = state.get("request") or state.get("repair_request")
    if not isinstance(request_value, dict):
        raise OwnerError("repair request payload is missing")
    patch_artifact = request_value.get("patch_artifact")
    if not isinstance(patch_artifact, str) or not Path(patch_artifact).is_file():
        raise OwnerError("repair request patch artifact is missing")
    command = [
        part.replace("{patch_artifact}", patch_artifact)
        .replace("{artifact_root}", str(artifact_root))
        for part in binding["pipeline"]["repair_command"]
    ]
    environment = os.environ.copy()
    environment["TRAINED_MTP_ABSOLUTE_DEADLINE_UTC"] = utc_text(deadline)
    completed = subprocess.run(
        command,
        cwd=Path(binding["pipeline"]["cwd"]),
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    diagnostic = artifact_root / "repair-command.json"
    atomic_json(
        diagnostic,
        {
            "schema_version": 1,
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "patch_artifact": patch_artifact,
            "patch_sha256": sha256(Path(patch_artifact)),
        },
    )
    if completed.returncode != 0:
        raise OwnerError("repair command failed")


def spend_since(
    claimed_at: dict[str, str], rates: dict[str, float], prior_spend: float
) -> float:
    current = utc_now()
    exposure = prior_spend
    for role, timestamp in claimed_at.items():
        seconds = max(0.0, (current - parse_utc(timestamp)).total_seconds())
        exposure += seconds * rates[role] / 3600.0
    return exposure


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--owner-state", type=Path, required=True)
    parser.add_argument("--detached-state", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    binding = load_json(args.binding)
    check_binding(binding, args.binding)
    if args.validate_only:
        print(json.dumps({"valid": True, "binding": str(args.binding)}))
        return 0

    status = load_json(STATUS)
    gate = status.get("claim_gate", {})
    if gate.get("claim_allowed") is not True:
        raise OwnerError("STATUS.json does not authorize claiming")
    detached = wait_for_detached_state(args.detached_state)
    if detached.get("unit_manager") != "pid" or detached.get("live") is False:
        raise OwnerError("controller was not launched by PID-managed detached-owner")

    args.artifact_root.mkdir(parents=True, exist_ok=True)
    write_state(
        args.owner_state,
        phase="preclaim",
        binding=str(args.binding),
        binding_sha256=sha256(args.binding),
        artifact_root=str(args.artifact_root),
    )
    active_session = {
        "unit": str(args.detached_state.resolve()),
        "unit_manager": "pid",
        "pid": detached["pid"],
        "start_ticks": detached["start_ticks"],
        "deadline_utc": binding["deadline_utc"],
        "artifact_root": str(args.artifact_root.resolve()),
        "expected_terminal": binding["pipeline"]["terminal_path"],
        "owner_state": str(args.owner_state.resolve()),
    }
    prior_spend = float(binding["reservation"]["prior_spend_usd"])
    update_status(active_session, "Two-H200 durable owner is entering exact-bench claims.", prior_spend)

    pool = GpuPool(LAB)
    sessions: dict[str, ExactClaimSession] = {}
    claimed_at: dict[str, str] = {}
    rates = {
        role: float(binding["benches"][role]["hourly_cost_usd"])
        for role in ("target", "trainer")
    }
    deadline = parse_utc(binding["deadline_utc"])
    terminal: dict[str, Any] | None = None
    release_conditions = {"target": "maintenance", "trainer": "maintenance"}
    try:
        with ExitStack() as stack:
            for role in ("target", "trainer"):
                session = ExactClaimSession(
                    pool,
                    PROJECT_ID,
                    binding["benches"][role]["id"],
                    lease_seconds=900,
                    heartbeat_seconds=45,
                    release_condition="ready",
                    release_contents={
                        "project": PROJECT_ID,
                        "role": role,
                        "state": "owner_exited_without_terminal",
                    },
                )
                sessions[role] = stack.enter_context(session)
                claimed_at[role] = str(session.claimed_at)

            for session in sessions.values():
                session.release_condition = "maintenance"
            write_state(
                args.owner_state,
                phase="both_benches_claimed",
                claims=claimed_at,
            )
            update_status(
                active_session,
                "Both exact H200 benches are claimed by one durable owner; the bound pipeline is running.",
                spend_since(claimed_at, rates, prior_spend),
            )

            repair_generation = 0
            while utc_now() < deadline - dt.timedelta(minutes=3):
                for session in sessions.values():
                    session.check()
                try:
                    terminal = run_pipeline(
                        binding, args.artifact_root, deadline, args.owner_state
                    )
                    break
                except (OwnerError, subprocess.TimeoutExpired, OSError) as error:
                    diagnostic = args.artifact_root / f"repair-{repair_generation}.json"
                    atomic_json(
                        diagnostic,
                        {
                            "schema_version": 1,
                            "classification": "recoverable_pipeline_or_retrieval_defect",
                            "error": repr(error),
                            "traceback": traceback.format_exc(),
                            "science_consumed": "unknown",
                            "claims": claimed_at,
                        },
                    )
                    repair_id = (
                        f"{claimed_at['target'].replace(':', '').replace('-', '')}"
                        f"-g{repair_generation}"
                    )
                    state = repair_wait(
                        args.artifact_root,
                        deadline,
                        diagnostic,
                        repair_id,
                        "pipeline-defined invalidated stage only",
                    )
                    if state.get("state") == "repair_terminal":
                        result = state.get("repair_terminal", {}).get("result")
                        if not result:
                            raise OwnerError("repair terminal has no adopted result")
                    elif state.get("state") != "requested":
                        raise OwnerError(f"repair did not produce a request: {state}")
                    else:
                        try:
                            consume_repair_request(
                                binding, state, args.artifact_root, deadline
                            )
                        except OwnerError as repair_error:
                            repair_generation += 1
                            write_state(
                                args.owner_state,
                                phase="repair_command_failed_retaining_claim",
                                repair_error=repr(repair_error),
                                next_repair_generation=repair_generation,
                            )
                            continue
                    repair_generation += 1

            if terminal is None:
                raise OwnerError("absolute deadline reached without a scientific terminal")

            resident = terminal.get("resident_release", {})
            for role in ("target", "trainer"):
                condition = resident.get(role, {}).get("condition", "maintenance")
                if condition not in {"ready", "maintenance"}:
                    raise OwnerError(f"invalid {role} release condition")
                release_conditions[role] = condition
            for role in ("trainer", "target"):
                sessions[role].release(
                    condition=release_conditions[role],
                    contents={
                        "project": PROJECT_ID,
                        "role": role,
                        "state": "scientific_terminal",
                        "terminal": binding["pipeline"]["terminal_path"],
                        **resident.get(role, {}).get("contents", {}),
                    },
                )
    finally:
        spend = (
            spend_since(claimed_at, rates, prior_spend)
            if claimed_at
            else prior_spend
        )
        write_state(
            args.owner_state,
            phase="owner_exit",
            actual_spend_usd=round(spend, 6),
            terminal=terminal,
            release_conditions=release_conditions,
        )
        update_status(
            None,
            (
                "Two-H200 owner reached and released a decision-bearing terminal."
                if terminal
                else "Two-H200 owner ended without a decision-bearing terminal; maintenance release applies."
            ),
            spend,
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OwnerError as error:
        print(f"owner error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
