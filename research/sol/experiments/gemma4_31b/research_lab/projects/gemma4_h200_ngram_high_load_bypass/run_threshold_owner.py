#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import shlex
import subprocess
import threading
import time

import run_bench_owner as base


PROJECT = Path(__file__).resolve().parent
REMOTE = base.REMOTE
LOCAL_STATE = PROJECT / "FULL_TRAJECTORY_CONTROLLER.json"
DEADLINE = dt.datetime(2026, 7, 25, 1, 40, tzinfo=dt.timezone.utc)
REMOTE_STATE = "FULL_TRAJECTORY_OWNER.json"
REMOTE_OUTPUT = "full-trajectory"
PRIOR_SPEND = 0.0


def stage_file(ip: str, source: Path, target: str, mode: str = "0444") -> None:
    expected = base.digest(source)
    matched = base.ssh(
        ip,
        f"test -f {shlex.quote(target)} && "
        f"test \"$(sha256sum {shlex.quote(target)} | cut -d' ' -f1)\" "
        f"= {expected}",
        120,
    )
    if matched.returncode:
        temporary = f"{target}.{expected}.part"
        copied = base.scp_to(ip, source, temporary)
        if copied.returncode:
            raise RuntimeError(
                f"typed_staging_boundary:{source.name}:{copied.stderr[-1000:]}"
            )
        finalized = base.ssh(
            ip,
            f"test \"$(sha256sum {shlex.quote(temporary)} | cut -d' ' -f1)\" "
            f"= {expected} && mv -f {shlex.quote(temporary)} "
            f"{shlex.quote(target)} && chmod {mode} {shlex.quote(target)}",
            180,
        )
        if finalized.returncode:
            raise RuntimeError(f"typed_staging_verify_boundary:{source.name}")


def retrieve(ip: str, artifact: Path) -> Path:
    artifact.mkdir(parents=True, exist_ok=True)
    archive = "full-trajectory-compact.tar.gz"
    command = (
        f"cd {shlex.quote(REMOTE)} && tar -czf {archive} "
        f"{REMOTE_STATE} {REMOTE_STATE.replace('.json', '.log')} "
        f"{REMOTE_OUTPUT} remote_experiment.py candidate "
        "bound_inputs/MATERIALIZED_SHA256SUMS.txt && "
        f"sha256sum {archive} > {archive}.sha256"
    )
    archived = base.ssh(ip, command, 600)
    base.atomic(
        artifact / "RETRIEVAL_COMMAND.json",
        {
            "returncode": archived.returncode,
            "stdout": archived.stdout,
            "stderr": archived.stderr,
        },
    )
    if archived.returncode:
        raise RuntimeError("recoverable_retrieval_defect:archive")
    for suffix in ("", ".sha256"):
        copied = base.scp_from(
            ip, f"{REMOTE}/{archive}{suffix}", artifact / f"{archive}{suffix}"
        )
        if copied.returncode:
            raise RuntimeError("recoverable_retrieval_defect:scp")
    expected = (artifact / f"{archive}.sha256").read_text().split()[0]
    if base.digest(artifact / archive) != expected:
        raise RuntimeError("recoverable_retrieval_defect:hash")
    snapshot = base.run(
        [
            str(base.ARTIFACT_SNAPSHOT),
            "--archive",
            str(artifact / archive),
            "--root",
            str(artifact / "snapshots"),
        ]
    )
    if snapshot.returncode:
        raise RuntimeError("recoverable_retrieval_defect:snapshot")
    return Path(json.loads(snapshot.stdout)["destination"])


def remote_workload_present(inspection: subprocess.CompletedProcess[str]) -> bool:
    if inspection.returncode:
        return True
    lines = [line.strip() for line in inspection.stdout.splitlines() if line.strip()]
    if not lines:
        return False
    try:
        state = json.loads(lines[0])
    except json.JSONDecodeError:
        return True
    return bool(state.get("Running")) or len(lines) > 1


def maintenance_contents(ip: str, terminal: dict | None) -> tuple[dict, bool]:
    inspection = base.ssh(
        ip,
        "sudo docker inspect gemma4-ngram-high-load-bypass-candidate "
        "--format '{{json .State}}' 2>/dev/null || true; "
        "nvidia-smi --query-compute-apps=pid,used_memory "
        "--format=csv,noheader,nounits 2>/dev/null || true",
        60,
    )
    workload_present = remote_workload_present(inspection)
    full = terminal.get("full") if terminal else None
    contents = {
        "schema_version": 1,
        "project": base.NAME,
        "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "image": (
            "docker.io/lmsysorg/sglang@"
            "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
        ),
        "checkpoint": base.CHECKPOINT + " remains resident and read-only.",
        "runtime": "Pinned SGLang v0.5.13 FP8, page-1 E5M2 KV, threshold-8 repaired NGRAM bypass.",
        "result": terminal.get("result") if terminal else "threshold_owner_failure",
        "component_result": "exact_positive_threshold_component",
        "component_science_consumed": True,
        "suffix_result": "exact_suffix",
        "suffix_science_consumed": True,
        "full_result": full.get("arm") if full else None,
        "full_science_consumed": full is not None,
        "artifacts": "Content-addressed compact terminal, server log, request rows, events, and source identities retrieved project-locally.",
        "server_state": (
            "Candidate or GPU process remains after owner terminal; director inspection required before reuse."
            if workload_present
            else "No running candidate or GPU process remains; resident checkpoint, image, and caches remain reusable."
        ),
        "remote_inspection": inspection.stdout[-4000:],
        "gpu_processes": (
            "present in remote_inspection"
            if workload_present
            else "none observed at release"
        ),
        "caches": "Image, checkpoint, CUDA graph, JIT, tokenizer, and runtime caches retained.",
    }
    return contents, workload_present


def main() -> int:
    claimed_at = base.claim()
    run_id = dt.datetime.now(dt.timezone.utc).strftime(
        "threshold-transition-%Y%m%dt%H%M%Sz"
    )
    artifact = PROJECT / "artifacts" / run_id
    artifact.mkdir(parents=True, exist_ok=False)
    ip = base.instance_ip()
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(30):
            result = base.pool("heartbeat", "--project", base.NAME)
            base.atomic(
                PROJECT / "OWNER_HEARTBEAT.json",
                {
                    "at_utc": base.utc_now(),
                    "returncode": result.returncode,
                    "stderr": result.stderr,
                },
            )

    threading.Thread(target=heartbeat, daemon=True).start()
    for _ in range(200):
        if LOCAL_STATE.exists():
            break
        time.sleep(0.02)
    owner = json.loads(LOCAL_STATE.read_text())
    active = {
        "unit": str(LOCAL_STATE),
        "unit_manager": "pid",
        "pid": owner["pid"],
        "start_ticks": owner["start_ticks"],
        "deadline_utc": DEADLINE.isoformat().replace("+00:00", "Z"),
        "artifact_root": str(artifact),
        "bench_id": base.BENCH,
        "remote_root": REMOTE,
        "expected_terminal": f"{REMOTE_OUTPUT}/FINAL_TERMINAL.json",
    }
    base.update_status(
        active,
        "Untouched fixed 1,036-request trajectory owner active; no component, prefix, or suffix replay is permitted.",
        PRIOR_SPEND,
    )

    try:
        created = base.ssh(
            ip,
            f"mkdir -p {shlex.quote(REMOTE + '/candidate')}",
            60,
        )
        if created.returncode:
            raise RuntimeError("typed_staging_boundary:mkdir")
        stage_file(
            ip,
            PROJECT / "candidate/high_load_bypass.py",
            REMOTE + "/candidate/high_load_bypass.py",
        )
        stage_file(
            ip,
            PROJECT / "candidate/sitecustomize.py",
            REMOTE + "/candidate/sitecustomize.py",
        )
        stage_file(
            ip,
            PROJECT / "remote_experiment.py",
            REMOTE + "/remote_experiment.py",
            "0555",
        )
        stage_file(
            ip,
            base.DETACHED_OWNER,
            REMOTE + "/detached-owner",
            "0555",
        )
        clean = base.ssh(
            ip,
            f"test ! -e {shlex.quote(REMOTE + '/' + REMOTE_OUTPUT)} && "
            f"test ! -e {shlex.quote(REMOTE + '/' + REMOTE_STATE)}",
            60,
        )
        if clean.returncode:
            raise RuntimeError("typed_no_replay_boundary:remote_output_exists")
        launched = base.ssh(
            ip,
            f"cd {shlex.quote(REMOTE)} && ./detached-owner start "
            f"--state {shlex.quote(REMOTE + '/' + REMOTE_STATE)} "
            f"--log {shlex.quote(REMOTE + '/' + REMOTE_STATE.replace('.json', '.log'))} "
            f"--cwd {shlex.quote(REMOTE)} --unit-manager pid -- "
            "python3 remote_experiment.py",
            60,
        )
        if launched.returncode:
            raise RuntimeError(
                "typed_remote_owner_boundary:launch:" + launched.stderr[-1000:]
            )

        terminal_present = False
        owner_live = True
        while dt.datetime.now(dt.timezone.utc) < DEADLINE:
            status = base.ssh(
                ip,
                f"cd {shlex.quote(REMOTE)} && ./detached-owner status "
                f"--state {shlex.quote(REMOTE_STATE)} 2>/dev/null; "
                f"test -f {REMOTE_OUTPUT}/FINAL_TERMINAL.json "
                "&& echo FINAL_PRESENT || true",
                45,
            )
            terminal_present = "FINAL_PRESENT" in status.stdout
            owner_live = '"live": true' in status.stdout
            base.atomic(
                artifact / "REMOTE_STATE.json",
                {
                    "at_utc": base.utc_now(),
                    "returncode": status.returncode,
                    "stdout": status.stdout,
                    "stderr": status.stderr,
                    "terminal_present": terminal_present,
                    "owner_live": owner_live,
                },
            )
            if terminal_present or not owner_live:
                break
            time.sleep(15)

        snapshot = retrieve(ip, artifact)
        terminal_path = snapshot / REMOTE_OUTPUT / "FINAL_TERMINAL.json"
        terminal = (
            json.loads(terminal_path.read_text()) if terminal_path.exists() else None
        )
        spend = base.spend_since(claimed_at, PRIOR_SPEND)
        base.atomic(
            artifact / "OWNER_TERMINAL.json",
            {
                "terminal_present": terminal is not None,
                "remote_owner_live_at_retrieval": owner_live,
                "deadline_reached": dt.datetime.now(dt.timezone.utc) >= DEADLINE,
                "snapshot": str(snapshot),
                "actual_spend_usd": spend,
            },
        )
        contents, workload_present = maintenance_contents(ip, terminal)
        base.atomic(PROJECT / "BENCH_CONTENTS.json", contents)
        release_args = [
            "release",
            "--project",
            base.NAME,
            "--contents",
            str(PROJECT / "BENCH_CONTENTS.json"),
        ]
        if workload_present:
            release_args.extend(["--condition", "maintenance"])
        released = base.pool(*release_args)
        if released.returncode:
            raise RuntimeError(
                "typed_pool_boundary:release:" + released.stderr[-1000:]
            )
        status_path = PROJECT / "STATUS.json"
        status_value = json.loads(status_path.read_text())
        status_value["active_session"] = None
        status_value["actual_spend_usd"] = spend
        status_value["last_researcher_run"] = {
            "at_utc": base.utc_now(),
            "artifact_root": str(artifact),
            "snapshot": str(snapshot),
        }
        if terminal is None:
            status_value["status"] = "blocked"
            status_value["summary"] = (
                "Threshold owner ended without an interpretable terminal; raw remote state and server diagnostics were retrieved before maintenance release."
            )
            status_value["next_action"] = (
                "Director disposition required for the retrieved no-terminal boundary."
            )
        else:
            full = terminal.get("full")
            status_value["status"] = "complete"
            status_value["summary"] = (
                f"Full trajectory={terminal['result']}; "
                f"exact={full['exact_index_aligned_semantics'] if full else False}; "
                f"cumulative provider exposure=${spend:.6f}."
            )
            status_value["next_action"] = (
                "Use the content-addressed threshold terminal for portfolio disposition; replay no component, settled prefix, suffix, or endpoint."
            )
        base.atomic(status_path, status_value)
        return 0 if terminal is not None else 2
    finally:
        stop.set()


if __name__ == "__main__":
    raise SystemExit(main())
