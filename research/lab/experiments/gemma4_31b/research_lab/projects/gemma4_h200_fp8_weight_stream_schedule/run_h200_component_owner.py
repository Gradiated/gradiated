#!/usr/bin/env python3
"""Durable owner for the one admitted persistent Stream-K H200 component."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path

P = Path(__file__).resolve().parent
LAB = P.parents[1]
FACTORY = Path("/root/workspace/research/factory/src")
REPAIR = Path("/root/workspace/research/factory/tools/repair-handshake")
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN = Path("/root/.config/nebius/glm-campaign/known_hosts")
BENCH = "h200-dflash-adapter-e00vyqp7gxsr34wrtz"
PROJECT = "gemma4_h200_fp8_weight_stream_schedule"
REMOTE = "/home/glmrunner/gemma4-fp8-weight-stream-persistent-streamk"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
RATE = 2.45
# The scheduled action allows at most 70 claimed minutes but must release by
# 07:20Z. The caller supplies the earlier absolute deadline.
OWNER_SECONDS = 70 * 60
DISPATCH_SHA256 = "549d3c1c5c13d67e7309cf50610a51c9485eb181b3a17423247287abd1a0b038"


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def claim_cost(prior: float, started: float) -> float:
    """Charge the full retained-bench claim, not merely this child process."""
    claimed = os.environ.get("CLAIM_STARTED_UTC")
    if claimed:
        began = dt.datetime.fromisoformat(claimed.replace("Z", "+00:00"))
        elapsed = max(0.0, (now() - began).total_seconds())
    else:
        elapsed = time.monotonic() - started
    return prior + elapsed * RATE / 3600


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, check=False, timeout=timeout)


def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return run(
        ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args],
        60,
    )


def ssh(command: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "ssh", "-i", str(KEY), "-o", "BatchMode=yes",
            "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={KNOWN}",
            "glmrunner@89.169.109.132", command,
        ],
        timeout,
    )


def copy(source: Path, destination: str, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return run(
        ["scp", "-p", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
         "-o", f"UserKnownHostsFile={KNOWN}", str(source), f"glmrunner@89.169.109.132:{destination}"],
        timeout,
    )


def update_status(**values: object) -> None:
    status = json.loads((P / "STATUS.json").read_text())
    status.update(values)
    atomic(P / "STATUS.json", status)


def checked_remote_file(source: Path) -> None:
    wanted = digest(source)
    target = f"{REMOTE}/{source.name}"
    probe = ssh(
        f"mkdir -p {shlex.quote(REMOTE)} && test -f {shlex.quote(target)} && "
        f"test \"$(sha256sum {shlex.quote(target)} | cut -d' ' -f1)\" = {wanted}",
        120,
    )
    if probe.returncode == 0:
        return
    part = f"{target}.{wanted}.part"
    sent = copy(source, part)
    if sent.returncode:
        raise RuntimeError(f"staging_scp:{source.name}:{sent.stderr[-500:]}")
    commit = ssh(
        f"test \"$(sha256sum {shlex.quote(part)} | cut -d' ' -f1)\" = {wanted} && "
        f"mv {shlex.quote(part)} {shlex.quote(target)}",
        120,
    )
    if commit.returncode:
        raise RuntimeError(f"staging_hash:{source.name}:{commit.stderr[-500:]}")


def remote_docker(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    rendered = " ".join(shlex.quote(item) for item in argv)
    return ssh(f"cd {shlex.quote(REMOTE)} && sudo -n docker run --rm --gpus all --network none --ipc=host -v {shlex.quote(REMOTE)}:/work/project -w /work/project {IMAGE} {rendered}", timeout)


def retrieve(remote_name: str, local: Path) -> None:
    got = run(
        ["scp", "-p", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
         "-o", f"UserKnownHostsFile={KNOWN}", f"glmrunner@89.169.109.132:{REMOTE}/{remote_name}", str(local)],
        900,
    )
    if got.returncode:
        raise RuntimeError(f"retrieval:{remote_name}:{got.stderr[-500:]}")


def main() -> int:
    if not KEY.exists() or not KNOWN.exists():
        raise RuntimeError("controller_identity_missing")
    started = time.monotonic()
    artifact = P / "artifacts" / now().strftime("persistent-streamk-%Y%m%dt%H%M%Sz")
    artifact.mkdir(parents=True)
    prior = float(json.loads((P / "STATUS.json").read_text())["actual_spend_usd"])
    supplied_deadline = os.environ.get("OWNER_DEADLINE_UTC")
    deadline = (
        dt.datetime.fromisoformat(supplied_deadline.replace("Z", "+00:00"))
        if supplied_deadline
        else now() + dt.timedelta(seconds=OWNER_SECONDS)
    )
    if deadline <= now():
        raise RuntimeError(f"owner_deadline_elapsed:{deadline.isoformat()}")
    heartbeat = pool("heartbeat", "--project", PROJECT, "--bench", BENCH)
    (artifact / "initial_heartbeat.stdout").write_text(heartbeat.stdout)
    (artifact / "initial_heartbeat.stderr").write_text(heartbeat.stderr)
    if heartbeat.returncode:
        raise RuntimeError(f"initial_heartbeat:{heartbeat.stderr[-500:]}")
    stopping = threading.Event()

    def keep_lease() -> None:
        while not stopping.wait(45):
            result = pool("heartbeat", "--project", PROJECT, "--bench", BENCH)
            atomic(artifact / "heartbeat.json", {"at_utc": now().isoformat(), "returncode": result.returncode, "stderr": result.stderr[-1000:]})

    thread = threading.Thread(target=keep_lease, daemon=True)
    thread.start()
    terminal: dict[str, object]
    release_condition = "maintenance"
    try:
        files = [
            P / "fp8_weight_stream_extension.cu",
            P / "build_candidate.py",
            P / "exact_shape_runner.py",
            P / "PERSISTENT_GROUPED_PHYSICAL_MODEL.json",
            P / "PERSISTENT_GROUPED_SOURCE.json",
        ]
        for source in files:
            checked_remote_file(source)
        atomic(artifact / "staging_manifest.json", {"remote_root": REMOTE, "files": [{"path": str(source), "sha256": digest(source), "bytes": source.stat().st_size} for source in files]})
        # The module identity includes the repaired include-root integration,
        # not just the CUDA source, so this cannot be confused with the
        # earlier sm_90a build attempts.
        source_hash = digest(P / "fp8_weight_stream_extension.cu")
        build_identity = hashlib.sha256(
            (
                source_hash
                + digest(P / "build_candidate.py")
                + digest(P / "exact_shape_runner.py")
                + digest(P / "PERSISTENT_GROUPED_PHYSICAL_MODEL.json")
                + digest(P / "PERSISTENT_GROUPED_SOURCE.json")
                + DISPATCH_SHA256
                + "/sgl-workspace/sglang/sgl-kernel"
                + "/usr/local/lib/python3.12/dist-packages/deep_gemm"
            ).encode()
        ).hexdigest()
        module_name = f"gemma4_fp8_weight_stream-sm90a-{build_identity[:16]}.so"
        atomic(artifact / "BUILD_STARTED.json", {
            "at_utc": now().isoformat(),
            "source_sha256": source_hash,
            "build_identity_sha256": build_identity,
            "cutlass_root": "/usr/local/lib/python3.12/dist-packages/deep_gemm",
            "candidate_cuda_invocation_started": False,
        })
        build = remote_docker([
            "python3", "build_candidate.py", "--project-root", "/work/project",
            "--sgl-kernel-root", "/sgl-workspace/sglang/sgl-kernel",
            "--cutlass-root", "/usr/local/lib/python3.12/dist-packages/deep_gemm",
            "--cutlass-util-root", "/usr/local/lib/python3.12/dist-packages/tilelang/3rdparty/cutlass",
            "--build-root", f"/work/project/build-sm90a-{build_identity[:16]}",
            "--snapshot", f"/work/project/{module_name}", "--output", "/work/project/BUILD_RESULT.json",
            "--expected-dispatch-sha256", DISPATCH_SHA256,
        ], 1200)
        (artifact / "build.stdout").write_text(build.stdout)
        (artifact / "build.stderr").write_text(build.stderr)
        if build.returncode:
            raise RuntimeError(f"build_failure:{build.stderr[-1000:]}")
        retrieve("BUILD_RESULT.json", artifact / "BUILD_RESULT.json")
        retrieve(module_name, artifact / module_name)
        module = artifact / module_name
        module_hash = digest(module)
        if json.loads((artifact / "BUILD_RESULT.json").read_text()).get("target") != "sm_90a":
            raise RuntimeError("build_metadata_missing_sm90a")
        marker = {
            "at_utc": now().isoformat(),
            "candidate_cuda_invocation_started": True,
            "arm": "stock_gate_up__deterministic_streamk_down",
            "reason": "immediately before unchanged alternating exact-consumer M32/M384 comparison",
        }
        atomic(artifact / "PERSISTENT_STREAMK_SCIENCE_STARTED.json", marker)
        results: dict[str, object] = {}
        for rows in (32, 384):
            component = remote_docker([
                "python3", "exact_shape_runner.py", "--module",
                f"/work/project/{module_name}", "--rows", str(rows),
                "--repetitions", "100", "--output",
                f"/work/project/PERSISTENT_STREAMK_M{rows}_RESULT.json",
            ], 1200)
            (artifact / f"M{rows}.stdout").write_text(component.stdout)
            (artifact / f"M{rows}.stderr").write_text(component.stderr)
            try:
                retrieve(
                    f"PERSISTENT_STREAMK_M{rows}_RESULT.json",
                    artifact / f"M{rows}_RESULT.json",
                )
            except Exception:
                if component.returncode == 0:
                    raise
            if component.returncode:
                raise RuntimeError(
                    f"component_failure_M{rows}:{component.stderr[-1000:]}"
                )
            results[f"M{rows}"] = json.loads(
                (artifact / f"M{rows}_RESULT.json").read_text()
            )
        result_path = P / "PERSISTENT_GROUPED_H200_COMPONENT_RESULT.json"
        atomic(result_path, {
            "schema_version": 1,
            "arm": "stock_gate_up__deterministic_streamk_down",
            "module": {"path": str(module.relative_to(P)), "sha256": module_hash},
            "physical_model": {
                "path": "PERSISTENT_GROUPED_PHYSICAL_MODEL.json",
                "sha256": digest(P / "PERSISTENT_GROUPED_PHYSICAL_MODEL.json"),
            },
            "stages": results,
        })
        terminal = {
            "schema_version": 1,
            "result": "measured_persistent_streamk_component",
            "scientific_sample_consumed": True,
            "candidate_cuda_invocation_started": True,
            "module": {"path": str(module.relative_to(P)), "sha256": module_hash},
            "result_path": str(result_path.relative_to(P)),
            "result_sha256": digest(result_path),
            "actual_spend_usd": claim_cost(prior, started),
            "completed_at_utc": now().isoformat(),
        }
        terminal_path = P / "PERSISTENT_GROUPED_H200_TERMINAL.json"
        atomic(terminal_path, terminal)
        update_status(actual_spend_usd=terminal["actual_spend_usd"], terminal=terminal, terminal_artifact=terminal_path.name, terminal_artifact_sha256=digest(terminal_path), active_session=None, status="complete", summary="The one admitted stock-grid persistent Stream-K exact M32/M384 component is measured and the warm H200 is released.")
        release_condition = "ready"
    except Exception as error:
        science_started = (artifact / "PERSISTENT_STREAMK_SCIENCE_STARTED.json").exists()
        terminal = {"schema_version": 1, "result": "typed_integration_or_retrieval_boundary", "scientific_sample_consumed": False, "candidate_cuda_invocation_started": science_started, "error": repr(error), "raw_evidence_root": str(artifact.relative_to(P)), "actual_spend_usd": claim_cost(prior, started), "completed_at_utc": now().isoformat()}
        repair_root = artifact / "repair"
        repair_id = f"persistent-streamk-{artifact.name}"
        ready = run([str(REPAIR), "ready", "--root", str(repair_root), "--repair-id", repair_id, "--deadline", deadline.isoformat(), "--failure-kind", "integration_or_retrieval_defect", "--diagnostic", repr(error), "--retry-scope", "only the invalidated build, retrieval, or unstarted consumer operation; never replay a valid M32 result"], 60)
        (artifact / "repair_ready.stdout").write_text(ready.stdout)
        (artifact / "repair_ready.stderr").write_text(ready.stderr)
        if ready.returncode:
            # A stale request must never cause a claim to be released before
            # the absolute repair deadline.  Keep heartbeating so a director
            # can inspect the preserved raw diagnostic on this warm bench.
            (artifact / "repair_handshake_stale_or_failed.json").write_text(json.dumps({"returncode": ready.returncode, "stdout": ready.stdout, "stderr": ready.stderr}, indent=2) + "\n")
            while now() < deadline:
                time.sleep(min(30, max(1, (deadline - now()).total_seconds())))
        else:
            # The lease remains live while a bounded repair request is awaited.
            # A request is surfaced rather than silently changing the science.
            waited = run([str(REPAIR), "wait", "--root", str(repair_root), "--repair-id", repair_id, "--poll-seconds", "5"], max(60, int((deadline - now()).total_seconds()) + 10))
            (artifact / "repair_wait.stdout").write_text(waited.stdout)
            (artifact / "repair_wait.stderr").write_text(waited.stderr)
            terminal["repair_handshake"] = {"ready_returncode": ready.returncode, "wait_returncode": waited.returncode, "wait_stdout": waited.stdout[-1000:], "wait_stderr": waited.stderr[-1000:]}
        terminal["actual_spend_usd"] = claim_cost(prior, started)
        terminal["completed_at_utc"] = now().isoformat()
        atomic(P / "REPAIR_TERMINAL.json", terminal)
        update_status(actual_spend_usd=terminal["actual_spend_usd"], summary="Persistent Stream-K owner retained the claim through the bounded repair handshake; director disposition is required.", terminal=terminal)
    finally:
        stopping.set()
        thread.join(2)
        atomic(P / "BENCH_CONTENTS.json", {"project": PROJECT, "result": terminal["result"], "artifacts": str(artifact.relative_to(P)), "candidate_cuda_invocation_started": terminal["candidate_cuda_invocation_started"], "release_condition": release_condition, "runtime": "Pinned SGLang v0.5.13 image; persistent Stream-K FP8 module source/build and warm model/CUDA caches retained."})
        if release_condition == "ready":
            released = pool("release", "--project", PROJECT, "--bench", BENCH, "--condition", "ready", "--contents", str(P / "BENCH_CONTENTS.json"))
            (artifact / "release.stdout").write_text(released.stdout)
            (artifact / "release.stderr").write_text(released.stderr)
            if released.returncode:
                raise RuntimeError(f"release_failure:{released.stderr[-500:]}")
        else:
            # The bounded handshake expired or surfaced a request; release only
            # to maintenance after durable diagnostics and a terminal exist.
            released = pool("release", "--project", PROJECT, "--bench", BENCH, "--condition", "maintenance", "--contents", str(P / "BENCH_CONTENTS.json"))
            (artifact / "release.stdout").write_text(released.stdout)
            (artifact / "release.stderr").write_text(released.stderr)
            if released.returncode:
                raise RuntimeError(f"maintenance_release_failure:{released.stderr[-500:]}")
            update_status(active_session=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
