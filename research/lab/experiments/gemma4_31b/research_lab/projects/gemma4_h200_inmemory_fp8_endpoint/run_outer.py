#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tarfile
import threading
import time


PROJECT_NAME = "gemma4_h200_inmemory_fp8_endpoint"
BENCH = "h200-kernel-frontier-e00pfvrckjvwn7bhet"
LAB = pathlib.Path("/root/workspace/research/lab/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / PROJECT_NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS_TOOLS = pathlib.Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
SSH_KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
REMOTE = "/home/glmrunner/gemma-kernel-frontier"
RATE = 2.46


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, **kwargs)


def pool(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(
        [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *arguments],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
        capture_output=True,
        check=check,
    )


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def copy_to(ip: str, sources: list[pathlib.Path], destination: str, timeout: int) -> None:
    command = [
        "scp", "-i", str(SSH_KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts",
        *map(str, sources), f"glmrunner@{ip}:{destination}",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"typed_transfer_boundary:scp_failed:{result.stderr[-1000:]}")


def matching_remote_checkpoint_files(ip: str, expected: dict[str, dict[str, object]], run_ssh: object) -> set[str]:
    checks = " ".join(
        shlex.quote(f"{name}:{row['bytes']}:{row['sha256']}")
        for name, row in expected.items()
    )
    command = f'''set -euo pipefail
cd {shlex.quote(REMOTE)}/checkpoint
for check in {checks}; do
  name=${{check%%:*}}
  rest=${{check#*:}}
  bytes=${{rest%%:*}}
  digest=${{rest#*:}}
  if test -f "$name" && test "$(stat -c%s -- "$name")" = "$bytes" && test "$(sha256sum -- "$name" | awk '{{print $1}}')" = "$digest"; then
    printf '%s\\n' "$name"
  fi
done'''
    result = run_ssh(ip, SSH_KEY, command, timeout=900)
    if result.returncode:
        raise RuntimeError("typed_remote_boundary:checkpoint_compare_failed")
    matched = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    if not matched.issubset(expected):
        raise RuntimeError("typed_remote_boundary:checkpoint_compare_unrecognized_file")
    return matched


def evaluate(root: pathlib.Path, elapsed: float) -> dict[str, object]:
    owner = json.loads((root / "OWNER_TERMINAL.json").read_text())
    if owner.get("classification") != "completed":
        return {"schema_version": 1, "status": "terminal", "classification": owner.get("classification", "owner_failure"), "pass": False, "owner_terminal": owner}
    candidate = json.loads((root / "exact-c32/TERMINAL.json").read_text())
    oracle = json.loads((root / "oracle.json").read_text())
    coherence_path = root / "coherence.json"
    coherence = json.loads(coherence_path.read_text()) if coherence_path.is_file() else {"pass": None, "skipped": True, "rows": []}
    def jsonl(path: pathlib.Path) -> list[dict[str, object]]:
        return [json.loads(line) for line in path.read_text().splitlines() if line] if path.is_file() else []

    audit = jsonl(root / "server-fp8-modules.jsonl")
    consumer_audit = jsonl(root / "server-fp8-consumer.jsonl")
    runtime_path = root / "server-fp8-runtime.json"
    runtime_audit = json.loads(runtime_path.read_text()) if runtime_path.is_file() else {}
    rows = candidate.get("rows", [])
    cache = candidate.get("cache", {})
    service = candidate.get("service_seconds_per_request")
    timing_valid = bool(
        oracle.get("pass")
        and candidate.get("pass")
        and candidate.get("complete_requests") == 32
        and len(rows) == 32
        and all(row.get("prompt_tokens") == 4214 and row.get("completion_tokens") == 358 and row.get("text_nonempty") and row.get("text_finite") for row in rows)
        and cache.get("cached_prompt_tokens_delta") == 17120
        and cache.get("uncached_prompt_tokens_delta") == 117728
        and isinstance(service, (int, float))
    )
    provenance_valid = bool(
        len(audit) == 240
        and len(consumer_audit) == 1
        and consumer_audit[0].get("consumer") == "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm"
        and consumer_audit[0].get("pid") == runtime_audit.get("pid")
        and runtime_audit.get("process_role") == "scheduler"
        and runtime_audit.get("sglang_commit") == "127b9e3283f7c2a43234b852ff5c9f1796d53624"
    )
    base = 0.9280403084687521
    if not timing_valid:
        classification = "endpoint_negative"
    elif service <= 0.7145910375209391:
        classification = "frontier_pass" if provenance_valid else "timing_proxy_frontier_pass"
    elif service <= 0.8352362776218769:
        classification = "useful_pass" if provenance_valid else "timing_proxy_useful_pass"
    elif service < base:
        classification = "retain_incremental" if provenance_valid else "timing_proxy_retain_incremental"
    else:
        classification = "endpoint_negative"
    return {
        "schema_version": 1,
        "status": "terminal",
        "classification": classification,
        "pass": timing_valid and provenance_valid and classification in {"frontier_pass", "useful_pass", "retain_incremental"},
        "timing_proxy_pass": timing_valid,
        "provenance_valid": provenance_valid,
        "service_seconds_per_request": service,
        "service_reduction_fraction": None if not isinstance(service, (int, float)) else 1 - service / base,
        "comparator_service_seconds_per_request": base,
        "frontier_ceiling_seconds_per_request": 0.7145910375209391,
        "useful_ceiling_seconds_per_request": 0.8352362776218769,
        "cache": cache,
        "oracle": oracle,
        "coherence": coherence,
        "fp8_module_count": len(audit),
        "fp8_consumer_audit": consumer_audit,
        "fp8_runtime_audit": runtime_audit,
        "provenance": json.loads((root / "provenance.json").read_text()) if (root / "provenance.json").is_file() else {"post_timing_capture": False},
        "provider_exposure_seconds": elapsed,
        "provider_spend_usd_conservative": elapsed * RATE / 3600,
        "raw_candidate_terminal": candidate,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--deadline-epoch", type=int, required=True)
    parser.add_argument("--repair-window-seconds", type=int, default=600)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    bench = inventory["benches"][BENCH]
    qkv_project = LAB / "projects" / "gemma4_h200_qkv_epilogue_fusion"
    qkv_status = json.loads((qkv_project / "STATUS.json").read_text())
    qkv_terminal_path = qkv_project / "artifacts/qkv-component-20260719t2326z/TERMINAL.json"
    qkv_terminal = json.loads(qkv_terminal_path.read_text()) if qkv_terminal_path.is_file() else {}
    qkv_terminal_emitted = (
        qkv_status.get("status") in {"complete", "completed", "terminal"}
        or qkv_terminal.get("status") == "terminal"
    )
    if not qkv_terminal_emitted:
        raise RuntimeError("cross_project_dependency:qkv_terminal_not_emitted")
    if qkv_status.get("active_session") is not None:
        raise RuntimeError("cross_project_dependency:qkv_session_not_released")
    claim = bench.get("claim") or {}
    if bench["status"] != "available" and not (
        bench["status"] == "claimed" and claim.get("project") == PROJECT_NAME
    ):
        raise RuntimeError(f"director has not marked bench ready: {bench['status']}")
    preparation = json.loads((PROJECT / "artifacts/local-preparation/MANIFEST.json").read_text())
    if preparation.get("pass") is not True:
        raise RuntimeError("project-local content manifest is not passing")
    if args.resume:
        if not args.artifact_root.is_dir() or (args.artifact_root / "TERMINAL.json").exists():
            raise RuntimeError("resume requires an unterminated owner artifact root")
    else:
        args.artifact_root.mkdir(parents=True, exist_ok=False)
    events = args.artifact_root / "outer-events.jsonl"
    started = time.time()

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(json.dumps({"time": time.time(), "event": event, **fields}, sort_keys=True) + "\n")

    claimed = False
    remote_verified = False
    remote_mutated = False
    heartbeat_stop = threading.Event()

    def heartbeat() -> None:
        while not heartbeat_stop.wait(45):
            result = pool("heartbeat", "--project", PROJECT_NAME, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-1000:])

    thread = threading.Thread(target=heartbeat, daemon=True)
    terminal: dict[str, object] | None = None
    try:
        claim = pool("claim", "--project", PROJECT_NAME, "--bench", BENCH, "--lease-seconds", "600")
        claimed = True
        emit("claimed", stdout=claim.stdout.strip())
        thread.start()
        sys.path.insert(0, str(NEBIUS_TOOLS))
        from placement_control import extract_public_ipv4, get_instance
        from stock_control import run_ssh, scp_from

        provider = get_instance(bench["resource"]["instance_id"])
        ip = extract_public_ipv4(provider)
        if not ip:
            raise RuntimeError("typed_provider_boundary:no_public_ip")
        known_hosts = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
        refresh = subprocess.run(["ssh-keygen", "-R", ip, "-f", str(known_hosts)], capture_output=True, text=True)
        emit("known_host_refreshed", ip=ip, returncode=refresh.returncode)
        identity = run_ssh(ip, SSH_KEY, "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version", timeout=60)
        (args.artifact_root / "remote-identity.stdout").write_text(identity.stdout)
        (args.artifact_root / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_remote_boundary:ssh_identity_failed")
        remote_verified = True
        prepare = run_ssh(ip, SSH_KEY, f"mkdir -p {REMOTE}/input {REMOTE}/checkpoint {REMOTE}/artifacts", timeout=60)
        if prepare.returncode:
            raise RuntimeError("typed_remote_boundary:prepare_failed")
        science_deadline = args.deadline_epoch - 1200
        if science_deadline <= time.time() + 300:
            raise RuntimeError("typed_budget_boundary:retrieval_reserve_consumed")
        expected_rows = {row["path"]: row for row in preparation["checkpoint_files"]}
        matched = matching_remote_checkpoint_files(ip, expected_rows, run_ssh)
        missing = [name for name in expected_rows if name not in matched]
        emit("checkpoint_compared", matched=sorted(matched), missing=missing)
        if missing:
            remove = run_ssh(
                ip,
                SSH_KEY,
                "rm -f -- " + " ".join(shlex.quote(f"{REMOTE}/checkpoint/{name}") for name in missing),
                timeout=60,
            )
            if remove.returncode:
                raise RuntimeError("typed_remote_boundary:checkpoint_partial_remove_failed")
            sources = [PROJECT / "inputs/checkpoint" / name for name in missing]
            copy_to(ip, sources, f"{REMOTE}/checkpoint/", max(60, int(science_deadline - time.time())))
            remote_mutated = True
            emit("checkpoint_staged", files=missing, bytes=sum(int(expected_rows[name]["bytes"]) for name in missing))
        scripts = [
            PROJECT / name
            for name in (
                "exact_shape_oracle.py",
                "endpoint_entrypoint.py",
                "remote_run.sh",
                "PINNED_SGLANG_AUDIT_CONTRACT.json",
            )
        ]
        scripts.extend([PROJECT / "inputs/exact_mix_runner.py", PROJECT / "inputs/coherence_runner.py"])
        copy_to(ip, scripts, f"{REMOTE}/input/", 300)
        remote_mutated = True
        remote_input_hashes = run_ssh(
            ip,
            SSH_KEY,
            f"cd {REMOTE}/input && sha256sum "
            + " ".join(shlex.quote(name) for name in preparation["gpu_inputs"]),
            timeout=60,
        )
        (args.artifact_root / "remote-input-sha256.txt").write_text(
            remote_input_hashes.stdout
        )
        if remote_input_hashes.returncode:
            raise RuntimeError("typed_remote_boundary:input_hash_failed")
        expected_inputs = {
            name: row["sha256"] for name, row in preparation["gpu_inputs"].items()
        }
        observed_inputs = {
            line.split(maxsplit=1)[1].lstrip("* "): line.split()[0]
            for line in remote_input_hashes.stdout.splitlines()
            if len(line.split(maxsplit=1)) == 2
        }
        if observed_inputs != expected_inputs:
            raise RuntimeError("typed_transfer_boundary:input_hash_mismatch")
        remote_hashes = run_ssh(ip, SSH_KEY, f"cd {REMOTE}/checkpoint && sha256sum *", timeout=max(60, int(science_deadline - time.time())))
        (args.artifact_root / "remote-checkpoint-sha256.txt").write_text(remote_hashes.stdout)
        if remote_hashes.returncode:
            raise RuntimeError("typed_remote_boundary:checkpoint_hash_failed")
        expected = {row["path"]: row["sha256"] for row in preparation["checkpoint_files"]}
        observed = {line.split(maxsplit=1)[1].lstrip("* "): line.split()[0] for line in remote_hashes.stdout.splitlines() if len(line.split(maxsplit=1)) == 2}
        if observed != expected:
            raise RuntimeError("typed_transfer_boundary:checkpoint_hash_mismatch")
        worker_timeout = max(60, int(science_deadline - time.time()))
        worker = run_ssh(ip, SSH_KEY, f"timeout --signal=TERM {worker_timeout} bash {REMOTE}/input/remote_run.sh", timeout=worker_timeout + 30)
        (args.artifact_root / "remote-worker.stdout").write_text(worker.stdout)
        (args.artifact_root / "remote-worker.stderr").write_text(worker.stderr)
        compact = run_ssh(ip, SSH_KEY, f"cat {REMOTE}/artifacts/inmemory-fp8/OWNER_TERMINAL.json", timeout=30)
        observed_owner = json.loads(compact.stdout) if compact.returncode == 0 else {}
        repairable = observed_owner.get("classification") in {"consumer_failure", "owner_failure"}
        if worker.returncode and repairable and time.time() + 60 < science_deadline:
            atomic(args.artifact_root / "REPAIR_READY.json", {"owner_terminal": observed_owner, "repair_deadline_epoch": min(science_deadline, time.time() + args.repair_window_seconds)})
            repair_deadline = min(science_deadline, time.time() + args.repair_window_seconds)
            request = args.artifact_root / "REPAIR_REQUEST.json"
            while time.time() < repair_deadline and not request.exists():
                time.sleep(5)
            if request.exists() and json.loads(request.read_text()).get("retry") is True:
                copy_to(ip, scripts, f"{REMOTE}/input/", 300)
                retry_timeout = max(60, int(science_deadline - time.time()))
                worker = run_ssh(ip, SSH_KEY, f"timeout --signal=TERM {retry_timeout} bash {REMOTE}/input/remote_run.sh", timeout=retry_timeout + 30)
                (args.artifact_root / "remote-worker-retry.stdout").write_text(worker.stdout)
                (args.artifact_root / "remote-worker-retry.stderr").write_text(worker.stderr)
        partial = args.artifact_root / ".terminal.tar.gz.partial"
        sidecar = args.artifact_root / "terminal.tar.gz.sha256"
        scp_from(ip, SSH_KEY, f"{REMOTE}/inmemory-fp8-terminal.tar.gz", partial)
        scp_from(ip, SSH_KEY, f"{REMOTE}/inmemory-fp8-terminal.tar.gz.sha256", sidecar)
        actual_hash = hashlib.sha256(partial.read_bytes()).hexdigest()
        if actual_hash != sidecar.read_text().split()[0]:
            raise RuntimeError("typed_retrieval_boundary:archive_hash_mismatch")
        archive = args.artifact_root / "terminal.tar.gz"
        partial.replace(archive)
        retrieved = args.artifact_root / "retrieved"
        retrieved.mkdir()
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(retrieved, filter="data")
        terminal = evaluate(retrieved, time.time() - started)
        atomic(args.artifact_root / "TERMINAL.json", terminal)
        emit("terminal_retrieved", classification=terminal["classification"])
        return 0 if terminal.get("pass") else 1
    except Exception as error:
        emit("outer_error", error_type=type(error).__name__, message=str(error))
        if terminal is None:
            terminal = {"schema_version": 1, "status": "terminal", "classification": "owner_failure", "pass": False, "error": {"type": type(error).__name__, "message": str(error)}}
            atomic(args.artifact_root / "TERMINAL.json", terminal)
        return 1
    finally:
        heartbeat_stop.set()
        if thread.is_alive():
            thread.join(timeout=5)
        if claimed:
            classification = (terminal or {}).get("classification", "owner_failure")
            if remote_mutated:
                contents = {
                    "project": PROJECT_NAME,
                    "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                    "checkpoint": f"Exact immutable eight-file checkpoint retained at {REMOTE}/checkpoint.",
                    "image": "Pinned SGLang v0.5.12 image retained if the remote worker reached image staging.",
                    "runtime": f"Single in-memory FP8 endpoint schedule terminal: {classification}.",
                    "caches": "Any completed SGLang FP8/CUDA graph compilation caches are retained.",
                    "server_state": "In-memory FP8 server retained if healthy; otherwise image, checkpoint, and caches retained.",
                    "artifacts": "Compact terminal and raw endpoint artifacts retrieved project-locally when available.",
                }
            else:
                contents = dict(bench["contents"])
                contents["runtime"] = "No remote mutation or scientific invocation; local controller failed before SSH identity and was repaired."
            contents_path = args.artifact_root / "BENCH_CONTENTS.json"
            atomic(contents_path, contents)
            condition = "ready"
            release = pool("release", "--project", PROJECT_NAME, "--condition", condition, "--contents", str(contents_path), check=False)
            emit("released", condition=condition, returncode=release.returncode, stderr=release.stderr[-1000:])


if __name__ == "__main__":
    raise SystemExit(main())
