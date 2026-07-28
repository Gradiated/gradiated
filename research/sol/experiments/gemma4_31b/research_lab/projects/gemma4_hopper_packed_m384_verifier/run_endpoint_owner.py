#!/usr/bin/env python3
"""Durable host-side owner for the one admitted packed-M384 endpoint pair."""
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
READMISSION = ROOT / "DIRECTOR_H100_PACKED_M384_ENDPOINT_READMISSION_20260726T1741Z.json"
BINDING = ROOT / "ENDPOINT_OWNER_BINDING.json"
MANIFEST = ROOT / "inputs/endpoint/ENDPOINT_INPUT_MANIFEST.json"
STATE = ROOT / "ENDPOINT_OWNER_PROGRESS.json"
TERMINAL = ROOT / "ENDPOINT_OWNER_TERMINAL.json"
ARTIFACTS = ROOT / "artifacts/endpoint"
DEADLINE = dt.datetime.fromisoformat("2026-07-26T19:00:00+00:00")
PRIOR_SPEND = 0.34
RATE = 2.95
REMOTE_ROOT = "/home/glmrunner/gemma4_hopper_packed_m384_endpoint"


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


def run(command: list[str], timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout)


def remain(reserve: float = 0.0) -> float:
    seconds = (DEADLINE - dt.datetime.now(dt.UTC)).total_seconds() - reserve
    if seconds <= 0:
        raise TimeoutError("endpoint_release_deadline_reached")
    return seconds


def pool(action: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return run(
        [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), action,
         "--project", PROJECT, "--bench", BENCH, *extra],
        timeout=min(60, remain()),
    )


def inventory_bench() -> dict:
    value = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = value["benches"]
    if isinstance(benches, dict):
        bench = benches.get(BENCH)
    else:
        bench = next((row for row in benches if row.get("id") == BENCH), None)
    if not isinstance(bench, dict):
        raise RuntimeError("bound_bench_missing")
    return bench


def verify_binding() -> None:
    binding = json.loads(BINDING.read_text())
    expected_readmission = "4e8e8c4fb3005a7f5a66d8efdcff627b58273f59065f176265ab2a86fbc90063"
    if digest(READMISSION) != expected_readmission:
        raise RuntimeError("readmission_digest_mismatch")
    if binding.get("readmission_sha256") != expected_readmission:
        raise RuntimeError("owner_readmission_binding_mismatch")
    if binding.get("owner_path") != "run_endpoint_owner.py" or binding.get("owner_sha256") != digest(ROOT / "run_endpoint_owner.py"):
        raise RuntimeError("owner_source_binding_mismatch")


def ssh(user: str, host: str, command: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return run(["ssh", "-i", str(IDENTITY), "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes", f"{user}@{host}", command], timeout=timeout)


def scp_to(user: str, host: str, source: pathlib.Path, destination: str) -> subprocess.CompletedProcess[str]:
    return run(["scp", "-p", "-i", str(IDENTITY), "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes", str(source), f"{user}@{host}:{destination}"], timeout=remain(120))


def scp_from(user: str, host: str, source: str, destination: pathlib.Path) -> subprocess.CompletedProcess[str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    return run(["scp", "-p", "-i", str(IDENTITY), "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes", f"{user}@{host}:{source}", str(destination)], timeout=remain(60))


def progress(phase: str, **extra: object) -> None:
    atomic(STATE, {"at_utc": utc(), "phase": phase, **extra})


def manifest_rows() -> tuple[dict, list[dict]]:
    manifest = json.loads(MANIFEST.read_text())
    rows = manifest["packet_files"] + manifest["checkpoint_files"]
    for row in rows:
        source = ROOT / row["source"]
        relative = pathlib.PurePosixPath(row["path"])
        if not source.is_file() or relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"unsafe_or_missing_manifest_input:{row['path']}")
        if source.stat().st_size != row["bytes"] or digest(source) != row["sha256"]:
            raise RuntimeError(f"local_manifest_mismatch:{row['path']}")
    return manifest, rows


def remote_stage(user: str, host: str) -> None:
    manifest, rows = manifest_rows()
    manifest_sha = digest(MANIFEST)
    temporary = f"{REMOTE_ROOT}.stage-{os.getpid()}"
    progress("staging_prepare", remote_root=REMOTE_ROOT, manifest_sha256=manifest_sha)
    prepare = ssh(user, host, shlex.join(["bash", "-lc", f"rm -rf {shlex.quote(temporary)}; mkdir -p {shlex.quote(temporary)}/input {shlex.quote(temporary)}/checkpoint {shlex.quote(temporary)}/artifacts"]), timeout=remain(180))
    if prepare.returncode:
        raise RuntimeError(f"remote_stage_prepare_failed:{prepare.stderr[-1000:]}")
    manifest_copy = scp_to(user, host, MANIFEST, f"{temporary}/input/ENDPOINT_INPUT_MANIFEST.json")
    if manifest_copy.returncode:
        raise RuntimeError(f"manifest_copy_failed:{manifest_copy.stderr[-1000:]}")
    for index, row in enumerate(rows, start=1):
        source = ROOT / row["source"]
        parent = pathlib.PurePosixPath(row["path"]).parent.as_posix()
        made = ssh(user, host, shlex.join(["mkdir", "-p", f"{temporary}/{parent}" ]), timeout=remain(120))
        if made.returncode:
            raise RuntimeError(f"remote_parent_prepare_failed:{row['path']}:{made.stderr[-500:]}")
        progress("staging_copy", file=row["path"], ordinal=index, total=len(rows), bytes=row["bytes"])
        copied = scp_to(user, host, source, f"{temporary}/{row['path']}")
        if copied.returncode:
            raise RuntimeError(f"immutable_copy_failed:{row['path']}:{copied.stderr[-1000:]}")
    verifier = """
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); expected=sys.argv[2]
def d(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
 return h.hexdigest()
m=root/'input/ENDPOINT_INPUT_MANIFEST.json'
assert d(m)==expected
v=json.loads(m.read_text())
for r in v['packet_files']+v['checkpoint_files']:
 p=root/r['path']; assert p.is_file() and not p.is_symlink() and p.stat().st_size==r['bytes'] and d(p)==r['sha256'],r['path']
print('manifest_verified')
"""
    checked = ssh(user, host, shlex.join(["python3", "-c", verifier, temporary, manifest_sha]), timeout=remain(600))
    if checked.returncode or checked.stdout.strip() != "manifest_verified":
        raise RuntimeError(f"remote_manifest_verification_failed:{checked.stdout[-400:]}:{checked.stderr[-1000:]}")
    promoted = ssh(user, host, shlex.join(["bash", "-lc", f"rm -rf {shlex.quote(REMOTE_ROOT)}; mv {shlex.quote(temporary)} {shlex.quote(REMOTE_ROOT)}"]), timeout=remain(180))
    if promoted.returncode:
        raise RuntimeError(f"remote_stage_promotion_failed:{promoted.stderr[-1000:]}")
    atomic(ROOT / "ENDPOINT_STAGING.json", {"at_utc": utc(), "remote_root": REMOTE_ROOT, "manifest_sha256": manifest_sha, "files": len(rows), "checkpoint_bytes": manifest["checkpoint_total_bytes"], "state": "atomically_promoted"})
    progress("staging_complete", remote_root=REMOTE_ROOT)


def retrieve(user: str, host: str) -> dict:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    remote_archive = f"{REMOTE_ROOT}/endpoint-artifacts.tar.gz"
    package = ssh(user, host, shlex.join(["bash", "-lc", f"cd {shlex.quote(REMOTE_ROOT)} && tar -czf {shlex.quote(remote_archive)} artifacts"]), timeout=remain(180))
    report = {"package_exit": package.returncode, "package_stderr": package.stderr[-1200:]}
    copied = scp_from(user, host, remote_archive, ARTIFACTS / "endpoint-artifacts.tar.gz")
    report.update({"scp_exit": copied.returncode, "scp_stderr": copied.stderr[-1200:]})
    for name in ("artifacts/ENDPOINT_TERMINAL.json", "artifacts/INVOCATION_STATE.json"):
        local = ARTIFACTS / pathlib.PurePosixPath(name).name
        item = scp_from(user, host, f"{REMOTE_ROOT}/{name}", local)
        report[name] = {"exit": item.returncode, "stderr": item.stderr[-600:]}
    atomic(ARTIFACTS / "RETRIEVAL.json", report)
    return report


def update_status(actual_spend: float, active: dict | None) -> None:
    path = ROOT / "STATUS.json"
    value = json.loads(path.read_text())
    value["actual_spend_usd"] = round(actual_spend, 6)
    value["active_session"] = active
    temporary = path.with_suffix(".json.part")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def release(claimed_at: str, final: dict, condition: str) -> None:
    elapsed = max(0.0, time.time() - dt.datetime.fromisoformat(claimed_at.replace("Z", "+00:00")).timestamp())
    cost = PRIOR_SPEND + elapsed * RATE / 3600.0
    final.update({"claimed_at": claimed_at, "claim_seconds": elapsed, "claim_cost_usd": elapsed * RATE / 3600.0, "actual_spend_usd": cost, "released_at_utc": utc()})
    atomic(TERMINAL, final)
    contents = {"project": PROJECT, "result": final.get("classification"), "candidate_cuda_started": bool((final.get("invocation") or {}).get("candidate_science_started")), "artifacts": str(ARTIFACTS), "checkpoint": "Project-local immutable endpoint checkpoint staged and verified at /home/glmrunner/gemma4_hopper_packed_m384_endpoint/checkpoint.", "image": "Pinned SGLang v0.5.13 image pulled/retained when endpoint launch passed.", "server_state": "Candidate container retained if ENDPOINT_TERMINAL.json exists; maintenance disposition required."}
    contents_path = ROOT / "ENDPOINT_RELEASE_CONTENTS.json"
    atomic(contents_path, contents)
    released = pool("release", "--expected-claimed-at", claimed_at, "--condition", condition, "--contents", str(contents_path))
    final["release_exit"] = released.returncode
    final["release_stdout"] = released.stdout[-1600:]
    final["release_stderr"] = released.stderr[-1600:]
    atomic(TERMINAL, final)
    update_status(cost, None)


def main() -> int:
    verify_binding()
    if not IDENTITY.is_file() or not KNOWN_HOSTS.is_file():
        raise RuntimeError("ssh_identity_or_known_hosts_missing")
    if dt.datetime.now(dt.UTC) >= DEADLINE:
        raise RuntimeError("release_deadline_elapsed_before_claim")
    claimed = pool("claim", "--lease-seconds", "3600")
    if claimed.returncode:
        raise RuntimeError(f"sole_bench_claim_failed:{claimed.stderr[-1200:]}")
    bench = inventory_bench()
    claim = bench.get("claim") or {}
    if bench.get("status") != "claimed" or claim.get("project") != PROJECT:
        raise RuntimeError("claim_not_owned_after_claim")
    resource = bench["resource"]
    if resource.get("ssh_user") != "glmrunner" or resource.get("known_hosts_namespace") != str(KNOWN_HOSTS):
        raise RuntimeError("unexpected_ssh_binding")
    claimed_at = str(claim["claimed_at"])
    user, host = str(resource["ssh_user"]), str(resource["public_ipv4"])
    stop = threading.Event()
    def beat() -> None:
        while not stop.wait(30):
            result = pool("heartbeat")
            atomic(ROOT / "ENDPOINT_OWNER_HEARTBEAT.json", {"at_utc": utc(), "exit": result.returncode, "stdout": result.stdout[-500:], "stderr": result.stderr[-500:]})
    threading.Thread(target=beat, daemon=True).start()
    final: dict = {"schema_version": 1, "project": PROJECT, "bench": BENCH, "claimed_at": claimed_at, "started_at_utc": utc(), "classification": "unknown"}
    update_status(PRIOR_SPEND, {"unit": str((ROOT / "ENDPOINT_OWNER_STATE.json").resolve()), "unit_manager": "pid", "claimed_at": claimed_at, "deadline_utc": DEADLINE.isoformat().replace("+00:00", "Z"), "artifact_root": str(ARTIFACTS.resolve()), "expected_terminal": "artifacts/ENDPOINT_TERMINAL.json"})
    try:
        progress("claimed", claimed_at=claimed_at, host=host)
        remote_stage(user, host)
        progress("endpoint_pair_started")
        outer = ["python3", f"{REMOTE_ROOT}/input/endpoint_pair.py", "--root", REMOTE_ROOT, "--manifest", f"{REMOTE_ROOT}/input/ENDPOINT_INPUT_MANIFEST.json", "--absolute-deadline-epoch", "1785092400"]
        worker = ssh(user, host, shlex.join(["bash", "-lc", f"{' '.join(shlex.quote(item) for item in outer)} > {shlex.quote(REMOTE_ROOT)}/artifacts/endpoint_pair.stdout 2> {shlex.quote(REMOTE_ROOT)}/artifacts/endpoint_pair.stderr"]), timeout=remain(120))
        final.update({"worker_exit": worker.returncode, "worker_stdout": worker.stdout[-2000:], "worker_stderr": worker.stderr[-2000:]})
        retrieval = retrieve(user, host)
        final["retrieval"] = retrieval
        invocation_path = ARTIFACTS / "INVOCATION_STATE.json"
        terminal_path = ARTIFACTS / "ENDPOINT_TERMINAL.json"
        final["invocation"] = json.loads(invocation_path.read_text()) if invocation_path.is_file() else None
        endpoint = json.loads(terminal_path.read_text()) if terminal_path.is_file() else None
        final["endpoint_terminal"] = endpoint
        if endpoint and endpoint.get("classification") in {"endpoint_positive", "endpoint_nonpositive", "semantic_or_path_reject"}:
            final["classification"] = endpoint["classification"]
            progress("scientific_terminal_retrieved", classification=final["classification"])
            release(claimed_at, final, "maintenance")
            return 0
        diagnostic = ROOT / "ENDPOINT_RECOVERABLE_DIAGNOSTIC.json"
        final["classification"] = "recoverable_endpoint_integration_or_retrieval_defect"
        atomic(diagnostic, final)
        repair_id = f"endpoint-{int(time.time())}"
        repair_deadline = (DEADLINE - dt.timedelta(minutes=3)).isoformat().replace("+00:00", "Z")
        ready = run(["/root/workspace/research/factory/tools/repair-handshake", "ready", "--root", str(ROOT), "--repair-id", repair_id, "--deadline", repair_deadline, "--failure-kind", "integration_or_retrieval", "--diagnostic", str(diagnostic), "--retry-scope", "repair only the endpoint launcher, server, observer, or retrieval boundary; preserve staged checkpoint and persisted control stage"], timeout=30)
        final.update({"repair_id": repair_id, "repair_ready_exit": ready.returncode, "repair_ready_stdout": ready.stdout[-1000:], "repair_ready_stderr": ready.stderr[-1000:]})
        atomic(TERMINAL, final)
        progress("repair_ready", repair_id=repair_id)
        wait = run(["/root/workspace/research/factory/tools/repair-handshake", "wait", "--root", str(ROOT), "--repair-id", repair_id], timeout=max(1, int(remain(120))))
        final["repair_wait_exit"] = wait.returncode
        final["repair_wait_stdout"] = wait.stdout[-1000:]
        final["classification"] = "repair_deadline_or_handoff"
        release(claimed_at, final, "maintenance")
        return 1
    except Exception as error:
        final.update({"classification": "recoverable_owner_or_external_failure", "exception": repr(error)})
        diagnostic = ROOT / "ENDPOINT_RECOVERABLE_DIAGNOSTIC.json"
        atomic(diagnostic, final)
        repair_id = f"endpoint-{int(time.time())}"
        repair_deadline = (DEADLINE - dt.timedelta(minutes=3)).isoformat().replace("+00:00", "Z")
        ready = run(["/root/workspace/research/factory/tools/repair-handshake", "ready", "--root", str(ROOT), "--repair-id", repair_id, "--deadline", repair_deadline, "--failure-kind", "owner_or_external", "--diagnostic", str(diagnostic), "--retry-scope", "repair only the failed endpoint staging, launcher, server, observer, or retrieval boundary; preserve staged immutable inputs and any persisted control stage"], timeout=30)
        final.update({"repair_id": repair_id, "repair_ready_exit": ready.returncode, "repair_ready_stdout": ready.stdout[-1000:], "repair_ready_stderr": ready.stderr[-1000:]})
        atomic(TERMINAL, final)
        progress("repair_ready", repair_id=repair_id)
        wait = run(["/root/workspace/research/factory/tools/repair-handshake", "wait", "--root", str(ROOT), "--repair-id", repair_id], timeout=max(1, int(remain(120))))
        final["repair_wait_exit"] = wait.returncode
        final["repair_wait_stdout"] = wait.stdout[-1000:]
        final["classification"] = "repair_deadline_or_handoff"
        release(claimed_at, final, "maintenance")
        return 1
    finally:
        stop.set()


if __name__ == "__main__":
    raise SystemExit(main())
