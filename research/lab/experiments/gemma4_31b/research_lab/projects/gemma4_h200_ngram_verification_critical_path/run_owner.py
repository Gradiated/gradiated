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
NEBIUS = pathlib.Path(
    "/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius"
)
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
NAME = "gemma4_h200_ngram_verification_critical_path"
BENCH = "h200-ngram-critical-e00bwcwgsxawx1jmgw"
REMOTE = "/home/glmrunner/gemma4-ngram-critical"
DEADLINE = dt.datetime(2026, 7, 24, 13, 10, tzinfo=dt.timezone.utc)
INTERVENTION_DEADLINE = dt.datetime(
    2026, 7, 24, 12, 40, tzinfo=dt.timezone.utc
)
PROVIDER_STARTED = dt.datetime(
    2026, 7, 24, 11, 20, 18, tzinfo=dt.timezone.utc
)
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)


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
    os.replace(temporary, path)


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


def launch_gate() -> None:
    status = json.loads((PROJECT / "STATUS.json").read_text())
    if status.get("bench_id") != BENCH:
        raise RuntimeError("typed_binding_boundary:status_bench_mismatch")
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = benches[BENCH] if isinstance(benches, dict) else next(
        row for row in benches if row["id"] == BENCH
    )
    claim = bench.get("claim")
    attached = (
        bench.get("status") == "claimed"
        and isinstance(claim, dict)
        and claim.get("project") == NAME
    )
    if not attached and (
        bench.get("status") != "available" or bench.get("claim") is not None
    ):
        raise RuntimeError("typed_pool_boundary:assigned_bench_not_available")
    if not attached and "not awaited or started" not in bench["contents"].get(
        "server_state", ""
    ):
        raise RuntimeError("typed_resident_boundary:bench_not_empty")


def instance_ip() -> str:
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = benches[BENCH] if isinstance(benches, dict) else next(
        row for row in benches if row["id"] == BENCH
    )
    sys.path.insert(0, str(NEBIUS))
    from placement_control import extract_public_ipv4, get_instance

    value = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
    if not value:
        raise RuntimeError("typed_provider_boundary:no_public_ip")
    return value


def wait_ssh(ip: str, artifact: pathlib.Path) -> None:
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
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
        time.sleep(5)
    raise RuntimeError("typed_remote_boundary:ssh_readiness_timeout")


def remote_match(ip: str, target: str, size: int, sha256: str) -> bool:
    quoted = shlex.quote(target)
    command = (
        f"test -f {quoted} && "
        f"test \"$(stat -c %s {quoted})\" = {size} && "
        f"test \"$(sha256sum {quoted} | cut -d' ' -f1)\" = {sha256}"
    )
    timeout = max(90, min(2400, size // 35_000_000 + 90))
    return ssh(ip, command, timeout).returncode == 0


def stage_file(
    ip: str,
    source: pathlib.Path,
    target: str,
    expected_sha256: str,
    expected_bytes: int,
    artifact: pathlib.Path,
) -> dict[str, object]:
    if source.stat().st_size != expected_bytes or digest(source) != expected_sha256:
        raise RuntimeError(f"typed_local_integrity_boundary:{source}")
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
        f"rm -f {shlex.quote(partial)}",
    )
    if prepare.returncode:
        raise RuntimeError(f"typed_staging_boundary:prepare:{source.name}")
    timeout = max(900, min(5400, expected_bytes // 12_000_000 + 300))
    transfer = scp_to(ip, source, partial, timeout)
    if transfer.returncode:
        (artifact / f"{source.name}.scp.stderr").write_text(transfer.stderr)
        raise RuntimeError(f"typed_staging_boundary:transfer:{source.name}")
    finalize = ssh(
        ip,
        f"test \"$(stat -c %s {shlex.quote(partial)})\" = {expected_bytes} && "
        f"test \"$(sha256sum {shlex.quote(partial)} | cut -d' ' -f1)\" = "
        f"{expected_sha256} && chmod 0444 {shlex.quote(partial)} && "
        f"mv {shlex.quote(partial)} {shlex.quote(target)}",
        max(120, min(2400, expected_bytes // 35_000_000 + 120)),
    )
    if finalize.returncode:
        (artifact / f"{source.name}.finalize.stderr").write_text(finalize.stderr)
        raise RuntimeError(f"typed_staging_boundary:finalize:{source.name}")
    return {
        "path": target,
        "bytes": expected_bytes,
        "sha256": expected_sha256,
        "reused": False,
    }


def stage_packet(ip: str, artifact: pathlib.Path) -> list[dict[str, object]]:
    packet = json.loads((PROJECT / "SOURCE_TRACE_COUNTER_PACKET.json").read_text())
    rows = []
    for item in packet["checkpoint"]["files"]:
        rows.append(
            stage_file(
                ip,
                PROJECT / item["path"],
                f"{REMOTE}/checkpoint/{pathlib.Path(item['path']).name}",
                item["sha256"],
                item["bytes"],
                artifact,
            )
        )
        atomic(artifact / "staging-progress.json", rows)
    for item in packet["bound_files"]:
        rows.append(
            stage_file(
                ip,
                PROJECT / item["path"],
                f"{REMOTE}/project/{item['path']}",
                item["sha256"],
                item["bytes"],
                artifact,
            )
        )
        atomic(artifact / "staging-progress.json", rows)
    for path in [
        PROJECT / "SOURCE_TRACE_COUNTER_PACKET.json",
        PROJECT / "profile_runner.py",
        PROJECT / "profile_ranges.py",
        PROJECT / "remote_profile.py",
        PROJECT / "remote_pair.py",
    ]:
        rows.append(
            stage_file(
                ip,
                path,
                f"{REMOTE}/project/{path.name}",
                digest(path),
                path.stat().st_size,
                artifact,
            )
        )
        atomic(artifact / "staging-progress.json", rows)
    atomic(artifact / "STAGING_TERMINAL.json", {"pass": True, "files": rows})
    return rows


def pull_image(ip: str, artifact: pathlib.Path) -> None:
    inspect = ssh(
        ip,
        f"sudo docker image inspect {shlex.quote(IMAGE)} "
        "--format '{{json .RepoDigests}}'",
        60,
    )
    if inspect.returncode:
        pull = ssh(ip, f"sudo docker pull {shlex.quote(IMAGE)}", 5400)
        (artifact / "docker-pull.stdout").write_text(pull.stdout)
        (artifact / "docker-pull.stderr").write_text(pull.stderr)
        if pull.returncode:
            raise RuntimeError("typed_image_boundary:pull_failed")
    final = ssh(
        ip,
        f"sudo docker image inspect {shlex.quote(IMAGE)} "
        "--format '{{json .RepoDigests}}'",
        60,
    )
    (artifact / "docker-image.json").write_text(final.stdout)
    if final.returncode or "6113665a292b50fe" not in final.stdout:
        raise RuntimeError("typed_image_boundary:resident_digest_missing")


def start_worker(ip: str, stage: str, script: str, timeout_seconds: int) -> None:
    pid = f"{REMOTE}/{stage}.pid"
    exit_path = f"{REMOTE}/{stage}.exit"
    command = (
        f"cd {REMOTE}; /usr/bin/timeout --signal=TERM {timeout_seconds} "
        f"/usr/bin/python3 project/{script}; rc=$?; "
        f"printf '%s\\n' \"$rc\" > {exit_path}.part; "
        f"mv {exit_path}.part {exit_path}; exit \"$rc\""
    )
    result = ssh(
        ip,
        f"install -d {REMOTE}/artifacts; "
        f"rm -f {pid} {exit_path} {exit_path}.part; "
        f"nohup /usr/bin/bash -lc {shlex.quote(command)} "
        f"> {REMOTE}/artifacts/{stage}.worker.stdout "
        f"2> {REMOTE}/artifacts/{stage}.worker.stderr < /dev/null & echo $! > {pid}",
        60,
    )
    if result.returncode:
        raise RuntimeError(f"typed_launcher_boundary:{stage}")


def wait_worker(ip: str, stage: str, artifact: pathlib.Path) -> int:
    pid = f"{REMOTE}/{stage}.pid"
    exit_path = f"{REMOTE}/{stage}.exit"
    while dt.datetime.now(dt.timezone.utc) < DEADLINE:
        state = ssh(
            ip,
            f"if test -s {exit_path}; then printf 'exited '; cat {exit_path}; "
            f"elif test -s {pid} && kill -0 \"$(cat {pid})\"; then "
            "printf 'active\\n'; else printf 'lost\\n'; fi",
            30,
        )
        atomic(
            artifact / f"{stage}-worker-state.json",
            {
                "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "returncode": state.returncode,
                "stdout": state.stdout,
                "stderr": state.stderr,
            },
        )
        if state.returncode:
            raise RuntimeError(f"typed_remote_boundary:{stage}_state")
        words = state.stdout.split()
        if words and words[0] == "exited":
            return int(words[1]) if len(words) > 1 else 255
        if words and words[0] == "lost":
            raise RuntimeError(f"typed_remote_boundary:{stage}_lost")
        time.sleep(20)
    raise RuntimeError("typed_deadline_boundary:absolute_deadline")


def retrieve(ip: str, stage: str, artifact: pathlib.Path) -> pathlib.Path:
    remote_subtree = f"{REMOTE}/artifacts/{stage}"
    manifest = ssh(
        ip,
        f"find {shlex.quote(remote_subtree)} -type f -printf '%P\\t%s\\n' | sort",
        120,
    )
    (artifact / f"{stage}-remote-manifest.tsv").write_text(manifest.stdout)
    if manifest.returncode:
        raise RuntimeError(f"typed_retrieval_boundary:{stage}_manifest")
    archive_name = f"{stage}.tar.gz"
    pack = ssh(
        ip,
        f"cd {REMOTE} && rm -f {archive_name}.part {archive_name} && "
        f"tar -czf {archive_name}.part artifacts/{stage} "
        f"artifacts/{stage}.worker.stdout artifacts/{stage}.worker.stderr && "
        f"mv {archive_name}.part {archive_name} && sha256sum {archive_name}",
        1800,
    )
    (artifact / f"{stage}-pack.stdout").write_text(pack.stdout)
    (artifact / f"{stage}-pack.stderr").write_text(pack.stderr)
    if pack.returncode:
        raise RuntimeError(f"typed_retrieval_boundary:{stage}_pack")
    partial = artifact / f".{archive_name}.part"
    copied = scp_from(ip, f"{REMOTE}/{archive_name}", partial, 3600)
    if copied.returncode:
        (artifact / f"{stage}-scp.stderr").write_text(copied.stderr)
        raise RuntimeError(f"typed_retrieval_boundary:{stage}_copy")
    expected = pack.stdout.split()[0]
    if digest(partial) != expected:
        raise RuntimeError(f"typed_retrieval_boundary:{stage}_hash")
    archive = artifact / archive_name
    partial.replace(archive)
    retrieved = artifact / "retrieved"
    with tarfile.open(archive, "r:gz") as bundle:
        bundle.extractall(retrieved, filter="data")
    return retrieved / "artifacts" / stage


def wait_intervention(artifact: pathlib.Path) -> dict:
    ready = PROJECT / "PROFILE_READY.json"
    request = PROJECT / "INTERVENTION_REQUEST.json"
    atomic(
        ready,
        {
            "schema_version": 1,
            "artifact_root": str(artifact.relative_to(PROJECT)),
            "intervention_deadline_utc": INTERVENTION_DEADLINE.isoformat(),
            "claim_retained": True,
            "next": (
                "Analyze the retrieved exact c32 trace, install exactly one "
                "candidate_source.py, and write INTERVENTION_REQUEST.json."
            ),
        },
    )
    while dt.datetime.now(dt.timezone.utc) < INTERVENTION_DEADLINE:
        if request.exists():
            value = json.loads(request.read_text())
            source = PROJECT / "candidate_source.py"
            if (
                source.exists()
                and digest(source) == value.get("candidate_source_sha256")
                and value.get("mount_target")
                in {"ngram_worker.py", "decode_equivalent_lm_head.py"}
            ):
                return value
        time.sleep(10)
    raise RuntimeError("typed_deadline_boundary:intervention_not_ready")


def stage_candidate(
    ip: str, artifact: pathlib.Path, request: dict
) -> dict[str, object]:
    source = PROJECT / "candidate_source.py"
    row = stage_file(
        ip,
        source,
        f"{REMOTE}/project/candidate_source.py",
        request["candidate_source_sha256"],
        source.stat().st_size,
        artifact,
    )
    request_path = PROJECT / "INTERVENTION_REQUEST.json"
    stage_file(
        ip,
        request_path,
        f"{REMOTE}/project/INTERVENTION_REQUEST.json",
        digest(request_path),
        request_path.stat().st_size,
        artifact,
    )
    atomic(artifact / "INTERVENTION_STAGED.json", row)
    return row


def release(artifact: pathlib.Path, condition: str, contents: dict) -> None:
    contents_path = artifact / "BENCH_CONTENTS.json"
    atomic(contents_path, contents)
    result = pool(
        "release",
        "--project",
        NAME,
        "--condition",
        condition,
        "--contents",
        str(contents_path),
    )
    (artifact / "release.stdout").write_text(result.stdout)
    (artifact / "release.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("typed_pool_boundary:release")


def main() -> int:
    launch_gate()
    packet = PROJECT / "SOURCE_TRACE_COUNTER_PACKET.json"
    if not packet.exists():
        raise RuntimeError("typed_packet_boundary:missing")
    artifact = PROJECT / "artifacts" / (
        "ngram-critical-" + time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
    )
    artifact.mkdir(parents=True, exist_ok=False)
    repair_ready = PROJECT / "REPAIR_READY.json"
    repair_request = PROJECT / "REPAIR_REQUEST.json"
    if repair_ready.exists() and repair_request.exists():
        repair_ready.replace(artifact / "PRIOR_REPAIR_READY.json")
        repair_request.replace(artifact / "PRIOR_REPAIR_REQUEST.json")
    claim_started = dt.datetime.now(dt.timezone.utc)
    claim = pool(
        "claim",
        "--project",
        NAME,
        "--bench",
        BENCH,
        "--lease-seconds",
        "6300",
    )
    (artifact / "claim.stdout").write_text(claim.stdout)
    (artifact / "claim.stderr").write_text(claim.stderr)
    if claim.returncode:
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
    release_contents: dict = {}
    try:
        ip = instance_ip()
        wait_ssh(ip, artifact)
        atomic(
            PROJECT / "OWNER_STATE.json",
            {"phase": "staging", "artifact_root": str(artifact.relative_to(PROJECT))},
        )
        stage_packet(ip, artifact)
        pull_image(ip, artifact)
        atomic(
            PROJECT / "OWNER_STATE.json",
            {"phase": "profile", "artifact_root": str(artifact.relative_to(PROJECT))},
        )
        start_worker(ip, "profile", "remote_profile.py", 3000)
        profile_rc = wait_worker(ip, "profile", artifact)
        profile_root = retrieve(ip, "profile", artifact)
        profile_terminal_path = profile_root / "PROFILE_TERMINAL.json"
        if not profile_terminal_path.exists():
            raise RuntimeError("typed_profile_boundary:terminal_missing")
        profile_terminal = json.loads(profile_terminal_path.read_text())
        atomic(artifact / "PROFILE_TERMINAL.json", profile_terminal)
        if not profile_terminal.get("scientific_result_interpretable"):
            atomic(
                PROJECT / "REPAIR_READY.json",
                {
                    "schema_version": 1,
                    "classification": "recoverable_profile_consumer_defect",
                    "profile_returncode": profile_rc,
                    "artifact_root": str(artifact.relative_to(PROJECT)),
                    "claim_retained": True,
                    "repair_deadline_utc": INTERVENTION_DEADLINE.isoformat(),
                },
            )
            while dt.datetime.now(dt.timezone.utc) < INTERVENTION_DEADLINE:
                time.sleep(20)
            raise RuntimeError("typed_deadline_boundary:profile_repair_not_supplied")

        request = wait_intervention(artifact)
        stage_candidate(ip, artifact, request)
        atomic(
            PROJECT / "OWNER_STATE.json",
            {"phase": "matched_pair", "artifact_root": str(artifact.relative_to(PROJECT))},
        )
        start_worker(ip, "pair", "remote_pair.py", 4800)
        pair_rc = wait_worker(ip, "pair", artifact)
        pair_root = retrieve(ip, "pair", artifact)
        pair_terminal_path = pair_root / "PAIR_TERMINAL.json"
        if not pair_terminal_path.exists():
            state = ssh(
                ip,
                f"cat {REMOTE}/artifacts/pair/INVOCATION_STATE.json 2>/dev/null; "
                f"cat {REMOTE}/artifacts/pair.worker.stdout 2>/dev/null; "
                f"cat {REMOTE}/artifacts/pair.worker.stderr 2>/dev/null",
                120,
            )
            atomic(
                PROJECT / "REPAIR_READY.json",
                {
                    "schema_version": 1,
                    "classification": "recoverable_pair_consumer_or_harness_defect",
                    "pair_returncode": pair_rc,
                    "diagnostic": state.stdout[-8000:] + state.stderr[-2000:],
                    "artifact_root": str(artifact.relative_to(PROJECT)),
                    "claim_retained": True,
                    "repair_deadline_utc": DEADLINE.isoformat(),
                },
            )
            while dt.datetime.now(dt.timezone.utc) < DEADLINE:
                time.sleep(20)
            raise RuntimeError("typed_deadline_boundary:pair_repair_not_supplied")
        pair_terminal = json.loads(pair_terminal_path.read_text())
        atomic(artifact / "PAIR_TERMINAL.json", pair_terminal)
        provider_hours = (
            dt.datetime.now(dt.timezone.utc) - PROVIDER_STARTED
        ).total_seconds() / 3600
        actual_spend = provider_hours * 2.46
        terminal = {
            "schema_version": 1,
            "kind": "ngram_verification_critical_path",
            "profile": profile_terminal,
            "pair": pair_terminal,
            "pair_returncode": pair_rc,
            "claim_started_at_utc": claim_started.isoformat(),
            "provider_started_at_utc": PROVIDER_STARTED.isoformat(),
            "claim_completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "actual_spend_usd": actual_spend,
            "result": (
                "positive" if pair_terminal.get("valid")
                and pair_terminal.get("service_time_delta_fraction", 0) < 0
                else "nonpositive_or_invalid"
            ),
        }
        atomic(artifact / "TERMINAL.json", terminal)
        atomic(PROJECT / "LATEST_TERMINAL.json", terminal)
        release_condition = "ready"
        release_contents = {
            "project": NAME,
            "result": terminal["result"],
            "artifacts": str(artifact.relative_to(PROJECT)),
            "checkpoint": (
                "Exact 62,578,655,208-byte checkpoint remains resident and "
                "hash-verified at /home/glmrunner/gemma4-ngram-critical/checkpoint."
            ),
            "image": IMAGE,
            "runtime": "Pinned SGLang v0.5.13; profile and one matched c32 pair complete.",
            "server_state": "No experiment container or worker remains; image, checkpoint, and caches retained.",
            "actual_spend_usd": actual_spend,
        }
        return 0 if pair_terminal.get("valid") else 72
    except Exception as error:
        atomic(
            artifact / "OWNER_EXCEPTION.json",
            {
                "classification": "owner_exception",
                "error": f"{type(error).__name__}: {error}",
            },
        )
        if (PROJECT / "REPAIR_READY.json").exists():
            return 74
        release_condition = "maintenance"
        release_contents = {
            "project": NAME,
            "result": "typed_nonrecoverable_boundary",
            "artifacts": str(artifact.relative_to(PROJECT)),
            "runtime": f"{type(error).__name__}: {error}",
            "server_state": "Inspect retained remote state before reuse.",
        }
        return 75
    finally:
        stop.set()
        thread.join(timeout=3)
        if release_condition:
            release(artifact, release_condition, release_contents)


if __name__ == "__main__":
    raise SystemExit(main())
