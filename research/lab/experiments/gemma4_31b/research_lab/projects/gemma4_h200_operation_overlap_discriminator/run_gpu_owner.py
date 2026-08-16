from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
REPO = HERE.parents[6]
sys.path.insert(0, str(REPO / "research/factory/src"))
sys.path.insert(0, str(REPO / "research/lab/experiments/glm47flash/campaign_100/nebius"))
from grad_research.gpu_pool import GpuPool
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base

PROJECT = "gemma4_h200_operation_overlap_discriminator"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
INSTANCE = "computeinstance-e00vhh6h29fj68x91g"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
REMOTE = "/home/glmrunner/gemma4-operation-overlap"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
ARTIFACTS = HERE / "artifacts" / "gpu-profiler-off-20260724t2341z"
RATE = 2.46


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(16 << 20), b""):
            h.update(block)
    return h.hexdigest()


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def remote(ip: str, command: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*ssh_base(ip, KEY), command], text=True, capture_output=True, timeout=timeout)


def scp_to(ip: str, source: Path, target: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["scp", *ssh_base(ip, KEY)[1:-1], str(source), f"{SSH_USER}@{ip}:{target}"], text=True, capture_output=True, timeout=timeout)


def emit(event: str, **fields: object) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with (ARTIFACTS / "OWNER_EVENTS.jsonl").open("a") as f:
        f.write(json.dumps({"timestamp_utc": now(), "event": event, **fields}, sort_keys=True) + "\n")


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    pool = GpuPool(LAB)
    stop = threading.Event()
    heartbeat_error: list[str] = []

    def beat() -> None:
        while not stop.wait(40):
            try:
                pool.heartbeat(PROJECT)
                emit("heartbeat")
            except Exception as e:
                heartbeat_error.append(repr(e)); emit("heartbeat_failure", error=repr(e)); return

    claimed = json.loads((LAB / "runtime/gpus.json").read_text())["benches"][BENCH]["claim"]
    claimed_at = dt.datetime.fromisoformat(claimed["claimed_at"].replace("Z", "+00:00"))
    atomic(HERE / "STATUS.json", {**json.loads((HERE / "STATUS.json").read_text()), "active_session": {"kind": "bounded_claim_owner", "pid": os.getpid(), "unit": "foreground-run_gpu_owner", "unit_manager": "foreground_turn_owner", "deadline_utc": "2026-07-24T01:30:00Z", "artifact_root": str(ARTIFACTS), "bench_id": BENCH, "forward_progress": "claimed; reconciling project-local snapshot"}})
    thread = threading.Thread(target=beat, daemon=True); thread.start()
    final: dict[str, object] = {}
    condition = "ready"
    try:
        ip = extract_public_ipv4(get_instance(INSTANCE))
        if not ip: raise RuntimeError("typed_provider_boundary:no_public_ip")
        ident = remote(ip, "hostname; nvidia-smi --query-gpu=name,driver_version --format=csv,noheader; sudo docker image inspect " + shlex.quote(IMAGE) + " >/dev/null", 90)
        (ARTIFACTS / "remote-identity.stdout").write_text(ident.stdout)
        (ARTIFACTS / "remote-identity.stderr").write_text(ident.stderr)
        if ident.returncode: raise RuntimeError("typed_remote_boundary:identity_or_pinned_image_failed")
        tar = ARTIFACTS / "project-snapshot.tar"
        subprocess.run(["tar", "-cf", str(tar), "--exclude=artifacts", "--exclude=__pycache__", "-C", str(HERE), "."], check=True)
        digest = sha(tar)
        prep = remote(ip, f"mkdir -p {shlex.quote(REMOTE)} && if test -f {shlex.quote(REMOTE + '/project-snapshot.tar.sha256')}; then cat {shlex.quote(REMOTE + '/project-snapshot.tar.sha256')}; fi", 60)
        matched = prep.returncode == 0 and prep.stdout.strip().split()[0:1] == [digest]
        if not matched:
            part = f"{REMOTE}/project-snapshot.tar.{digest}.part"
            sent = scp_to(ip, tar, part, 1200)
            if sent.returncode: raise RuntimeError(f"typed_transfer_boundary: {sent.stderr[-1000:]}")
            done = remote(ip, f"test \"$(sha256sum {shlex.quote(part)} | awk '{{print $1}}')\" = {digest} && mv -f {shlex.quote(part)} {shlex.quote(REMOTE + '/project-snapshot.tar')} && printf '%s  %s\\n' {digest} project-snapshot.tar > {shlex.quote(REMOTE + '/project-snapshot.tar.sha256')} && rm -rf {shlex.quote(REMOTE + '/project')} && mkdir -p {shlex.quote(REMOTE + '/project')} && tar -xf {shlex.quote(REMOTE + '/project-snapshot.tar')} -C {shlex.quote(REMOTE + '/project')}", 180)
            if done.returncode: raise RuntimeError("typed_transfer_boundary:hash_or_extract_failed")
            emit("snapshot_transferred_once", sha256=digest, bytes=tar.stat().st_size)
        else:
            emit("snapshot_already_matched", sha256=digest)
        update = remote(ip, f"rm -rf {shlex.quote(REMOTE + '/artifacts')} && mkdir -p {shlex.quote(REMOTE + '/artifacts')} && sudo docker rm -f gemma-operation-overlap >/dev/null 2>&1 || true", 60)
        if update.returncode not in (0,): raise RuntimeError("remote_prepare_failed")
        cmd = (f"sudo docker run --rm --name gemma-operation-overlap --gpus all --ipc=host --shm-size=32g "
               f"-v {shlex.quote(REMOTE + '/project')}:/work/project -v {shlex.quote(REMOTE + '/artifacts')}:/work/artifacts "
               f"{IMAGE} python3 /work/project/operation_overlap_harness.py --binding /work/project/BINDING.json "
               f"--input-root /work/project/inputs --artifact-root /work/artifacts/overlap-component --warmups 5 --iterations 21 --seed 20260724")
        atomic(HERE / "STATUS.json", {**json.loads((HERE / "STATUS.json").read_text()), "active_session": {"kind": "bounded_claim_owner", "pid": os.getpid(), "unit": "foreground-run_gpu_owner", "unit_manager": "foreground_turn_owner", "deadline_utc": "2026-07-24T01:30:00Z", "artifact_root": str(ARTIFACTS), "bench_id": BENCH, "forward_progress": "profiler-off scientific invocation running"}})
        emit("scientific_invocation_started", command_hash=hashlib.sha256(cmd.encode()).hexdigest())
        run = remote(ip, f"{cmd} > {shlex.quote(REMOTE + '/artifacts/worker.stdout')} 2> {shlex.quote(REMOTE + '/artifacts/worker.stderr')}", 3600)
        (ARTIFACTS / "worker.stdout").write_text(run.stdout); (ARTIFACTS / "worker.stderr").write_text(run.stderr)
        for name in ("COMPONENT_TERMINAL.json", "INVOCATION_STATE.json"):
            got = remote(ip, f"cat {shlex.quote(REMOTE + '/artifacts/overlap-component/' + name)}", 60)
            (ARTIFACTS / name).write_text(got.stdout)
        final = json.loads((ARTIFACTS / "COMPONENT_TERMINAL.json").read_text())
        final["remote_returncode"] = run.returncode
        final["snapshot_sha256"] = digest
        atomic(ARTIFACTS / "FINAL_TERMINAL.json", final)
        emit("scientific_terminal", classification=final.get("classification"), returncode=run.returncode)
        if run.returncode not in (0, 2): raise RuntimeError("scientific_runner_failed_without_valid_terminal")
    except Exception as e:
        condition = "maintenance" if "typed_provider" in str(e) or "typed_remote" in str(e) else "ready"
        final = {"schema_version": 1, "status": "terminal", "classification": "typed_external_blocker" if condition == "maintenance" else "owner_failure", "reason": repr(e), "timestamp_utc": now()}
        atomic(ARTIFACTS / "FINAL_TERMINAL.json", final); emit("owner_failure", error=repr(e))
    finally:
        stop.set(); thread.join(5)
        elapsed = max(0.0, (dt.datetime.now(dt.timezone.utc) - claimed_at).total_seconds())
        spend = elapsed / 3600 * RATE
        status = json.loads((HERE / "STATUS.json").read_text())
        status.update({"active_session": None, "actual_spend_usd": round(spend, 6), "terminal_artifact": str(ARTIFACTS / "FINAL_TERMINAL.json"), "scientific_invocations_consumed": 1 if (ARTIFACTS / "INVOCATION_STATE.json").exists() and json.loads((ARTIFACTS / "INVOCATION_STATE.json").read_text()).get("scientific_invocation_started") else 0, "summary": str(final.get("classification")), "next_action": "Interpret component terminal and decide whether endpoint slice is admitted."})
        atomic(HERE / "STATUS.json", status)
        try:
            pool.release(PROJECT, contents={"project": PROJECT, "artifacts": str(ARTIFACTS), "runtime": "profiler-off exact-consumer component complete", "result": final.get("classification"), "snapshot_sha256": locals().get("digest"), "server_state": "No server; component container exited; image and caches retained."}, condition=condition)
        except Exception as e: emit("release_failure", error=repr(e))
        emit("bench_released", condition=condition, claimed_seconds=elapsed, actual_spend_usd=spend)
    return 0 if final.get("classification") not in {"typed_external_blocker", "owner_failure"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
