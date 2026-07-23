from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
REPO = HERE.parents[6]
sys.path.insert(0, str(REPO / "research/factory/src"))
sys.path.insert(0, str(REPO / "research/sol/experiments/glm47flash/campaign_100/nebius"))

from grad_research.gpu_pool import GpuPool  # noqa: E402
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base  # noqa: E402


PROJECT = "gemma4_h200_local_kv_int4_endpoint"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
INSTANCE = "computeinstance-e00vhh6h29fj68x91g"
REMOTE = "/home/glmrunner/gemma4-local-kv-int4-20260723t1337z"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
RATE_USD_PER_HOUR = 2.46
ABSOLUTE_DEADLINE = dt.datetime(2026, 7, 23, 15, 20, tzinfo=dt.timezone.utc)
ARTIFACTS = HERE / "artifacts" / "local-int4-component-20260723t1337z"
INPUTS = (
    "int4_kv_kernels.py",
    "int4_component.py",
    "analyze_component.py",
    "remote_component.sh",
    "inputs/source/decode_attention.v0.5.13.py",
    "inputs/source/memory_pool.v0.5.13.py",
    "inputs/source/triton_backend.v0.5.13.py",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_event(event: str, **fields: Any) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    row = {"timestamp_utc": utc_now(), "event": event, **fields}
    with (ARTIFACTS / "OWNER_EVENTS.jsonl").open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    atomic_json(ARTIFACTS / "OWNER_STATE.json", row)


def remote(ip: str, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*ssh_base(ip, KEY), command],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def scp_to(ip: str, source: Path, destination: str) -> None:
    result = subprocess.run(
        [
            "scp",
            *ssh_base(ip, KEY)[1:-1],
            str(source),
            f"{SSH_USER}@{ip}:{destination}",
        ],
        text=True,
        capture_output=True,
        timeout=600,
    )
    if result.returncode:
        raise RuntimeError(f"scp_to_failed:{source}:{result.stderr[-1000:]}")


def scp_from(ip: str, source: str, destination: Path) -> bool:
    result = subprocess.run(
        [
            "scp",
            *ssh_base(ip, KEY)[1:-1],
            f"{SSH_USER}@{ip}:{source}",
            str(destination),
        ],
        text=True,
        capture_output=True,
        timeout=600,
    )
    return result.returncode == 0


def admitted_inputs() -> list[dict[str, Any]]:
    rows = []
    for name in INPUTS:
        path = HERE / name
        rows.append(
            {
                "path": path,
                "relative": name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return rows


def stage(ip: str, rows: list[dict[str, Any]]) -> None:
    directories = sorted(
        {str(Path(REMOTE) / "input" / Path(row["relative"]).parent) for row in rows}
    )
    result = remote(
        ip,
        "mkdir -p "
        + " ".join(shlex.quote(path) for path in [*directories, f"{REMOTE}/artifacts"]),
        60,
    )
    if result.returncode:
        raise RuntimeError(f"remote_root_failed:{result.stderr[-1000:]}")
    for row in rows:
        target = str(Path(REMOTE) / "input" / row["relative"])
        probe = remote(
            ip,
            f"test -f {shlex.quote(target)} && "
            f"test $(stat -c %s {shlex.quote(target)}) -eq {row['bytes']} && "
            f"test $(sha256sum {shlex.quote(target)} | cut -d' ' -f1) = {row['sha256']}",
            60,
        )
        if probe.returncode == 0:
            append_event("input_matched", path=row["relative"], sha256=row["sha256"])
            continue
        part = target + f".part.{os.getpid()}"
        scp_to(ip, row["path"], part)
        finish = remote(
            ip,
            f"test $(stat -c %s {shlex.quote(part)}) -eq {row['bytes']} && "
            f"test $(sha256sum {shlex.quote(part)} | cut -d' ' -f1) = {row['sha256']} && "
            f"chmod 0444 {shlex.quote(part)} && mv -f {shlex.quote(part)} {shlex.quote(target)}",
            60,
        )
        if finish.returncode:
            raise RuntimeError(f"remote_finalize_failed:{row['relative']}")
        append_event("input_finalized", path=row["relative"], sha256=row["sha256"])


class Heartbeat(threading.Thread):
    def __init__(self, pool: GpuPool):
        super().__init__(daemon=True)
        self.pool = pool
        self.stop_event = threading.Event()
        self.error: str | None = None

    def run(self) -> None:
        while not self.stop_event.wait(40):
            try:
                self.pool.heartbeat(PROJECT)
            except Exception as error:
                self.error = str(error)
                append_event("heartbeat_failure", error=self.error)

    def stop(self) -> None:
        self.stop_event.set()
        self.join(timeout=5)


def update_status(**updates: Any) -> None:
    path = HERE / "STATUS.json"
    value = json.loads(path.read_text())
    value.update(updates)
    atomic_json(path, value)


def retrieve(ip: str) -> dict[str, Any]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    for name in ("component-compact.tar.gz.sha256", "component-compact.tar.gz"):
        if not scp_from(ip, f"{REMOTE}/{name}", ARTIFACTS / name):
            raise RuntimeError(f"compact_retrieval_failed:{name}")
    expected = (ARTIFACTS / "component-compact.tar.gz.sha256").read_text().split()[0]
    observed = sha256(ARTIFACTS / "component-compact.tar.gz")
    if observed != expected:
        raise RuntimeError("compact_hash_mismatch")
    extracted = ARTIFACTS / "retrieved"
    extracted.mkdir(exist_ok=True)
    with tarfile.open(ARTIFACTS / "component-compact.tar.gz", "r:gz") as archive:
        archive.extractall(extracted, filter="data")
    remote_terminal = json.loads((extracted / "REMOTE_TERMINAL.json").read_text())
    append_event("compact_retrieved", sha256=observed, remote_terminal=remote_terminal)
    return remote_terminal


def claimed_cost() -> float:
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    bench = inventory["benches"][BENCH]
    claimed = dt.datetime.fromisoformat(
        bench["claim"]["claimed_at"].replace("Z", "+00:00")
    )
    elapsed = max(0.0, (dt.datetime.now(dt.timezone.utc) - claimed).total_seconds())
    return elapsed / 3600 * RATE_USD_PER_HOUR


def main() -> int:
    pool = GpuPool(LAB)
    bench = pool.claim(PROJECT, bench_id=BENCH)
    if bench["id"] != BENCH:
        raise RuntimeError("unexpected_bench")
    heartbeat = Heartbeat(pool)
    heartbeat.start()
    update_status(
        active_session={
            "kind": "bounded_claim_owner",
            "pid": os.getpid(),
            "unit": None,
            "unit_manager": "foreground_turn_owner",
            "deadline_utc": ABSOLUTE_DEADLINE.isoformat().replace("+00:00", "Z"),
            "artifact_root": str(ARTIFACTS),
            "remote_root": REMOTE,
            "bench_id": BENCH,
            "forward_progress": "resolving_bench_and_staging_immutable_inputs",
        }
    )
    released = False
    try:
        instance = get_instance(INSTANCE)
        ip = extract_public_ipv4(instance)
        if not ip:
            raise RuntimeError("bench_public_ip_unavailable")
        rows = admitted_inputs()
        stage(ip, rows)
        atomic_json(
            HERE / "GPU_INPUT_MANIFEST.json",
            {
                "schema_version": 1,
                "bench_id": BENCH,
                "remote_root": REMOTE,
                "inputs": [
                    {key: row[key] for key in ("relative", "bytes", "sha256")}
                    for row in rows
                ],
            },
        )
        update_status(
            active_session={
                **json.loads((HERE / "STATUS.json").read_text())["active_session"],
                "forward_progress": "first_exact_component_invocation_running",
            }
        )
        command = (
            f"INT4_REMOTE_ROOT={shlex.quote(REMOTE)} "
            f"bash {shlex.quote(REMOTE + '/input/remote_component.sh')}"
        )
        started = time.time()
        result = remote(
            ip,
            command,
            max(60, int((ABSOLUTE_DEADLINE - dt.datetime.now(dt.timezone.utc)).total_seconds())),
        )
        (ARTIFACTS / "remote.stdout").write_text(result.stdout)
        (ARTIFACTS / "remote.stderr").write_text(result.stderr)
        append_event(
            "remote_worker_returned",
            exit_code=result.returncode,
            elapsed_seconds=time.time() - started,
        )
        terminal = retrieve(ip)
        component_path = ARTIFACTS / "retrieved/COMPONENT_TERMINAL.json"
        if component_path.is_file():
            component = json.loads(component_path.read_text())
            cost = claimed_cost()
            if component.get("component_pass"):
                atomic_json(
                    ARTIFACTS / "ENDPOINT_READY.json",
                    {
                        "reason": "component_gates_passed",
                        "deadline_utc": ABSOLUTE_DEADLINE.isoformat().replace("+00:00", "Z"),
                        "component_terminal": component,
                    },
                )
                update_status(
                    actual_spend_usd=cost,
                    active_session={
                        **json.loads((HERE / "STATUS.json").read_text())["active_session"],
                        "forward_progress": "component_passed_conditional_c32_pair_required",
                    },
                    next_action="Run exactly one conditional c32 control/candidate pair under this retained owner.",
                )
                return 3
            contents = {
                "project": PROJECT,
                "local_int4_result": component["decision"],
                "local_int4_actual_spend_usd": cost,
                "local_int4_artifacts": str(ARTIFACTS.relative_to(REPO)),
                "server_state": "Healthy retained baseline discriminator server left unchanged",
                "caches": "Pinned image, checkpoint, FP8/QKV stack, and Triton caches retained",
            }
            pool.release(PROJECT, contents=contents, condition="ready")
            released = True
            update_status(
                status="complete",
                actual_spend_usd=cost,
                active_session=None,
                summary="Exact group-64 signed-INT4 producer and actual paged Triton consumer reached a component gate terminal; c32 was not admissible.",
                next_action="Director should use COMPONENT_TERMINAL.json to close this fixed INT4 mechanism and schedule the next distinct project.",
            )
            return 0
        repair = {
            "schema_version": 1,
            "diagnostic": terminal,
            "remote_stdout": str(ARTIFACTS / "remote.stdout"),
            "remote_stderr": str(ARTIFACTS / "remote.stderr"),
            "deadline_utc": ABSOLUTE_DEADLINE.isoformat().replace("+00:00", "Z"),
        }
        atomic_json(ARTIFACTS / "REPAIR_READY.json", repair)
        update_status(
            actual_spend_usd=claimed_cost(),
            active_session={
                **json.loads((HERE / "STATUS.json").read_text())["active_session"],
                "forward_progress": "repair_ready_claim_retained",
                "repair_ready": str(ARTIFACTS / "REPAIR_READY.json"),
            },
        )
        while dt.datetime.now(dt.timezone.utc) < ABSOLUTE_DEADLINE:
            if (ARTIFACTS / "REPAIR_REQUEST.json").is_file():
                append_event("repair_request_observed")
                return 4
            time.sleep(10)
        return 5
    finally:
        heartbeat.stop()
        if not released and dt.datetime.now(dt.timezone.utc) >= ABSOLUTE_DEADLINE:
            try:
                pool.release(
                    PROJECT,
                    contents={
                        "project": PROJECT,
                        "local_int4_result": "director_disposition_required_at_absolute_deadline",
                        "local_int4_artifacts": str(ARTIFACTS.relative_to(REPO)),
                    },
                    condition="maintenance",
                )
                update_status(
                    actual_spend_usd=claimed_cost(),
                    active_session=None,
                    status="blocked",
                    summary="Absolute project deadline reached with a retained diagnostic requiring director disposition.",
                )
            except Exception as error:
                append_event("deadline_release_failure", error=str(error))


if __name__ == "__main__":
    raise SystemExit(main())
