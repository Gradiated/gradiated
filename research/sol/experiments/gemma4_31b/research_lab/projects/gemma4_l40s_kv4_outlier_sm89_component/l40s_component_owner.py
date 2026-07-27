#!/usr/bin/env python3
"""Bounded outer owner for one director-registered cold L40S component run."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import threading
import time


PROJECT = Path(__file__).resolve().parent
PACKET = PROJECT / "packet"
MANIFEST = PACKET / "PACKET_MANIFEST.json"
LAB = PROJECT.parents[1]
PROJECT_ID = "gemma4_l40s_kv4_outlier_sm89_component"
ACCELERATOR = "nvidia-l40s"
RUNTIME_COMMIT = "c6a6200a1a778a799ba61c395ac292317f01ebc9"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
MAX_LIFECYCLE_SECONDS = 27 * 60
HANDSHAKE = Path("/root/workspace/research/factory/tools/repair-handshake")
FACTORY_SRC = Path("/root/workspace/research/factory/src")
POOL = [
    "python3",
    "-m",
    "grad_research.gpu_pool",
    "--lab",
    str(LAB),
]
COMPACT_RESULT_FILES = (
    "SCIENCE_STARTED.json",
    "ARM_MARKERS.jsonl",
    "PRODUCER_STAGE.json",
    "CANDIDATE_RESOURCE_USAGE.txt",
    "RECOVERABLE.json",
    "TERMINAL.json",
    "INVOCATION_COMPLETE.json",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        **kwargs,
    )


def pool(*arguments: str, timeout: int = 60) -> dict:
    result = run(
        ["env", f"PYTHONPATH={FACTORY_SRC}", *POOL, *arguments],
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(
            f"gpu_pool_{arguments[0]}_failed:{result.stderr[-1200:]}"
        )
    return json.loads(result.stdout)


def load_manifest() -> dict:
    value = json.loads(MANIFEST.read_text())
    if value.get("schema_version") != 1 or not isinstance(value.get("files"), list):
        raise RuntimeError("packet_manifest_schema_invalid")
    files = {}
    for row in value["files"]:
        name = row.get("path")
        if (
            not isinstance(name, str)
            or name.startswith("/")
            or ".." in Path(name).parts
        ):
            raise RuntimeError(f"packet_path_invalid:{name}")
        path = PACKET / name
        if (
            not path.is_file()
            or path.stat().st_size != row.get("bytes")
            or sha256(path) != row.get("sha256")
        ):
            raise RuntimeError(f"packet_member_identity_mismatch:{name}")
        files[name] = {"bytes": row["bytes"], "sha256": row["sha256"]}
    if len(files) != len(value["files"]):
        raise RuntimeError("packet_manifest_duplicate_path")
    return {**value, "files": files}


def access_from_claim(claim: dict) -> tuple[str, str, Path, Path]:
    resource = claim.get("resource", {})
    host = resource.get("public_ipv4") or resource.get("ssh_host")
    user = resource.get("ssh_user")
    identity = resource.get("identity_file")
    known_hosts = resource.get("known_hosts_namespace") or resource.get(
        "known_hosts"
    )
    if not all(isinstance(item, str) and item for item in (host, user, identity, known_hosts)):
        raise RuntimeError("registered_bench_missing_explicit_ssh_identity")
    if user != "glmrunner":
        raise RuntimeError(f"registered_ssh_user_mismatch:{user}")
    identity_path = Path(identity)
    known_hosts_path = Path(known_hosts)
    if not identity_path.is_file() or not known_hosts_path.is_file():
        raise RuntimeError("registered_ssh_identity_path_missing")
    return host, user, identity_path, known_hosts_path


def ssh_base(host: str, user: str, identity: Path, known_hosts: Path) -> list[str]:
    return [
        "ssh",
        "-i",
        str(identity),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "ConnectTimeout=15",
        f"{user}@{host}",
    ]


def remote(
    access: tuple[str, str, Path, Path],
    script: str,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    host, user, identity, known_hosts = access
    return run(
        [*ssh_base(host, user, identity, known_hosts), "bash", "-s"],
        input=script,
        timeout=timeout,
    )


def scp(
    access: tuple[str, str, Path, Path],
    source: str,
    target: str,
    timeout: int,
    *,
    from_remote: bool = False,
) -> subprocess.CompletedProcess[str]:
    host, user, identity, known_hosts = access
    left = f"{user}@{host}:{source}" if from_remote else source
    right = target if from_remote else f"{user}@{host}:{target}"
    return run(
        [
            "scp",
            "-q",
            "-i",
            str(identity),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={known_hosts}",
            left,
            right,
        ],
        timeout=timeout,
    )


def remaining(deadline: float, reserve: int = 0) -> int:
    return max(0, int(deadline - time.time() - reserve))


def reconcile_member(
    access: tuple[str, str, Path, Path],
    local: Path,
    remote_path: str,
    row: dict,
    deadline: float,
) -> None:
    parent = str(Path(remote_path).parent)
    quoted_path = shlex.quote(remote_path)
    probe = remote(
        access,
        f"""set -euo pipefail
mkdir -p {shlex.quote(parent)}
if test -f {quoted_path} &&
   test "$(stat -c %s {quoted_path})" = {int(row['bytes'])} &&
   test "$(sha256sum {quoted_path} | cut -d' ' -f1)" = {shlex.quote(row['sha256'])}; then
  exit 0
fi
exit 9
""",
        min(120, remaining(deadline, 180)),
    )
    if probe.returncode == 0:
        return
    partial = remote_path + ".transfer-part"
    transfer = scp(
        access,
        str(local),
        partial,
        max(30, remaining(deadline, 180)),
    )
    if transfer.returncode:
        raise RuntimeError(
            f"packet_transfer_failed:{local.name}:{transfer.stderr[-800:]}"
        )
    finish = remote(
        access,
        f"""set -euo pipefail
test "$(stat -c %s {shlex.quote(partial)})" = {int(row['bytes'])}
test "$(sha256sum {shlex.quote(partial)} | cut -d' ' -f1)" = {shlex.quote(row['sha256'])}
chmod 0444 {shlex.quote(partial)}
mv -f {shlex.quote(partial)} {quoted_path}
""",
        min(120, remaining(deadline, 180)),
    )
    if finish.returncode:
        raise RuntimeError(
            f"packet_finalize_failed:{local.name}:{finish.stderr[-800:]}"
        )


def stage_packet(
    access: tuple[str, str, Path, Path],
    remote_root: str,
    manifest: dict,
    deadline: float,
) -> None:
    for name, row in manifest["files"].items():
        reconcile_member(
            access,
            PACKET / name,
            f"{remote_root}/packet/{name}",
            row,
            deadline,
        )
    manifest_row = {
        "bytes": MANIFEST.stat().st_size,
        "sha256": sha256(MANIFEST),
    }
    reconcile_member(
        access,
        MANIFEST,
        f"{remote_root}/packet/PACKET_MANIFEST.json",
        manifest_row,
        deadline,
    )


def heartbeat(stop: threading.Event, bench: str, events: list[dict]) -> None:
    while not stop.wait(25):
        try:
            value = pool("heartbeat", "--project", PROJECT_ID, "--bench", bench)
            events.append(
                {
                    "at": utc_now(),
                    "kind": "heartbeat",
                    "pass": True,
                    "lease_until_utc": value["claim"]["lease_until_utc"],
                }
            )
        except Exception as error:
            events.append(
                {
                    "at": utc_now(),
                    "kind": "heartbeat",
                    "pass": False,
                    "error": repr(error),
                }
            )


def pull_image(
    access: tuple[str, str, Path, Path],
    remote_root: str,
    deadline: float,
) -> None:
    image = shlex.quote(IMAGE)
    result = remote(
        access,
        f"""set -euo pipefail
mkdir -p {shlex.quote(remote_root)}/cache/torch_extensions {shlex.quote(remote_root)}/home
sudo -n docker pull {image}
sudo -n docker image inspect {image} --format '{{{{json .RepoDigests}}}}' |
  grep -F 'sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6'
revision=$(sudo -n docker image inspect {image} --format '{{{{index .Config.Labels "org.opencontainers.image.revision"}}}}')
test "$revision" = {RUNTIME_COMMIT}
""",
        min(600, remaining(deadline, 300)),
    )
    if result.returncode:
        raise RuntimeError(
            f"runtime_image_pull_or_identity_failed:{result.stderr[-1200:]}"
        )


def invoke(
    access: tuple[str, str, Path, Path],
    remote_root: str,
    attempt: int,
    mode: str,
    deadline: float,
    producer_remote_result: str | None,
) -> tuple[subprocess.CompletedProcess[str], str]:
    attempt_root = f"{remote_root}/output/attempt-{attempt}"
    result_root = f"{attempt_root}/result"
    container = f"gemma4-kv4-sm89-{attempt}"
    mode_arguments = f"--mode {shlex.quote(mode)}"
    if mode == "consumer-only":
        if producer_remote_result is None:
            raise RuntimeError("consumer_only_without_remote_producer")
        mode_arguments += (
            f" --producer-snapshot {shlex.quote(producer_remote_result + '/PRODUCER_SNAPSHOT.pt')}"
            f" --producer-stage {shlex.quote(producer_remote_result + '/PRODUCER_STAGE.json')}"
        )
    command = (
        "cd /work/state/packet && "
        "python3 run_sm89_component.py "
        f"--artifact-root /work/state/output/attempt-{attempt}/result "
        f"{mode_arguments}"
    )
    timeout = min(900, remaining(deadline, 150))
    if timeout < 60:
        raise RuntimeError("insufficient_time_for_component_invocation")
    script = f"""set -euo pipefail
mkdir -p {shlex.quote(attempt_root)}
uid=$(id -u)
gid=$(id -g)
printf '%s\n' '{{"at":"{utc_now()}","state":"launch_attempted","mode":"{mode}"}}' > {shlex.quote(attempt_root)}/LAUNCH_ATTEMPTED.json
set +e
sudo -n docker run --rm --name {shlex.quote(container)} --gpus all --ipc=host \
  --user "$uid:$gid" \
  -e HOME=/work/state/home \
  -e TORCH_EXTENSIONS_DIR=/work/state/cache/torch_extensions \
  -e PYTHONUNBUFFERED=1 \
  -v {shlex.quote(remote_root)}:/work/state \
  --entrypoint /bin/bash {shlex.quote(IMAGE)} -lc {shlex.quote(command)} \
  >{shlex.quote(attempt_root)}/runner.stdout \
  2>{shlex.quote(attempt_root)}/runner.stderr
rc=$?
set -e
printf '%s\n' "$rc" > {shlex.quote(attempt_root)}/runner.exit
exit "$rc"
"""
    result = remote(access, script, timeout)
    return result, attempt_root


def retrieve_compact(
    access: tuple[str, str, Path, Path],
    remote_attempt: str,
    local_attempt: Path,
) -> dict:
    local_attempt.mkdir(parents=True, exist_ok=True)
    rows = []
    required = ("runner.stdout", "runner.stderr", "runner.exit")
    for name in (*required, "LAUNCH_ATTEMPTED.json"):
        target = local_attempt / name
        fetch = scp(
            access,
            f"{remote_attempt}/{name}",
            str(target) + ".part",
            90,
            from_remote=True,
        )
        if fetch.returncode == 0:
            os.replace(str(target) + ".part", target)
            rows.append(
                {
                    "path": name,
                    "bytes": target.stat().st_size,
                    "sha256": sha256(target),
                }
            )
    result_root = remote_attempt + "/result"
    for name in COMPACT_RESULT_FILES:
        target = local_attempt / name
        fetch = scp(
            access,
            f"{result_root}/{name}",
            str(target) + ".part",
            120,
            from_remote=True,
        )
        if fetch.returncode == 0:
            os.replace(str(target) + ".part", target)
            rows.append(
                {
                    "path": name,
                    "bytes": target.stat().st_size,
                    "sha256": sha256(target),
                }
            )
    retrieved = {row["path"] for row in rows}
    value = {
        "schema_version": 1,
        "files": rows,
        "required_raw_present": all(name in retrieved for name in required),
        "science_started": "SCIENCE_STARTED.json" in retrieved,
        "terminal_present": "TERMINAL.json" in retrieved,
        "recoverable_present": "RECOVERABLE.json" in retrieved,
        "producer_stage_present": "PRODUCER_STAGE.json" in retrieved,
    }
    atomic_json(local_attempt / "RETRIEVAL.json", value)
    return value


def validate_terminal(local_attempt: Path) -> dict | None:
    terminal_path = local_attempt / "TERMINAL.json"
    complete_path = local_attempt / "INVOCATION_COMPLETE.json"
    if not terminal_path.exists() or not complete_path.exists():
        return None
    terminal = json.loads(terminal_path.read_text())
    complete = json.loads(complete_path.read_text())
    if (
        complete.get("terminal_sha256") != sha256(terminal_path)
        or terminal.get("sample_consumed") is not True
        or terminal.get("decision") not in {"positive", "negative"}
        or terminal.get("classification")
        not in {
            "component_positive",
            "numerical_or_ownership_negative",
            "complete_producer_consumer_nonpositive",
        }
    ):
        return None
    return terminal


def repair_request(
    artifact_root: Path,
    repair_id: str,
    diagnostic: Path,
    retry_scope: str,
    deadline: float,
) -> dict | None:
    repair_deadline = dt.datetime.fromtimestamp(
        deadline - 90, dt.timezone.utc
    ).isoformat().replace("+00:00", "Z")
    ready = run(
        [
            str(HANDSHAKE),
            "ready",
            "--root",
            str(artifact_root),
            "--repair-id",
            repair_id,
            "--deadline",
            repair_deadline,
            "--failure-kind",
            "ordinary_component_launcher_api_consumer_or_retrieval_defect",
            "--diagnostic",
            str(diagnostic),
            "--retry-scope",
            retry_scope,
        ],
        timeout=30,
    )
    if ready.returncode:
        raise RuntimeError(f"repair_ready_failed:{ready.stderr[-800:]}")
    wait_timeout = remaining(deadline, 85)
    if wait_timeout <= 0:
        return None
    try:
        waited = run(
            [
                str(HANDSHAKE),
                "wait",
                "--root",
                str(artifact_root),
                "--repair-id",
                repair_id,
                "--poll-seconds",
                "3",
            ],
            timeout=wait_timeout,
        )
    except subprocess.TimeoutExpired:
        return None
    if waited.returncode:
        return None
    value = json.loads(waited.stdout)
    request = value.get("request")
    if not isinstance(request, dict) or request.get("retry_scope") != retry_scope:
        raise RuntimeError("repair_request_scope_mismatch")
    return request


def validate_patch_request(request: dict) -> dict:
    path_value = request.get("patch_artifact")
    if not isinstance(path_value, str) or not path_value:
        raise RuntimeError("repair_patch_artifact_required")
    path = Path(path_value).resolve()
    if PROJECT.resolve() not in path.parents:
        raise RuntimeError("repair_patch_must_be_project_local")
    value = json.loads(path.read_text())
    if (
        value.get("kind") != "sm89_component_repair_patch"
        or value.get("packet_manifest") != str(MANIFEST.resolve())
        or value.get("packet_manifest_sha256") != sha256(MANIFEST)
    ):
        raise RuntimeError("repair_patch_binding_invalid")
    return load_manifest()


def inspect_remote(
    access: tuple[str, str, Path, Path], remote_root: str
) -> dict:
    result = remote(
        access,
        f"""set +e
sudo -n docker ps --format '{{{{.Names}}}} {{{{.Status}}}}' | grep '^gemma4-kv4-sm89-' || true
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits || true
du -sh {shlex.quote(remote_root)} 2>/dev/null || true
""",
        45,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-2000:],
    }


def write_owner_terminal(
    artifact_root: Path,
    *,
    classification: str,
    claim: dict,
    started: float,
    deadline: float,
    events: list[dict],
    scientific_terminal: dict | None,
    release: dict | None,
    remote_state: dict,
) -> None:
    claim_seconds = max(0.0, time.time() - started)
    hourly_rate = float(claim["hourly_cost_usd"])
    value = {
        "schema_version": 1,
        "kind": "l40s_kv4_outlier_sm89_component_owner_terminal",
        "classification": classification,
        "claim": {
            "bench": claim["id"],
            "claimed_at": claim["claim"]["claimed_at"],
            "claim_seconds": claim_seconds,
            "hourly_rate_usd": hourly_rate,
            "conservative_project_exposure_usd": claim_seconds
            * hourly_rate
            / 3600.0,
        },
        "started_epoch": started,
        "absolute_deadline_epoch": deadline,
        "finished_at_utc": utc_now(),
        "events": events,
        "scientific_terminal": scientific_terminal,
        "remote_state": remote_state,
        "release": release,
    }
    atomic_json(artifact_root / "TERMINAL.json", value)
    atomic_json(artifact_root / "OWNER_TERMINAL.json", value)


def release_scientific(
    claim: dict,
    artifact_root: Path,
    terminal: dict,
    remote_state: dict,
) -> dict:
    contents = artifact_root / "BENCH_CONTENTS.json"
    atomic_json(
        contents,
        {
            "project": PROJECT_ID,
            "model": None,
            "runtime_commit": RUNTIME_COMMIT,
            "image": IMAGE,
            "component_result": terminal["classification"],
            "component_cache": "compiled extension and immutable image retained",
            "gpu_processes": "none" if not remote_state["stdout"].strip() else "inspect_output_recorded",
        },
    )
    return pool(
        "release",
        "--project",
        PROJECT_ID,
        "--bench",
        claim["id"],
        "--expected-claimed-at",
        claim["claim"]["claimed_at"],
        "--contents",
        str(contents),
        "--condition",
        "ready",
    )


def release_terminal_boundary(
    claim: dict,
    artifact_root: Path,
    classification: str,
    remote_state: dict,
) -> dict:
    contents = artifact_root / "BENCH_CONTENTS.json"
    atomic_json(
        contents,
        {
            "project": PROJECT_ID,
            "model": None,
            "runtime_commit": RUNTIME_COMMIT,
            "image": IMAGE,
            "component_result": classification,
            "component_cache": "remote packet, image, extension cache, and any producer snapshot retained",
            "remote_inspection": remote_state,
        },
    )
    return pool(
        "release",
        "--project",
        PROJECT_ID,
        "--bench",
        claim["id"],
        "--expected-claimed-at",
        claim["claim"]["claimed_at"],
        "--contents",
        str(contents),
        "--condition",
        "maintenance",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument(
        "--deadline-seconds", type=int, default=MAX_LIFECYCLE_SECONDS
    )
    args = parser.parse_args()
    if not 0 < args.deadline_seconds <= MAX_LIFECYCLE_SECONDS:
        raise SystemExit("deadline_must_be_positive_and_at_most_1620_seconds")
    if args.artifact_root.exists():
        raise SystemExit("artifact_root_must_not_exist")
    if not HANDSHAKE.is_file():
        raise SystemExit("shared_repair_handshake_missing")
    manifest = load_manifest()
    preview = pool("show", "--bench", args.bench)
    if preview.get("accelerator") != ACCELERATOR:
        raise SystemExit("director_bound_bench_is_not_l40s")
    access = access_from_claim(preview)
    args.artifact_root.mkdir(parents=True)
    started = time.time()
    deadline = started + args.deadline_seconds
    claim = pool(
        "claim",
        "--project",
        PROJECT_ID,
        "--bench",
        args.bench,
        "--accelerator",
        ACCELERATOR,
        "--lease-seconds",
        str(args.deadline_seconds),
    )
    claimed_at = claim["claim"]["claimed_at"]
    safe_claim_id = re.sub(r"[^A-Za-z0-9._-]", "-", claim["id"])
    remote_root = (
        f"/home/glmrunner/gemma4-kv4-sm89-{claimed_at.replace(':', '-')}"
    )
    events = [
        {
            "at": utc_now(),
            "kind": "claim",
            "bench": claim["id"],
            "claimed_at": claimed_at,
        }
    ]
    stop = threading.Event()
    heartbeat_thread = threading.Thread(
        target=heartbeat, args=(stop, claim["id"], events), daemon=True
    )
    heartbeat_thread.start()
    scientific_terminal = None
    classification = "unknown_retained_boundary"
    release = None
    producer_remote_result = None
    attempt = 0
    unreachable = False
    state = "prepare"
    mode = "full"
    remote_attempt = None
    local_attempt = None
    repair_generation = 0
    while remaining(deadline, 150) >= 60 and scientific_terminal is None:
        retry_scope = None
        diagnostic_path = None
        try:
            if claim["id"] != args.bench or claim["accelerator"] != ACCELERATOR:
                raise RuntimeError("claimed_bench_identity_mismatch")
            if access_from_claim(claim) != access:
                raise RuntimeError("claimed_bench_access_identity_changed")
            if state == "prepare":
                preflight = remote(
                    access,
                    "set -euo pipefail; nvidia-smi --query-gpu=name,compute_cap,memory.total --format=csv,noheader,nounits; sudo -n docker version --format '{{.Server.Version}}'",
                    min(120, remaining(deadline, 180)),
                )
                (args.artifact_root / "preflight.stdout").write_text(
                    preflight.stdout
                )
                (args.artifact_root / "preflight.stderr").write_text(
                    preflight.stderr
                )
                if preflight.returncode == 255:
                    unreachable = True
                    classification = "unsafe_or_unreachable_guest"
                    break
                if (
                    preflight.returncode
                    or "L40S" not in preflight.stdout
                    or "8.9" not in preflight.stdout
                ):
                    raise RuntimeError("l40s_sm89_or_docker_preflight_failed")
                stage_packet(access, remote_root, manifest, deadline)
                pull_image(access, remote_root, deadline)
                state = "invoke"
                continue
            if state == "invoke":
                attempt += 1
                remote_attempt = f"{remote_root}/output/attempt-{attempt}"
                local_attempt = args.artifact_root / f"attempt-{attempt}"
                _, observed_remote_attempt = invoke(
                    access,
                    remote_root,
                    attempt,
                    mode,
                    deadline,
                    producer_remote_result,
                )
                if observed_remote_attempt != remote_attempt:
                    raise RuntimeError("invocation_attempt_root_mismatch")
                state = "retrieve"
            if state == "retrieve":
                if remote_attempt is None or local_attempt is None:
                    raise RuntimeError("retrieval_state_missing_attempt")
                retrieval = retrieve_compact(
                    access, remote_attempt, local_attempt
                )
                terminal = validate_terminal(local_attempt)
                if terminal is not None and retrieval["required_raw_present"]:
                    scientific_terminal = terminal
                    classification = terminal["classification"]
                    break
                diagnostic_path = local_attempt / "RETRIEVAL.json"
                if not retrieval["required_raw_present"]:
                    retry_scope = "retrieval_only"
                elif retrieval["recoverable_present"]:
                    diagnostic = json.loads(
                        (local_attempt / "RECOVERABLE.json").read_text()
                    )
                    retry_scope = diagnostic["retry_scope"]
                    if (
                        retry_scope
                        == "consumer_only_from_bound_producer_snapshot"
                        and retrieval["producer_stage_present"]
                    ):
                        producer_remote_result = remote_attempt + "/result"
                else:
                    retry_scope = "retrieval_only"
            else:
                raise RuntimeError(f"owner_state_not_implemented:{state}")
        except subprocess.TimeoutExpired as error:
            classification = "absolute_operation_timeout"
            diagnostic_path = args.artifact_root / (
                f"OWNER_ERROR_g{repair_generation + 1}.json"
            )
            atomic_json(
                diagnostic_path,
                {
                    "at": utc_now(),
                    "error": repr(error),
                    "state": state,
                    "classification": classification,
                },
            )
            if remaining(deadline, 150) < 60:
                break
            retry_scope = (
                "retrieval_only"
                if state in {"invoke", "retrieve"} and remote_attempt is not None
                else "full_unconsumed_attempt"
            )
            if retry_scope == "retrieval_only":
                state = "retrieve"
        except Exception as error:
            diagnostic_path = args.artifact_root / (
                f"OWNER_ERROR_g{repair_generation + 1}.json"
            )
            atomic_json(
                diagnostic_path,
                {
                    "at": utc_now(),
                    "error": repr(error),
                    "state": state,
                    "classification": classification,
                },
            )
            retry_scope = (
                "retrieval_only"
                if state in {"invoke", "retrieve"} and remote_attempt is not None
                else "full_unconsumed_attempt"
            )
            if retry_scope == "retrieval_only":
                state = "retrieve"

        if retry_scope is None or diagnostic_path is None:
            continue
        repair_generation += 1
        repair_id = f"{safe_claim_id}-g{repair_generation}"
        request = repair_request(
            args.artifact_root,
            repair_id,
            diagnostic_path,
            retry_scope,
            deadline,
        )
        if request is None:
            classification = "absolute_repair_deadline"
            break
        if retry_scope == "retrieval_only":
            state = "retrieve"
            continue
        manifest = validate_patch_request(request)
        stage_packet(access, remote_root, manifest, deadline)
        if retry_scope == "full_unconsumed_attempt":
            mode = "full"
            state = "prepare"
        elif retry_scope == "consumer_only_from_bound_producer_snapshot":
            if producer_remote_result is None:
                diagnostic_path = args.artifact_root / (
                    f"OWNER_ERROR_g{repair_generation + 1}.json"
                )
                atomic_json(
                    diagnostic_path,
                    {
                        "at": utc_now(),
                        "error": "bound_producer_snapshot_not_available",
                    },
                )
                state = "retrieve"
            else:
                mode = "consumer-only"
                state = "invoke"
        else:
            diagnostic_path = args.artifact_root / (
                f"OWNER_ERROR_g{repair_generation + 1}.json"
            )
            atomic_json(
                diagnostic_path,
                {
                    "at": utc_now(),
                    "error": f"owner_retry_scope_not_implemented:{retry_scope}",
                },
            )
            state = "retrieve"

    if scientific_terminal is None and classification not in {
        "absolute_repair_deadline",
        "absolute_operation_timeout",
        "unsafe_or_unreachable_guest",
    }:
        classification = "absolute_lifecycle_deadline"

    remote_state = inspect_remote(access, remote_root)
    if scientific_terminal is not None:
        release = release_scientific(
            claim, args.artifact_root, scientific_terminal, remote_state
        )
    elif classification in {
        "absolute_repair_deadline",
        "absolute_lifecycle_deadline",
        "absolute_operation_timeout",
        "unsafe_or_unreachable_guest",
        "unknown_retained_boundary",
    }:
        release = release_terminal_boundary(
            claim, args.artifact_root, classification, remote_state
        )
    else:
        raise RuntimeError(f"nonterminal_release_refused:{classification}")
    stop.set()
    heartbeat_thread.join(timeout=5)
    write_owner_terminal(
        args.artifact_root,
        classification=classification,
        claim=claim,
        started=started,
        deadline=deadline,
        events=events,
        scientific_terminal=scientific_terminal,
        release=release,
        remote_state=remote_state,
    )
    return (
        0
        if scientific_terminal is not None
        and scientific_terminal.get("decision") == "positive"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
