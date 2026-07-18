#!/usr/bin/env python3
"""Durable owner for the admitted exact-vLLM owner-local-view experiment."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
LAB = HERE.parent.parent
LOWER_PATH = HERE.parent / "exact_vllm_h200_transfer_view_endpoint/launch_transfer_view.py"
RUNNER = HERE / "trace_endpoint_runner.py"
FIXED_OWNER = HERE.parent / "exact_vllm_h200_fixed_session_endpoint/vllm_fixed_session_owner.py"
TRACE = HERE.parent / "gemma_exact_cache_trace_contract/TRACE_PACKET.json"
ASSERTION = HERE / "artifacts/DIRECTOR_IDENTITY_ASSERTION.json"
STATUS = HERE / "STATUS.json"
RAW_CHECKPOINT = HERE.parent / "sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint"
CHECKPOINT_TERMINAL = RAW_CHECKPOINT.parent / "CHECKPOINT_TERMINAL.json"
RUNTIME_PARENT = Path("/root/workspace/.agents/runtime/gemma4-31b")
NEBIUS_TOOLS = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0, str(NEBIUS_TOOLS))

from placement_control import (  # noqa: E402
    VerifiedRetainedOwner,
    build_create_command,
    extract_instance_id,
    extract_public_ipv4,
    get_instance,
    make_cloud_init,
    wait_ssh,
)
from session_staging import (  # noqa: E402
    checkpoint_files,
    transfer_checkpoint,
    transfer_timeout_seconds,
    validate_local_files_cached,
)
from stock_control import run_ssh, scp_from, scp_to  # noqa: E402
from vllm_smoke_control import start_independent_watchdog, write_create_diagnostic  # noqa: E402


KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUB = KEY.with_suffix(".pub")
WORK = "/home/glmrunner/gemma-owner-local-view"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


lower = load_module(LOWER_PATH, "exact_vllm_corrected_lower")
lower.fixed.WORK = WORK
lower.fixed.RUNNER = RUNNER


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def emit(path: Path, event: str, **fields: object) -> None:
    with path.open("a") as handle:
        handle.write(canonical({"epoch": time.time(), "event": event, **fields}) + "\n")


def update_status(**fields: object) -> None:
    value = json.loads(STATUS.read_text())
    value.update(fields)
    write(STATUS, value)


def normalized_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        [
            {"path": str(row["path"]), "sha256": str(row["sha256"]), "bytes": int(row["bytes"])}
            for row in rows
        ],
        key=lambda row: str(row["path"]),
    )


def find_terminal_rows(value: object, expected: list[dict[str, object]]) -> list[dict[str, object]]:
    wanted = normalized_rows(expected)
    candidates: list[list[dict[str, object]]] = []

    def walk(node: object) -> None:
        if isinstance(node, list) and node and all(isinstance(row, dict) for row in node):
            if all({"path", "sha256", "bytes"}.issubset(row) for row in node):
                candidates.append(node)  # type: ignore[arg-type]
        if isinstance(node, dict):
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    for rows in candidates:
        if normalized_rows(rows) == wanted:
            return normalized_rows(rows)
    raise RuntimeError("checkpoint_terminal_rows_not_bound_to_director_assertion")


def identity() -> tuple[dict[str, bool], list[dict[str, object]]]:
    assertion = json.loads(ASSERTION.read_text())
    terminal = json.loads(CHECKPOINT_TERMINAL.read_text())
    rows = normalized_rows(terminal["files"])
    checks = {
        "director_assertion": assertion.get("pass") is True,
        "checkpoint_terminal_pass": terminal.get("pass") is True,
        "checkpoint_index": sha(RAW_CHECKPOINT / "model.safetensors.index.json") == assertion["bound"]["checkpoint_index_sha256"],
        "trace_hash": sha(TRACE) == assertion["bound"]["trace_sha256"],
        "staging_hash": sha(NEBIUS_TOOLS / "session_staging.py") == assertion["bound"]["staging_sha256"],
        "checkpoint_source": RAW_CHECKPOINT.is_dir(),
        "terminal_rows": len(rows) == 8,
        "exact_model": lower.fixed.MODEL == assertion["bound"]["model"],
        "exact_revision": lower.fixed.REV == assertion["bound"]["revision"],
        "exact_image": lower.fixed.IMAGE == assertion["bound"]["runtime_image"],
    }
    if not all(checks.values()):
        raise RuntimeError("owner_local_immutable_identity_gate_failed")
    return checks, rows


def manifest_text(rows: list[dict[str, object]]) -> str:
    return "".join(f"{row['sha256']}  {row['path']}\n" for row in rows)


def view_checks(view: Path, rows: list[dict[str, object]], *, validate_cached: bool) -> dict[str, object]:
    expected_manifest = manifest_text(rows)
    manifest = view / "model-files.sha256"
    link_rows = []
    for row in rows:
        source = RAW_CHECKPOINT / str(row["path"])
        target = view / str(row["path"])
        source_stat = source.stat()
        target_stat = target.stat()
        link_rows.append(
            {
                "path": row["path"],
                "bytes": target_stat.st_size,
                "same_device": source_stat.st_dev == target_stat.st_dev,
                "same_inode": source_stat.st_ino == target_stat.st_ino,
                "size_pass": target_stat.st_size == int(row["bytes"]),
            }
        )
    discovered = checkpoint_files(view)
    discovered_rows = []
    for row in discovered:
        if dataclasses.is_dataclass(row):
            value = dataclasses.asdict(row)
        elif hasattr(row, "_asdict"):
            value = row._asdict()
        elif hasattr(row, "__dict__"):
            value = dict(row.__dict__)
        else:
            value = {"repr": repr(row)}
        discovered_rows.append(json.loads(json.dumps(value, default=str)))
    cached_pass = validate_local_files_cached(view, rows, persist_marker=True) if validate_cached else False
    checks = {
        "manifest_exact": manifest.read_text() == expected_manifest,
        "manifest_sha256": sha(manifest),
        "hardlinks_pass": all(row["same_device"] and row["same_inode"] and row["size_pass"] for row in link_rows),
        "checkpoint_files_count": len(discovered) == len(rows) + 1,
        "cached_integrity_pass": cached_pass,
    }
    return {"pass": all(value for key, value in checks.items() if key != "manifest_sha256"), "checks": checks, "links": link_rows, "checkpoint_files": discovered_rows}


def hashing_monitor(stop: threading.Event, output: Path, total_bytes: int, started_io: dict[str, int]) -> None:
    while not stop.wait(2):
        try:
            current = {}
            for line in Path(f"/proc/{os.getpid()}/io").read_text().splitlines():
                key, value = line.split(":", 1)
                current[key] = int(value.strip())
            write(
                output,
                {
                    "schema_version": 1,
                    "classification": "correct_owner_local_hashing_progress",
                    "stage": "session_staging_validate_local_files_cached",
                    "pid": os.getpid(),
                    "total_checkpoint_bytes": total_bytes,
                    "process_read_char_delta": current.get("rchar", 0) - started_io.get("rchar", 0),
                    "process_storage_read_bytes_delta": current.get("read_bytes", 0) - started_io.get("read_bytes", 0),
                    "observed_epoch": time.time(),
                },
            )
        except Exception:
            pass


def create_view(view: Path, rows: list[dict[str, object]], run_out: Path) -> dict[str, object]:
    view.mkdir(parents=True, exist_ok=False)
    for row in rows:
        source = RAW_CHECKPOINT / str(row["path"])
        target = view / str(row["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(source, target)
    temporary = view / "model-files.sha256.part"
    temporary.write_text(manifest_text(rows))
    temporary.replace(view / "model-files.sha256")
    started_io = {}
    for line in Path(f"/proc/{os.getpid()}/io").read_text().splitlines():
        key, value = line.split(":", 1)
        started_io[key] = int(value.strip())
    progress_path = HERE / "artifacts/HASHING_PROGRESS.json"
    write(
        progress_path,
        {
            "schema_version": 1,
            "classification": "correct_owner_local_hashing_progress",
            "stage": "session_staging_validate_local_files_cached_started",
            "pid": os.getpid(),
            "total_checkpoint_bytes": sum(int(row["bytes"]) for row in rows),
            "observed_epoch": time.time(),
        },
    )
    stop = threading.Event()
    monitor = threading.Thread(
        target=hashing_monitor,
        args=(stop, progress_path, sum(int(row["bytes"]) for row in rows), started_io),
        daemon=True,
    )
    monitor.start()
    try:
        result = view_checks(view, rows, validate_cached=True)
    finally:
        stop.set()
        monitor.join(timeout=5)
    terminal = {
        "schema_version": 1,
        "classification": "run_local_view_terminal",
        "pass": result["pass"],
        "view": str(view),
        "source_checkpoint": str(RAW_CHECKPOINT),
        "rows": rows,
        **result,
        "owner_pid": os.getpid(),
        "observed_epoch": time.time(),
    }
    write(run_out / "RUN_LOCAL_VIEW_TERMINAL.json", terminal)
    write(HERE / "artifacts/RUN_LOCAL_VIEW_TERMINAL.json", terminal)
    if not terminal["pass"]:
        raise RuntimeError("run_local_view_terminal_failed")
    return terminal


def recheck_view(view: Path, rows: list[dict[str, object]], output: Path, stage: str) -> None:
    result = view_checks(view, rows, validate_cached=True)
    terminal = {
        "schema_version": 1,
        "classification": "run_local_view_immediate_recheck",
        "stage": stage,
        "observed_epoch": time.time(),
        **result,
    }
    write(output, terminal)
    if not terminal["pass"]:
        raise RuntimeError(f"run_local_view_recheck_failed:{stage}")


def actual_lower_audit(output: Path, name: str, deadline_epoch: int, identity_checks: dict[str, bool]) -> str:
    lower.fixed.CHECKPOINT = RUNTIME_PARENT / name / "checkpoint"
    rendered = lower.corrected_remote(deadline_epoch)
    rendered = rendered.replace(
        '--mode baseline_after_semantic',
        f'--mode endpoint_c16_c32 --deadline-epoch {deadline_epoch}',
    )
    rendered_path = output.parent / "RENDERED_REMOTE.sh"
    rendered_path.write_text(rendered)
    rendered_path.chmod(0o700)
    runner_text = RUNNER.read_text()
    owner_text = Path(__file__).read_text()
    checks = {
        **identity_checks,
        "rendered_nonempty": len(rendered) > 1000,
        "docker_bootstrap": "nvidia-container-toolkit" in rendered and "systemctl enable --now docker" in rendered,
        "diagnostic_entrypoint": "--entrypoint nvidia-smi" in rendered,
        "server_entrypoint": "--entrypoint vllm" in rendered and " serve " in rendered,
        "container_exit_fails_readiness": "docker inspect -f" in rendered and "exit 70" in rendered,
        "semantic_then_scored_ladder": rendered.index("--mode semantic") < rendered.index("--mode endpoint_c16_c32") and 'packet["primary_groups"][-1:]' in runner_text,
        "simultaneous_concurrency": "threading.Barrier" in runner_text and "ThreadPoolExecutor" in runner_text,
        "separate_10k": "separate_10k_stream" in runner_text,
        "c32_decision_headroom_gate": "primary_c32" in runner_text and "c32_gate" in runner_text and "deadline_epoch" in runner_text,
        "exit_trap_logs_metrics": "trap finalize EXIT" in rendered and "metrics-final.prom" in rendered and "server.log" in rendered,
        "telemetry_stopped_before_tar": rendered.index("kill \"$(cat \"$w/runtime/gpu-telemetry.pid\")") < rendered.index("tar --sort=name"),
        "atomic_tar_checksum": "results.tar.gz.part" in rendered and "results.tar.gz.sha256.part" in rendered,
        "token_and_itl": "per_token_arrival_seconds" in runner_text and "inter_token_latency_seconds" in runner_text,
        "queue_prefill_decode_metrics": "/metrics" in runner_text and "metrics-final.prom" in rendered,
        "provider_useful_cost_accounting": "provider_active_seconds" in rendered and "useful_gpu_seconds" in runner_text and "estimated_compute_cost_usd" in rendered,
        "durable_user_owner": "INVOCATION_ID" in owner_text and "SYSTEMD_EXEC_PID" in owner_text,
        "shared_watchdog": "unit_manager=\"user\"" in owner_text,
        "shared_lifecycle": "VerifiedRetainedOwner" in owner_text,
        "conditional_sglang": "VLLM_MARKET_TRIGGER" in rendered and "sglang.launch_server" in rendered and "2.094181" in rendered,
        "exact_remote_paths": f"w={WORK}" in rendered and f"-v \"$w:$w\"" in rendered and "$w/input/trace_endpoint_runner.py" in rendered,
        "served_model_matches_requests": "--served-model-name 'google/gemma-4-31B-it'" in rendered,
    }
    terminal = {
        "schema_version": 1,
        "classification": "actual_lower_behavioral_audit",
        "pass": all(checks.values()),
        "checks": checks,
        "rendered_remote_sha256": sha(rendered_path),
        "rendered_remote": str(rendered_path),
        "deadline_epoch": deadline_epoch,
        "name": name,
    }
    write(output, terminal)
    write(HERE / "artifacts/FINAL_AUDIT.json", terminal)
    if not terminal["pass"]:
        raise RuntimeError("actual_lower_behavioral_audit_failed")
    return rendered


def ownership_snapshot(path: Path, name: str, stage: str, deadline_epoch: float | None = None, **fields: object) -> None:
    snapshot = {
        "schema_version": 1,
        "classification": "durable_owner_watchdog_snapshot",
        "name": name,
        "stage": stage,
        "pid": os.getpid(),
        "invocation_id_present": bool(os.getenv("INVOCATION_ID")),
        "systemd_exec_pid": os.getenv("SYSTEMD_EXEC_PID"),
        "pid_matches_systemd_exec_pid": os.getenv("SYSTEMD_EXEC_PID") == str(os.getpid()),
        "cgroup": Path("/proc/self/cgroup").read_text().strip(),
        "deadline_epoch": deadline_epoch,
        "observed_epoch": time.time(),
        **fields,
    }
    write(path, snapshot)
    write(HERE / "artifacts/OWNER_WATCHDOG_SNAPSHOT.json", snapshot)


def safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, "r:gz") as handle:
        for member in handle.getmembers():
            target = (destination / member.name).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise RuntimeError("unsafe_result_archive_member")
        handle.extractall(destination)


def run(parent: Path, name: str, wall_seconds: int, provider_seconds: int) -> int:
    if not os.getenv("INVOCATION_ID") or os.getenv("SYSTEMD_EXEC_PID") != str(os.getpid()):
        raise RuntimeError("durable user systemd owner required")
    if name != name.lower() or not all(char.islower() or char.isdigit() or char == "-" for char in name):
        raise RuntimeError("owner_name_not_rfc1123_lowercase")
    if wall_seconds != 7200 or provider_seconds != 5100:
        raise RuntimeError("budget_contract_mismatch")
    started = time.time()
    wall_deadline = started + wall_seconds
    run_out = parent / f"{name}-run"
    run_out.mkdir(parents=True, exist_ok=False)
    events = run_out / "events.jsonl"
    view_root = RUNTIME_PARENT / name
    view = view_root / "checkpoint"
    stage = "identity"
    instance_id = None
    transfer_complete = False
    terminal = False
    update_status(
        summary="Durable owner is constructing and validating the unique run-local checkpoint view before any provider create.",
        next_action="Do not restart: follow the durable user-systemd owner through local hashing, gated provider create, transfer, and endpoint terminal.",
        active_session={"name": name, "stage": stage, "owner_pid": os.getpid(), "wall_deadline_epoch": wall_deadline},
    )
    try:
        checks, rows = identity()
        with VerifiedRetainedOwner(name, run_out / "cleanup.json") as owner:
            ownership_snapshot(run_out / "owner-snapshot.json", name, "local_view_construction", wall_deadline, identity_checks=checks)
            emit(events, "owner_started", wall_deadline_epoch=wall_deadline, checks=checks)
            stage = "local_view_validation"
            local_terminal = create_view(view, rows, run_out)
            emit(events, "run_local_view_terminal", terminal_sha256=sha(run_out / "RUN_LOCAL_VIEW_TERMINAL.json"))
            update_status(
                run_local_view_terminal="artifacts/RUN_LOCAL_VIEW_TERMINAL.json",
                active_session={"name": name, "stage": "provider_preflight", "owner_pid": os.getpid(), "wall_deadline_epoch": wall_deadline},
            )
            stage = "provider_preflight"
            preflight_path = run_out / "PROVIDER_PREFLIGHT.json"
            if lower.preflight(preflight_path) != 0:
                shutil.copy2(preflight_path, HERE / "artifacts/PROVIDER_PREFLIGHT.json")
                raise RuntimeError("authenticated_provider_preflight_failed")
            shutil.copy2(preflight_path, HERE / "artifacts/PROVIDER_PREFLIGHT.json")
            if time.time() + provider_seconds > wall_deadline:
                raise RuntimeError("insufficient_wall_headroom_for_bounded_provider_session")
            provider_deadline = time.time() + provider_seconds
            stage = "actual_lower_audit"
            rendered = actual_lower_audit(run_out / "FINAL_AUDIT.json", name, int(provider_deadline), checks)
            stage = "precreate_view_recheck"
            recheck_view(view, rows, run_out / "PRECREATE_VIEW_RECHECK.json", "immediately_before_create")
            create_command = build_create_command(
                name=name,
                disk_name=name + "-boot",
                cloud_init=make_cloud_init(PUB.read_text()),
                disk_gib=250,
                platform="gpu-h200-sxm",
                preset="1gpu-16vcpu-200gb",
                preemptible=True,
            )
            stage = "provider_create"
            proc = subprocess.run(create_command, capture_output=True, text=True, timeout=180)
            write_create_diagnostic(run_out, proc)
            if proc.returncode:
                raise RuntimeError("provider_create_failed")
            instance_id = extract_instance_id(json.loads(proc.stdout))
            owner.bind_instance(instance_id)
            watchdog = start_independent_watchdog(
                instance_id,
                name + "-boot",
                provider_deadline,
                name + "-watchdog",
                unit_manager="user",
            )
            write(run_out / "watchdog.json", watchdog)
            ownership_snapshot(
                run_out / "owner-watchdog-snapshot.json",
                name,
                "provider_created_waiting_for_ip",
                provider_deadline,
                instance_id=instance_id,
                disk_name=name + "-boot",
                watchdog=watchdog,
                run_local_view_terminal_sha256=sha(run_out / "RUN_LOCAL_VIEW_TERMINAL.json"),
            )
            emit(events, "provider_created", instance_id=instance_id, watchdog=watchdog)
            update_status(
                summary="One H200 allocation is live under the durable owner and shared user watchdog; transfer and exact endpoint science are sequentially owned.",
                active_session={"name": name, "stage": "provider_created_waiting_for_ip", "instance_id": instance_id, "provider_deadline_epoch": provider_deadline, "watchdog": watchdog},
            )
            stage = "public_ip"
            ip = None
            ip_deadline = min(provider_deadline, time.time() + 600)
            while time.time() < ip_deadline:
                item = get_instance(instance_id)
                ip = extract_public_ipv4(item) if item else None
                if ip:
                    break
                time.sleep(5)
            if not ip:
                raise RuntimeError("public_ip_timeout")
            stage = "ssh"
            wait_ssh(ip, KEY, min(provider_deadline, time.time() + 600))
            prep = run_ssh(
                ip,
                KEY,
                f"sudo install -d -o glmrunner -g glmrunner {WORK} {WORK}/model {WORK}/input {WORK}/artifacts {WORK}/runtime && test -w {WORK}/model",
                timeout=60,
            )
            write(run_out / "session-parent.json", {"returncode": prep.returncode, "stdout": prep.stdout, "stderr": prep.stderr[-4096:]})
            if prep.returncode:
                raise RuntimeError("glmrunner_session_parent_create_failed")
            stage = "pretransfer_view_recheck"
            recheck_view(view, rows, run_out / "PRETRANSFER_VIEW_RECHECK.json", "immediately_before_transfer_checkpoint")
            stage = "checkpoint_transfer"
            total_bytes = sum(int(row["bytes"]) for row in rows)
            timeout = min(transfer_timeout_seconds(total_bytes), max(900, int(provider_deadline - time.time() - 900)))
            transfer = transfer_checkpoint(ip, KEY, view, WORK + "/model", timeout_seconds=timeout)
            transfer_value = dataclasses.asdict(transfer) if dataclasses.is_dataclass(transfer) else dict(transfer.__dict__)
            write(run_out / "checkpoint-transfer.json", transfer_value)
            emit(events, "checkpoint_transferred", **transfer_value)
            transfer_complete = True
            shutil.rmtree(view_root)
            stage = "program_transfer"
            scp_to(ip, KEY, [TRACE, RUNNER], WORK + "/input/")
            stage = "science"
            ownership_snapshot(
                run_out / "owner-watchdog-snapshot.json",
                name,
                "exact_endpoint_science",
                provider_deadline,
                instance_id=instance_id,
                disk_name=name + "-boot",
                watchdog=watchdog,
                checkpoint_transfer=transfer_value,
            )
            update_status(
                active_session={"name": name, "stage": "exact_endpoint_science", "instance_id": instance_id, "provider_deadline_epoch": provider_deadline, "watchdog": watchdog}
            )
            remote = run_ssh(
                ip,
                KEY,
                "bash -s",
                timeout=max(60, int(provider_deadline - time.time() - 120)),
                input_text=rendered,
            )
            write(
                run_out / "remote-diagnostic.json",
                {"returncode": remote.returncode, "stdout": remote.stdout[-16000:], "stderr": remote.stderr[-16000:]},
            )
            stage = "retrieval"
            archive = run_out / "results.tar.gz"
            checksum = run_out / "results.tar.gz.sha256"
            scp_from(ip, KEY, WORK + "/results.tar.gz", archive)
            scp_from(ip, KEY, WORK + "/results.tar.gz.sha256", checksum)
            if sha(archive) != checksum.read_text().split()[0]:
                raise RuntimeError("retrieved_archive_checksum_mismatch")
            bundle = run_out / "endpoint-bundle"
            safe_extract(archive, bundle)
            summary_path = bundle / "artifacts/SUMMARY.json"
            trigger_path = bundle / "artifacts/VLLM_MARKET_TRIGGER.json"
            summary = json.loads(summary_path.read_text())
            trigger = json.loads(trigger_path.read_text())
            semantic_pass = summary.get("semantic", {}).get("pass") is True
            vllm_pass = summary.get("vllm", {}).get("pass") is True
            conditional_pass = True
            if trigger.get("pass") is True:
                sglang_terminal = bundle / "artifacts/sglang/TERMINAL.json"
                conditional_pass = trigger.get("run_sglang") is True and sglang_terminal.is_file() and json.loads(sglang_terminal.read_text()).get("pass") is True
            write(HERE / "artifacts/SUMMARY.json", summary)
            write(HERE / "artifacts/VLLM_MARKET_TRIGGER.json", trigger)
            write(
                run_out / "LOCAL_TERMINAL_EVALUATION.json",
                {
                    "schema_version": 1,
                    "classification": "retrieved_exact_endpoint_terminal_evaluation",
                    "pass": remote.returncode == 0 and semantic_pass and vllm_pass and conditional_pass,
                    "remote_returncode": remote.returncode,
                    "semantic_pass": semantic_pass,
                    "vllm_pass": vllm_pass,
                    "conditional_pass": conditional_pass,
                    "summary_sha256": sha(summary_path),
                    "trigger_sha256": sha(trigger_path),
                },
            )
            if remote.returncode or not semantic_pass or not vllm_pass or not conditional_pass:
                raise RuntimeError("typed_remote_science_failure")
            owner.complete("exact_vllm_h200_owner_local_view_endpoint_terminal")
            terminal = True
            update_status(
                status="completed",
                summary="Exact vLLM endpoint terminal retrieved and evaluated; authenticated retained-owner cleanup completed.",
                next_action="Director should consume artifacts/SUMMARY.json and VLLM_MARKET_TRIGGER.json.",
                active_session=None,
                terminal_artifact="artifacts/SUMMARY.json",
                last_result_classification="exact_vllm_owner_local_view_endpoint_terminal",
            )
            return 0
    except Exception as error:
        classification = "typed_precreate_failure" if instance_id is None else "typed_paid_endpoint_failure"
        failure = {
            "schema_version": 1,
            "classification": classification,
            "stage": stage,
            "error_type": type(error).__name__,
            "message": str(error)[:4000],
            "instance_id": instance_id,
            "provider_mutations": 0 if instance_id is None else 1,
            "observed_epoch": time.time(),
        }
        write(run_out / "failure.json", failure)
        write(HERE / "artifacts/FAILURE.json", failure)
        emit(events, "failure", **failure)
        update_status(
            status="completed",
            summary=f"Owner produced {classification} at {stage}; no paid repair is authorized.",
            next_action="Director should consume artifacts/FAILURE.json and reallocate the lane.",
            active_session=None,
            terminal_artifact="artifacts/FAILURE.json",
            last_result_classification=classification,
        )
        return 1
    finally:
        if view_root.exists() and (transfer_complete or terminal or instance_id is None):
            shutil.rmtree(view_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("run")
    command.add_argument("--artifacts-parent", type=Path, required=True)
    command.add_argument("--name", required=True)
    command.add_argument("--wall-seconds", type=int, default=7200)
    command.add_argument("--provider-seconds", type=int, default=5100)
    args = parser.parse_args()
    return run(args.artifacts_parent, args.name, args.wall_seconds, args.provider_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
