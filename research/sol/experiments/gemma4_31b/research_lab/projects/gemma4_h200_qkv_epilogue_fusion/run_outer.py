#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import threading
import time


PROJECT_NAME = "gemma4_h200_qkv_epilogue_fusion"
PRIMARY_PROJECT = "gemma4_h200_inmemory_fp8_endpoint"
BENCH = "h200-kernel-frontier-e00pfvrckjvwn7bhet"
LAB = pathlib.Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / PROJECT_NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS_TOOLS = pathlib.Path(
    "/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius"
)
SSH_KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
REMOTE = "/home/glmrunner/gemma4-qkv-epilogue"
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
        "scp",
        "-i",
        str(SSH_KEY),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts",
        *map(str, sources),
        f"glmrunner@{ip}:{destination}",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"typed_transfer_boundary:scp_failed:{result.stderr[-1000:]}")


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_archive(archive: pathlib.Path, destination: pathlib.Path) -> None:
    destination.mkdir()
    with tarfile.open(archive, "r:gz") as bundle:
        bundle.extractall(destination, filter="data")


def evaluate_component(component: dict[str, object]) -> str:
    decision = component.get("decision", {})
    if decision.get("component_pass") is True:
        return "component_pass"
    if component.get("oracles", {}).get("numerical_pass") is not True:
        return "numeric_negative"
    if component.get("oracles", {}).get("no_materialization_pass") is not True:
        return "path_unproven"
    saving = decision.get("conservative_saving_seconds_per_request")
    if isinstance(saving, (int, float)) and saving > 0:
        return "retain_incremental"
    return "component_negative"


def evaluate_endpoint(endpoint_root: pathlib.Path) -> tuple[str, dict[str, object]]:
    owner = json.loads((endpoint_root / "OWNER_TERMINAL.json").read_text())
    if owner.get("classification") != "completed":
        return str(owner.get("classification", "integration_failure")), {"owner": owner}
    candidate = json.loads((endpoint_root / "exact-c32/TERMINAL.json").read_text())
    audit = [
        json.loads(line)
        for line in (endpoint_root / "qkv-audit.jsonl").read_text().splitlines()
        if line
    ]
    rows = candidate.get("rows", [])
    cache = candidate.get("cache", {})
    service = candidate.get("service_seconds_per_request")
    valid = bool(
        candidate.get("pass")
        and candidate.get("complete_requests") == 32
        and len(rows) == 32
        and all(
            row.get("prompt_tokens") == 4214
            and row.get("completion_tokens") == 358
            and row.get("text_nonempty")
            and row.get("text_finite")
            for row in rows
        )
        and cache.get("cached_prompt_tokens_delta") == 17120
        and cache.get("uncached_prompt_tokens_delta") == 117728
        and {(row["num_q_heads"], row["num_kv_heads"], row["head_dim"]) for row in audit}
        >= {(32, 16, 256), (32, 4, 512)}
        and isinstance(service, (int, float))
    )
    classification = (
        "endpoint_useful"
        if valid and service <= 0.8275116547125038
        else "endpoint_negative"
    )
    return classification, {
        "owner": owner,
        "candidate": candidate,
        "audit": audit,
        "valid": valid,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--input-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--deadline-epoch", type=int, required=True)
    parser.add_argument("--repair-window-seconds", type=int, default=600)
    args = parser.parse_args()
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = (
        benches[BENCH]
        if isinstance(benches, dict)
        else next(row for row in benches if row["id"] == BENCH)
    )
    project_status = json.loads((PROJECT / "STATUS.json").read_text())
    primary = json.loads((LAB / "projects" / PRIMARY_PROJECT / "STATUS.json").read_text())
    primary_owns_next_use = bool(
        primary.get("status") == "active"
        and (
            primary.get("active_session") is not None
            or int(primary.get("priority", 0)) >= int(project_status.get("priority", 0))
        )
    )
    if primary_owns_next_use:
        raise RuntimeError("typed_shared_dependency:primary_fp8_project_still_active")
    if bench["status"] != "available" or bench.get("claim") is not None:
        raise RuntimeError(f"typed_shared_dependency:bench_not_released:{bench['status']}")
    manifest = json.loads(args.input_manifest.read_text())
    if any(file_sha256(pathlib.Path(row["path"])) != row["sha256"] for row in manifest["files"]):
        raise RuntimeError("project-local immutable input manifest mismatch")
    runner = PROJECT / "inputs/exact_mix_runner.py"
    if file_sha256(runner) != "143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7":
        raise RuntimeError("project-local exact runner identity mismatch")
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    events = args.artifact_root / "outer-events.jsonl"
    started = time.time()

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(
                json.dumps({"time": time.time(), "event": event, **fields}, sort_keys=True)
                + "\n"
            )

    claimed = False
    remote_mutated = False
    heartbeat_stop = threading.Event()
    terminal: dict[str, object] | None = None

    def heartbeat() -> None:
        while not heartbeat_stop.wait(45):
            result = pool("heartbeat", "--project", PROJECT_NAME, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-1000:])

    thread = threading.Thread(target=heartbeat, daemon=True)

    def repairable_worker(
        ip: str,
        remote_command,
        stage: str,
        scripts: list[pathlib.Path],
        science_deadline: float,
        run_ssh,
    ) -> tuple[subprocess.CompletedProcess, int]:
        timeout = max(60, int(science_deadline - time.time()))
        command = f"timeout --signal=TERM {timeout} {remote_command(1)}"
        worker = run_ssh(ip, SSH_KEY, command, timeout=timeout + 30)
        (args.artifact_root / f"{stage}.stdout").write_text(worker.stdout)
        (args.artifact_root / f"{stage}.stderr").write_text(worker.stderr)
        if worker.returncode == 0:
            return worker, 1
        request = args.artifact_root / "REPAIR_REQUEST.json"
        ready = {
            "stage": stage,
            "returncode": worker.returncode,
            "stderr_tail": worker.stderr[-4000:],
            "repair_deadline_epoch": min(
                science_deadline, time.time() + args.repair_window_seconds
            ),
        }
        atomic(args.artifact_root / "REPAIR_READY.json", ready)
        while time.time() < ready["repair_deadline_epoch"] and not request.exists():
            time.sleep(5)
        if not request.exists() or json.loads(request.read_text()).get("retry") is not True:
            return worker, 1
        copy_to(ip, scripts, f"{REMOTE}/input/", 300)
        retry_timeout = max(60, int(science_deadline - time.time()))
        retry_command = f"timeout --signal=TERM {retry_timeout} {remote_command(2)}"
        retry = run_ssh(ip, SSH_KEY, retry_command, timeout=retry_timeout + 30)
        (args.artifact_root / f"{stage}-retry.stdout").write_text(retry.stdout)
        (args.artifact_root / f"{stage}-retry.stderr").write_text(retry.stderr)
        return retry, 2

    try:
        claim = pool(
            "claim", "--project", PROJECT_NAME, "--bench", BENCH, "--lease-seconds", "600"
        )
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
        refresh = subprocess.run(
            ["ssh-keygen", "-R", ip, "-f", str(known_hosts)],
            capture_output=True,
            text=True,
        )
        emit("known_host_refreshed", returncode=refresh.returncode)
        identity = run_ssh(
            ip,
            SSH_KEY,
            "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version",
            timeout=60,
        )
        (args.artifact_root / "remote-identity.stdout").write_text(identity.stdout)
        (args.artifact_root / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_remote_boundary:ssh_identity_failed")
        science_deadline = args.deadline_epoch - 600
        if science_deadline <= time.time() + 300:
            raise RuntimeError("typed_budget_boundary:retrieval_reserve_consumed")
        prepare = run_ssh(
            ip,
            SSH_KEY,
            f"mkdir -p {REMOTE}/input {REMOTE}/artifacts",
            timeout=60,
        )
        if prepare.returncode:
            raise RuntimeError("typed_remote_boundary:prepare_failed")
        scripts = [
            PROJECT / "qkv_epilogue_discriminator.py",
            PROJECT / "remote_component.sh",
            PROJECT / "install_endpoint_patch.py",
            PROJECT / "remote_endpoint.sh",
            runner,
        ]
        copy_to(ip, scripts, f"{REMOTE}/input/", 300)
        remote_mutated = True
        expected = {path.name: file_sha256(path) for path in scripts}
        remote_hashes = run_ssh(
            ip, SSH_KEY, f"cd {REMOTE}/input && sha256sum {' '.join(expected)}", timeout=60
        )
        (args.artifact_root / "remote-input-sha256.txt").write_text(remote_hashes.stdout)
        observed = {
            line.split(maxsplit=1)[1].lstrip("* "): line.split()[0]
            for line in remote_hashes.stdout.splitlines()
            if len(line.split(maxsplit=1)) == 2
        }
        if remote_hashes.returncode or observed != expected:
            raise RuntimeError("typed_transfer_boundary:input_hash_mismatch")
        component, component_attempt = repairable_worker(
            ip,
            lambda attempt: (
                f"env QKV_COMPONENT_RUN_ID=run-{args.artifact_root.name}-attempt-{attempt} "
                f"bash {REMOTE}/input/remote_component.sh"
            ),
            "component-worker",
            scripts,
            science_deadline,
            run_ssh,
        )
        component_run = f"run-{args.artifact_root.name}-attempt-{component_attempt}"
        candidate_start = run_ssh(
            ip,
            SSH_KEY,
            f"cat {REMOTE}/artifacts/component/{component_run}/SCIENTIFIC_STARTED",
            timeout=30,
        )
        compact_terminal = run_ssh(
            ip, SSH_KEY, f"cat {REMOTE}/artifacts/component/{component_run}/TERMINAL.json", timeout=30
        )
        compact_result = run_ssh(
            ip, SSH_KEY, f"cat {REMOTE}/artifacts/component/{component_run}/RESULT.json", timeout=30
        )
        (args.artifact_root / "component-SCIENTIFIC_STARTED").write_text(
            candidate_start.stdout
        )
        (args.artifact_root / "component-TERMINAL.json").write_text(compact_terminal.stdout)
        (args.artifact_root / "component-RESULT.json").write_text(compact_result.stdout)
        if (
            component.returncode
            or candidate_start.returncode
            or compact_terminal.returncode
            or compact_result.returncode
        ):
            raise RuntimeError("component_runtime_failure")
        component_result = json.loads(compact_result.stdout)
        component_classification = evaluate_component(component_result)
        emit("component_persisted", classification=component_classification)

        component_partial = args.artifact_root / ".component.tar.gz.partial"
        component_sidecar = args.artifact_root / "component.tar.gz.sha256"
        scp_from(ip, SSH_KEY, f"{REMOTE}/component.tar.gz", component_partial)
        scp_from(ip, SSH_KEY, f"{REMOTE}/component.tar.gz.sha256", component_sidecar)
        if file_sha256(component_partial) != component_sidecar.read_text().split()[0]:
            raise RuntimeError("typed_retrieval_boundary:component_archive_hash_mismatch")
        component_archive = args.artifact_root / "component.tar.gz"
        component_partial.replace(component_archive)
        extract_archive(component_archive, args.artifact_root / "component")

        endpoint_detail = None
        classification = component_classification
        if component_classification == "component_pass":
            endpoint, _ = repairable_worker(
                ip,
                lambda _attempt: f"bash {REMOTE}/input/remote_endpoint.sh",
                "endpoint-worker",
                scripts,
                science_deadline,
                run_ssh,
            )
            endpoint_partial = args.artifact_root / ".endpoint.tar.gz.partial"
            endpoint_sidecar = args.artifact_root / "endpoint.tar.gz.sha256"
            scp_from(ip, SSH_KEY, f"{REMOTE}/endpoint-terminal.tar.gz", endpoint_partial)
            scp_from(ip, SSH_KEY, f"{REMOTE}/endpoint-terminal.tar.gz.sha256", endpoint_sidecar)
            if file_sha256(endpoint_partial) != endpoint_sidecar.read_text().split()[0]:
                raise RuntimeError("typed_retrieval_boundary:endpoint_archive_hash_mismatch")
            endpoint_archive = args.artifact_root / "endpoint.tar.gz"
            endpoint_partial.replace(endpoint_archive)
            endpoint_root = args.artifact_root / "endpoint"
            extract_archive(endpoint_archive, endpoint_root)
            classification, endpoint_detail = evaluate_endpoint(endpoint_root)
            if endpoint.returncode and classification not in {
                "integration_failure",
                "endpoint_negative",
                "path_unproven",
            }:
                raise RuntimeError("endpoint_runtime_failure")

        elapsed = time.time() - started
        terminal = {
            "schema_version": 1,
            "status": "terminal",
            "classification": classification,
            "pass": classification in {"endpoint_useful", "retain_incremental"},
            "component": component_result,
            "endpoint": endpoint_detail,
            "provider_exposure_seconds": elapsed,
            "provider_spend_usd_conservative": elapsed * RATE / 3600,
        }
        atomic(args.artifact_root / "TERMINAL.json", terminal)
        emit("terminal", classification=classification)
        return 0 if terminal["pass"] else 1
    except Exception as error:
        emit("outer_error", error_type=type(error).__name__, message=str(error))
        if terminal is None:
            terminal = {
                "schema_version": 1,
                "status": "terminal",
                "classification": "owner_failure",
                "pass": False,
                "error": {"type": type(error).__name__, "message": str(error)},
                "provider_exposure_seconds": time.time() - started,
                "provider_spend_usd_conservative": (time.time() - started) * RATE / 3600,
            }
            atomic(args.artifact_root / "TERMINAL.json", terminal)
        return 1
    finally:
        heartbeat_stop.set()
        if thread.is_alive():
            thread.join(timeout=5)
        if claimed:
            classification = (terminal or {}).get("classification", "owner_failure")
            contents = {
                "project": PROJECT_NAME,
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "checkpoint": "Exact immutable checkpoint retained at /home/glmrunner/gemma-kernel-frontier/checkpoint if staged by the primary FP8 project.",
                "image": "Pinned SGLang v0.5.12 image retained if staged by the primary FP8 project.",
                "runtime": f"QKV epilogue schedule terminal: {classification}.",
                "caches": "Triton and any endpoint CUDA-graph compilation caches retained.",
                "server_state": "BF16 QKV-epilogue server retained if the conditional endpoint completed healthy; otherwise no server guarantee.",
                "artifacts": "Component terminal and any conditional endpoint terminal retrieved project-locally.",
            }
            contents_path = args.artifact_root / "BENCH_CONTENTS.json"
            atomic(contents_path, contents)
            condition = "maintenance" if classification == "owner_failure" else "ready"
            release = pool(
                "release",
                "--project",
                PROJECT_NAME,
                "--condition",
                condition,
                "--contents",
                str(contents_path),
                check=False,
            )
            emit(
                "released",
                condition=condition,
                returncode=release.returncode,
                stderr=release.stderr[-1000:],
            )


if __name__ == "__main__":
    raise SystemExit(main())
