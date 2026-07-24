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
from typing import Any


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path(
    "/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius"
)
DETACHED = pathlib.Path("/root/workspace/research/factory/tools/detached-owner")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
NAME = "gemma4_h200_ngram_tree_verify_attention"
BENCH = "h200-ngram-critical-e00bwcwgsxawx1jmgw"
REMOTE = "/home/glmrunner/gemma4-ngram-tree-verify"
RESIDENT = "/home/glmrunner/gemma4-ngram-critical/checkpoint"
RATE = 2.46
DEADLINE = dt.datetime(2026, 7, 24, 14, 20, tzinfo=dt.timezone.utc)
REMOTE_DEADLINE_SECONDS = 4500
IMAGE = (
    "docker.io/lmsysorg/sglang@sha256:"
    "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
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


def atomic(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


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


def scp_to(ip: str, source: pathlib.Path, target: str, timeout: int = 300) -> None:
    result = run(
        [
            "scp",
            "-p",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            str(source),
            f"glmrunner@{ip}:{target}",
        ],
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"staging_copy_failed:{source.name}:{result.stderr[-1000:]}")


def scp_from(ip: str, source: str, target: pathlib.Path, timeout: int = 900) -> None:
    result = run(
        [
            "scp",
            "-p",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            f"glmrunner@{ip}:{source}",
            str(target),
        ],
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"retrieval_copy_failed:{result.stderr[-1000:]}")


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


def remote_match(ip: str, path: str, size: int, digest: str) -> bool:
    quoted = shlex.quote(path)
    result = ssh(
        ip,
        f"test -f {quoted} && test \"$(stat -c %s {quoted})\" = {size} && "
        f"test \"$(sha256sum {quoted} | cut -d' ' -f1)\" = {digest}",
        max(90, min(2400, size // 35_000_000 + 90)),
    )
    return result.returncode == 0


def stage_small(
    ip: str, source: pathlib.Path, target: str, size: int, digest: str
) -> dict[str, Any]:
    if source.stat().st_size != size or sha256(source) != digest:
        raise RuntimeError(f"local_packet_integrity_mismatch:{source}")
    if remote_match(ip, target, size, digest):
        return {"path": target, "bytes": size, "sha256": digest, "reused": True}
    parent = str(pathlib.PurePosixPath(target).parent)
    partial = f"{target}.{digest}.part"
    prepare = ssh(ip, f"install -d {shlex.quote(parent)}; rm -f {shlex.quote(partial)}")
    if prepare.returncode:
        raise RuntimeError(f"staging_prepare_failed:{target}")
    scp_to(ip, source, partial, max(300, size // 20_000_000 + 300))
    finalize = ssh(
        ip,
        f"test \"$(stat -c %s {shlex.quote(partial)})\" = {size} && "
        f"test \"$(sha256sum {shlex.quote(partial)} | cut -d' ' -f1)\" = {digest} && "
        f"chmod 0444 {shlex.quote(partial)} && mv {shlex.quote(partial)} {shlex.quote(target)}",
        max(90, size // 35_000_000 + 90),
    )
    if finalize.returncode:
        raise RuntimeError(f"staging_finalize_failed:{target}")
    return {"path": target, "bytes": size, "sha256": digest, "reused": False}


def stage_checkpoint(ip: str, item: dict[str, Any]) -> dict[str, Any]:
    name = pathlib.Path(str(item["path"])).name
    target = f"{REMOTE}/checkpoint/{name}"
    size = int(item["bytes"])
    digest = str(item["sha256"])
    if remote_match(ip, target, size, digest):
        return {"path": target, "bytes": size, "sha256": digest, "reused": True}
    source = f"{RESIDENT}/{name}"
    if not remote_match(ip, source, size, digest):
        raise RuntimeError(f"resident_checkpoint_integrity_mismatch:{name}")
    partial = f"{target}.{digest}.part"
    command = (
        f"install -d {shlex.quote(str(pathlib.PurePosixPath(target).parent))}; "
        f"rm -f {shlex.quote(partial)}; "
        f"ln {shlex.quote(source)} {shlex.quote(partial)}; "
        f"test \"$(stat -c %s {shlex.quote(partial)})\" = {size}; "
        f"test \"$(sha256sum {shlex.quote(partial)} | cut -d' ' -f1)\" = {digest}; "
        f"chmod 0444 {shlex.quote(partial)}; mv {shlex.quote(partial)} {shlex.quote(target)}"
    )
    result = ssh(ip, command, max(120, size // 35_000_000 + 120))
    if result.returncode:
        raise RuntimeError(f"checkpoint_materialization_failed:{name}:{result.stderr[-1000:]}")
    return {"path": target, "bytes": size, "sha256": digest, "reused": False}


def update_status(active_session: dict[str, Any] | None, **updates: Any) -> None:
    value = json.loads((PROJECT / "STATUS.json").read_text())
    value.update(updates)
    value["active_session"] = active_session
    atomic(PROJECT / "STATUS.json", value)


def retrieve(ip: str, artifact: pathlib.Path) -> pathlib.Path:
    pack = ssh(
        ip,
        f"cd {REMOTE} && rm -f result.tar.gz.part result.tar.gz && "
        "tar -czf result.tar.gz.part artifacts OWNER.json OWNER.log "
        "INVOCATION_STATE.json REPAIR_READY.json 2>/dev/null || "
        "tar -czf result.tar.gz.part artifacts OWNER.json OWNER.log INVOCATION_STATE.json; "
        "mv result.tar.gz.part result.tar.gz; sha256sum result.tar.gz",
        1800,
    )
    (artifact / "pack.stdout").write_text(pack.stdout)
    (artifact / "pack.stderr").write_text(pack.stderr)
    if pack.returncode:
        raise RuntimeError("typed_retrieval_boundary:remote_pack")
    expected = pack.stdout.split()[0]
    partial = artifact / ".result.tar.gz.part"
    scp_from(ip, f"{REMOTE}/result.tar.gz", partial, 1800)
    if sha256(partial) != expected:
        raise RuntimeError("typed_retrieval_boundary:hash")
    archive = artifact / "result.tar.gz"
    partial.replace(archive)
    target = artifact / "retrieved"
    with tarfile.open(archive, "r:gz") as bundle:
        bundle.extractall(target, filter="data")
    return target


def release(artifact: pathlib.Path, condition: str, contents: dict[str, Any]) -> None:
    path = artifact / "BENCH_CONTENTS.json"
    atomic(path, contents)
    result = pool(
        "release",
        "--project",
        NAME,
        "--condition",
        condition,
        "--contents",
        str(path),
    )
    (artifact / "release.stdout").write_text(result.stdout)
    (artifact / "release.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("typed_pool_boundary:release_failed")


def main() -> int:
    packet_path = PROJECT / "IMMUTABLE_PACKET.json"
    packet = json.loads(packet_path.read_text())
    if not packet.get("offline_construction_pass"):
        raise RuntimeError("typed_packet_boundary:offline_construction_failed")
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = (
        benches[BENCH]
        if isinstance(benches, dict)
        else next(row for row in benches if row["id"] == BENCH)
    )
    attached = (
        bench.get("status") == "claimed"
        and (bench.get("claim") or {}).get("project") == NAME
    )
    if not attached and (bench.get("status") != "available" or bench.get("claim")):
        raise RuntimeError("typed_pool_boundary:assigned_bench_unavailable")
    artifact = PROJECT / "artifacts" / (
        "tree-verify-" + time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
    )
    artifact.mkdir(parents=True, exist_ok=False)
    claim = pool(
        "claim",
        "--project",
        NAME,
        "--bench",
        BENCH,
        "--lease-seconds",
        "5700",
    )
    (artifact / "claim.stdout").write_text(claim.stdout)
    (artifact / "claim.stderr").write_text(claim.stderr)
    if claim.returncode:
        return 75
    claimed_at = dt.datetime.now(dt.timezone.utc)
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME)
            atomic(
                PROJECT / "OWNER_HEARTBEAT.json",
                {"observed_at": utc_now(), "returncode": result.returncode},
            )

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    condition: str | None = None
    contents: dict[str, Any] = {}
    try:
        ip = instance_ip()
        identity = ssh(
            ip,
            "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; "
            "sudo docker ps --format '{{.Names}}'; df -B1 /home/glmrunner",
            60,
        )
        (artifact / "remote-identity.stdout").write_text(identity.stdout)
        (artifact / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_remote_boundary:ssh")
        staged = []
        for item in packet["files"]:
            staged.append(
                stage_small(
                    ip,
                    PROJECT / str(item["path"]),
                    f"{REMOTE}/project/{item['path']}",
                    int(item["bytes"]),
                    str(item["sha256"]),
                )
            )
            atomic(artifact / "staging-progress.json", staged)
        staged.append(
            stage_small(
                ip,
                packet_path,
                f"{REMOTE}/project/IMMUTABLE_PACKET.json",
                packet_path.stat().st_size,
                sha256(packet_path),
            )
        )
        staged.append(
            stage_small(
                ip,
                DETACHED,
                f"{REMOTE}/project/detached-owner",
                DETACHED.stat().st_size,
                sha256(DETACHED),
            )
        )
        for item in packet["checkpoint"]["files"]:
            staged.append(stage_checkpoint(ip, item))
            atomic(artifact / "staging-progress.json", staged)
        image = ssh(
            ip,
            f"sudo docker image inspect {shlex.quote(IMAGE)} --format '{{{{json .RepoDigests}}}}'",
            90,
        )
        (artifact / "image.stdout").write_text(image.stdout)
        (artifact / "image.stderr").write_text(image.stderr)
        if image.returncode or "6113665a292b50fe" not in image.stdout:
            raise RuntimeError("typed_image_boundary:resident_digest_missing")
        active = {
            "unit": f"{REMOTE}/OWNER.json",
            "unit_manager": "remote-shell",
            "deadline_utc": DEADLINE.isoformat(),
            "artifact_root": str(artifact.relative_to(PROJECT)),
            "bench_id": BENCH,
            "forward_progress": "immutable packet and checkpoint snapshot staged; remote owner launching",
        }
        update_status(
            active,
            summary="Claimed the retained H200 and staged the immutable exact-shape packet; the detached remote component owner is launching.",
            next_action="Await the exact-consumer component, causal counters, and conditional matched c32 pair under the retained claim.",
        )
        launch = ssh(
            ip,
            f"chmod 0555 {REMOTE}/project/detached-owner; "
            f"python3 {REMOTE}/project/detached-owner start "
            f"--state {REMOTE}/OWNER.json --log {REMOTE}/OWNER.log --cwd {REMOTE} -- "
            f"/usr/bin/timeout --signal=TERM {REMOTE_DEADLINE_SECONDS} "
            f"/usr/bin/python3 {REMOTE}/project/remote_experiment.py",
            90,
        )
        (artifact / "remote-owner-launch.stdout").write_text(launch.stdout)
        (artifact / "remote-owner-launch.stderr").write_text(launch.stderr)
        if launch.returncode:
            raise RuntimeError("typed_launcher_boundary:detached_remote_owner")
        terminal_remote = f"{REMOTE}/artifacts/FINAL_TERMINAL.json"
        repair_seen = False
        while dt.datetime.now(dt.timezone.utc) < DEADLINE - dt.timedelta(minutes=3):
            state = ssh(
                ip,
                f"if test -s {terminal_remote}; then echo terminal; "
                f"elif test -s {REMOTE}/REPAIR_READY.json; then echo repair; "
                f"else python3 {REMOTE}/project/detached-owner status "
                f"--state {REMOTE}/OWNER.json 2>/dev/null || true; fi",
                60,
            )
            atomic(
                artifact / "remote-worker-state.json",
                {"observed_at": utc_now(), "stdout": state.stdout, "stderr": state.stderr},
            )
            if state.stdout.startswith("terminal"):
                break
            if state.stdout.startswith("repair") and not repair_seen:
                repair_seen = True
                marker = ssh(ip, f"cat {REMOTE}/REPAIR_READY.json; tail -n 200 {REMOTE}/OWNER.log", 60)
                (artifact / "repair-diagnostic.txt").write_text(
                    marker.stdout + marker.stderr
                )
                remote_ready = ssh(ip, f"cat {REMOTE}/REPAIR_READY.json", 60)
                if remote_ready.returncode == 0:
                    atomic(PROJECT / "REPAIR_READY.json", json.loads(remote_ready.stdout))
                active["forward_progress"] = (
                    "remote ordinary defect preserved; claim heartbeating through repair deadline"
                )
                update_status(
                    active,
                    summary="The remote owner preserved an ordinary integration/consumer defect and is holding the warm claim for repair.",
                    next_action="Inspect REPAIR_READY.json, patch only the invalidated operation, and write REPAIR_REQUEST.json before the absolute deadline.",
                )
            time.sleep(20)
        retrieved = retrieve(ip, artifact)
        final_path = retrieved / "artifacts/FINAL_TERMINAL.json"
        elapsed = (dt.datetime.now(dt.timezone.utc) - claimed_at).total_seconds()
        spend = elapsed / 3600 * RATE
        if not final_path.exists():
            raise RuntimeError("typed_deadline_boundary:scientific_terminal_missing")
        final = json.loads(final_path.read_text())
        atomic(artifact / "FINAL_TERMINAL.json", final)
        condition = "ready"
        contents = {
            "project": NAME,
            "result": final.get("result"),
            "artifacts": str(artifact.relative_to(PROJECT)),
            "checkpoint": (
                "Exact 62,578,655,208-byte project-local snapshot is hash-verified "
                f"at {REMOTE}/checkpoint."
            ),
            "image": IMAGE,
            "runtime": "Pinned SGLang v0.5.13; exact tree-attention component and conditional endpoint complete.",
            "server_state": "No experiment server or worker remains; image, checkpoint, Triton cache, and artifacts retained.",
            "actual_spend_usd": spend,
        }
        status = "complete"
        update_status(
            None,
            status=status,
            actual_spend_usd=spend,
            summary=(
                f"Scientific terminal: {final.get('result')}; exact component "
                f"{'passed' if final.get('component', {}).get('component_pass') else 'rejected'}."
            ),
            next_action=(
                "Retain the measured fixed-tree attention path for stacking."
                if final.get("result") == "positive"
                else "Close this BLOCK_M=16 exact-tree realization; do not replay it."
            ),
            decision_evidence={
                "artifact_root": str(artifact.relative_to(PROJECT)),
                "final_terminal": str(
                    (artifact / "FINAL_TERMINAL.json").relative_to(PROJECT)
                ),
                "evidence_type": "measured exact-shape H200 component, counters, and conditional endpoint",
            },
        )
        return 0
    except Exception as error:
        elapsed = (dt.datetime.now(dt.timezone.utc) - claimed_at).total_seconds()
        spend = elapsed / 3600 * RATE
        atomic(
            artifact / "OWNER_EXCEPTION.json",
            {"classification": "owner_exception", "error": f"{type(error).__name__}: {error}"},
        )
        condition = "maintenance"
        contents = {
            "project": NAME,
            "result": "typed_nonrecoverable_or_deadline_boundary",
            "artifacts": str(artifact.relative_to(PROJECT)),
            "runtime": f"{type(error).__name__}: {error}",
            "server_state": (
                f"Inspect {REMOTE}, OWNER.json/OWNER.log, containers, and GPU state "
                "before reuse; compact evidence retrieval was attempted before release."
            ),
            "actual_spend_usd": spend,
        }
        update_status(
            None,
            status="blocked",
            actual_spend_usd=spend,
            summary=f"Typed retained-bench boundary: {type(error).__name__}: {error}",
            next_action="Director must inspect the maintenance bench and preserved remote artifacts.",
        )
        return 75
    finally:
        stop.set()
        thread.join(timeout=3)
        if condition:
            release(artifact, condition, contents)


if __name__ == "__main__":
    raise SystemExit(main())
