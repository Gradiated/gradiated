#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import sys
import threading
import time


PROJECT = "gemma4_hopper_packed_m384_verifier"
BENCH = "h100-paged-fp8-e00mkpyvykfak0bg1m"
ROOT = pathlib.Path(__file__).resolve().parent
LAB = ROOT.parent.parent
IDENTITY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
READMISSION = ROOT / "GRAPH_CAPTURE_REPAIR_READMISSION.json"
READY = ROOT / "GRAPH_CAPTURE_REPAIR_READY.json"
MANIFEST = ROOT / "inputs/endpoint/ENDPOINT_INPUT_MANIFEST.json"
REPAIR_MANIFEST = ROOT / "inputs/endpoint/GRAPH_REPAIR_INPUT_MANIFEST.json"
STATE = ROOT / "GRAPH_REPAIR_OWNER_PROGRESS.json"
HEARTBEAT = ROOT / "GRAPH_REPAIR_OWNER_HEARTBEAT.json"
TERMINAL = ROOT / "GRAPH_REPAIR_OWNER_TERMINAL.json"
LOCAL_ARTIFACTS = ROOT / "artifacts/graph-repair"
REMOTE_ROOT = "/home/glmrunner/gemma4_hopper_packed_m384_endpoint"
DEADLINE = dt.datetime.fromisoformat("2026-07-26T19:55:00+00:00")
PRIOR_SPEND = 2.134908377952046
RATE = 2.95


def utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def run(
    command: list[str], timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def remain(reserve: float = 0.0) -> float:
    seconds = (DEADLINE - dt.datetime.now(dt.UTC)).total_seconds() - reserve
    if seconds <= 0:
        raise TimeoutError("candidate_release_deadline_reached")
    return seconds


def pool(action: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            "-m",
            "grad_research.gpu_pool",
            "--lab",
            str(LAB),
            action,
            "--project",
            PROJECT,
            "--bench",
            BENCH,
            *extra,
        ],
        timeout=min(60, remain()),
    )


def inventory_bench() -> dict:
    value = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = value["benches"]
    bench = (
        benches.get(BENCH)
        if isinstance(benches, dict)
        else next((row for row in benches if row.get("id") == BENCH), None)
    )
    if not isinstance(bench, dict):
        raise RuntimeError("bound_bench_missing")
    return bench


def progress(phase: str, **extra: object) -> None:
    atomic(STATE, {"at_utc": utc(), "phase": phase, **extra})


def verify_admission() -> None:
    if not READMISSION.is_file():
        raise RuntimeError("graph_repair_readmission_missing")
    readmission = json.loads(READMISSION.read_text())
    evidence = readmission.get("evidence") or {}
    bench = readmission.get("bench") or {}
    ready_sha = digest(READY)
    if (
        readmission.get("project") != PROJECT
        or evidence.get("graph_capture_repair_ready_sha256") != ready_sha
        or bench.get("id") != BENCH
        or bench.get("candidate_release_deadline_utc")
        != "2026-07-26T19:55:00Z"
        or not readmission.get("candidate_only_resume", False)
    ):
        raise RuntimeError("graph_repair_readmission_binding_mismatch")
    ready = json.loads(READY.read_text())
    owner = ready.get("retained_repair_owner") or {}
    if (
        owner.get("path") != "run_graph_repair_owner.py"
        or owner.get("sha256") != digest(ROOT / "run_graph_repair_owner.py")
        or ready.get("gpu_claim_allowed") is not False
    ):
        raise RuntimeError("graph_repair_owner_binding_mismatch")


def ssh(
    user: str, host: str, command: str, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "ssh",
            "-i",
            str(IDENTITY),
            "-o",
            "BatchMode=yes",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            "-o",
            "StrictHostKeyChecking=yes",
            f"{user}@{host}",
            command,
        ],
        timeout=timeout,
    )


def scp_to(
    user: str, host: str, source: pathlib.Path, destination: str
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "scp",
            "-p",
            "-i",
            str(IDENTITY),
            "-o",
            "BatchMode=yes",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            "-o",
            "StrictHostKeyChecking=yes",
            str(source),
            f"{user}@{host}:{destination}",
        ],
        timeout=remain(120),
    )


def scp_from(
    user: str, host: str, source: str, destination: pathlib.Path
) -> subprocess.CompletedProcess[str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    return run(
        [
            "scp",
            "-p",
            "-i",
            str(IDENTITY),
            "-o",
            "BatchMode=yes",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            "-o",
            "StrictHostKeyChecking=yes",
            f"{user}@{host}:{source}",
            str(destination),
        ],
        timeout=remain(60),
    )


def verify_local_manifest() -> tuple[dict, dict]:
    manifest = json.loads(MANIFEST.read_text())
    repair_manifest = json.loads(REPAIR_MANIFEST.read_text())
    rows = {
        row["path"]: row
        for row in manifest["packet_files"] + manifest["checkpoint_files"]
    }
    for row in repair_manifest["files"]:
        if (
            row["path"] != "input/ENDPOINT_INPUT_MANIFEST.json"
            and rows.get(row["path"]) != row
        ):
            raise RuntimeError(f"repair_manifest_not_full_manifest:{row['path']}")
        source = ROOT / row["source"]
        if (
            not source.is_file()
            or source.stat().st_size != row["bytes"]
            or digest(source) != row["sha256"]
        ):
            raise RuntimeError(f"local_repair_input_mismatch:{row['path']}")
    return manifest, repair_manifest


def patch_retained_root(user: str, host: str) -> None:
    manifest, repair_manifest = verify_local_manifest()
    stage = f"{REMOTE_ROOT}/.graph-repair-stage-{os.getpid()}"
    prepared = ssh(
        user,
        host,
        shlex.join(
            [
                "bash",
                "-lc",
                f"rm -rf {shlex.quote(stage)} && mkdir -p {shlex.quote(stage)}",
            ]
        ),
        timeout=remain(180),
    )
    if prepared.returncode:
        raise RuntimeError(
            f"remote_repair_stage_prepare_failed:{prepared.stderr[-1000:]}"
        )
    repair_manifest_copy = scp_to(
        user,
        host,
        REPAIR_MANIFEST,
        f"{stage}/input/GRAPH_REPAIR_INPUT_MANIFEST.json",
    )
    if repair_manifest_copy.returncode:
        raise RuntimeError(
            "repair_manifest_copy_failed:"
            f"{repair_manifest_copy.stderr[-1000:]}"
        )
    for ordinal, row in enumerate(repair_manifest["files"], start=1):
        progress(
            "repair_input_copy",
            ordinal=ordinal,
            total=len(repair_manifest["files"]),
            path=row["path"],
        )
        parent = pathlib.PurePosixPath(row["path"]).parent.as_posix()
        made = ssh(
            user,
            host,
            shlex.join(["mkdir", "-p", f"{stage}/{parent}"]),
            timeout=remain(120),
        )
        if made.returncode:
            raise RuntimeError(f"repair_stage_parent_failed:{row['path']}")
        copied = scp_to(
            user, host, ROOT / row["source"], f"{stage}/{row['path']}"
        )
        if copied.returncode:
            raise RuntimeError(
                f"repair_input_copy_failed:{row['path']}:{copied.stderr[-1000:]}"
            )

    verifier = """
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); stage=pathlib.Path(sys.argv[2])
manifest=json.loads((stage/'input/ENDPOINT_INPUT_MANIFEST.json').read_text())
def d(path):
 h=hashlib.sha256()
 with path.open('rb') as handle:
  for chunk in iter(lambda:handle.read(8*1024*1024),b''): h.update(chunk)
 return h.hexdigest()
repair_manifest=json.loads((stage/'input/GRAPH_REPAIR_INPUT_MANIFEST.json').read_text())
assert d(stage/'input/ENDPOINT_INPUT_MANIFEST.json')==repair_manifest['full_manifest_sha256']
repair={row['path']:row for row in repair_manifest['files']}
for row in manifest['packet_files']+manifest['checkpoint_files']:
 path=(stage if row['path'] in repair else root)/row['path']
 assert path.is_file() and path.stat().st_size==row['bytes'],row['path']
 assert d(path)==row['sha256'],row['path']
print('retained_root_and_repair_verified')
"""
    checked = ssh(
        user,
        host,
        shlex.join(["python3", "-c", verifier, REMOTE_ROOT, stage]),
        timeout=remain(900),
    )
    if (
        checked.returncode
        or checked.stdout.strip() != "retained_root_and_repair_verified"
    ):
        raise RuntimeError(
            f"retained_root_verification_failed:{checked.stdout[-500:]}:"
            f"{checked.stderr[-1500:]}"
        )
    move_paths = [
        row["path"] for row in repair_manifest["files"]
    ] + ["input/GRAPH_REPAIR_INPUT_MANIFEST.json"]
    moves = " && ".join(
        f"mv -f {shlex.quote(stage + '/' + path)} "
        f"{shlex.quote(REMOTE_ROOT + '/' + path)}"
        for path in move_paths
    )
    promoted = ssh(
        user,
        host,
        shlex.join(
            [
                "bash",
                "-lc",
                f"{moves} && rm -rf {shlex.quote(stage)}",
            ]
        ),
        timeout=remain(180),
    )
    if promoted.returncode:
        raise RuntimeError(
            f"repair_input_promotion_failed:{promoted.stderr[-1000:]}"
        )
    progress(
        "retained_root_repair_promoted",
        manifest_sha256=digest(MANIFEST),
        repair_manifest_sha256=digest(REPAIR_MANIFEST),
    )


def rotate_remote_artifacts(user: str, host: str, attempt: int) -> None:
    command = (
        f"cd {shlex.quote(REMOTE_ROOT)} && "
        f"if [ -d artifacts ]; then mv artifacts "
        f"artifacts.pre-graph-repair-{attempt}; fi && mkdir artifacts"
    )
    result = ssh(
        user,
        host,
        shlex.join(["bash", "-lc", command]),
        timeout=remain(120),
    )
    if result.returncode:
        raise RuntimeError(f"artifact_rotation_failed:{result.stderr[-1000:]}")


def retrieve(user: str, host: str, attempt: int) -> dict:
    destination = LOCAL_ARTIFACTS / f"attempt-{attempt}"
    destination.mkdir(parents=True, exist_ok=True)
    remote_archive = f"{REMOTE_ROOT}/graph-repair-attempt-{attempt}.tar.gz"
    package = ssh(
        user,
        host,
        shlex.join(
            [
                "bash",
                "-lc",
                f"cd {shlex.quote(REMOTE_ROOT)} && "
                f"tar -czf {shlex.quote(remote_archive)} artifacts",
            ]
        ),
        timeout=remain(180),
    )
    copied = scp_from(
        user, host, remote_archive, destination / "artifacts.tar.gz"
    )
    report: dict = {
        "package_exit": package.returncode,
        "package_stderr": package.stderr[-1500:],
        "scp_exit": copied.returncode,
        "scp_stderr": copied.stderr[-1500:],
    }
    for name in ("INVOCATION_STATE.json", "ENDPOINT_TERMINAL.json"):
        item = scp_from(
            user,
            host,
            f"{REMOTE_ROOT}/artifacts/{name}",
            destination / name,
        )
        report[name] = {
            "exit": item.returncode,
            "stderr": item.stderr[-800:],
        }
    atomic(destination / "RETRIEVAL.json", report)
    return report


def update_status(actual_spend: float, active: dict | None) -> None:
    path = ROOT / "STATUS.json"
    value = json.loads(path.read_text())
    value["actual_spend_usd"] = round(actual_spend, 6)
    value["active_session"] = active
    temporary = path.with_suffix(".json.part")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def release(
    claimed_at: str, final: dict, condition: str = "maintenance"
) -> None:
    start = dt.datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
    elapsed = max(0.0, (dt.datetime.now(dt.UTC) - start).total_seconds())
    cost = PRIOR_SPEND + elapsed * RATE / 3600.0
    final.update(
        {
            "claimed_at": claimed_at,
            "claim_seconds": elapsed,
            "claim_cost_usd": elapsed * RATE / 3600.0,
            "actual_spend_usd": cost,
            "released_at_utc": utc(),
        }
    )
    atomic(TERMINAL, final)
    contents = {
        "schema_version": 1,
        "project": PROJECT,
        "result": final.get("classification"),
        "scientific_terminal": (
            "candidate_endpoint_consumed"
            if final.get("endpoint_terminal")
            else "candidate_endpoint_unconsumed_or_unknown"
        ),
        "candidate_cuda_started": bool(
            (final.get("invocation") or {}).get("candidate_science_started")
        ),
        "checkpoint": (
            "Verified retained checkpoint at "
            "/home/glmrunner/gemma4_hopper_packed_m384_endpoint/checkpoint."
        ),
        "image": "Pinned SGLang v0.5.13 image retained.",
        "artifacts": str(LOCAL_ARTIFACTS),
        "server_state": (
            "Healthy candidate container retained when endpoint terminal exists; "
            "director maintenance disposition required."
        ),
    }
    contents_path = ROOT / "GRAPH_REPAIR_RELEASE_CONTENTS.json"
    atomic(contents_path, contents)
    released = pool(
        "release",
        "--expected-claimed-at",
        claimed_at,
        "--condition",
        condition,
        "--contents",
        str(contents_path),
    )
    final["release_exit"] = released.returncode
    final["release_stdout"] = released.stdout[-1800:]
    final["release_stderr"] = released.stderr[-1800:]
    atomic(TERMINAL, final)
    update_status(cost, None)


def invocation_for(attempt: int) -> tuple[dict | None, dict | None]:
    root = LOCAL_ARTIFACTS / f"attempt-{attempt}"
    invocation_path = root / "INVOCATION_STATE.json"
    terminal_path = root / "ENDPOINT_TERMINAL.json"
    invocation = (
        json.loads(invocation_path.read_text())
        if invocation_path.is_file()
        else None
    )
    endpoint = (
        json.loads(terminal_path.read_text())
        if terminal_path.is_file()
        else None
    )
    return invocation, endpoint


def repair_wait(
    final: dict,
    claimed_at: str,
    generation: int,
    science_started: bool | None,
) -> bool:
    diagnostic = (
        LOCAL_ARTIFACTS / f"attempt-{generation}" / "OWNER_DIAGNOSTIC.json"
    )
    atomic(diagnostic, final)
    repair_id = f"graph-repair-{generation}-{int(time.time())}"
    deadline = (DEADLINE - dt.timedelta(seconds=90)).isoformat().replace(
        "+00:00", "Z"
    )
    retry_scope = (
        "repair only candidate result retrieval or offline consumer; the c32 "
        "candidate request is consumed and must not replay"
        if science_started is True
        else "repair only the graph-capture wrapper, candidate server launcher, "
        "or retrieval boundary; control is persisted and candidate request remains unsubmitted"
        if science_started is False
        else "repair classification or retrieval only; candidate submission state "
        "is unknown and no request may replay"
    )
    ready = run(
        [
            "/root/workspace/research/factory/tools/repair-handshake",
            "ready",
            "--root",
            str(ROOT),
            "--repair-id",
            repair_id,
            "--deadline",
            deadline,
            "--failure-kind",
            "candidate_graph_capture_or_consumer",
            "--diagnostic",
            str(diagnostic),
            "--retry-scope",
            retry_scope,
        ],
        timeout=30,
    )
    final.update(
        {
            "repair_id": repair_id,
            "repair_generation": generation,
            "repair_ready_exit": ready.returncode,
            "repair_ready_stdout": ready.stdout[-1200:],
            "repair_ready_stderr": ready.stderr[-1200:],
        }
    )
    atomic(TERMINAL, final)
    progress(
        "repair_ready",
        repair_id=repair_id,
        generation=generation,
        candidate_science_started=science_started,
        claimed_at=claimed_at,
    )
    wait = run(
        [
            "/root/workspace/research/factory/tools/repair-handshake",
            "wait",
            "--root",
            str(ROOT),
            "--repair-id",
            repair_id,
        ],
        timeout=max(1, int(remain(90))),
    )
    final["repair_wait_exit"] = wait.returncode
    final["repair_wait_stdout"] = wait.stdout[-1200:]
    atomic(TERMINAL, final)
    return wait.returncode == 0 and science_started is False


def main() -> int:
    verify_admission()
    if not IDENTITY.is_file() or not KNOWN_HOSTS.is_file():
        raise RuntimeError("ssh_identity_or_known_hosts_missing")
    if dt.datetime.now(dt.UTC) >= DEADLINE:
        raise RuntimeError("candidate_release_deadline_elapsed_before_claim")
    claimed = pool("claim", "--lease-seconds", "3600")
    if claimed.returncode:
        raise RuntimeError(f"sole_bench_claim_failed:{claimed.stderr[-1200:]}")
    bench = inventory_bench()
    claim = bench.get("claim") or {}
    if bench.get("status") != "claimed" or claim.get("project") != PROJECT:
        raise RuntimeError("claim_not_owned_after_claim")
    resource = bench["resource"]
    if (
        resource.get("ssh_user") != "glmrunner"
        or resource.get("known_hosts_namespace") != str(KNOWN_HOSTS)
    ):
        raise RuntimeError("unexpected_ssh_binding")
    claimed_at = str(claim["claimed_at"])
    user = str(resource["ssh_user"])
    host = str(resource["public_ipv4"])
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(30):
            result = pool("heartbeat")
            atomic(
                HEARTBEAT,
                {
                    "at_utc": utc(),
                    "exit": result.returncode,
                    "stdout": result.stdout[-600:],
                    "stderr": result.stderr[-600:],
                },
            )

    threading.Thread(target=beat, daemon=True).start()
    final: dict = {
        "schema_version": 1,
        "project": PROJECT,
        "bench": BENCH,
        "claimed_at": claimed_at,
        "started_at_utc": utc(),
        "classification": "unknown",
    }
    try:
        progress("claimed", claimed_at=claimed_at, host=host)
        attempt = 1
        while True:
            try:
                patch_retained_root(user, host)
                rotate_remote_artifacts(user, host, attempt)
                progress(
                    "candidate_graph_capture_started",
                    attempt=attempt,
                    claimed_at=claimed_at,
                )
                outer = [
                    "python3",
                    f"{REMOTE_ROOT}/input/candidate_resume.py",
                    "--root",
                    REMOTE_ROOT,
                    "--manifest",
                    f"{REMOTE_ROOT}/input/ENDPOINT_INPUT_MANIFEST.json",
                    "--oracle",
                    f"{REMOTE_ROOT}/input/CONTROL_TOKEN_ORACLE.json",
                    "--absolute-deadline-epoch",
                    "1785095700",
                ]
                command = (
                    f"{shlex.join(outer)} > "
                    f"{shlex.quote(REMOTE_ROOT)}/artifacts/candidate_resume.stdout "
                    f"2> {shlex.quote(REMOTE_ROOT)}/artifacts/candidate_resume.stderr"
                )
                worker = ssh(
                    user,
                    host,
                    shlex.join(["bash", "-lc", command]),
                    timeout=remain(90),
                )
                final.update(
                    {
                        "attempt": attempt,
                        "worker_exit": worker.returncode,
                        "worker_stdout": worker.stdout[-2000:],
                        "worker_stderr": worker.stderr[-2000:],
                    }
                )
                final["retrieval"] = retrieve(user, host, attempt)
                invocation, endpoint = invocation_for(attempt)
                final["invocation"] = invocation
                final["endpoint_terminal"] = endpoint
                if endpoint and endpoint.get("classification") in {
                    "endpoint_positive",
                    "endpoint_nonpositive",
                    "semantic_or_path_reject",
                }:
                    final["classification"] = endpoint["classification"]
                    progress(
                        "scientific_terminal_retrieved",
                        classification=final["classification"],
                        attempt=attempt,
                    )
                    release(claimed_at, final)
                    return 0
            except Exception as error:
                final.update(
                    {
                        "attempt": attempt,
                        "exception": repr(error),
                    }
                )
                invocation, endpoint = invocation_for(attempt)
                final["invocation"] = invocation
                final["endpoint_terminal"] = endpoint
            invocation = final.get("invocation")
            science_started = (
                invocation.get("candidate_science_started")
                if isinstance(invocation, dict)
                and "candidate_science_started" in invocation
                else None
            )
            final["classification"] = (
                "recoverable_post_submission_consumer_or_retrieval_defect"
                if science_started is True
                else "recoverable_pre_submission_graph_capture_or_launcher_defect"
                if science_started is False
                else "unknown_candidate_submission_state_retrieval_required"
            )
            atomic(TERMINAL, final)
            if not repair_wait(final, claimed_at, attempt, science_started):
                final["classification"] = "repair_deadline_or_handoff"
                release(claimed_at, final)
                return 1
            attempt += 1
    except Exception as error:
        final.update(
            {
                "classification": "owner_exception_pending_deadline_release",
                "exception": repr(error),
            }
        )
        atomic(TERMINAL, final)
        if dt.datetime.now(dt.UTC) < DEADLINE - dt.timedelta(seconds=120):
            repair_wait(final, claimed_at, 99, None)
        final["classification"] = "repair_deadline_or_handoff"
        release(claimed_at, final)
        return 1
    finally:
        stop.set()


if __name__ == "__main__":
    raise SystemExit(main())
