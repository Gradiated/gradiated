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


NAME = "sglang_v0512_h200_gemma4_mtp_endpoint"
LAB = pathlib.Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path(
    "/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius"
)
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
REMOTE = "/home/glmrunner/sglang-v0513-mtp-accepted-depth"
REMOTE_CHECKPOINT = (
    "/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint"
)
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
PRIOR_SPEND = 2.877536599679788
AUTHORIZED_SPEND = 12.0
MAX_CLAIM_SECONDS = 90 * 60
RETRIEVAL_RESERVE_SECONDS = 10 * 60


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, **kwargs)


def pool(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            "-m",
            "grad_research.gpu_pool",
            "--lab",
            str(LAB),
            *arguments,
        ],
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
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--absolute-deadline-epoch", type=int, required=True)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    events = args.artifact_root / "outer-events.jsonl"
    manifest = json.loads((PROJECT / "ACCEPTED_DEPTH_INPUT_MANIFEST.json").read_text())
    if manifest.get("pass") is not True:
        raise RuntimeError("project_local_manifest_invalid")
    if sha256(PROJECT / manifest["source_binding"]) != manifest["source_binding_sha256"]:
        raise RuntimeError("source_binding_identity_mismatch")
    for section in ("checkpoint", "assistant", "stack", "programs"):
        for row in manifest[section]:
            path = PROJECT / row["path"]
            if (
                not path.is_file()
                or path.stat().st_size != row["bytes"]
                or sha256(path) != row["sha256"]
            ):
                raise RuntimeError(f"project_local_snapshot_invalid:{row['path']}")

    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = benches[BENCH] if isinstance(benches, dict) else next(
        row for row in benches if row["id"] == BENCH
    )
    rate = float(bench["hourly_cost_usd"])
    budget_seconds = int((AUTHORIZED_SPEND - PRIOR_SPEND) * 3600 / rate)
    lifecycle_deadline = int(
        datetime.datetime.fromisoformat(
            bench["lifecycle"]["deadline_utc"].replace("Z", "+00:00")
        ).timestamp()
    )
    claim_deadline = min(
        args.absolute_deadline_epoch,
        lifecycle_deadline - 5 * 60,
        int(time.time()) + MAX_CLAIM_SECONDS,
        int(time.time()) + budget_seconds,
    )
    if claim_deadline <= time.time() + RETRIEVAL_RESERVE_SECONDS + 600:
        raise RuntimeError("typed_budget_boundary:insufficient_claim_window")

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(
                json.dumps(
                    {"epoch": time.time(), "event": event, **fields}, sort_keys=True
                )
                + "\n"
            )
            handle.flush()

    started = time.time()
    stop = threading.Event()
    claimed = False
    ip: str | None = None
    terminal: dict[str, object] | None = None
    release_condition = "ready"

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-1000:])

    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    try:
        claim = pool(
            "claim",
            "--project",
            NAME,
            "--bench",
            BENCH,
            "--lease-seconds",
            str(claim_deadline - int(time.time())),
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
        prepare = run_ssh(
            ip,
            KEY,
            f"mkdir -p {REMOTE}/input {REMOTE}/assistant {REMOTE}/artifacts {REMOTE_CHECKPOINT}",
            timeout=60,
        )
        if prepare.returncode:
            raise RuntimeError("typed_remote_boundary:prepare_failed")

        def reconcile(
            rows: list[dict[str, object]], remote_directory: str
        ) -> None:
            remote_names = " ".join(
                shlex.quote(pathlib.Path(str(row["path"])).name) for row in rows
            )
            command = (
                f"cd {shlex.quote(remote_directory)}; "
                f"for name in {remote_names}; do "
                "if test -f \"$name\"; then "
                "printf '%s\\t%s\\t%s\\n' \"$name\" \"$(stat -c%s -- \"$name\")\" "
                "\"$(sha256sum -- \"$name\" | awk '{print $1}')\"; "
                "else printf '%s\\tMISSING\\tMISSING\\n' \"$name\"; fi; done"
            )
            remote = run_ssh(
                ip,
                KEY,
                command,
                timeout=max(
                    120, min(1200, claim_deadline - int(time.time()) - 60)
                ),
            )
            if remote.returncode:
                raise RuntimeError("typed_remote_boundary:manifest_reconcile_failed")
            observed = {
                fields[0]: (fields[1], fields[2])
                for line in remote.stdout.splitlines()
                if len(fields := line.split("\t")) == 3
            }
            for row in rows:
                source = PROJECT / str(row["path"])
                name = source.name
                expected = (str(row["bytes"]), str(row["sha256"]))
                if observed.get(name) == expected:
                    emit(
                        "immutable_file_reused",
                        name=name,
                        bytes=row["bytes"],
                        sha256=row["sha256"],
                    )
                    continue
                partial = f"{remote_directory}/.{name}.{row['sha256']}.part"
                final = f"{remote_directory}/{name}"
                timeout = max(
                    120, min(2400, claim_deadline - int(time.time()) - 60)
                )
                scp_to(ip, source, partial, timeout)
                finalize = run_ssh(
                    ip,
                    KEY,
                    f"test \"$(stat -c%s -- {shlex.quote(partial)})\" = {row['bytes']} "
                    f"&& test \"$(sha256sum -- {shlex.quote(partial)} | awk '{{print $1}}')\" = {row['sha256']} "
                    f"&& chmod 0444 {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {shlex.quote(final)}",
                    timeout=120,
                )
                if finalize.returncode:
                    raise RuntimeError(
                        f"typed_transfer_boundary:hash_or_finalize_failed:{name}"
                    )
                emit(
                    "immutable_file_staged",
                    name=name,
                    bytes=row["bytes"],
                    sha256=row["sha256"],
                )

        reconcile(manifest["checkpoint"], REMOTE_CHECKPOINT)
        reconcile(manifest["assistant"], f"{REMOTE}/assistant")
        reconcile(manifest["stack"], f"{REMOTE}/input")
        # The producer-fused patch installs from its descriptive project-local
        # filename, while the patched runtime imports the immutable payload by
        # the historical module name `residual_intervention`.
        residual_row = next(
            row
            for row in manifest["stack"]
            if pathlib.Path(str(row["path"])).name
            == "producer_fused_swa_translation.py"
        )
        residual_source = PROJECT / str(residual_row["path"])
        residual_partial = (
            f"{REMOTE}/input/.residual_intervention.py."
            f"{residual_row['sha256']}.part"
        )
        residual_final = f"{REMOTE}/input/residual_intervention.py"
        residual_matched = run_ssh(
            ip,
            KEY,
            f"test -f {shlex.quote(residual_final)} "
            f"&& test \"$(sha256sum -- {shlex.quote(residual_final)} "
            f"| awk '{{print $1}}')\" = {residual_row['sha256']}",
            timeout=60,
        )
        if residual_matched.returncode:
            scp_to(ip, residual_source, residual_partial, 300)
            residual_finalized = run_ssh(
                ip,
                KEY,
                f"test \"$(sha256sum -- {shlex.quote(residual_partial)} "
                f"| awk '{{print $1}}')\" = {residual_row['sha256']} "
                f"&& chmod 0444 {shlex.quote(residual_partial)} "
                f"&& mv -f {shlex.quote(residual_partial)} "
                f"{shlex.quote(residual_final)}",
                timeout=120,
            )
            if residual_finalized.returncode:
                raise RuntimeError(
                    "typed_transfer_boundary:"
                    "program_finalize_failed:residual_intervention.py"
                )
        emit(
            "program_staged",
            name="residual_intervention.py",
            sha256=residual_row["sha256"],
        )
        program_rows = []
        for row in manifest["programs"]:
            mapped = dict(row)
            if pathlib.Path(str(row["path"])).name == "accepted_depth_sitecustomize.py":
                mapped["remote_name"] = "sitecustomize.py"
            else:
                mapped["remote_name"] = pathlib.Path(str(row["path"])).name
            program_rows.append(mapped)
        for row in program_rows:
            source = PROJECT / str(row["path"])
            name = str(row["remote_name"])
            partial = f"{REMOTE}/input/.{name}.{row['sha256']}.part"
            final = f"{REMOTE}/input/{name}"
            matched = run_ssh(
                ip,
                KEY,
                f"test -f {shlex.quote(final)} && test \"$(sha256sum -- {shlex.quote(final)} | awk '{{print $1}}')\" = {row['sha256']}",
                timeout=60,
            )
            if matched.returncode:
                scp_to(ip, source, partial, 300)
                finalized = run_ssh(
                    ip,
                    KEY,
                    f"test \"$(sha256sum -- {shlex.quote(partial)} | awk '{{print $1}}')\" = {row['sha256']} "
                    f"&& chmod 0444 {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {shlex.quote(final)}",
                    timeout=120,
                )
                if finalized.returncode:
                    raise RuntimeError(
                        f"typed_transfer_boundary:program_finalize_failed:{name}"
                    )
            emit("program_staged", name=name, sha256=row["sha256"])

        worker_timeout = max(
            60, claim_deadline - int(time.time()) - RETRIEVAL_RESERVE_SECONDS
        )
        worker = run_ssh(
            ip,
            KEY,
            f"timeout --signal=TERM {worker_timeout} bash {REMOTE}/input/remote_accepted_depth.sh",
            timeout=worker_timeout + 30,
        )
        (args.artifact_root / "remote-worker.stdout").write_text(worker.stdout)
        (args.artifact_root / "remote-worker.stderr").write_text(worker.stderr)
        emit("worker_returned", returncode=worker.returncode)

        state_result = run_ssh(
            ip, KEY, f"cat {REMOTE}/artifacts/INVOCATION_STATE.json", timeout=30
        )
        worker_terminal_result = run_ssh(
            ip, KEY, f"cat {REMOTE}/artifacts/WORKER_TERMINAL.json", timeout=30
        )
        if state_result.returncode or worker_terminal_result.returncode:
            raise RuntimeError("typed_retrieval_boundary:compact_terminal_missing")
        invocation_state = json.loads(state_result.stdout)
        worker_terminal = json.loads(worker_terminal_result.stdout)
        atomic(args.artifact_root / "INVOCATION_STATE.json", invocation_state)
        atomic(args.artifact_root / "REMOTE_WORKER_TERMINAL.json", worker_terminal)

        archive_partial = args.artifact_root / ".compact.tar.gz.part"
        sidecar = args.artifact_root / "compact.tar.gz.sha256"
        scp_from(ip, f"{REMOTE}/compact.tar.gz", archive_partial, 300)
        scp_from(ip, f"{REMOTE}/compact.tar.gz.sha256", sidecar, 60)
        if sha256(archive_partial) != sidecar.read_text().split()[0]:
            raise RuntimeError("typed_retrieval_boundary:compact_hash_mismatch")
        archive = args.artifact_root / "compact.tar.gz"
        os.replace(archive_partial, archive)
        retrieved = args.artifact_root / "retrieved"
        retrieved.mkdir()
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(retrieved, filter="data")
        final_path = retrieved / "FINAL_TERMINAL.json"
        if final_path.is_file():
            terminal = json.loads(final_path.read_text())
        elif worker.returncode:
            raise RuntimeError(
                f"typed_worker_boundary:{worker_terminal.get('message','unknown')}"
            )
        else:
            raise RuntimeError("typed_retrieval_boundary:scientific_terminal_missing")
    except Exception as exception:
        emit("owner_failure", error=f"{type(exception).__name__}: {exception}"[:4000])
        terminal = {
            "schema_version": 1,
            "status": "terminal",
            "classification": "typed_external_or_owner_boundary",
            "pass": False,
            "error": f"{type(exception).__name__}: {exception}"[:4000],
        }
        release_condition = "maintenance" if ip is None else "ready"
    finally:
        stop.set()
        if heartbeat_thread.is_alive():
            heartbeat_thread.join(timeout=2)
        ended = time.time()
        exposure = max(0.0, ended - started) if claimed else 0.0
        new_spend = exposure * rate / 3600
        cumulative = PRIOR_SPEND + new_spend
        terminal = terminal or {
            "schema_version": 1,
            "status": "terminal",
            "classification": "owner_no_terminal",
            "pass": False,
        }
        terminal["provider"] = {
            "bench_id": BENCH,
            "exposure_seconds": exposure,
            "hourly_cost_usd": rate,
            "new_iteration_spend_usd": new_spend,
            "historical_settled_spend_usd": PRIOR_SPEND,
            "cumulative_project_spend_usd": cumulative,
            "authorized_cumulative_spend_usd": AUTHORIZED_SPEND,
        }
        atomic(args.artifact_root / "RECONCILED_TERMINAL.json", terminal)
        if claimed:
            contents = {
                "artifacts": str(args.artifact_root),
                "checkpoint": f"Exact immutable checkpoint retained at {REMOTE_CHECKPOINT}.",
                "image": "Pinned SGLang v0.5.13 digest 6113665a retained.",
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "project": NAME,
                "runtime": f"Accepted-depth terminal: {terminal.get('classification')}",
                "server_state": "Healthy final MTP server retained when scientific execution reached a server terminal; image/checkpoint/assistant and compiled caches retained otherwise.",
                "mtp_claim_cost_usd": new_spend,
                "mtp_cumulative_project_cost_usd": cumulative,
            }
            contents_path = args.artifact_root / "bench-contents.json"
            atomic(contents_path, contents)
            released = pool(
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
                condition=release_condition,
                returncode=released.returncode,
                stderr=released.stderr[-1000:],
            )
    return 0 if terminal.get("pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
