#!/usr/bin/env python3
"""Bounded shared-bench owner for one exact current-SGLang L40S endpoint.

This program is deliberately unusable without a positive hash-bound offline
terminal.  It uses the lab GPU pool, keeps one outer heartbeat across a
consumer-only repair, retrieves decision artifacts before releasing, and
never creates or destroys provider resources.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import threading
import time

PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY_SRC = Path("/root/workspace/research/factory/src")
GPU_POOL = ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
HANDSHAKE = Path("/root/workspace/research/factory/tools/repair-handshake")
PROJECT_ID = "gemma4_l40s_current_runtime_fp8_endpoint_rebase"
ACCELERATOR = "nvidia-l40s"
MODEL = "google/gemma-4-31B-it"
COMMIT = "c6a6200a1a778a799ba61c395ac292317f01ebc9"
REMOTE = "/home/glmrunner/gemma4-l40s-current-runtime-fp8-rebase"
CONTAINER = "gemma4-l40s-current-runtime-fp8"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(32 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def pool(*args: str, timeout: int = 60) -> dict:
    result = subprocess.run(
        ["env", f"PYTHONPATH={FACTORY_SRC}", *GPU_POOL, *args],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"gpu_pool_{args[0]}_failed:{result.stderr[-1000:]}")
    return json.loads(result.stdout)


def ssh_base(ip: str, key: Path, known_hosts: Path) -> list[str]:
    return [
        "ssh",
        "-i",
        str(key),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "ConnectTimeout=15",
        f"glmrunner@{ip}",
    ]


def remote(
    ip: str,
    key: Path,
    known_hosts: Path,
    script: str,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*ssh_base(ip, key, known_hosts), "bash", "-s"],
        input=script,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def scp(
    ip: str,
    key: Path,
    known_hosts: Path,
    source: Path,
    target: str,
    timeout: int,
) -> None:
    result = subprocess.run(
        [
            "scp",
            "-q",
            "-i",
            str(key),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={known_hosts}",
            str(source),
            f"glmrunner@{ip}:{target}",
        ],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"scp_failed:{source.name}:{result.stderr[-1000:]}")


def validate_positive_terminal(path: Path) -> dict:
    value = json.loads(path.read_text())
    if (
        value.get("decision") != "positive"
        or value.get("later_lifecycle", {}).get("kind") != "exact_command"
        or value.get("selected_revision", {}).get("commit") != COMMIT
        or value.get("memory", {}).get("fits_single_l40s") is not True
    ):
        raise RuntimeError("positive_offline_terminal_required")
    return value


def validate_checkpoint(checkpoint: Path, terminal: dict) -> dict[str, dict]:
    checkpoint = checkpoint.resolve()
    if PROJECT.resolve() not in checkpoint.parents:
        raise RuntimeError("checkpoint_must_be_immutable_project_local_snapshot")
    source = terminal["bound_inputs"]["checkpoint_terminal"]
    manifest = json.loads(Path(source["path"]).read_text())
    expected = {
        row["path"]: {"bytes": row["bytes"], "sha256": row["sha256"]}
        for row in manifest["files"]
    }
    for name, identity in expected.items():
        path = checkpoint / name
        if path.stat().st_size != identity["bytes"] or sha256(path) != identity["sha256"]:
            raise RuntimeError(f"checkpoint_identity_mismatch:{name}")
    return expected


def reconcile_file(
    ip: str,
    key: Path,
    known_hosts: Path,
    local: Path,
    remote_root: str,
    identity: dict,
    timeout: int,
) -> None:
    target = f"{remote_root}/{local.name}"
    probe = remote(
        ip,
        key,
        known_hosts,
        f"""set -euo pipefail
if test -f {shlex.quote(target)}; then
  actual=$(sha256sum {shlex.quote(target)} | cut -d' ' -f1)
  size=$(stat -c %s {shlex.quote(target)})
  test "$actual" = {shlex.quote(identity['sha256'])} &&
    test "$size" = {identity['bytes']} && echo MATCH && exit 0
fi
echo MISSING
""",
        1800,
    )
    if probe.returncode:
        raise RuntimeError(f"remote_reconcile_probe_failed:{local.name}")
    if probe.stdout.strip().endswith("MATCH"):
        return
    temporary = target + ".transfer-part"
    scp(ip, key, known_hosts, local, temporary, timeout)
    finish = remote(
        ip,
        key,
        known_hosts,
        f"""set -euo pipefail
test "$(stat -c %s {shlex.quote(temporary)})" = {identity['bytes']}
test "$(sha256sum {shlex.quote(temporary)} | cut -d' ' -f1)" = {shlex.quote(identity['sha256'])}
chmod 0444 {shlex.quote(temporary)}
mv -f {shlex.quote(temporary)} {shlex.quote(target)}
""",
        1800,
    )
    if finish.returncode:
        raise RuntimeError(f"remote_reconcile_finalize_failed:{local.name}")


def retrieve(
    ip: str,
    key: Path,
    known_hosts: Path,
    remote_output: str,
    output: Path,
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    names = (
        "TERMINAL.json",
        "SCIENCE_STARTED.json",
        "consumer.stdout",
        "consumer.stderr",
        "server.log",
    )
    result: dict[str, object] = {"retrieved": [], "missing": []}
    for name in names:
        target = output / name
        fetch = subprocess.run(
            [
                "scp",
                "-q",
                "-i",
                str(key),
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                f"UserKnownHostsFile={known_hosts}",
                f"glmrunner@{ip}:{remote_output}/{name}",
                str(target) + ".part",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if fetch.returncode:
            result["missing"].append(name)
        else:
            os.replace(str(target) + ".part", target)
            result["retrieved"].append(name)
    atomic_json(output / "RETRIEVAL.json", result)
    return result


def heartbeat(stop: threading.Event, bench: str, events: list[dict]) -> None:
    while not stop.wait(30):
        try:
            value = pool("heartbeat", "--project", PROJECT_ID, "--bench", bench)
            events.append({"at": now(), "kind": "heartbeat", "pass": True})
            _ = value
        except Exception as error:
            events.append(
                {"at": now(), "kind": "heartbeat", "pass": False, "error": repr(error)}
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--positive-terminal", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--ip", required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--deadline-seconds", type=int, default=2400)
    parser.add_argument("--bench")
    args = parser.parse_args()
    if args.deadline_seconds != 2400:
        raise SystemExit("deadline_must_equal_2400_seconds")
    if args.artifact_root.exists():
        raise SystemExit("artifact_root_must_not_exist")

    terminal = validate_positive_terminal(args.positive_terminal)
    checkpoint_manifest = validate_checkpoint(args.checkpoint, terminal)
    launch = json.loads(
        Path(terminal["bound_inputs"]["launch"]["path"]).read_text()
    )["args"]
    started = time.time()
    deadline = started + args.deadline_seconds
    claim_args = [
        "claim",
        "--project",
        PROJECT_ID,
        "--accelerator",
        ACCELERATOR,
        "--model",
        MODEL,
        "--lease-seconds",
        str(args.deadline_seconds),
    ]
    if args.bench:
        claim_args.extend(["--bench", args.bench])
    claim = pool(*claim_args)
    bench = claim["id"]
    claimed_at = claim["claim"]["claimed_at"]
    events: list[dict] = [{"at": now(), "kind": "claim", "bench": bench}]
    stop = threading.Event()
    heartbeat_thread = threading.Thread(
        target=heartbeat, args=(stop, bench, events), daemon=True
    )
    heartbeat_thread.start()
    release_condition = "maintenance"
    consumed = False
    classification = "owner_failure"
    args.artifact_root.mkdir(parents=True)
    try:
        if claim["accelerator"] != ACCELERATOR:
            raise RuntimeError("claimed_accelerator_mismatch")
        if time.time() >= deadline:
            raise RuntimeError("deadline_before_remote_preflight")
        preflight = remote(
            args.ip,
            args.key,
            args.known_hosts,
            "set -e; nvidia-smi --query-gpu=name,compute_cap,memory.total --format=csv,noheader,nounits; sudo -n docker version --format '{{.Server.Version}}'",
            120,
        )
        (args.artifact_root / "preflight.stdout").write_text(preflight.stdout)
        (args.artifact_root / "preflight.stderr").write_text(preflight.stderr)
        if preflight.returncode or "L40S" not in preflight.stdout:
            raise RuntimeError("l40s_preflight_failed")

        prepare = remote(
            args.ip,
            args.key,
            args.known_hosts,
            f"set -e; mkdir -p {REMOTE}/checkpoint {REMOTE}/input {REMOTE}/output",
            60,
        )
        if prepare.returncode:
            raise RuntimeError("remote_prepare_failed")
        for name, identity in checkpoint_manifest.items():
            reconcile_file(
                args.ip,
                args.key,
                args.known_hosts,
                args.checkpoint / name,
                f"{REMOTE}/checkpoint",
                identity,
                max(60, int(deadline - time.time() - 600)),
            )
        workload_path = Path(terminal["bound_inputs"]["workload"]["path"])
        for local in (PROJECT / "exact_c32_consumer.py", workload_path):
            reconcile_file(
                args.ip,
                args.key,
                args.known_hosts,
                local,
                f"{REMOTE}/input",
                {"bytes": local.stat().st_size, "sha256": sha256(local)},
                300,
            )

        image = shlex.quote(args.image)
        launch_line = " ".join(shlex.quote(item) for item in launch)
        server = remote(
            args.ip,
            args.key,
            args.known_hosts,
            f"""set -euo pipefail
sudo -n docker pull {image}
revision=$(sudo -n docker image inspect {image} --format '{{{{index .Config.Labels "org.opencontainers.image.revision"}}}}')
test "$revision" = {COMMIT}
sudo -n docker rm -f {CONTAINER} >/dev/null 2>&1 || true
sudo -n docker run -d --name {CONTAINER} --gpus all --ipc=host --network=host \
  -v {REMOTE}/checkpoint:/work/checkpoint:ro {image} \
  python3 -m sglang.launch_server {launch_line}
for _ in $(seq 1 180); do
  curl -fsS --max-time 3 http://127.0.0.1:30000/v1/models >/dev/null && exit 0
  sleep 5
done
exit 1
""",
            max(60, min(1200, int(deadline - time.time() - 360))),
        )
        (args.artifact_root / "server-start.stdout").write_text(server.stdout)
        (args.artifact_root / "server-start.stderr").write_text(server.stderr)
        if server.returncode:
            raise RuntimeError("server_start_or_readiness_failed")

        attempt = 0
        while time.time() < deadline - 180:
            attempt += 1
            remote_output = f"{REMOTE}/output/attempt-{attempt}"
            run = remote(
                args.ip,
                args.key,
                args.known_hosts,
                f"""set -o pipefail
rm -rf {remote_output}
python3 {REMOTE}/input/exact_c32_consumer.py \
  --output {remote_output} \
  --workload {REMOTE}/input/{workload_path.name} \
  --arm current-sglang-l40s-exact-c32 \
  >{remote_output}.stdout 2>{remote_output}.stderr
rc=$?
cp {remote_output}.stdout {remote_output}/consumer.stdout 2>/dev/null || true
cp {remote_output}.stderr {remote_output}/consumer.stderr 2>/dev/null || true
sudo -n docker logs {CONTAINER} >{remote_output}/server.log 2>&1 || true
exit $rc
""",
                max(180, int(deadline - time.time() - 120)),
            )
            retrieved = retrieve(
                args.ip,
                args.key,
                args.known_hosts,
                remote_output,
                args.artifact_root / f"attempt-{attempt}",
            )
            science = "SCIENCE_STARTED.json" in retrieved["retrieved"]
            terminal_present = "TERMINAL.json" in retrieved["retrieved"]
            consumed = consumed or science
            if run.returncode == 0 and terminal_present:
                measured = json.loads(
                    (args.artifact_root / f"attempt-{attempt}/TERMINAL.json").read_text()
                )
                if measured.get("pass") is True:
                    classification = "scientific_terminal"
                    release_condition = "ready"
                    break
            if science and terminal_present:
                classification = "scientific_negative"
                release_condition = "ready"
                break
            diagnostic = args.artifact_root / f"attempt-{attempt}/RETRIEVAL.json"
            repair_deadline = dt.datetime.fromtimestamp(
                deadline - 120, dt.timezone.utc
            ).isoformat().replace("+00:00", "Z")
            subprocess.run(
                [
                    str(HANDSHAKE),
                    "ready",
                    "--root",
                    str(args.artifact_root),
                    "--deadline",
                    repair_deadline,
                    "--failure-kind",
                    "ordinary_endpoint_consumer_or_retrieval_defect",
                    "--diagnostic",
                    str(diagnostic),
                    "--retry-scope",
                    "consumer_and_retrieval_only",
                ],
                check=True,
                timeout=30,
            )
            wait = subprocess.run(
                [
                    str(HANDSHAKE),
                    "wait",
                    "--root",
                    str(args.artifact_root),
                    "--poll-seconds",
                    "5",
                ],
                timeout=max(30, int(deadline - time.time() - 120)),
            )
            if wait.returncode or attempt >= 2:
                classification = "repair_deadline_or_limit"
                break
        if time.time() >= deadline - 120:
            classification = "absolute_deadline"
    except Exception as error:
        classification = "typed_owner_failure"
        atomic_json(
            args.artifact_root / "OWNER_ERROR.json",
            {"at": now(), "error": repr(error), "sample_consumed": consumed},
        )
    finally:
        stop.set()
        heartbeat_thread.join(timeout=5)
        contents = args.artifact_root / "release-contents.json"
        atomic_json(
            contents,
            {
                "model": MODEL,
                "runtime_commit": COMMIT,
                "classification": classification,
                "sample_consumed": consumed,
            },
        )
        release = pool(
            "release",
            "--project",
            PROJECT_ID,
            "--bench",
            bench,
            "--expected-claimed-at",
            claimed_at,
            "--contents",
            str(contents),
            "--condition",
            release_condition,
        )
        atomic_json(
            args.artifact_root / "OWNER_TERMINAL.json",
            {
                "schema_version": 1,
                "classification": classification,
                "sample_consumed": consumed,
                "events": events,
                "release": release,
                "started_epoch": started,
                "deadline_epoch": deadline,
                "finished_at": now(),
            },
        )
    return 0 if classification == "scientific_terminal" else 2


if __name__ == "__main__":
    raise SystemExit(main())
