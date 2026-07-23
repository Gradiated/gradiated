#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
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


NAME = "gemma4_h200_residual_h2d_sync_residency"
LAB = pathlib.Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path(
    "/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius"
)
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
REMOTE = "/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination"
REMOTE_INPUT = f"{REMOTE}/input"
REMOTE_CHECKPOINT = f"{REMOTE}/checkpoint"
REMOTE_ARTIFACTS = f"{REMOTE}/residual-h2d-artifacts"
AUTHORIZED_USD = 12.0
MAX_CLAIM_SECONDS = 90 * 60
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
        raise RuntimeError(
            f"typed_transfer_boundary:scp_failed:{source.name}:{result.stderr[-1200:]}"
        )


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
        raise RuntimeError(
            f"typed_retrieval_boundary:scp_failed:{source}:{result.stderr[-1200:]}"
        )


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
    if args.pair_only and args.intervention_request is None:
        raise RuntimeError("pair_intervention_request_missing")
    intervention_request = (
        json.loads(args.intervention_request.read_text())
        if args.intervention_request is not None
        else None
    )
    remote_artifacts = (
        f"{REMOTE}/residual-h2d-pair-artifacts"
        if args.pair_only
        else REMOTE_ARTIFACTS
    )

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(
                json.dumps(
                    {"epoch": time.time(), "event": event, **fields}, sort_keys=True
                )
                + "\n"
            )
            handle.flush()

    snapshot = json.loads((PROJECT / "INPUT_SNAPSHOT.json").read_text())
    verification = json.loads((PROJECT / "SNAPSHOT_VERIFICATION.json").read_text())
    if (
        verification.get("pass") is not True
        or verification.get("input_snapshot_sha256")
        != sha256(PROJECT / "INPUT_SNAPSHOT.json")
    ):
        raise RuntimeError("project_local_snapshot_verification_invalid")
    for section in ("checkpoint", "programs"):
        for row in snapshot[section]:
            path = PROJECT / row["path"]
            if (
                not path.is_file()
                or path.stat().st_size != int(row["bytes"])
            ):
                raise RuntimeError(f"project_local_snapshot_invalid:{row['path']}")
    for path in (
        PROJECT / "sitecustomize.py",
        PROJECT / "remote_trace.sh",
        PROJECT / "analyze_profile.py",
        PROJECT / "analyze_h2d_binding.py",
    ):
        if not path.is_file():
            raise RuntimeError(f"project_program_missing:{path.name}")
    emit("project_local_snapshot_verified", checkpoint_bytes=sum(
        int(row["bytes"]) for row in snapshot["checkpoint"]
    ))

    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = (
        benches[args.bench]
        if isinstance(benches, dict)
        else next(row for row in benches if row["id"] == args.bench)
    )
    if bench["accelerator"] != "nvidia-h200-sxm":
        raise RuntimeError("typed_pool_boundary:bench_not_h200_sxm")
    rate = float(bench["hourly_cost_usd"])
    prior_spend = float(
        json.loads((PROJECT / "STATUS.json").read_text()).get(
            "actual_spend_usd", 0.0
        )
    )
    if prior_spend >= AUTHORIZED_USD:
        raise RuntimeError("typed_budget_boundary:reservation_exhausted")

    started = time.time()
    claim_deadline = min(
        args.absolute_deadline_epoch,
        int(started) + MAX_CLAIM_SECONDS,
        int(started) + int((AUTHORIZED_USD - prior_spend) * 3600 / rate),
    )
    if claim_deadline <= time.time() + RETRIEVAL_RESERVE_SECONDS + 900:
        raise RuntimeError("typed_budget_boundary:insufficient_claim_window")

    claimed = False
    stop = threading.Event()
    terminal: dict[str, object] | None = None
    release_condition = "ready"
    ip: str | None = None
    invocation_state: dict[str, object] = {}
    worker_terminal: dict[str, object] = {}

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-1000:])

    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)

    try:
        lease = max(600, claim_deadline - int(time.time()))
        claim = pool(
            "claim",
            "--project",
            NAME,
            "--bench",
            args.bench,
            "--lease-seconds",
            str(lease),
        )
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
        prepared = run_ssh(
            ip,
            KEY,
            f"mkdir -p {REMOTE_INPUT} {REMOTE_CHECKPOINT} {remote_artifacts}",
            timeout=60,
        )
        if prepared.returncode:
            raise RuntimeError("typed_remote_boundary:prepare_failed")

        def stage(
            source: pathlib.Path,
            remote_name: str,
            remote_directory: str,
            expected: str | None = None,
            expected_bytes: int | None = None,
        ) -> None:
            content_hash = expected or sha256(source)
            content_bytes = expected_bytes or source.stat().st_size
            final = f"{remote_directory}/{remote_name}"
            partial = f"{remote_directory}/.{remote_name}.{content_hash}.part"
            check_command = (
                f"test -f {shlex.quote(final)} "
                f"&& test \"$(stat -c %s {shlex.quote(final)})\" = {content_bytes} "
                f"&& test \"$(sha256sum {shlex.quote(final)} | awk '{{print $1}}')\" = {shlex.quote(content_hash)}"
            )
            matched = run_ssh(
                ip,
                KEY,
                check_command,
                timeout=max(120, min(1800, claim_deadline - int(time.time()))),
            )
            transferred = False
            if matched.returncode:
                timeout = max(
                    120,
                    claim_deadline
                    - int(time.time())
                    - RETRIEVAL_RESERVE_SECONDS,
                )
                scp_to(ip, source, partial, timeout)
                finalized = run_ssh(
                    ip,
                    KEY,
                    f"test \"$(stat -c %s {shlex.quote(partial)})\" = {content_bytes} "
                    f"&& test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {shlex.quote(content_hash)} "
                    f"&& chmod 0444 {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {shlex.quote(final)}",
                    timeout=max(120, min(1800, claim_deadline - int(time.time()))),
                )
                if finalized.returncode:
                    raise RuntimeError(
                        f"typed_transfer_boundary:hash_or_finalize_failed:{remote_name}"
                    )
                transferred = True
            emit(
                "input_reconciled",
                name=remote_name,
                sha256=content_hash,
                bytes=content_bytes,
                transferred=transferred,
            )

        for row in snapshot["checkpoint"]:
            stage(
                PROJECT / row["path"],
                row["remote_name"],
                REMOTE_CHECKPOINT,
                row["sha256"],
                int(row["bytes"]),
            )
        for row in snapshot["programs"]:
            stage(
                PROJECT / row["path"],
                row["remote_name"],
                REMOTE_INPUT,
                row["sha256"],
                int(row["bytes"]),
            )
        stage(PROJECT / "sitecustomize.py", "sitecustomize.py", REMOTE_INPUT)
        stage(PROJECT / "remote_trace.sh", "remote_trace.sh", REMOTE_INPUT)
        if args.pair_only:
            assert intervention_request is not None
            for row in intervention_request["files"]:
                source = (PROJECT / row["path"]).resolve()
                if (
                    PROJECT not in source.parents
                    or sha256(source) != row["sha256"]
                ):
                    raise RuntimeError("pair_intervention_file_invalid")
                stage(source, row["remote_name"], REMOTE_INPUT)
        emit("immutable_staging_complete")

        def retrieve_state() -> tuple[dict[str, object], dict[str, object]]:
            diagnostics = []
            for attempt in range(1, 4):
                state_result = run_ssh(
                    ip, KEY, f"cat {remote_artifacts}/INVOCATION_STATE.json", timeout=30
                )
                terminal_result = run_ssh(
                    ip, KEY, f"cat {remote_artifacts}/WORKER_TERMINAL.json", timeout=30
                )
                diagnostics.append(
                    {
                        "attempt": attempt,
                        "state_returncode": state_result.returncode,
                        "state_stderr": state_result.stderr[-1000:],
                        "terminal_returncode": terminal_result.returncode,
                        "terminal_stderr": terminal_result.stderr[-1000:],
                    }
                )
                if (
                    state_result.returncode == 0
                    and state_result.stdout.strip()
                    and terminal_result.returncode == 0
                    and terminal_result.stdout.strip()
                ):
                    state_value = json.loads(state_result.stdout)
                    terminal_value = json.loads(terminal_result.stdout)
                    atomic(args.artifact_root / "INVOCATION_STATE.json", state_value)
                    atomic(
                        args.artifact_root / "REMOTE_WORKER_TERMINAL.json",
                        terminal_value,
                    )
                    atomic(
                        args.artifact_root / "RETRIEVAL_DIAGNOSTIC.json",
                        diagnostics,
                    )
                    return state_value, terminal_value
                time.sleep(5 * attempt)
            atomic(args.artifact_root / "RETRIEVAL_DIAGNOSTIC.json", diagnostics)
            raise RuntimeError(
                "typed_retrieval_boundary:compact_state_unavailable_after_three_attempts"
            )

        def retrieve_compact(label: str) -> None:
            partial = args.artifact_root / f".{label}-compact.tar.gz.part"
            sidecar = args.artifact_root / f"{label}-compact.tar.gz.sha256"
            scp_from(ip, f"{remote_artifacts}/compact.tar.gz", partial, 300)
            scp_from(
                ip, f"{remote_artifacts}/compact.tar.gz.sha256", sidecar, 60
            )
            if sha256(partial) != sidecar.read_text().split()[0]:
                raise RuntimeError(
                    f"typed_retrieval_boundary:{label}_compact_hash_mismatch"
                )
            archive = args.artifact_root / f"{label}-compact.tar.gz"
            os.replace(partial, archive)
            destination = args.artifact_root / label
            destination.mkdir(exist_ok=True)
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(destination, filter="data")

        def run_worker(mode: str) -> int:
            timeout = max(
                60,
                claim_deadline - int(time.time()) - RETRIEVAL_RESERVE_SECONDS,
            )
            worker = run_ssh(
                ip,
                KEY,
                f"timeout --signal=TERM {timeout} bash {REMOTE_INPUT}/remote_trace.sh {shlex.quote(mode)}",
                timeout=timeout + 45,
            )
            (args.artifact_root / f"{mode}.worker.stdout").write_text(worker.stdout)
            (args.artifact_root / f"{mode}.worker.stderr").write_text(worker.stderr)
            emit("worker_returned", mode=mode, returncode=worker.returncode)
            nonlocal invocation_state, worker_terminal
            invocation_state, worker_terminal = retrieve_state()
            retrieve_compact(mode)
            return worker.returncode

        def wait_for_repair(mode: str) -> bool:
            repair_deadline = min(
                claim_deadline - RETRIEVAL_RESERVE_SECONDS,
                int(time.time()) + 20 * 60,
            )
            atomic(
                args.artifact_root / "REPAIR_READY.json",
                {
                    "schema_version": 1,
                    "mode": mode,
                    "worker_terminal": worker_terminal,
                    "invocation_state": invocation_state,
                    "repair_deadline_epoch": repair_deadline,
                    "constraint": "Repair only ordinary wiring for the same workload, bindings, and trace decision gate.",
                },
            )
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
                stage(source, row["remote_name"], REMOTE_INPUT)
            request.rename(
                args.artifact_root / f"REPAIR_REQUEST.{mode}.consumed.json"
            )
            return True

        if args.pair_only:
            assert intervention_request is not None
            pair_rc = run_worker("pair")
            if (
                pair_rc
                and worker_terminal.get("classification") == "integration_failure"
                and not invocation_state.get("candidate_science_started")
                and wait_for_repair("pair")
            ):
                pair_rc = run_worker("pair")
            if pair_rc:
                raise RuntimeError(
                    f"typed_pair_boundary:{worker_terminal.get('message', 'worker_failed')}"
                )
            pair_terminal_path = args.artifact_root / "pair/PAIR_TERMINAL.json"
            if not pair_terminal_path.is_file():
                raise RuntimeError("typed_pair_boundary:pair_terminal_missing")
            pair_terminal = json.loads(pair_terminal_path.read_text())
            atomic(args.artifact_root / "PERSISTED_PAIR.json", pair_terminal)

            prediction_rc = run_worker("candidate_trace")
            if (
                prediction_rc
                and worker_terminal.get("classification") == "integration_failure"
                and not invocation_state.get("prediction_science_started")
                and wait_for_repair("candidate_trace")
            ):
                prediction_rc = run_worker("candidate_trace")
            if prediction_rc:
                raise RuntimeError(
                    "typed_prediction_trace_boundary:"
                    + str(worker_terminal.get("message", "worker_failed"))
                )

            prediction_sqlite = args.artifact_root / "prediction.sqlite"
            scp_from(
                ip,
                f"{remote_artifacts}/prediction.sqlite",
                prediction_sqlite,
                600,
            )
            report_hash = run_ssh(
                ip,
                KEY,
                f"sha256sum {remote_artifacts}/prediction.nsys-rep",
                timeout=180,
            )
            if report_hash.returncode:
                raise RuntimeError(
                    "typed_retrieval_boundary:prediction_report_hash_unavailable"
                )
            (args.artifact_root / "prediction.nsys-rep.sha256").write_text(
                report_hash.stdout
            )
            prediction_terminal_path = (
                args.artifact_root
                / "candidate_trace/prediction/TERMINAL.json"
            )
            prediction_attribution = (
                args.artifact_root / "PREDICTION_TRACE_ATTRIBUTION.json"
            )
            analyzed = run(
                [
                    sys.executable,
                    str(PROJECT / "analyze_profile.py"),
                    "--sqlite",
                    str(prediction_sqlite),
                    "--terminal",
                    str(prediction_terminal_path),
                    "--output",
                    str(prediction_attribution),
                ],
                capture_output=True,
            )
            (args.artifact_root / "analyze-prediction.stdout").write_text(
                analyzed.stdout
            )
            (args.artifact_root / "analyze-prediction.stderr").write_text(
                analyzed.stderr
            )
            if analyzed.returncode:
                raise RuntimeError(
                    "typed_prediction_trace_boundary:attribution_failed"
                )
            prediction_binding_path = (
                args.artifact_root / "PREDICTION_H2D_BINDING.json"
            )
            bound = run(
                [
                    sys.executable,
                    str(PROJECT / "analyze_h2d_binding.py"),
                    "--sqlite",
                    str(prediction_sqlite),
                    "--attribution",
                    str(prediction_attribution),
                    "--output",
                    str(prediction_binding_path),
                ],
                capture_output=True,
            )
            (args.artifact_root / "analyze-prediction-h2d.stdout").write_text(
                bound.stdout
            )
            (args.artifact_root / "analyze-prediction-h2d.stderr").write_text(
                bound.stderr
            )
            if bound.returncode:
                raise RuntimeError(
                    "typed_prediction_trace_boundary:h2d_binding_failed"
                )
            prediction_binding = json.loads(prediction_binding_path.read_text())
            prediction_pass = not prediction_binding[
                "surviving_repeated_small_h2d"
            ]
            classification = str(pair_terminal["classification"])
            if not prediction_pass:
                classification = "close_prediction_small_h2d_survives"
            run_spend = (time.time() - started) * rate / 3600
            terminal = {
                **pair_terminal,
                "status": "terminal",
                "classification": classification,
                "pass": True,
                "source_trace_binding": json.loads(
                    (
                        PROJECT
                        / "artifacts/residual-h2d-current-frontier-20260723t0403z/CURRENT_H2D_BINDING.corrected.json"
                    ).read_text()
                ),
                "intervention": intervention_request,
                "prediction_trace_terminal": json.loads(
                    prediction_terminal_path.read_text()
                ),
                "prediction_trace_attribution": json.loads(
                    prediction_attribution.read_text()
                ),
                "prediction_h2d_binding": prediction_binding,
                "prediction_pass": prediction_pass,
                "profile_report_remote_sha256": report_hash.stdout.split()[0],
                "provider_exposure_seconds": time.time() - started,
                "provider_spend_usd": run_spend,
                "cumulative_provider_spend_usd": prior_spend + run_spend,
            }
            atomic(args.artifact_root / "TERMINAL.json", terminal)
            emit("scientific_terminal", classification=classification)
            return 0

        trace_rc = run_worker("trace")
        if (
            trace_rc
            and worker_terminal.get("classification") == "integration_failure"
            and not invocation_state.get("trace_science_started")
            and wait_for_repair("trace")
        ):
            trace_rc = run_worker("trace")
        if trace_rc:
            raise RuntimeError(
                f"typed_trace_boundary:{worker_terminal.get('message', 'worker_failed')}"
            )

        trace_sqlite = args.artifact_root / "current-frontier.sqlite"
        scp_from(
            ip,
            f"{REMOTE_ARTIFACTS}/current-frontier.sqlite",
            trace_sqlite,
            600,
        )
        report_hash = run_ssh(
            ip,
            KEY,
            f"sha256sum {REMOTE_ARTIFACTS}/current-frontier.nsys-rep",
            timeout=180,
        )
        if report_hash.returncode:
            raise RuntimeError(
                "typed_retrieval_boundary:profile_report_hash_unavailable"
            )
        (args.artifact_root / "current-frontier.nsys-rep.sha256").write_text(
            report_hash.stdout
        )
        trace_terminal = args.artifact_root / "trace/trace/TERMINAL.json"
        attribution = args.artifact_root / "CURRENT_TRACE_ATTRIBUTION.json"
        analyzed = run(
            [
                sys.executable,
                str(PROJECT / "analyze_profile.py"),
                "--sqlite",
                str(trace_sqlite),
                "--terminal",
                str(trace_terminal),
                "--output",
                str(attribution),
            ],
            capture_output=True,
        )
        (args.artifact_root / "analyze-profile.stdout").write_text(analyzed.stdout)
        (args.artifact_root / "analyze-profile.stderr").write_text(analyzed.stderr)
        if analyzed.returncode:
            raise RuntimeError("typed_trace_boundary:attribution_failed")
        binding_path = args.artifact_root / "CURRENT_H2D_BINDING.json"
        bound = run(
            [
                sys.executable,
                str(PROJECT / "analyze_h2d_binding.py"),
                "--sqlite",
                str(trace_sqlite),
                "--attribution",
                str(attribution),
                "--output",
                str(binding_path),
            ],
            capture_output=True,
        )
        (args.artifact_root / "analyze-h2d.stdout").write_text(bound.stdout)
        (args.artifact_root / "analyze-h2d.stderr").write_text(bound.stderr)
        if bound.returncode:
            raise RuntimeError("typed_trace_boundary:h2d_binding_failed")
        binding = json.loads(binding_path.read_text())

        if not binding["surviving_repeated_small_h2d"]:
            run_spend = (time.time() - started) * rate / 3600
            terminal = {
                "schema_version": 1,
                "status": "terminal",
                "classification": "close_residual_small_h2d_absent_current_stack",
                "pass": True,
                "trace_terminal": json.loads(trace_terminal.read_text()),
                "trace_attribution": json.loads(attribution.read_text()),
                "h2d_binding": binding,
                "profile_report_remote_sha256": report_hash.stdout.split()[0],
                "provider_exposure_seconds": time.time() - started,
                "provider_spend_usd": run_spend,
                "cumulative_provider_spend_usd": prior_spend + run_spend,
            }
            atomic(args.artifact_root / "TERMINAL.json", terminal)
            emit("scientific_terminal", classification=terminal["classification"])
            return 0

        intervention_deadline = min(
            claim_deadline - RETRIEVAL_RESERVE_SECONDS,
            int(time.time()) + 30 * 60,
        )
        intervention_request = args.artifact_root / "INTERVENTION_REQUEST.json"
        atomic(
            args.artifact_root / "INTERVENTION_READY.json",
            {
                "schema_version": 1,
                "binding": binding,
                "request_path": str(intervention_request),
                "deadline_epoch": intervention_deadline,
                "constraint": "Freeze exactly one semantic-preserving intervention; then run one profiler-off c32 control/candidate pair and the minimum prediction trace.",
            },
        )
        while (
            time.time() < intervention_deadline
            and not intervention_request.is_file()
        ):
            time.sleep(5)
        if not intervention_request.is_file():
            raise RuntimeError("typed_owner_boundary:intervention_request_timeout")
        request = json.loads(intervention_request.read_text())
        if request.get("admitted") is not True:
            raise RuntimeError("typed_intervention_boundary:request_not_admitted")
        for row in request.get("files", []):
            source = (PROJECT / row["path"]).resolve()
            if PROJECT not in source.parents or sha256(source) != row["sha256"]:
                raise RuntimeError("intervention_request_file_invalid")
            stage(source, row["remote_name"], REMOTE_INPUT)
        atomic(args.artifact_root / "INTERVENTION_ADMITTED.json", request)
        pair_rc = run_worker(str(request.get("worker_mode", "pair")))
        if pair_rc:
            raise RuntimeError(
                f"typed_pair_boundary:{worker_terminal.get('message', 'worker_failed')}"
            )
        pair_terminal_path = (
            args.artifact_root
            / str(request.get("worker_mode", "pair"))
            / "PAIR_TERMINAL.json"
        )
        if not pair_terminal_path.is_file():
            raise RuntimeError("typed_pair_boundary:pair_terminal_missing")
        atomic(
            args.artifact_root / "PERSISTED_PAIR.json",
            json.loads(pair_terminal_path.read_text()),
        )
        prediction_mode = str(request.get("prediction_mode", "candidate_trace"))
        prediction_rc = run_worker(prediction_mode)
        if prediction_rc:
            raise RuntimeError(
                f"typed_prediction_trace_boundary:{worker_terminal.get('message', 'worker_failed')}"
            )
        run_spend = (time.time() - started) * rate / 3600
        terminal = {
            **json.loads(pair_terminal_path.read_text()),
            "status": "terminal",
            "source_trace_binding": binding,
            "intervention": request,
            "provider_exposure_seconds": time.time() - started,
            "provider_spend_usd": run_spend,
            "cumulative_provider_spend_usd": prior_spend + run_spend,
        }
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
        if ip and claimed and "retrieve_state" in locals():
            try:
                invocation_state, worker_terminal = retrieve_state()
            except Exception as retrieval_error:
                emit("retrieval_error", message=str(retrieval_error))
        run_spend = (time.time() - started) * rate / 3600 if claimed else 0.0
        terminal = {
            "schema_version": 1,
            "status": "terminal",
            "classification": "typed_external_or_owner_boundary",
            "pass": False,
            "error": {"type": type(error).__name__, "message": message},
            "invocation_state": invocation_state,
            "worker_terminal": worker_terminal,
            "provider_exposure_seconds": time.time() - started if claimed else 0,
            "provider_spend_usd": run_spend,
            "cumulative_provider_spend_usd": prior_spend + run_spend,
        }
        atomic(args.artifact_root / "TERMINAL.json", terminal)
        emit("outer_error", error_type=type(error).__name__, message=message)
        return 1
    finally:
        stop.set()
        if heartbeat_thread.is_alive():
            heartbeat_thread.join(timeout=5)
        if claimed:
            contents = {
                "project": NAME,
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "checkpoint": f"Exact immutable checkpoint retained at {REMOTE_CHECKPOINT}; project-local admitted snapshot verified.",
                "image": "Pinned SGLang v0.5.13 linux/amd64 digest 6113665a retained.",
                "runtime": f"Producer-fused current-frontier small-H2D decision: {(terminal or {}).get('classification', 'owner_boundary')}.",
                "caches": "SGLang FP8, QKV, Nsight, Triton, CUTLASS, and CUDA graph caches retained warm.",
                "server_state": "No server guaranteed; immutable image/checkpoint and compiled caches are ready for the MTP accepted-depth lane.",
                "artifacts": f"Compact terminal and current-frontier profile SQLite retrieved under {args.artifact_root}.",
            }
            contents_path = args.artifact_root / "BENCH_CONTENTS.json"
            atomic(contents_path, contents)
            release = pool(
                "release",
                "--project",
                NAME,
                "--condition",
                release_condition,
                "--contents",
                str(contents_path),
                check=False,
            )
            emit(
                "released",
                returncode=release.returncode,
                stderr=release.stderr[-1000:],
            )


if __name__ == "__main__":
    raise SystemExit(main())
