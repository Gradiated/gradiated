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


NAME = "gemma4_h200_fp8_layer_dataflow_fusion"
LAB = pathlib.Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
REMOTE = "/home/glmrunner/gemma4-fp8-layer-fusion"
AUTHORIZED_USD = 10.0
MAX_CLAIM_SECONDS = 100 * 60
RETRIEVAL_RESERVE_SECONDS = 15 * 60


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, **kwargs)


def pool(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *arguments],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
        capture_output=True,
        check=check,
    )


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def scp(ip: str, source: str, destination: str, timeout: int, *, from_remote: bool = False) -> subprocess.CompletedProcess[str]:
    left = f"glmrunner@{ip}:{source}" if from_remote else source
    right = destination if from_remote else f"glmrunner@{ip}:{destination}"
    return run(
        [
            "scp",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            left,
            right,
        ],
        capture_output=True,
        timeout=timeout,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--absolute-deadline-epoch", type=int, required=True)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    events = args.artifact_root / "outer-events.jsonl"

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(json.dumps({"epoch": time.time(), "event": event, **fields}, sort_keys=True) + "\n")
            handle.flush()

    manifest = json.loads((PROJECT / "GPU_INPUT_MANIFEST.json").read_text())
    if manifest.get("pass") is not True:
        raise RuntimeError("project_local_input_manifest_invalid")
    for section in ("checkpoint", "stack", "exact_source", "programs"):
        for row in manifest[section]:
            path = PROJECT / row["path"]
            if not path.is_file() or path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
                raise RuntimeError(f"project_local_snapshot_invalid:{row['path']}")

    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = benches[args.bench] if isinstance(benches, dict) else next(row for row in benches if row["id"] == args.bench)
    if bench["accelerator"] != "nvidia-h200-sxm":
        raise RuntimeError("typed_pool_boundary:bench_not_h200_sxm")
    rate = float(bench["hourly_cost_usd"])
    status = json.loads((PROJECT / "STATUS.json").read_text())
    prior_spend = max(
        float(status.get("actual_spend_usd", 0.0)),
        float(status.get("historical_project_spend_usd", 0.0)),
    )
    remaining_spend = AUTHORIZED_USD - prior_spend
    claim_deadline = min(
        args.absolute_deadline_epoch,
        int(time.time()) + MAX_CLAIM_SECONDS,
        int(time.time()) + int(remaining_spend * 3600 / rate),
    )
    if claim_deadline <= time.time() + RETRIEVAL_RESERVE_SECONDS + 600:
        raise RuntimeError("typed_budget_boundary:insufficient_claim_window")

    started = time.time()
    claimed = False
    stop = threading.Event()
    release_condition = "ready"
    final_contents: dict[str, object] = {}

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-1000:])

    thread = threading.Thread(target=heartbeat, daemon=True)

    try:
        lease = max(600, claim_deadline - int(time.time()))
        claimed_result = pool(
            "claim",
            "--project",
            NAME,
            "--bench",
            args.bench,
            "--lease-seconds",
            str(lease),
        )
        claimed = True
        emit("claimed", lease=lease, result=json.loads(claimed_result.stdout))
        thread.start()

        sys.path.insert(0, str(NEBIUS))
        from placement_control import extract_public_ipv4, get_instance
        from stock_control import run_ssh

        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip:
            raise RuntimeError("typed_provider_boundary:no_public_ip")
        identity = run_ssh(
            ip,
            KEY,
            "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version",
            timeout=60,
        )
        (args.artifact_root / "remote-identity.stdout").write_text(identity.stdout)
        (args.artifact_root / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_remote_boundary:ssh_identity_failed")
        prepared = run_ssh(
            ip,
            KEY,
            f"mkdir -p {REMOTE}/input/stack {REMOTE}/checkpoint {REMOTE}/artifacts {REMOTE}/torch-extensions",
            timeout=60,
        )
        if prepared.returncode:
            raise RuntimeError("typed_remote_boundary:prepare_failed")

        def stage(source: pathlib.Path, destination: str) -> None:
            expected = sha256(source)
            partial = f"{destination}.{expected}.part"
            matched = run_ssh(
                ip,
                KEY,
                f"test -f {shlex.quote(destination)} && test \"$(sha256sum {shlex.quote(destination)} | awk '{{print $1}}')\" = {expected}",
                timeout=max(60, min(1800, claim_deadline - int(time.time()))),
            )
            if matched.returncode:
                transferred = scp(
                    ip,
                    str(source),
                    partial,
                    max(60, claim_deadline - int(time.time()) - RETRIEVAL_RESERVE_SECONDS),
                )
                if transferred.returncode:
                    raise RuntimeError(f"typed_transfer_boundary:scp_failed:{source.name}:{transferred.stderr[-1200:]}")
                mode = "0555" if source.suffix == ".sh" else "0444"
                finalized = run_ssh(
                    ip,
                    KEY,
                    f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {expected} && chmod {mode} {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {shlex.quote(destination)}",
                    timeout=max(120, min(1800, claim_deadline - int(time.time()))),
                )
                if finalized.returncode:
                    raise RuntimeError(f"typed_transfer_boundary:hash_or_finalize_failed:{source.name}")
            emit("input_staged", name=source.name, bytes=source.stat().st_size, sha256=expected)

        for row in manifest["checkpoint"]:
            stage(PROJECT / row["path"], f"{REMOTE}/checkpoint/{pathlib.Path(row['path']).name}")
        for row in manifest["stack"]:
            stage(PROJECT / row["path"], f"{REMOTE}/input/stack/{pathlib.Path(row['path']).name}")
        for row in manifest["programs"]:
            stage(PROJECT / row["path"], f"{REMOTE}/input/{pathlib.Path(row['path']).name}")
        stage(PROJECT / "GPU_INPUT_MANIFEST.json", f"{REMOTE}/input/GPU_INPUT_MANIFEST.json")
        emit("immutable_staging_complete", checkpoint_bytes=sum(row["bytes"] for row in manifest["checkpoint"]))

        def retrieve_json(remote_path: str, local_name: str, required: bool = True) -> dict[str, object]:
            diagnostics = []
            for attempt in range(1, 4):
                result = run_ssh(ip, KEY, f"cat {shlex.quote(remote_path)}", timeout=30)
                diagnostics.append({"attempt": attempt, "returncode": result.returncode, "stderr": result.stderr[-1000:]})
                if result.returncode == 0 and result.stdout.strip():
                    value = json.loads(result.stdout)
                    atomic(args.artifact_root / local_name, value)
                    return value
                time.sleep(5 * attempt)
            atomic(args.artifact_root / f"{local_name}.retrieval.json", diagnostics)
            if required:
                raise RuntimeError(f"typed_retrieval_boundary:unavailable:{remote_path}")
            return {}

        def retrieve_compact() -> None:
            archive_part = args.artifact_root / ".fusion-stack-compact.tar.gz.part"
            sidecar = args.artifact_root / "fusion-stack-compact.tar.gz.sha256"
            first = scp(ip, f"{REMOTE}/fusion-stack-compact.tar.gz", str(archive_part), 300, from_remote=True)
            second = scp(ip, f"{REMOTE}/fusion-stack-compact.tar.gz.sha256", str(sidecar), 60, from_remote=True)
            if first.returncode or second.returncode:
                raise RuntimeError("typed_retrieval_boundary:compact_transfer_failed")
            if sha256(archive_part) != sidecar.read_text().split()[0]:
                raise RuntimeError("typed_retrieval_boundary:compact_hash_mismatch")
            archive = args.artifact_root / "fusion-stack-compact.tar.gz"
            os.replace(archive_part, archive)
            extracted = args.artifact_root / "remote"
            extracted.mkdir(exist_ok=True)
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(extracted, filter="data")

        def invoke() -> tuple[int, dict[str, object], dict[str, object], dict[str, object]]:
            timeout = max(60, claim_deadline - int(time.time()) - RETRIEVAL_RESERVE_SECONDS)
            worker = run_ssh(
                ip,
                KEY,
                f"timeout --signal=TERM {timeout} bash {REMOTE}/input/remote_fusion_stack.sh",
                timeout=timeout + 60,
            )
            (args.artifact_root / "worker.stdout").write_text(worker.stdout)
            (args.artifact_root / "worker.stderr").write_text(worker.stderr)
            emit("worker_returned", returncode=worker.returncode)
            invocation = retrieve_json(f"{REMOTE}/artifacts/INVOCATION_STATE.json", "INVOCATION_STATE.json")
            component = retrieve_json(
                f"{REMOTE}/artifacts/component-rms/INVOCATION_STATE.json",
                "COMPONENT_INVOCATION_STATE.json",
                required=False,
            )
            worker_terminal = retrieve_json(f"{REMOTE}/artifacts/WORKER_TERMINAL.json", "REMOTE_WORKER_TERMINAL.json")
            retrieve_compact()
            return worker.returncode, invocation, component, worker_terminal

        returncode, invocation, component_invocation, worker_terminal = invoke()
        while returncode and worker_terminal.get("classification") == "integration_failure":
            scientific_started = bool(
                invocation.get("control_science_started")
                or invocation.get("candidate_science_started")
                or component_invocation.get("candidate_science_started")
            )
            if scientific_started:
                break
            repair_deadline = min(claim_deadline - RETRIEVAL_RESERVE_SECONDS, int(time.time()) + 20 * 60)
            atomic(
                args.artifact_root / "REPAIR_READY.json",
                {
                    "schema_version": 1,
                    "diagnostic": worker_terminal,
                    "invocation_state": invocation,
                    "component_invocation_state": component_invocation,
                    "repair_deadline_epoch": repair_deadline,
                    "constraint": "same intervention, workload, bound identities, and decision gates",
                },
            )
            request = args.artifact_root / "REPAIR_REQUEST.json"
            while time.time() < repair_deadline and not request.is_file():
                time.sleep(5)
            if not request.is_file():
                raise RuntimeError("typed_repair_boundary:deadline_expired")
            repair = json.loads(request.read_text())
            if repair.get("retry") is not True:
                raise RuntimeError("typed_repair_boundary:retry_not_authorized")
            for row in repair.get("files", []):
                source = (PROJECT / row["path"]).resolve()
                if PROJECT not in source.parents or sha256(source) != row["sha256"]:
                    raise RuntimeError("typed_repair_boundary:file_invalid")
                stage(source, f"{REMOTE}/input/{row['remote_name']}")
            request.rename(args.artifact_root / "REPAIR_REQUEST.consumed.json")
            returncode, invocation, component_invocation, worker_terminal = invoke()

        paired_path = args.artifact_root / "remote/PAIRED_TERMINAL.json"
        component_path = args.artifact_root / "remote/component-rms/TERMINAL.json"
        decision = None
        if paired_path.is_file():
            decision = json.loads(paired_path.read_text())
        elif component_path.is_file():
            decision = json.loads(component_path.read_text())
        if decision is None:
            raise RuntimeError(f"typed_scientific_boundary:{worker_terminal.get('message', 'decision_terminal_missing')}")
        if (
            component_path.is_file()
            and worker_terminal.get("classification") == "endpoint_external_blocker"
        ):
            decision["component_classification"] = decision.get("classification")
            decision["classification"] = "component_positive_endpoint_blocked_storage"
            decision["pass"] = False
            decision["endpoint_blocker"] = worker_terminal
        exposure = time.time() - started
        spend = exposure * rate / 3600
        decision["provider_exposure_seconds"] = exposure
        decision["provider_spend_usd"] = spend
        decision["cumulative_provider_spend_usd"] = prior_spend + spend
        if decision["cumulative_provider_spend_usd"] > AUTHORIZED_USD:
            decision["pass"] = False
            decision["classification"] = "budget_violation"
        atomic(args.artifact_root / "TERMINAL.json", decision)
        final_contents = {
            "project": NAME,
            "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "checkpoint": f"Exact immutable checkpoint retained at {REMOTE}/checkpoint",
            "image": "SGLang v0.5.13 digest 6113665 retained",
            "runtime": f"E5M2 FP8+QKV stack with RMSNorm-to-FP8 decision: {decision.get('classification')}",
            "caches": f"CUDA extension and graph caches retained at {REMOTE}/torch-extensions",
            "server_state": (
                "Candidate server gemma-rms-fp8-candidate-v0513 retained"
                if paired_path.is_file()
                else "No endpoint server launched because the component did not promote"
            ),
            "artifacts": "Compact terminal and raw worker diagnostics retrieved project-locally",
        }
        emit("scientific_terminal", classification=decision.get("classification"), spend_usd=spend)
        return 0 if decision.get("pass") else 1
    except Exception as exception:
        atomic(
            args.artifact_root / "OUTER_FAILURE.json",
            {
                "schema_version": 1,
                "classification": str(exception).split(":", 1)[0],
                "message": str(exception),
                "provider_exposure_seconds": time.time() - started,
            },
        )
        if str(exception).startswith(
            ("typed_remote_boundary", "typed_provider_boundary", "typed_retrieval_boundary")
        ):
            release_condition = "maintenance"
        raise
    finally:
        if claimed:
            stop.set()
            thread.join(timeout=5)
            contents = final_contents or {
                "project": NAME,
                "runtime": "Fusion owner ended at a typed boundary; inspect retrieved diagnostics",
                "checkpoint": f"Project-local snapshot may be retained at {REMOTE}/checkpoint",
                "image": "Pinned SGLang v0.5.13 image retained when staged",
                "artifacts": str(args.artifact_root),
            }
            contents_path = args.artifact_root / "BENCH_CONTENTS.json"
            atomic(contents_path, contents)
            pool(
                "release",
                "--project",
                NAME,
                "--condition",
                release_condition,
                "--contents",
                str(contents_path),
                check=False,
            )


if __name__ == "__main__":
    raise SystemExit(main())
