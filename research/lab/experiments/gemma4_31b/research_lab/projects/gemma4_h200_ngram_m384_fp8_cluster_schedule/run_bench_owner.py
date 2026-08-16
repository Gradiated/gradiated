#!/usr/bin/env python3
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
NEBIUS = pathlib.Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
NAME = "gemma4_h200_ngram_m384_fp8_cluster_schedule"
BENCH = "h200-ngram-verifier-e00kcm9nfhwt7e7gbc"
REMOTE = "/home/glmrunner/gemma4-h200-ngram-m384-cluster"
DEADLINE = dt.datetime(2026, 7, 24, 18, 50, tzinfo=dt.timezone.utc)
REPAIR_DEADLINE = dt.datetime(2026, 7, 24, 18, 42, tzinfo=dt.timezone.utc)
RATE = 2.46


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def run(args: list[str], timeout: int | None = None, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout, **kwargs)


def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return run(
        ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
    )


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def ssh(host: str, command: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
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
            f"UserKnownHostsFile={KNOWN}",
            f"glmrunner@{host}",
            command,
        ],
        timeout,
    )


def scp_to(host: str, source: pathlib.Path, target: str, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "scp",
            "-p",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            f"UserKnownHostsFile={KNOWN}",
            str(source),
            f"glmrunner@{host}:{target}",
        ],
        timeout,
    )


def scp_from(host: str, source: str, target: pathlib.Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "scp",
            "-p",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            f"UserKnownHostsFile={KNOWN}",
            f"glmrunner@{host}:{source}",
            str(target),
        ],
        timeout,
    )


def host_for_bench() -> str:
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = benches[BENCH] if isinstance(benches, dict) else next(row for row in benches if row["id"] == BENCH)
    sys.path.insert(0, str(NEBIUS))
    from placement_control import extract_public_ipv4, get_instance

    host = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
    if not host:
        raise RuntimeError("typed_provider_boundary:no_public_ip")
    return host


def update_status(active: dict[str, object] | None, **updates: object) -> None:
    value = json.loads((PROJECT / "STATUS.json").read_text())
    value.update(updates)
    value["active_session"] = active
    atomic(PROJECT / "STATUS.json", value)


def stage(host: str, artifact: pathlib.Path, rows: list[dict[str, object]]) -> None:
    prepared = ssh(host, f"install -d {shlex.quote(REMOTE)} {shlex.quote(REMOTE + '/project')} {shlex.quote(REMOTE + '/artifacts')}")
    if prepared.returncode:
        raise RuntimeError("typed_staging_boundary:remote_prepare")
    staged = []
    for row in rows:
        source = PROJECT / str(row["path"])
        target = f"{REMOTE}/{row['remote']}"
        expected = str(row["sha256"])
        check = ssh(
            host,
            f'test -f {shlex.quote(target)} && test "$(sha256sum {shlex.quote(target)} | cut -d" " -f1)" = {expected}',
        )
        reused = check.returncode == 0
        if not reused:
            partial = f"{target}.{expected}.part"
            copied = scp_to(host, source, partial)
            (artifact / f"{source.name}.scp.stderr").write_text(copied.stderr)
            if copied.returncode:
                raise RuntimeError(f"typed_staging_boundary:scp:{source.name}")
            mode = "0555" if row["remote"] in {"detached-owner"} or str(row["remote"]).endswith(".py") else "0444"
            finalized = ssh(
                host,
                f'test "$(sha256sum {shlex.quote(partial)} | cut -d" " -f1)" = {expected} && chmod {mode} {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {shlex.quote(target)}',
            )
            if finalized.returncode:
                raise RuntimeError(f"typed_staging_boundary:finalize:{source.name}")
        staged.append({**row, "target": target, "reused": reused})
    atomic(artifact / "STAGING_MANIFEST.json", {"files": staged, "remote_root": REMOTE})


def retrieve(host: str, artifact: pathlib.Path, suffix: str) -> pathlib.Path:
    remote_archive = f"{REMOTE}/compact-{suffix}.tar.gz"
    packed = ssh(
        host,
        f"cd {shlex.quote(REMOTE)} && tar -czf {shlex.quote(remote_archive)} REMOTE_OWNER.json REMOTE_OWNER.log REPAIR_READY.json artifacts 2>/dev/null || tar -czf {shlex.quote(remote_archive)} REMOTE_OWNER.json REMOTE_OWNER.log artifacts; sha256sum {shlex.quote(remote_archive)}",
        300,
    )
    (artifact / f"pack-{suffix}.stdout").write_text(packed.stdout)
    (artifact / f"pack-{suffix}.stderr").write_text(packed.stderr)
    if packed.returncode or not packed.stdout.strip():
        raise RuntimeError("recoverable_retrieval_defect:pack")
    expected = packed.stdout.split()[0]
    archive = artifact / f"compact-{suffix}.tar.gz"
    copied = scp_from(host, remote_archive, archive)
    if copied.returncode or sha256(archive) != expected:
        raise RuntimeError("recoverable_retrieval_defect:copy_or_hash")
    target = artifact / f"retrieved-{suffix}"
    target.mkdir(exist_ok=True)
    with tarfile.open(archive, "r:gz") as bundle:
        bundle.extractall(target, filter="data")
    return target


def release(artifact: pathlib.Path, condition: str, contents: dict[str, object]) -> None:
    path = artifact / "BENCH_CONTENTS.json"
    atomic(path, contents)
    result = pool("release", "--project", NAME, "--condition", condition, "--contents", str(path))
    (artifact / "release.stdout").write_text(result.stdout)
    (artifact / "release.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("typed_pool_boundary:release")


def main() -> int:
    manifest = json.loads((PROJECT / "FROZEN_PACKET.json").read_text())
    if manifest["director_binding_sha256"] != sha256(PROJECT / "DIRECTOR_BINDING.json"):
        raise RuntimeError("frozen_director_binding_mismatch")
    for row in manifest["files"]:
        path = PROJECT / row["path"]
        if not path.is_file() or path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            raise RuntimeError(f"frozen_input_mismatch:{row['path']}")
    artifact = PROJECT / "artifacts" / dt.datetime.now(dt.timezone.utc).strftime("m384-cluster-%Y%m%dt%H%M%Sz")
    artifact.mkdir(parents=True)
    claim_started = time.time()
    prior_spend = float(json.loads((PROJECT / "STATUS.json").read_text()).get("actual_spend_usd", 0.0))
    claim = pool("claim", "--project", NAME, "--bench", BENCH, "--lease-seconds", "3300")
    (artifact / "claim.stdout").write_text(claim.stdout)
    (artifact / "claim.stderr").write_text(claim.stderr)
    if claim.returncode:
        raise RuntimeError("typed_pool_boundary:claim")
    host = host_for_bench()
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME)
            atomic(PROJECT / "OWNER_HEARTBEAT.json", {"at_utc": now(), "returncode": result.returncode, "stderr": result.stderr})

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    disposition = "claim_retained"
    try:
        identity = ssh(
            host,
            "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits",
        )
        (artifact / "remote-identity.stdout").write_text(identity.stdout)
        (artifact / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_remote_boundary:ssh")
        stage(host, artifact, manifest["files"])
        while dt.datetime.now(dt.timezone.utc) < DEADLINE:
            launch = ssh(
                host,
                f"cd {shlex.quote(REMOTE)} && chmod 0555 detached-owner && ./detached-owner start --state REMOTE_OWNER.json --log REMOTE_OWNER.log --cwd {shlex.quote(REMOTE)} --unit-manager pid -- python3 project/remote_experiment.py",
            )
            (artifact / f"remote-launch-{int(time.time())}.stdout").write_text(launch.stdout)
            (artifact / f"remote-launch-{int(time.time())}.stderr").write_text(launch.stderr)
            if launch.returncode:
                raise RuntimeError("typed_remote_owner_boundary:launch")
            while dt.datetime.now(dt.timezone.utc) < DEADLINE:
                time.sleep(15)
                state = ssh(
                    host,
                    f"cd {shlex.quote(REMOTE)} && ./detached-owner status --state REMOTE_OWNER.json; test -f artifacts/FINAL_TERMINAL.json && echo FINAL || true; test -f REPAIR_READY.json && echo REPAIR || true",
                )
                atomic(artifact / "REMOTE_STATE.json", {"at_utc": now(), "stdout": state.stdout, "stderr": state.stderr, "returncode": state.returncode})
                if "FINAL" in state.stdout:
                    retrieved = retrieve(host, artifact, "final")
                    terminal = json.loads((retrieved / "artifacts/FINAL_TERMINAL.json").read_text())
                    spend = (time.time() - claim_started) / 3600 * RATE
                    release(
                        artifact,
                        "ready",
                        {
                            "schema_version": 1,
                            "project": NAME,
                            "result": terminal["result"],
                            "artifacts": str(artifact.relative_to(PROJECT)),
                            "checkpoint": "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint remains resident and read-only.",
                            "runtime": "Pinned SGLang v0.5.13 image plus M384 extension build/JIT caches retained; accelerator unoccupied.",
                            "server_state": "Component and endpoint containers removed; accelerator unoccupied.",
                            "candidate": "M384-only CUTLASS 1x2x1 cluster extension retained under /home/glmrunner/gemma4-h200-ngram-m384-cluster.",
                        },
                    )
                    disposition = "scientific_terminal_released_available"
                    update_status(
                        None,
                        status="complete",
                        actual_spend_usd=prior_spend + spend,
                        summary=f"M384 cluster terminal: {terminal['result']}.",
                        terminal={
                            "classification": "scientific_terminal",
                            "path": str((retrieved / "artifacts/FINAL_TERMINAL.json").relative_to(PROJECT)),
                            "current_attempt_provider_spend_usd": spend,
                            "prior_provider_spend_usd": prior_spend,
                        },
                    )
                    return 0
                if "REPAIR" in state.stdout:
                    retrieved = retrieve(host, artifact, f"repair-{int(time.time())}")
                    ready = json.loads((retrieved / "REPAIR_READY.json").read_text())
                    atomic(
                        PROJECT / "REPAIR_READY.json",
                        {
                            "at_utc": now(),
                            "artifact_root": str(artifact),
                            "diagnostic": ready,
                            "repair_deadline_utc": REPAIR_DEADLINE.isoformat(),
                            "claim_retained": True,
                        },
                    )
                    request = PROJECT / "REPAIR_REQUEST.json"
                    while dt.datetime.now(dt.timezone.utc) < REPAIR_DEADLINE and not request.exists():
                        time.sleep(5)
                    if not request.exists():
                        raise RuntimeError("typed_repair_boundary:deadline")
                    value = json.loads(request.read_text())
                    if value.get("retry") is not True:
                        raise RuntimeError("typed_repair_boundary:retry_not_authorized")
                    repair_rows = []
                    for row in value.get("files", []):
                        source = PROJECT / row["path"]
                        repair_rows.append(
                            {
                                "path": row["path"],
                                "remote": row["remote"],
                                "sha256": sha256(source),
                                "bytes": source.stat().st_size,
                            }
                        )
                    stage(host, artifact, repair_rows)
                    request.rename(PROJECT / f"REPAIR_REQUEST.consumed.{int(time.time())}.json")
                    ssh(host, f"rm -f {shlex.quote(REMOTE + '/REPAIR_READY.json')} {shlex.quote(REMOTE + '/REMOTE_OWNER.json')}")
                    break
        raise RuntimeError("typed_deadline_boundary:absolute")
    except Exception as error:
        atomic(artifact / "OWNER_EXCEPTION.json", {"at_utc": now(), "error": repr(error)})
        try:
            retrieve(host, artifact, "boundary")
        except Exception as retrieval_error:
            atomic(artifact / "RETRIEVAL_EXCEPTION.json", {"at_utc": now(), "error": repr(retrieval_error)})
        spend = (time.time() - claim_started) / 3600 * RATE
        release(
            artifact,
            "maintenance",
            {
                "schema_version": 1,
                "project": NAME,
                "result": "typed_boundary",
                "error": repr(error),
                "artifacts": str(artifact.relative_to(PROJECT)),
                "server_state": "Director inspection required after compact retrieval attempt.",
            },
        )
        disposition = "typed_boundary_released_maintenance"
        update_status(
            None,
            status="complete",
            actual_spend_usd=prior_spend + spend,
            summary=f"Typed boundary after retrieval attempt: {error!r}.",
            terminal={
                "classification": "typed_boundary",
                "artifact_root": str(artifact.relative_to(PROJECT)),
                "current_attempt_provider_spend_usd": spend,
                "prior_provider_spend_usd": prior_spend,
            },
        )
        return 2
    finally:
        stop.set()
        thread.join(5)
        atomic(
            PROJECT / "OWNER_TERMINAL.json",
            {
                "at_utc": now(),
                "disposition": disposition,
                "claimed_seconds": time.time() - claim_started,
                "conservative_provider_spend_usd": (time.time() - claim_started) / 3600 * RATE,
            },
        )


if __name__ == "__main__":
    raise SystemExit(main())
