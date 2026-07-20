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


NAME = "gemma4_h200_v0513_fp8_qkv_residual_profile"
LAB = pathlib.Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
REMOTE = "/home/glmrunner/gemma4-h200-v0513-fp8-qkv-residual-profile"
AUTHORIZED_USD = 8.0
MAX_CLAIM_SECONDS = 150 * 60
RETRIEVAL_RESERVE_SECONDS = 15 * 60

REMOTE_NAMES = {
    "authoritative_qkv_terminal": "AUTHORITATIVE_QKV_TERMINAL.json",
    "endpoint_entrypoint": "proven_v0513_endpoint_entrypoint.py",
    "paired_runner": "proven_v0513_paired_endpoint_runner.py",
    "qkv_runner": "fp8_qkv_paired_runner.py",
    "qkv_sitecustomize": "bound_stack_sitecustomize.py",
    "qkv_installer": "install_endpoint_patch.py",
    "qkv_kernel": "qkv_epilogue_discriminator.py",
    "qkv_launcher": "bound_remote_fp8_stack.sh",
    "qkv_input_manifest": "FP8_QKV_INPUT_MANIFEST.json",
}


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


def scp_to(ip: str, source: pathlib.Path, destination: str, timeout: int) -> None:
    result = run(
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
            str(source),
            f"glmrunner@{ip}:{destination}",
        ],
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"typed_transfer_boundary:scp_failed:{source.name}:{result.stderr[-1200:]}")


def scp_from(ip: str, source: str, destination: pathlib.Path, timeout: int) -> None:
    result = run(
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
            f"glmrunner@{ip}:{source}",
            str(destination),
        ],
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"typed_retrieval_boundary:scp_failed:{source}:{result.stderr[-1200:]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--absolute-deadline-epoch", type=int, required=True)
    parser.add_argument("--pair-only", action="store_true")
    parser.add_argument("--intervention-request", type=pathlib.Path)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    events = args.artifact_root / "outer-events.jsonl"
    pair_intervention: dict[str, object] | None = None
    pair_boundary: str | None = None
    if args.pair_only:
        if args.intervention_request is None:
            raise RuntimeError("pair_intervention_request_missing")
        request_path = args.intervention_request.resolve()
        if PROJECT not in request_path.parents:
            raise RuntimeError("pair_intervention_request_outside_project")
        pair_intervention = json.loads(request_path.read_text())
        pair_boundary = str(pair_intervention.get("boundary"))
        if pair_boundary not in {"attention_kv", "fp8_linear", "global_attention"}:
            raise RuntimeError("pair_intervention_boundary_invalid")

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(json.dumps({"epoch": time.time(), "event": event, **fields}, sort_keys=True) + "\n")
            handle.flush()

    manifest = json.loads((PROJECT / "INPUT_MANIFEST.json").read_text())
    if manifest.get("pass") is not True or sha256(PROJECT / "BINDINGS.json") != manifest["bindings_sha256"]:
        raise RuntimeError("project_local_input_manifest_invalid")
    for row in manifest["bound_files"] + manifest["checkpoint_files"]:
        path = PROJECT / row["path"]
        if not path.is_file() or path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            raise RuntimeError(f"project_local_snapshot_invalid:{row['path']}")
    local_programs = (PROJECT / "remote_profile_pair.sh", PROJECT / "residual_sitecustomize.py", PROJECT / "analyze_profile.py")
    for path in local_programs:
        if not path.is_file():
            raise RuntimeError(f"local_program_missing:{path.name}")

    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = benches[args.bench] if isinstance(benches, dict) else next(row for row in benches if row["id"] == args.bench)
    if bench["accelerator"] != "nvidia-h200-sxm":
        raise RuntimeError("typed_pool_boundary:bench_not_h200_sxm")
    rate = float(bench["hourly_cost_usd"])
    prior_spend = float(json.loads((PROJECT / "STATUS.json").read_text()).get("measured_project_spend_usd", 0.0))
    remaining_spend = AUTHORIZED_USD - prior_spend
    budget_seconds = int(remaining_spend * 3600 / rate)
    claim_deadline = min(args.absolute_deadline_epoch, int(time.time()) + MAX_CLAIM_SECONDS, int(time.time()) + budget_seconds)
    if claim_deadline <= time.time() + RETRIEVAL_RESERVE_SECONDS + 600:
        raise RuntimeError("typed_budget_boundary:insufficient_claim_window")

    started = time.time()
    claimed = False
    terminal: dict[str, object] | None = None
    release_condition = "ready"
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-1000:])

    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    ip: str | None = None
    worker_terminal: dict[str, object] = {}
    invocation_state: dict[str, object] = {}
    if pair_boundary == "attention_kv":
        remote_artifacts = f"{REMOTE}/attention-artifacts-v2"
    elif pair_boundary == "fp8_linear":
        remote_artifacts = f"{REMOTE}/fp8-linear-artifacts"
    elif pair_boundary == "global_attention":
        remote_artifacts = f"{REMOTE}/global-attention-artifacts"
    else:
        remote_artifacts = f"{REMOTE}/artifacts"

    try:
        lease = max(600, claim_deadline - int(time.time()))
        claim = pool("claim", "--project", NAME, "--bench", args.bench, "--lease-seconds", str(lease))
        claimed = True
        emit("claimed", claim=json.loads(claim.stdout))
        heartbeat_thread.start()

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
        prepare = run_ssh(ip, KEY, f"mkdir -p {REMOTE}/input {REMOTE}/checkpoint {remote_artifacts}", timeout=60)
        if prepare.returncode:
            raise RuntimeError("typed_remote_boundary:prepare_failed")

        def stage(source: pathlib.Path, remote_name: str, remote_directory: str) -> None:
            expected = sha256(source)
            final = f"{remote_directory}/{remote_name}"
            partial = f"{remote_directory}/.{remote_name}.{expected}.part"
            matched = run_ssh(
                ip,
                KEY,
                f"test -f {shlex.quote(final)} && test \"$(sha256sum {shlex.quote(final)} | awk '{{print $1}}')\" = {shlex.quote(expected)}",
                timeout=max(60, min(900, claim_deadline - int(time.time()))),
            )
            if matched.returncode:
                scp_to(ip, source, partial, max(60, claim_deadline - int(time.time()) - RETRIEVAL_RESERVE_SECONDS))
                finalized = run_ssh(
                    ip,
                    KEY,
                    f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {shlex.quote(expected)} && chmod 0444 {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {shlex.quote(final)}",
                    timeout=max(120, min(1800, claim_deadline - int(time.time()))),
                )
                if finalized.returncode:
                    raise RuntimeError(f"typed_transfer_boundary:hash_or_finalize_failed:{remote_name}")
            emit("input_staged", name=remote_name, sha256=expected, bytes=source.stat().st_size)

        for row in manifest["checkpoint_files"]:
            stage(PROJECT / row["path"], row["name"], f"{REMOTE}/checkpoint")
        bound = {row["label"]: row for row in manifest["bound_files"]}
        for label, remote_name in REMOTE_NAMES.items():
            stage(PROJECT / bound[label]["path"], remote_name, f"{REMOTE}/input")
        stage(PROJECT / "residual_sitecustomize.py", "sitecustomize.py", f"{REMOTE}/input")
        stage(PROJECT / "remote_profile_pair.sh", "remote_profile_pair.sh", f"{REMOTE}/input")
        reset_fp8_candidate = PROJECT / "RESET_INVALID_FP8_CANDIDATE.json"
        if pair_boundary == "fp8_linear" and reset_fp8_candidate.is_file():
            stage(reset_fp8_candidate, reset_fp8_candidate.name, f"{REMOTE}/input")
        if args.pair_only:
            attention = PROJECT / "intervention/attention_deferred_local_kv.py"
            if sha256(attention) != "4e11a14e2dc149789a4b4350e02de3d3283ad88fc259d6417f05a734fc1451d8":
                raise RuntimeError("retained_attention_intervention_identity_mismatch")
            stage(attention, "attention_intervention.py", f"{REMOTE}/input")
        emit("immutable_staging_complete", checkpoint_bytes=manifest["checkpoint_bytes"])

        def retrieve_state() -> tuple[dict[str, object], dict[str, object]]:
            diagnostics = []
            for attempt in range(1, 4):
                state_result = run_ssh(ip, KEY, f"cat {remote_artifacts}/INVOCATION_STATE.json", timeout=30)
                terminal_result = run_ssh(ip, KEY, f"cat {remote_artifacts}/WORKER_TERMINAL.json", timeout=30)
                diagnostics.append(
                    {
                        "attempt": attempt,
                        "state_returncode": state_result.returncode,
                        "state_stderr": state_result.stderr[-1000:],
                        "terminal_returncode": terminal_result.returncode,
                        "terminal_stderr": terminal_result.stderr[-1000:],
                    }
                )
                if state_result.returncode == 0 and state_result.stdout.strip() and terminal_result.returncode == 0 and terminal_result.stdout.strip():
                    state_value = json.loads(state_result.stdout)
                    terminal_value = json.loads(terminal_result.stdout)
                    atomic(args.artifact_root / "INVOCATION_STATE.json", state_value)
                    atomic(args.artifact_root / "REMOTE_WORKER_TERMINAL.json", terminal_value)
                    atomic(args.artifact_root / "RETRIEVAL_DIAGNOSTIC.json", diagnostics)
                    return state_value, terminal_value
                time.sleep(5 * attempt)
            atomic(args.artifact_root / "RETRIEVAL_DIAGNOSTIC.json", diagnostics)
            raise RuntimeError("typed_retrieval_boundary:compact_state_unavailable_after_three_attempts")

        def retrieve_compact(label: str) -> None:
            archive_partial = args.artifact_root / f".{label}-compact.tar.gz.part"
            sidecar = args.artifact_root / f"{label}-compact.tar.gz.sha256"
            scp_from(ip, f"{REMOTE}/compact.tar.gz", archive_partial, 240)
            scp_from(ip, f"{REMOTE}/compact.tar.gz.sha256", sidecar, 60)
            if sha256(archive_partial) != sidecar.read_text().split()[0]:
                raise RuntimeError(f"typed_retrieval_boundary:{label}_compact_hash_mismatch")
            archive = args.artifact_root / f"{label}-compact.tar.gz"
            os.replace(archive_partial, archive)
            destination = args.artifact_root / label
            destination.mkdir(exist_ok=True)
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(destination, filter="data")

        def run_worker(mode: str) -> int:
            timeout = max(60, claim_deadline - int(time.time()) - RETRIEVAL_RESERVE_SECONDS)
            worker = run_ssh(
                ip,
                KEY,
                f"timeout --signal=TERM {timeout} bash {REMOTE}/input/remote_profile_pair.sh {shlex.quote(mode)}",
                timeout=timeout + 45,
            )
            (args.artifact_root / f"{mode}.worker.stdout").write_text(worker.stdout)
            (args.artifact_root / f"{mode}.worker.stderr").write_text(worker.stderr)
            emit("worker_returned", mode=mode, returncode=worker.returncode)
            nonlocal invocation_state, worker_terminal
            invocation_state, worker_terminal = retrieve_state()
            retrieve_compact(mode)
            return worker.returncode

        def repairable(mode: str) -> bool:
            if worker_terminal.get("classification") != "integration_failure":
                return False
            if mode == "profile":
                return not invocation_state.get("profile_science_started")
            return not invocation_state.get("candidate_science_started")

        def wait_for_repair(mode: str) -> bool:
            repair_deadline = min(claim_deadline - RETRIEVAL_RESERVE_SECONDS, int(time.time()) + 20 * 60)
            ready = {
                "schema_version": 1,
                "mode": mode,
                "worker_terminal": worker_terminal,
                "invocation_state": invocation_state,
                "repair_deadline_epoch": repair_deadline,
                "constraint": "Repair only ordinary wiring for the same workload, bindings, intervention, and decision gates.",
            }
            atomic(args.artifact_root / "REPAIR_READY.json", ready)
            request = args.artifact_root / "REPAIR_REQUEST.json"
            while time.time() < repair_deadline and not request.is_file():
                time.sleep(5)
            if not request.is_file():
                return False
            value = json.loads(request.read_text())
            if value.get("retry") is not True or value.get("mode") != mode:
                return False
            for row in value.get("files", []):
                source = (PROJECT / row["path"]).resolve()
                if PROJECT not in source.parents or sha256(source) != row["sha256"]:
                    raise RuntimeError("repair_request_file_invalid")
                stage(source, row["remote_name"], f"{REMOTE}/input")
            request.rename(args.artifact_root / f"REPAIR_REQUEST.{mode}.consumed.json")
            return True

        if args.pair_only:
            assert pair_intervention is not None and pair_boundary is not None
            intervention = pair_intervention
            if not intervention.get("source_justification"):
                raise RuntimeError("pair_intervention_request_invalid")
            files = intervention.get("files", [])
            if not files or sum(row.get("remote_name") == "residual_intervention.py" for row in files) != 1:
                raise RuntimeError("pair_intervention_module_missing_or_ambiguous")
            for row in files:
                source = (PROJECT / row["path"]).resolve()
                if PROJECT not in source.parents or sha256(source) != row["sha256"]:
                    raise RuntimeError("attention_intervention_file_invalid")
                stage(source, row["remote_name"], f"{REMOTE}/input")
            atomic(args.artifact_root / "INTERVENTION_ADMITTED.json", intervention)
            pair_mode = {
                "attention_kv": "attention_pair",
                "fp8_linear": "fp8_linear_pair",
                "global_attention": "global_attention_pair",
            }[pair_boundary]
            pair_rc = run_worker(pair_mode)
            if pair_rc and repairable(pair_mode) and wait_for_repair(pair_mode):
                pair_rc = run_worker(pair_mode)
            pair_terminal_path = args.artifact_root / pair_mode / "PAIRED_TERMINAL.json"
            if pair_rc or not pair_terminal_path.is_file():
                raise RuntimeError(f"typed_pair_boundary:{worker_terminal.get('message', 'worker_failed')}")
            paired = json.loads(pair_terminal_path.read_text())
            run_spend = (time.time() - started) * rate / 3600
            terminal = {
                **paired,
                "attribution": json.loads((PROJECT / "artifacts/residual-profile-20260720t0821z/ATTRIBUTION.json").read_text()),
                "attention_subtype_map": json.loads((PROJECT / "ATTENTION_SUBTYPE_MAP.json").read_text()),
                "intervention": intervention,
                "retained_attention_intervention_sha256": sha256(PROJECT / "intervention/attention_deferred_local_kv.py"),
                "provider_exposure_seconds": time.time() - started,
                "provider_spend_usd": run_spend,
                "cumulative_provider_spend_usd": prior_spend + run_spend,
            }
            fp8_map = PROJECT / "FP8_LINEAR_SHAPE_MAP.json"
            if fp8_map.is_file():
                terminal["fp8_linear_shape_map"] = json.loads(fp8_map.read_text())
            global_ncu = PROJECT / "GLOBAL_ATTENTION_NCU.json"
            if global_ncu.is_file():
                terminal["global_attention_ncu"] = json.loads(global_ncu.read_text())
            if terminal["cumulative_provider_spend_usd"] > AUTHORIZED_USD:
                terminal["classification"] = "budget_violation"
                terminal["pass"] = False
            atomic(args.artifact_root / "TERMINAL.json", terminal)
            emit("scientific_terminal", classification=terminal.get("classification"))
            return 0 if terminal.get("pass") else 1

        profile_rc = run_worker("profile")
        if profile_rc and repairable("profile") and wait_for_repair("profile"):
            profile_rc = run_worker("profile")
        if profile_rc:
            raise RuntimeError(f"typed_profile_boundary:{worker_terminal.get('message', 'worker_failed')}")

        profile_sqlite = args.artifact_root / "control-profile.sqlite"
        scp_from(ip, f"{REMOTE}/artifacts/control-profile.sqlite", profile_sqlite, 600)
        profile_report = args.artifact_root / "control-profile.nsys-rep"
        report_sidecar = args.artifact_root / "control-profile.nsys-rep.sha256"
        report_hash = run_ssh(ip, KEY, f"sha256sum {REMOTE}/artifacts/control-profile.nsys-rep", timeout=120)
        if report_hash.returncode:
            raise RuntimeError("typed_retrieval_boundary:profile_report_hash_unavailable")
        report_sidecar.write_text(report_hash.stdout)
        profile_terminal = args.artifact_root / "profile/profile/TERMINAL.json"
        attribution_path = args.artifact_root / "ATTRIBUTION.json"
        analyzed = run(
            [sys.executable, str(PROJECT / "analyze_profile.py"), "--sqlite", str(profile_sqlite), "--terminal", str(profile_terminal), "--output", str(attribution_path)],
            capture_output=True,
        )
        (args.artifact_root / "analyze-profile.stdout").write_text(analyzed.stdout)
        (args.artifact_root / "analyze-profile.stderr").write_text(analyzed.stderr)
        if analyzed.returncode:
            raise RuntimeError("typed_profile_boundary:attribution_failed")
        attribution_value = json.loads(attribution_path.read_text())
        hot = attribution_value.get("hottest_eligible_boundary")
        if not hot:
            terminal = {
                "schema_version": 1,
                "status": "terminal",
                "classification": "no_eligible_boundary",
                "pass": True,
                "attribution": attribution_value,
            }
            atomic(args.artifact_root / "TERMINAL.json", terminal)
            return 0

        intervention_deadline = min(claim_deadline - RETRIEVAL_RESERVE_SECONDS, int(time.time()) + 30 * 60)
        atomic(
            args.artifact_root / "INTERVENTION_READY.json",
            {
                "schema_version": 1,
                "hottest_eligible_boundary": hot,
                "attribution_path": str(attribution_path),
                "request_path": str(args.artifact_root / "INTERVENTION_REQUEST.json"),
                "deadline_epoch": intervention_deadline,
                "required_module": "residual_intervention.py with install() and RESIDUAL_CANDIDATE_AUDIT proof",
            },
        )
        intervention_request = args.artifact_root / "INTERVENTION_REQUEST.json"
        while time.time() < intervention_deadline and not intervention_request.is_file():
            time.sleep(5)
        if not intervention_request.is_file():
            raise RuntimeError("typed_intervention_boundary:request_deadline_expired")
        intervention = json.loads(intervention_request.read_text())
        if intervention.get("boundary") != hot["boundary"] or float(intervention.get("boundary_wall_fraction", -1)) != float(hot["wall_fraction"]):
            raise RuntimeError("intervention_boundary_mismatch")
        if not intervention.get("source_justification") or not intervention.get("intervention_id"):
            raise RuntimeError("intervention_justification_missing")
        files = intervention.get("files", [])
        if not files or sum(row.get("remote_name") == "residual_intervention.py" for row in files) != 1:
            raise RuntimeError("intervention_module_missing_or_ambiguous")
        for row in files:
            source = (PROJECT / row["path"]).resolve()
            if PROJECT not in source.parents or sha256(source) != row["sha256"]:
                raise RuntimeError("intervention_file_invalid")
            stage(source, row["remote_name"], f"{REMOTE}/input")
        atomic(args.artifact_root / "INTERVENTION_ADMITTED.json", intervention)

        pair_rc = run_worker("pair")
        if pair_rc and repairable("pair") and wait_for_repair("pair"):
            pair_rc = run_worker("pair")
        pair_terminal_path = args.artifact_root / "pair/PAIRED_TERMINAL.json"
        if pair_rc or not pair_terminal_path.is_file():
            raise RuntimeError(f"typed_pair_boundary:{worker_terminal.get('message', 'worker_failed')}")
        paired = json.loads(pair_terminal_path.read_text())
        terminal = {
            **paired,
            "attribution": attribution_value,
            "intervention": intervention,
            "profile_report_remote_sha256": report_hash.stdout.split()[0],
            "provider_exposure_seconds": time.time() - started,
            "provider_spend_usd": (time.time() - started) * rate / 3600,
        }
        terminal["cumulative_provider_spend_usd"] = prior_spend + terminal["provider_spend_usd"]
        if terminal["cumulative_provider_spend_usd"] > AUTHORIZED_USD:
            terminal["classification"] = "budget_violation"
            terminal["pass"] = False
        atomic(args.artifact_root / "TERMINAL.json", terminal)
        emit("scientific_terminal", classification=terminal.get("classification"))
        return 0 if terminal.get("pass") else 1
    except Exception as error:
        message = str(error)
        if any(
            marker in message
            for marker in (
                "no_public_ip",
                "ssh_identity_failed",
                "typed_retrieval_boundary",
            )
        ):
            release_condition = "maintenance"
        if ip and claimed:
            try:
                invocation_state, worker_terminal = retrieve_state()
            except Exception as retrieval_error:
                emit("retrieval_error", message=str(retrieval_error))
        terminal = {
            "schema_version": 1,
            "status": "terminal",
            "classification": "typed_external_or_owner_boundary",
            "pass": False,
            "error": {"type": type(error).__name__, "message": str(error)},
            "invocation_state": invocation_state,
            "worker_terminal": worker_terminal,
            "provider_exposure_seconds": time.time() - started if claimed else 0,
            "provider_spend_usd": (time.time() - started) * rate / 3600 if claimed else 0,
        }
        atomic(args.artifact_root / "TERMINAL.json", terminal)
        emit("outer_error", error_type=type(error).__name__, message=str(error))
        return 1
    finally:
        stop.set()
        if heartbeat_thread.is_alive():
            heartbeat_thread.join(timeout=5)
        if claimed:
            contents = {
                "project": NAME,
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "checkpoint": f"Exact immutable project snapshot retained at {REMOTE}/checkpoint.",
                "image": "Pinned SGLang v0.5.13 linux/amd64 digest 6113665a retained if pull completed.",
                "runtime": f"Exact FP8+QKV residual profile owner terminal: {(terminal or {}).get('classification', 'owner_boundary')}.",
                "caches": "SGLang FP8, QKV, Nsight, Triton, CUTLASS, and CUDA graph caches retained.",
                "server_state": "Final candidate server retained when healthy; otherwise immutable image/checkpoint/caches retained.",
                "artifacts": f"Compact terminals and profile SQLite retrieved under {args.artifact_root} when available.",
            }
            contents_path = args.artifact_root / "BENCH_CONTENTS.json"
            atomic(contents_path, contents)
            release = pool("release", "--project", NAME, "--condition", release_condition, "--contents", str(contents_path), check=False)
            emit("released", returncode=release.returncode, stderr=release.stderr[-1000:])


if __name__ == "__main__":
    raise SystemExit(main())
