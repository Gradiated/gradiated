#!/usr/bin/env python3
"""Bounded owner for the single admitted H200 verifier experiment.

The owner retains the pool claim across immutable staging, the remote workload,
artifact retrieval, and repair-ready waits.  It releases only after a scientific
terminal or an evidence-backed nonrecoverable boundary.
"""

from __future__ import annotations

import datetime as dt
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


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path(
    "/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius"
)
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
NAME = "gemma4_h200_ngram_decode_equivalent_verifier"
BENCH = "h200-ngram-verifier-e00kcm9nfhwt7e7gbc"
REMOTE = "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier"
REMOTE_UNIT = "gemma4-ngram-decode-equivalent-experiment.service"
REMOTE_PID = f"{REMOTE}/WORKER.pid"
REMOTE_EXIT = f"{REMOTE}/WORKER.exit"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
DEADLINE = dt.datetime(2026, 7, 24, 16, 45, tzinfo=dt.timezone.utc)
REPAIR_DEADLINE = dt.datetime(2026, 7, 24, 16, 15, tzinfo=dt.timezone.utc)


def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False, **kwargs)


def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "python3",
            "-m",
            "grad_research.gpu_pool",
            "--lab",
            str(LAB),
            *args,
        ],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
    )


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(16 * 1024 * 1024):
            value.update(block)
    return value.hexdigest()


def ssh(ip: str, command: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "ssh",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "ServerAliveInterval=20",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            f"glmrunner@{ip}",
            command,
        ],
        timeout=timeout,
    )


def scp_to(
    ip: str, source: pathlib.Path, target: str, timeout: int
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "scp",
            "-p",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "ServerAliveInterval=20",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            str(source),
            f"glmrunner@{ip}:{target}",
        ],
        timeout=timeout,
    )


def scp_from(
    ip: str, source: str, target: pathlib.Path, timeout: int
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "scp",
            "-p",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "ServerAliveInterval=20",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            f"glmrunner@{ip}:{source}",
            str(target),
        ],
        timeout=timeout,
    )


def instance_ip() -> str:
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = (
        benches[BENCH]
        if isinstance(benches, dict)
        else next(row for row in benches if row["id"] == BENCH)
    )
    sys.path.insert(0, str(NEBIUS))
    from placement_control import extract_public_ipv4, get_instance

    value = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
    if not value:
        raise RuntimeError("typed_provider_boundary:no_public_ip")
    return value


def wait_ssh(ip: str, artifact: pathlib.Path) -> None:
    deadline = time.monotonic() + 600
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        result = ssh(
            ip,
            "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; "
            "sudo docker --version; df -B1 /home/glmrunner",
            30,
        )
        if result.returncode == 0:
            (artifact / "remote-identity.stdout").write_text(result.stdout)
            (artifact / "remote-identity.stderr").write_text(result.stderr)
            return
        time.sleep(min(20, attempt * 2))
    raise RuntimeError("typed_remote_boundary:ssh_readiness_timeout")


def remote_match(ip: str, target: str, size: int, sha256: str) -> bool:
    quoted = shlex.quote(target)
    command = (
        f"test -f {quoted} && "
        f"test \"$(stat -c %s {quoted})\" = {size} && "
        f"test \"$(sha256sum {quoted} | cut -d' ' -f1)\" = {sha256}"
    )
    return ssh(ip, command, max(60, min(1800, size // 40_000_000 + 60))).returncode == 0


def stage_file(
    ip: str,
    source: pathlib.Path,
    target: str,
    expected_sha256: str,
    expected_bytes: int,
    artifact: pathlib.Path,
) -> dict[str, object]:
    if source.stat().st_size != expected_bytes:
        raise RuntimeError(f"typed_local_integrity_boundary:size:{source.name}")
    if remote_match(ip, target, expected_bytes, expected_sha256):
        return {
            "path": target,
            "bytes": expected_bytes,
            "sha256": expected_sha256,
            "reused": True,
        }
    partial = f"{target}.{expected_sha256}.part"
    parent = str(pathlib.PurePosixPath(target).parent)
    prepare = ssh(
        ip,
        f"install -d {shlex.quote(parent)} && "
        f"test ! -e {shlex.quote(target)} || chmod u+w {shlex.quote(target)} && "
        f"rm -f {shlex.quote(partial)}",
    )
    if prepare.returncode:
        raise RuntimeError(f"typed_staging_boundary:prepare:{source.name}")
    timeout = max(900, min(5400, expected_bytes // 15_000_000 + 300))
    transfer = scp_to(ip, source, partial, timeout)
    if transfer.returncode:
        (artifact / f"{source.name}.scp.stderr").write_text(transfer.stderr)
        raise RuntimeError(f"typed_staging_boundary:transfer:{source.name}")
    quoted_partial = shlex.quote(partial)
    quoted_target = shlex.quote(target)
    finalize = ssh(
        ip,
        f"test \"$(stat -c %s {quoted_partial})\" = {expected_bytes} && "
        f"test \"$(sha256sum {quoted_partial} | cut -d' ' -f1)\" = {expected_sha256} && "
        f"chmod 0444 {quoted_partial} && mv -f {quoted_partial} {quoted_target}",
        max(120, min(1800, expected_bytes // 40_000_000 + 90)),
    )
    if finalize.returncode:
        (artifact / f"{source.name}.finalize.stderr").write_text(finalize.stderr)
        raise RuntimeError(f"typed_staging_boundary:verify_or_finalize:{source.name}")
    return {
        "path": target,
        "bytes": expected_bytes,
        "sha256": expected_sha256,
        "reused": False,
    }


def stage(ip: str, artifact: pathlib.Path) -> list[dict[str, object]]:
    checkpoint = PROJECT / "inputs/checkpoint"
    manifest = json.loads((PROJECT / "CHECKPOINT_MANIFEST.json").read_text())
    rows: list[dict[str, object]] = []
    prepare = ssh(
        ip,
        f"install -d {REMOTE}/input {REMOTE}/checkpoint {REMOTE}/artifacts",
    )
    if prepare.returncode:
        raise RuntimeError("typed_staging_boundary:remote_roots")
    for row in manifest["files"]:
        rows.append(
            stage_file(
                ip,
                checkpoint / row["name"],
                f"{REMOTE}/checkpoint/{row['name']}",
                row["sha256"],
                int(row["bytes"]),
                artifact,
            )
        )
        atomic(artifact / "staging-progress.json", rows)
    code_files = [
        PROJECT / "remote_experiment.py",
        PROJECT / "decode_equivalent_lm_head.py",
        PROJECT / "discriminator_hook.py",
        PROJECT / "sitecustomize.py",
        PROJECT / "token_trace_hook.py",
        PROJECT / "inputs/bound/exact_runner.py",
        PROJECT / "inputs/bound/endpoint_entrypoint.py",
    ]
    for source in code_files:
        rows.append(
            stage_file(
                ip,
                source,
                f"{REMOTE}/input/{source.name}",
                digest(source),
                source.stat().st_size,
                artifact,
            )
        )
        atomic(artifact / "staging-progress.json", rows)
    atomic(artifact / "STAGING_TERMINAL.json", {"pass": True, "files": rows})
    return rows


def pull_image(ip: str, artifact: pathlib.Path) -> None:
    inspect = ssh(
        ip,
        f"sudo docker image inspect {shlex.quote(IMAGE)} --format '{{{{.Id}}}}'",
        60,
    )
    if inspect.returncode:
        result = ssh(ip, f"sudo docker pull {shlex.quote(IMAGE)}", 5400)
        (artifact / "docker-pull.stdout").write_text(result.stdout)
        (artifact / "docker-pull.stderr").write_text(result.stderr)
        if result.returncode:
            raise RuntimeError("typed_image_boundary:pull_failed")
    final = ssh(
        ip,
        f"sudo docker image inspect {shlex.quote(IMAGE)} --format '{{{{json .RepoDigests}}}}'",
        60,
    )
    (artifact / "docker-image.json").write_text(final.stdout)
    if final.returncode or "6113665a292b50fe" not in final.stdout:
        raise RuntimeError("typed_image_boundary:digest_not_resolved")


def start_remote(ip: str, artifact: pathlib.Path) -> None:
    existing = ssh(
        ip,
        f"test -s {REMOTE_PID} && kill -0 \"$(cat {REMOTE_PID})\"",
        30,
    )
    if existing.returncode == 0:
        (artifact / "remote-resume.txt").write_text(
            "Attached to the already-running admitted remote process; no invocation replayed.\n"
        )
        return
    command = (
        f"cd {REMOTE}; "
        f"/usr/bin/timeout --signal=TERM 20700 "
        f"/usr/bin/python3 input/remote_experiment.py; "
        "rc=$?; "
        f"printf '%s\\n' \"$rc\" > {REMOTE_EXIT}.part; "
        f"mv {REMOTE_EXIT}.part {REMOTE_EXIT}; "
        "exit \"$rc\""
    )
    result = ssh(
        ip,
        f"rm -f {REMOTE_PID} {REMOTE_EXIT} {REMOTE_EXIT}.part; "
        f"nohup /usr/bin/bash -lc {shlex.quote(command)} "
        f"> {REMOTE}/artifacts/worker.stdout "
        f"2> {REMOTE}/artifacts/worker.stderr < /dev/null & "
        f"echo $! > {REMOTE_PID}",
        60,
    )
    (artifact / "remote-start.stdout").write_text(result.stdout)
    (artifact / "remote-start.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("typed_launcher_boundary:remote_systemd_start")


def wait_remote(ip: str, artifact: pathlib.Path) -> tuple[str, str]:
    while dt.datetime.now(dt.timezone.utc) < DEADLINE:
        state = ssh(
            ip,
            f"if test -s {REMOTE_EXIT}; then "
            f"printf 'exited\\n'; cat {REMOTE_EXIT}; "
            f"elif test -s {REMOTE_PID} && kill -0 \"$(cat {REMOTE_PID})\"; then "
            "printf 'active\\n'; "
            "else printf 'lost\\n'; fi",
            30,
        )
        if state.returncode:
            raise RuntimeError("typed_remote_boundary:process_state_unreachable")
        lines = [line.strip() for line in state.stdout.splitlines()]
        active = lines[0] if lines else "unknown"
        atomic(
            artifact / "remote-unit-state.json",
            {"observed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "raw": lines},
        )
        if active != "active":
            worker = ssh(
                ip,
                f"cat {REMOTE}/artifacts/worker.stdout 2>/dev/null || true; "
                "printf '\\n--- STDERR ---\\n'; "
                f"cat {REMOTE}/artifacts/worker.stderr 2>/dev/null || true",
                120,
            )
            (artifact / "remote-worker.log").write_text(
                worker.stdout + "\n--- SSH STDERR ---\n" + worker.stderr
            )
            return active, json.dumps(lines)
        time.sleep(20)
    ssh(
        ip,
        f"test -s {REMOTE_PID} && kill -TERM \"$(cat {REMOTE_PID})\" || true",
        180,
    )
    raise RuntimeError("typed_deadline_boundary:absolute_deadline")


def retrieve(ip: str, artifact: pathlib.Path) -> pathlib.Path:
    manifest = ssh(
        ip,
        f"find {REMOTE}/artifacts -type f -printf '%P\\t%s\\n' | sort",
        120,
    )
    (artifact / "remote-artifact-manifest.tsv").write_text(manifest.stdout)
    if manifest.returncode:
        raise RuntimeError("typed_retrieval_boundary:manifest")
    pack = ssh(
        ip,
        f"cd {REMOTE} && rm -f compact.tar.gz.part compact.tar.gz && "
        "tar -czf compact.tar.gz.part artifacts && "
        "mv compact.tar.gz.part compact.tar.gz && sha256sum compact.tar.gz",
        900,
    )
    (artifact / "compact-manifest.stdout").write_text(pack.stdout)
    (artifact / "compact-manifest.stderr").write_text(pack.stderr)
    if pack.returncode:
        raise RuntimeError("typed_retrieval_boundary:pack")
    partial = artifact / ".compact.tar.gz.part"
    copied = scp_from(ip, f"{REMOTE}/compact.tar.gz", partial, 1800)
    if copied.returncode:
        (artifact / "compact.scp.stderr").write_text(copied.stderr)
        raise RuntimeError("typed_retrieval_boundary:copy")
    expected = pack.stdout.split()[0]
    if digest(partial) != expected:
        raise RuntimeError("typed_retrieval_boundary:hash")
    archive = artifact / "compact.tar.gz"
    partial.replace(archive)
    retrieved = artifact / "retrieved"
    with tarfile.open(archive, "r:gz") as bundle:
        bundle.extractall(retrieved, filter="data")
    return retrieved / "artifacts"


def requests_accepted(root: pathlib.Path) -> dict[str, object]:
    serial = sorted(root.glob("*-serial-rows.json"))
    row_counts: dict[str, int] = {}
    for path in serial:
        try:
            row_counts[path.name] = len(json.loads(path.read_text()))
        except (OSError, ValueError, TypeError):
            row_counts[path.name] = -1
    candidate_audits = sorted(root.glob("candidate-*-candidate-audit.jsonl"))
    audit_events = sum(
        len(path.read_text().splitlines()) for path in candidate_audits
    )
    return {
        "row_counts": row_counts,
        "candidate_audit_events": audit_events,
        "any_request_row": any(value > 0 for value in row_counts.values()),
        "candidate_path_present": audit_events > 0,
    }


def repair_wait(
    artifact: pathlib.Path,
    diagnostic: dict[str, object],
) -> None:
    repair = PROJECT / "REPAIR_READY.json"
    request = PROJECT / "REPAIR_REQUEST.json"
    atomic(
        repair,
        {
            "schema_version": 1,
            "classification": "recoverable_integration_or_consumer_defect",
            "artifact_root": str(artifact.relative_to(PROJECT)),
            "repair_deadline_utc": REPAIR_DEADLINE.isoformat(),
            "diagnostic": diagnostic,
            "claim_retained": True,
        },
    )
    while dt.datetime.now(dt.timezone.utc) < REPAIR_DEADLINE:
        if request.exists():
            raise RuntimeError("repair_request_requires_active_owner_patch")
        time.sleep(20)
    raise RuntimeError("typed_deadline_boundary:repair_deadline")


def release(artifact: pathlib.Path, condition: str) -> None:
    result = pool("release", "--project", NAME, "--condition", condition)
    (artifact / "release.stdout").write_text(result.stdout)
    (artifact / "release.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("typed_pool_boundary:release")


def main() -> int:
    artifact = PROJECT / "artifacts" / (
        "h200-verifier-" + time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
    )
    artifact.mkdir(parents=True, exist_ok=False)
    repair_ready = PROJECT / "REPAIR_READY.json"
    if repair_ready.exists():
        repair_ready.replace(artifact / "prior-REPAIR_READY.json")
    atomic(PROJECT / "OWNER_STATE.json", {"phase": "claim", "artifact_root": str(artifact)})
    claim = pool(
        "claim",
        "--project",
        NAME,
        "--bench",
        BENCH,
        "--lease-seconds",
        "23400",
    )
    (artifact / "claim.stdout").write_text(claim.stdout)
    (artifact / "claim.stderr").write_text(claim.stderr)
    if claim.returncode:
        atomic(
            PROJECT / "OWNER_TERMINAL.json",
            {"pass": False, "classification": "typed_pool_boundary:claim"},
        )
        return 75

    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME)
            atomic(
                PROJECT / "OWNER_HEARTBEAT.json",
                {
                    "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "returncode": result.returncode,
                },
            )

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    release_condition: str | None = None
    try:
        ip = instance_ip()
        wait_ssh(ip, artifact)
        atomic(PROJECT / "OWNER_STATE.json", {"phase": "staging", "artifact_root": str(artifact)})
        stage(ip, artifact)
        atomic(PROJECT / "OWNER_STATE.json", {"phase": "image", "artifact_root": str(artifact)})
        pull_image(ip, artifact)
        atomic(PROJECT / "OWNER_STATE.json", {"phase": "scientific_run", "artifact_root": str(artifact)})
        start_remote(ip, artifact)
        state, raw_state = wait_remote(ip, artifact)
        atomic(PROJECT / "OWNER_STATE.json", {"phase": "retrieval", "artifact_root": str(artifact)})
        retrieved = retrieve(ip, artifact)
        terminal_path = retrieved / "TERMINAL.json"
        if terminal_path.exists():
            terminal = json.loads(terminal_path.read_text())
            atomic(artifact / "TERMINAL.json", terminal)
            atomic(
                PROJECT / "LATEST_TERMINAL.json",
                {"artifact_root": str(artifact.relative_to(PROJECT)), **terminal},
            )
            atomic(
                PROJECT / "OWNER_TERMINAL.json",
                {
                    "pass": bool(terminal.get("pass")),
                    "classification": "scientific_terminal",
                    "remote_unit_state": state,
                    "artifact_root": str(artifact.relative_to(PROJECT)),
                },
            )
            release_condition = "ready"
            return 0 if terminal.get("pass") else 72

        evidence = requests_accepted(retrieved)
        diagnostic = {
            "remote_unit_state": state,
            "remote_unit_raw": raw_state,
            **evidence,
        }
        atomic(artifact / "NO_TERMINAL_DIAGNOSTIC.json", diagnostic)
        if not evidence["any_request_row"] and not evidence["candidate_path_present"]:
            repair_wait(artifact, diagnostic)
        if (
            evidence["candidate_path_present"]
            or any(
                value > 0
                for name, value in evidence["row_counts"].items()
                if name.startswith("candidate-")
            )
        ):
            atomic(
                PROJECT / "OWNER_TERMINAL.json",
                {
                    "pass": False,
                    "classification": "consumed_scientific_arm_without_terminal",
                    "diagnostic": diagnostic,
                    "artifact_root": str(artifact.relative_to(PROJECT)),
                },
            )
            release_condition = "maintenance"
            return 73
        repair_wait(artifact, diagnostic)
        return 75
    except Exception as error:
        atomic(
            artifact / "OWNER_EXCEPTION.json",
            {
                "classification": "owner_exception",
                "error": f"{type(error).__name__}: {error}",
            },
        )
        # A retained claim is intentional for an ordinary pre-invocation or
        # consumer defect.  The active researcher resolves the handshake.
        if (PROJECT / "REPAIR_READY.json").exists():
            return 74
        atomic(
            PROJECT / "OWNER_TERMINAL.json",
            {
                "pass": False,
                "classification": "nonrecoverable_owner_or_external_boundary",
                "error": f"{type(error).__name__}: {error}",
                "artifact_root": str(artifact.relative_to(PROJECT)),
            },
        )
        release_condition = "maintenance"
        return 75
    finally:
        stop.set()
        thread.join(timeout=3)
        if release_condition:
            release(artifact, release_condition)


if __name__ == "__main__":
    raise SystemExit(main())
