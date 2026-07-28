#!/usr/bin/env python3
"""Durable retained-claim owner for the admitted streaming H100 component cycle."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
import time

PROJECT = "gemma4_hopper_packed_m384_verifier"
ROOT = Path(__file__).resolve().parent
LAB = ROOT.parent.parent
ADMISSION = ROOT / "DIRECTOR_HOPPER_PACKED_STREAMING_H100_ADMISSION_20260726T2042Z.json"
READY = ROOT / "PACKED_M384_STREAMING_H100_COMPONENT_READY.json"
MANIFEST = ROOT / "STREAMING_H100_COMPONENT_INPUT_MANIFEST.json"
STATE = ROOT / "STREAMING_H100_COMPONENT_OWNER_STATE.json"
HEARTBEAT = ROOT / "STREAMING_H100_COMPONENT_OWNER_HEARTBEAT.json"
TERMINAL = ROOT / "STREAMING_H100_COMPONENT_OWNER_TERMINAL.json"
ARTIFACTS = ROOT / "artifacts" / "h100-streaming-component"
IDENTITY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = Path("/root/.config/nebius/glm-campaign/known_hosts")
IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"

def utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")

def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)

def run(command: list[str], timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout)

def pool(bench: str, action: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), action, "--project", PROJECT, "--bench", bench, *extra], timeout=60)

def claimed_bench(bench_id: str) -> dict:
    rows = json.loads((LAB / "runtime" / "gpus.json").read_text())["benches"]
    row = rows.get(bench_id) if isinstance(rows, dict) else next((item for item in rows if item.get("id") == bench_id), None)
    if not isinstance(row, dict):
        raise RuntimeError("bound_bench_missing")
    claim = row.get("claim") or {}
    if row.get("status") != "claimed" or claim.get("project") != PROJECT:
        raise RuntimeError("claim_not_owned")
    if row.get("accelerator") != "nvidia-h100-sxm" or row.get("provider") != "nebius":
        raise RuntimeError("bound_h100_nebius_required")
    return row

def verify_binding(bench_id: str, deadline_utc: str, readmission_path: Path) -> None:
    admission = json.loads(ADMISSION.read_text())
    ready = json.loads(READY.read_text())
    predecessor = ROOT / "PACKED_M384_STREAMING_ACCURACY_READY.json"
    if admission.get("project") != PROJECT or admission["consumes"]["ready_sha256"] != digest(predecessor):
        raise RuntimeError("admission_predecessor_binding_mismatch")
    owner = ready.get("owner") or {}
    if owner.get("path") != Path(__file__).name or owner.get("sha256") != digest(Path(__file__)):
        raise RuntimeError("owner_binding_mismatch")
    if ready.get("input_manifest", {}).get("sha256") != digest(MANIFEST):
        raise RuntimeError("input_manifest_binding_mismatch")
    if ready.get("gpu_claim_allowed") is not False:
        raise RuntimeError("pre_readmission_ready_must_not_allow_claim")
    readmission = json.loads(readmission_path.read_text())
    if (
        readmission.get("project") != PROJECT
        or readmission.get("ready_sha256") != digest(READY)
        or readmission.get("bench_id") != bench_id
        or readmission.get("deadline_utc") != deadline_utc
        or readmission.get("reservation_usd") != 7.0
        or readmission.get("gpu_claim_allowed") is not True
    ):
        raise RuntimeError("post_reservation_readmission_binding_mismatch")
    if bench_id == "h200-causal-head-e00b9qw8d6qd7wrjj1":
        raise RuntimeError("claimed_causal_h200_excluded")

def ssh_base(user: str, host: str) -> list[str]:
    return ["ssh", "-i", str(IDENTITY), "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes", f"{user}@{host}"]

def heartbeat(bench_id: str, stop: threading.Event) -> None:
    while not stop.wait(60):
        completed = pool(bench_id, "heartbeat")
        atomic(HEARTBEAT, {"at_utc": utc(), "exit": completed.returncode, "stdout": completed.stdout[-2000:], "stderr": completed.stderr[-2000:]})

def stage(user: str, host: str) -> str:
    manifest = json.loads(MANIFEST.read_text())
    for row in manifest["files"]:
        path = ROOT / row["source"]
        if not path.is_file() or path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
            raise RuntimeError(f"local_manifest_mismatch:{row['path']}")
    packet = ROOT / "artifacts" / "h100-streaming-component.packet.tar"
    packed = run(["/root/workspace/research/factory/tools/manifest-pack", "--root", str(ROOT), "--manifest", str(MANIFEST), "--archive", str(packet)])
    if packed.returncode:
        raise RuntimeError(f"packet_pack_failed:{packed.stderr[-1000:]}")
    remote_root = f"/home/{user}/{PROJECT}-streaming"
    manifest_sha = digest(MANIFEST)
    packet_root = f"{remote_root}/packet-{manifest_sha}"
    verifier = """import hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); m=p/'STREAMING_H100_COMPONENT_INPUT_MANIFEST.json'
def d(x):
 h=hashlib.sha256()
 with x.open('rb') as f:
  for c in iter(lambda:f.read(1048576),b''): h.update(c)
 return h.hexdigest()
ok=m.is_file() and d(m)==sys.argv[2]
if ok:
 for r in json.loads(m.read_text())['files']:
  x=p/r['path']; ok=ok and x.is_file() and not x.is_symlink() and x.stat().st_size==r['bytes'] and d(x)==r['sha256']
print('matched' if ok else 'stage_required')"""
    prepared = run(ssh_base(user, host) + [f"mkdir -p {shlex.quote(remote_root)}/artifacts; python3 -c {shlex.quote(verifier)} {shlex.quote(packet_root)} {shlex.quote(manifest_sha)}"], timeout=180)
    if prepared.returncode:
        raise RuntimeError(f"remote_packet_reconcile_failed:{prepared.stderr[-1000:]}")
    remote_state = prepared.stdout.strip()
    if remote_state == "stage_required":
        temporary_root = f"{packet_root}.tmp-{os.getpid()}"
        made = run(ssh_base(user, host) + [f"rm -rf {shlex.quote(temporary_root)}; mkdir -p {shlex.quote(temporary_root)}"], timeout=180)
        if made.returncode:
            raise RuntimeError(f"remote_packet_prepare_failed:{made.stderr[-1000:]}")
        copied = run(["scp", "-i", str(IDENTITY), "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes", str(packet), f"{user}@{host}:{temporary_root}/packet.tar"], timeout=900)
        if copied.returncode:
            raise RuntimeError(f"packet_copy_failed:{copied.stderr[-1000:]}")
        install = f"tar -xf {shlex.quote(temporary_root)}/packet.tar -C {shlex.quote(temporary_root)} && python3 -c {shlex.quote(verifier)} {shlex.quote(temporary_root)} {shlex.quote(manifest_sha)} && test ! -e {shlex.quote(packet_root)} && mv -T {shlex.quote(temporary_root)} {shlex.quote(packet_root)}"
        installed = run(ssh_base(user, host) + [install], timeout=300)
        if installed.returncode:
            raise RuntimeError(f"packet_finalize_failed:{installed.stderr[-1000:]}")
    elif remote_state != "matched":
        raise RuntimeError(f"remote_packet_reconcile_unrecognized:{remote_state}")
    image = run(ssh_base(user, host) + ["sudo -n docker pull " + shlex.quote(IMAGE)], timeout=1200)
    if image.returncode:
        raise RuntimeError(f"image_pull_failed:{image.stderr[-1000:]}")
    atomic(ROOT / "STREAMING_H100_COMPONENT_STAGING.json", {"at_utc": utc(), "remote_root": remote_root, "packet_root": packet_root, "remote_state": remote_state, "manifest_sha256": manifest_sha, "packet_sha256": digest(packet), "image": IMAGE})
    return remote_root, packet_root

def retrieve(user: str, host: str, remote_root: str) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    fetched = run(["scp", "-r", "-i", str(IDENTITY), "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes", f"{user}@{host}:{remote_root}/artifacts/h100-streaming-component/.", str(ARTIFACTS)], timeout=300)
    if fetched.returncode:
        raise RuntimeError(f"artifact_retrieval_failed:{fetched.stderr[-1000:]}")

def canonical_digest(value: dict) -> str:
    return hashlib.sha256(
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    ).hexdigest()

def invocation_state() -> dict | None:
    path = ARTIFACTS / "INVOCATION_STATE.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        return {"malformed": repr(error)}
    return value if isinstance(value, dict) else {"malformed": "not_object"}

def repair_disposition(phase: str, invocation: dict | None) -> tuple[str, set[str]]:
    if invocation is None or invocation.get("phase") == "pre_science":
        return "pre_science_unsubmitted", {"stage", "run_unsubmitted_cycle", "retrieve"}
    if invocation.get("phase") == "science_started" or invocation.get("candidate_cuda_invocation_started"):
        return "science_started_ambiguous", {"retrieve", "offline_result_construction"}
    if invocation.get("phase") == "scientific_terminal_recorded":
        return "terminal_retrieval_only", {"retrieve", "offline_result_construction"}
    return f"unknown_invocation_state_after_{phase}", {"retrieve"}

def read_requested_repair(repair_id: str, allowed: set[str]) -> dict:
    waited = run([
        "/root/workspace/research/factory/tools/repair-handshake", "wait",
        "--root", str(ROOT), "--repair-id", repair_id,
    ])
    if waited.returncode:
        raise RuntimeError(f"repair_wait_failed:{waited.stderr[-1000:]}")
    response = json.loads(waited.stdout)
    request_path = Path(str(response["request_path"]))
    request = json.loads(request_path.read_text())
    ready_path = request_path.with_name("REPAIR_READY.json")
    ready = json.loads(ready_path.read_text())
    if request.get("ready_sha256") != canonical_digest(ready):
        raise RuntimeError("repair_request_hash_binding_mismatch")
    scope = request.get("retry_scope")
    if not isinstance(scope, str) or scope not in allowed:
        raise RuntimeError(f"repair_scope_not_permitted:{scope}")
    patch = request.get("patch_artifact")
    if patch is not None:
        patch_path = Path(str(patch)).resolve()
        try:
            patch_path.relative_to(ROOT)
        except ValueError as error:
            raise RuntimeError("repair_patch_not_project_local") from error
        if not patch_path.is_file():
            raise RuntimeError("repair_patch_missing")
        request["patch_sha256"] = digest(patch_path)
    request["scope"] = scope
    request["repair_id"] = repair_id
    atomic(request_path.with_name("REPAIR_APPLIED.json"), {
        "at_utc": utc(), "state": "repair_applied", "repair_id": repair_id,
        "request_sha256": canonical_digest(request), "scope": scope,
        "patch_artifact": patch, "patch_sha256": request.get("patch_sha256"),
    })
    return request

def retain_for_repair(
    deadline: dt.datetime, diagnostic: dict, phase: str
) -> str:
    diagnostic_path = ROOT / "STREAMING_H100_COMPONENT_RECOVERABLE_DIAGNOSTIC.json"
    invocation = invocation_state()
    disposition, allowed = repair_disposition(phase, invocation)
    atomic(diagnostic_path, {
        **diagnostic, "phase": phase, "invocation": invocation,
        "disposition": disposition, "allowed_retry_scopes": sorted(allowed),
    })
    repair_id = f"streaming-h100-{time.time_ns()}"
    ready = run([
        "/root/workspace/research/factory/tools/repair-handshake", "ready",
        "--root", str(ROOT), "--repair-id", repair_id, "--deadline",
        deadline.isoformat().replace("+00:00", "Z"), "--failure-kind", "integration",
        "--diagnostic", str(diagnostic_path),
        "--retry-scope", "one of: stage, run_unsubmitted_cycle, retrieve, offline_result_construction",
    ])
    if ready.returncode:
        raise RuntimeError(f"repair_ready_failed:{ready.stderr[-1000:]}")
    atomic(STATE, {"at_utc": utc(), "phase": "repair_waiting", "repair_id": repair_id, "disposition": disposition, "allowed_retry_scopes": sorted(allowed)})
    request = read_requested_repair(repair_id, allowed)
    atomic(STATE, {"at_utc": utc(), "phase": "repair_resumed", "repair_id": repair_id, "repair_scope": request["scope"], "invocation_disposition": disposition})
    return str(request["scope"])

def apply_offline_result_patch() -> None:
    applied = sorted((ROOT / ".repair-handshakes").glob("*/REPAIR_APPLIED.json"))
    if not applied:
        raise RuntimeError("offline_result_patch_record_missing")
    record = json.loads(applied[-1].read_text())
    patch = record.get("patch_artifact")
    if not isinstance(patch, str):
        raise RuntimeError("offline_result_patch_required")
    completed = run([sys.executable, patch, "--artifact-root", str(ARTIFACTS)], timeout=300)
    atomic(ARTIFACTS / "offline-result-patch.log.json", {
        "exit": completed.returncode, "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:], "patch_sha256": record.get("patch_sha256"),
    })
    if completed.returncode:
        raise RuntimeError("offline_result_patch_failed")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--deadline-utc", required=True)
    parser.add_argument("--readmission", type=Path, required=True)
    args = parser.parse_args()
    deadline = dt.datetime.fromisoformat(args.deadline_utc.replace("Z", "+00:00"))
    if deadline <= dt.datetime.now(dt.UTC):
        raise RuntimeError("absolute_deadline_elapsed")
    if not IDENTITY.is_file() or not KNOWN_HOSTS.is_file():
        raise RuntimeError("ssh_identity_preflight_failed")
    verify_binding(args.bench, args.deadline_utc, args.readmission)
    row = claimed_bench(args.bench)
    resource = row["resource"]
    user, host = resource["ssh_user"], resource["public_ipv4"]
    if user != "glmrunner" or resource.get("known_hosts_namespace") != str(KNOWN_HOSTS):
        raise RuntimeError("unexpected_ssh_identity")
    atomic(STATE, {"at_utc": utc(), "phase": "claimed_owner_started", "bench": args.bench, "deadline_utc": args.deadline_utc, "claimed_at": row["claim"]["claimed_at"]})
    stop = threading.Event()
    thread = threading.Thread(target=heartbeat, args=(args.bench, stop), daemon=True)
    thread.start()
    terminal: dict = {"started_at_utc": utc(), "bench": args.bench, "claimed_at": row["claim"]["claimed_at"]}
    phase = "stage"
    remote_root = ""
    packet_root = ""
    try:
        while dt.datetime.now(dt.UTC) < deadline:
            try:
                if phase == "stage":
                    remote_root, packet_root = stage(user, host)
                    atomic(STATE, {"at_utc": utc(), "phase": "packet_and_image_staged", "remote_root": remote_root, "packet_root": packet_root})
                    phase = "run_unsubmitted_cycle"
                if phase == "run_unsubmitted_cycle":
                    worker_seconds = int((deadline - dt.datetime.now(dt.UTC)).total_seconds()) - 300
                    if worker_seconds <= 0:
                        raise TimeoutError("insufficient_deadline_for_component_and_retrieval")
                    command = f"sudo -n docker run --rm --gpus all --ipc=host --entrypoint python3 -v {shlex.quote(packet_root + ':/project:ro')} -v {shlex.quote(remote_root + '/artifacts:/artifacts')} {shlex.quote(IMAGE)} /project/streaming_accuracy_component_runner.py --artifact-root /artifacts/h100-streaming-component --source /project/packed_m384_streaming_cluster.cu --source-sha256 2262a4a20e9438671f795eeb8aad7f5db9cbe65ae446a94758e3d4c1cce78656 --control /project/inputs/source/extend_attention.py --repetitions 25 --seed 20260726"
                    atomic(STATE, {"at_utc": utc(), "phase": "launch_attempted", "remote_root": remote_root})
                    worker = run(ssh_base(user, host) + [f"mkdir -p {shlex.quote(remote_root)}/artifacts/h100-streaming-component; {command} > {shlex.quote(remote_root)}/artifacts/h100-streaming-component/stdout.log 2> {shlex.quote(remote_root)}/artifacts/h100-streaming-component/stderr.log"], timeout=worker_seconds)
                    terminal.update({"worker_exit": worker.returncode, "ssh_stdout": worker.stdout[-2000:], "ssh_stderr": worker.stderr[-2000:]})
                    phase = "retrieve"
                if phase == "retrieve":
                    retrieve(user, host, remote_root)
                elif phase == "offline_result_construction":
                    apply_offline_result_patch()
                terminal["invocation"] = invocation_state()
                result = ARTIFACTS / "PACKED_M384_STREAMING_COMPONENT_RESULT.json"
                terminal["result"] = json.loads(result.read_text()) if result.exists() else None
                if terminal["result"] is None:
                    raise RuntimeError("typed_missing_component_terminal")
                terminal["classification"] = "scientific_terminal_retrieved"
                atomic(TERMINAL, terminal)
                contents = json.dumps({"project": PROJECT, "result": terminal["result"].get("result"), "artifacts": str(ARTIFACTS), "candidate_cuda_started": bool((terminal["invocation"] or {}).get("candidate_cuda_invocation_started")), "image": IMAGE, "server_state": "No server retained; image, packet, and compiler cache remain resident."})
                released = pool(args.bench, "release", "--condition", "ready", "--contents", contents)
                terminal.update({"release_exit": released.returncode, "release_stdout": released.stdout[-2000:], "release_stderr": released.stderr[-2000:]})
                atomic(TERMINAL, terminal)
                return 0
            except Exception as error:
                terminal["exception"] = repr(error)
                requested = retain_for_repair(deadline, terminal, phase)
                phase = requested
        atomic(TERMINAL, {**terminal, "classification": "absolute_deadline_repair_handoff"})
        return 1
    finally:
        stop.set()

if __name__ == "__main__":
    raise SystemExit(main())
