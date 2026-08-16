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
import threading
import time


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
DETACHED = pathlib.Path("/root/workspace/research/factory/tools/detached-owner")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
NAME = "gemma4_h200_ngram_qlen_mask_target_verify"
BENCH = "h200-ngram-verifier-e00kcm9nfhwt7e7gbc"
REMOTE_LEGACY = "/home/glmrunner/gemma4-ngram-qlen-two-stage"
REMOTE = os.environ["QLEN_REMOTE_ROOT"]
DEADLINE = dt.datetime(2026, 7, 24, 19, 50, tzinfo=dt.timezone.utc)
REPAIR_DEADLINE = dt.datetime(2026, 7, 24, 19, 40, tzinfo=dt.timezone.utc)
RATE = 2.46


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(args: list[str], timeout: int | None = None, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout, **kwargs)


def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return run(
        ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
    )


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ssh(host: str, command: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "ssh", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "ServerAliveInterval=20",
            "-o", "ServerAliveCountMax=3", "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={KNOWN}", f"glmrunner@{host}", command,
        ],
        timeout,
    )


def scp_to(host: str, source: pathlib.Path, target: str) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "scp", "-p", "-i", str(KEY), "-o", "BatchMode=yes",
            "-o", f"UserKnownHostsFile={KNOWN}", str(source), f"glmrunner@{host}:{target}",
        ],
        300,
    )


def scp_from(host: str, source: str, target: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "scp", "-p", "-i", str(KEY), "-o", "BatchMode=yes",
            "-o", f"UserKnownHostsFile={KNOWN}", f"glmrunner@{host}:{source}", str(target),
        ],
        600,
    )


def instance_ip() -> str:
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = benches[BENCH] if isinstance(benches, dict) else next(x for x in benches if x["id"] == BENCH)
    sys.path.insert(0, str(NEBIUS))
    from placement_control import extract_public_ipv4, get_instance

    value = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
    if not value:
        raise RuntimeError("typed_provider_boundary:no_public_ip")
    return value


def update_status(active: dict[str, object] | None, **updates: object) -> None:
    value = json.loads((PROJECT / "STATUS.json").read_text())
    value.update(updates)
    value["active_session"] = active
    atomic(PROJECT / "STATUS.json", value)


def stage(host: str, artifact: pathlib.Path) -> None:
    packet = PROJECT / "FROZEN_PACKET.production-two-stage.tar"
    control_reference = PROJECT / "repair-v2-control-reference.tar.gz"
    rows = []
    retired = f"{REMOTE_LEGACY}.retired-{pathlib.Path(REMOTE).name.rsplit('-', 1)[-1]}"
    prepare = ssh(
        host,
        f"install -d {shlex.quote(REMOTE)} && "
        f"if test -e {shlex.quote(REMOTE_LEGACY)} && ! test -L {shlex.quote(REMOTE_LEGACY)}; then "
        f"mv {shlex.quote(REMOTE_LEGACY)} {shlex.quote(retired)}; fi && "
        f"ln -sfn {shlex.quote(REMOTE)} {shlex.quote(REMOTE_LEGACY)}",
    )
    if prepare.returncode:
        raise RuntimeError("typed_staging_boundary:remote_prepare")
    for source, target in (
        (packet, f"{REMOTE}/FROZEN_PACKET.production-two-stage.tar"),
        (control_reference, f"{REMOTE}/repair-v2-control-reference.tar.gz"),
        (DETACHED, f"{REMOTE}/detached-owner"),
    ):
        digest = sha256(source)
        check = ssh(host, f'test -f {shlex.quote(target)} && test "$(sha256sum {shlex.quote(target)} | cut -d" " -f1)" = {digest}')
        reused = check.returncode == 0
        if not reused:
            partial = f"{target}.{digest}.part"
            copy = scp_to(host, source, partial)
            (artifact / f"{source.name}.scp.stderr").write_text(copy.stderr)
            if copy.returncode:
                raise RuntimeError(f"typed_staging_boundary:scp:{source.name}")
            finalize = ssh(host, f'test "$(sha256sum {shlex.quote(partial)} | cut -d" " -f1)" = {digest} && chmod 0444 {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {shlex.quote(target)}')
            if finalize.returncode:
                raise RuntimeError(f"typed_staging_boundary:finalize:{source.name}")
        rows.append({"path": target, "sha256": digest, "bytes": source.stat().st_size, "reused": reused})
    extract = ssh(host, f"cd {shlex.quote(REMOTE)} && install -d project artifacts control-reference && tar -xf FROZEN_PACKET.production-two-stage.tar -C project && tar -xzf repair-v2-control-reference.tar.gz -C control-reference && chmod +x detached-owner")
    (artifact / "extract.stdout").write_text(extract.stdout)
    (artifact / "extract.stderr").write_text(extract.stderr)
    if extract.returncode:
        raise RuntimeError("typed_staging_boundary:extract")
    atomic(artifact / "STAGING_MANIFEST.json", {"files": rows, "remote_root": REMOTE})


def retrieve(host: str, artifact: pathlib.Path) -> pathlib.Path:
    pack = ssh(host, f"cd {shlex.quote(REMOTE)} && tar -czf compact.tar.gz OWNER.json OWNER.log INVOCATION_STATE.json REPAIR_READY.json artifacts 2>/dev/null || tar -czf compact.tar.gz OWNER.json OWNER.log INVOCATION_STATE.json artifacts; sha256sum compact.tar.gz", 300)
    (artifact / "pack.stdout").write_text(pack.stdout)
    (artifact / "pack.stderr").write_text(pack.stderr)
    if pack.returncode:
        raise RuntimeError("recoverable_retrieval_defect:pack")
    expected = pack.stdout.split()[0]
    archive = artifact / "compact.tar.gz"
    copy = scp_from(host, f"{REMOTE}/compact.tar.gz", archive)
    if copy.returncode or sha256(archive) != expected:
        raise RuntimeError("recoverable_retrieval_defect:copy_or_hash")
    snapshots = artifact / "snapshots"
    snapshot = run(
        [
            "/root/workspace/research/factory/tools/artifact-snapshot",
            "--archive", str(archive), "--root", str(snapshots),
        ]
    )
    (artifact / "artifact-snapshot.stdout").write_text(snapshot.stdout)
    (artifact / "artifact-snapshot.stderr").write_text(snapshot.stderr)
    if snapshot.returncode:
        raise RuntimeError("recoverable_retrieval_defect:artifact_snapshot")
    result = json.loads(snapshot.stdout)
    return pathlib.Path(result["destination"])


def release(artifact: pathlib.Path, condition: str, contents: dict[str, object]) -> None:
    path = artifact / "BENCH_CONTENTS.json"
    atomic(path, contents)
    result = pool("release", "--project", NAME, "--condition", condition, "--contents", str(path))
    (artifact / "release.stdout").write_text(result.stdout)
    (artifact / "release.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("typed_pool_boundary:release")


def main() -> int:
    artifact = pathlib.Path(os.environ["QLEN_ARTIFACT_ROOT"])
    artifact.mkdir(parents=True, exist_ok=True)
    claim_started = time.time()
    claim = pool("claim", "--project", NAME, "--bench", BENCH, "--lease-seconds", "300")
    (artifact / "claim.stdout").write_text(claim.stdout)
    (artifact / "claim.stderr").write_text(claim.stderr)
    if claim.returncode:
        raise RuntimeError("typed_pool_boundary:claim")
    host = instance_ip()
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(45):
            value = pool("heartbeat", "--project", NAME)
            atomic(PROJECT / "OWNER_HEARTBEAT.json", {"at_utc": now(), "returncode": value.returncode, "stderr": value.stderr})

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    active = {
        "unit": str(PROJECT / "LOCAL_OWNER.json"),
        "unit_manager": "pid",
        "pid": os.getpid(),
        "start_ticks": int(pathlib.Path(f"/proc/{os.getpid()}/stat").read_text().split()[21]),
        "deadline_utc": "2026-07-24T19:50:00Z",
        "artifact_root": str(artifact),
        "bench_id": BENCH,
        "remote_root": REMOTE,
        "expected_terminal": "artifacts/FINAL_TERMINAL.json",
    }
    prior_spend = float(json.loads((PROJECT / "STATUS.json").read_text()).get("actual_spend_usd", 0.0))
    update_status(active, summary="PID-managed owner claimed the retained H200; the first real c32/Q12 two-stage captured-call component is running.")
    disposition = "unknown"
    try:
        identity = ssh(host, "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits")
        (artifact / "remote-identity.stdout").write_text(identity.stdout)
        (artifact / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_remote_boundary:ssh")
        ring = ssh(
            host,
            "sudo docker inspect gemma4-ngram-ring-live-suffix > /tmp/qlen-ring-inspect.json 2>/dev/null || true; "
            "sudo docker logs gemma4-ngram-ring-live-suffix > /tmp/qlen-ring.stdout 2> /tmp/qlen-ring.stderr || true; "
            "sudo docker rm -f gemma4-ngram-ring-live-suffix",
            180,
        )
        (artifact / "ring-stop.stdout").write_text(ring.stdout)
        (artifact / "ring-stop.stderr").write_text(ring.stderr)
        if ring.returncode:
            raise RuntimeError("typed_resident_server_boundary:ring_stop")
        stage(host, artifact)
        launch = ssh(host, f"cd {shlex.quote(REMOTE)} && ./detached-owner start --state OWNER.json --log OWNER.log --cwd {shlex.quote(REMOTE)} --unit-manager pid -- python3 project/production_remote_experiment.py")
        (artifact / "remote-launch.stdout").write_text(launch.stdout)
        (artifact / "remote-launch.stderr").write_text(launch.stderr)
        if launch.returncode:
            raise RuntimeError("typed_remote_owner_boundary:launch")
        while dt.datetime.now(dt.timezone.utc) < DEADLINE:
            time.sleep(15)
            state = ssh(host, f"cd {shlex.quote(REMOTE)} && ./detached-owner status --state OWNER.json; test -f artifacts/FINAL_TERMINAL.json && echo FINAL || true; test -f REPAIR_READY.json && echo REPAIR || true")
            atomic(artifact / "REMOTE_STATE.json", {"at_utc": now(), "stdout": state.stdout, "stderr": state.stderr, "returncode": state.returncode})
            if "FINAL" in state.stdout:
                retrieved = retrieve(host, artifact)
                terminal = json.loads((retrieved / "artifacts/FINAL_TERMINAL.json").read_text())
                spend = (time.time() - claim_started) / 3600 * RATE
                release(artifact, "ready", {
                    "schema_version": 1,
                    "project": NAME,
                    "result": terminal["result"],
                    "artifacts": str(artifact.relative_to(PROJECT)),
                    "checkpoint": "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint remains resident and read-only.",
                    "runtime": "Pinned SGLang v0.5.13 image and compilation caches retained; accelerator unoccupied.",
                    "server_state": "Component/endpoint containers removed; accelerator unoccupied.",
                })
                disposition = "scientific_terminal_released_available"
                update_status(None, status="complete", actual_spend_usd=prior_spend + spend, summary=f"Two-stage QLEN terminal: {terminal['result']}.", terminal={"classification": "scientific_terminal", "path": str((retrieved / "artifacts/FINAL_TERMINAL.json").relative_to(PROJECT)), "current_attempt_provider_spend_usd": spend, "prior_provider_spend_usd": prior_spend})
                return 0
            if "REPAIR" in state.stdout:
                retrieve(host, artifact)
                atomic(PROJECT / "REPAIR_READY.json", {"at_utc": now(), "artifact_root": str(artifact), "diagnostic": "Remote ordinary integration/consumer defect retrieved; claim retained.", "repair_deadline_utc": REPAIR_DEADLINE.isoformat(), "claim_retained": True})
                while dt.datetime.now(dt.timezone.utc) < REPAIR_DEADLINE:
                    request = PROJECT / "REPAIR_REQUEST.json"
                    if request.exists():
                        stage(host, artifact)
                        remote_request = pathlib.Path(f"{REMOTE}/REPAIR_REQUEST.json")
                        request_copy = scp_to(host, request, str(remote_request))
                        if request_copy.returncode:
                            raise RuntimeError("recoverable_repair_request_transfer")
                        request.rename(PROJECT / f"REPAIR_REQUEST.consumed.{int(time.time())}.json")
                        break
                    time.sleep(10)
                else:
                    raise RuntimeError("typed_repair_boundary:deadline")
        raise RuntimeError("typed_deadline_boundary:absolute")
    except Exception as error:
        atomic(artifact / "OWNER_EXCEPTION.json", {"at_utc": now(), "error": repr(error)})
        try:
            retrieve(host, artifact)
        except Exception as retrieval_error:
            atomic(artifact / "RETRIEVAL_EXCEPTION.json", {"at_utc": now(), "error": repr(retrieval_error)})
        spend = (time.time() - claim_started) / 3600 * RATE
        release(artifact, "maintenance", {"schema_version": 1, "project": NAME, "result": "typed_boundary", "error": repr(error), "artifacts": str(artifact.relative_to(PROJECT)), "server_state": "Director inspection required after compact retrieval attempt."})
        disposition = "typed_boundary_released_maintenance"
        update_status(None, status="complete", actual_spend_usd=prior_spend + spend, summary=f"Typed boundary after retrieval attempt: {error!r}.", terminal={"classification": "typed_boundary", "artifact_root": str(artifact.relative_to(PROJECT)), "current_attempt_provider_spend_usd": spend, "prior_provider_spend_usd": prior_spend})
        return 2
    finally:
        stop.set()
        thread.join(5)
        atomic(PROJECT / "OWNER_TERMINAL.json", {"at_utc": now(), "disposition": disposition, "claimed_seconds": time.time() - claim_started, "conservative_provider_spend_usd": (time.time() - claim_started) / 3600 * RATE})


if __name__ == "__main__":
    raise SystemExit(main())
