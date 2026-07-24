#!/usr/bin/env python3
"""Bounded owner for the exact KV4 L40S component.

The owner waits behind priority-6200, atomically claims only the admitted
bench, retains the claim through staging/run/retrieval/counter repair, and
releases only after durable evidence or a typed boundary.
"""

from __future__ import annotations

import argparse
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


NAME = "gemma4_l40s_qserve_kv4_attention_component"
PREDECESSOR = "gemma4_l40s_qserve_w4a8_mlp_component"
BENCH = "l40s-qserve-e00a74kcbps8v00fk4"
LAB = pathlib.Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
PACKET_NAME = "KV4_TRITON_POINTER_REPAIR_PACKET.tar.gz"
MANIFEST_NAME = "KV4_TRITON_POINTER_REPAIR_INPUT_MANIFEST.json"
PACKET_SHA256 = "45472047380028df34f8d702c3101dab326154bdfb919bfb835c12ff7761de8f"
MANIFEST_SHA256 = "c52ba4019a47c7713124e2bc10b95104cf6fd9df37f50f0219eb966b9f38a2f8"
RATE = 0.8629833
AUTHORIZED_USD = 4.0
PRIOR_SPEND_USD = 0.006726643004733981
REMOTE_ROOT = "/home/glmrunner/gemma4-kv4-attention"


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, **kwargs)


def pool(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *arguments],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
        capture_output=True,
        check=check,
    )


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def inventory_bench() -> dict:
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    return benches[BENCH] if isinstance(benches, dict) else next(x for x in benches if x["id"] == BENCH)


def predecessor_released() -> bool:
    status = json.loads((LAB / "projects" / PREDECESSOR / "STATUS.json").read_text())
    bench = inventory_bench()
    return status.get("status") != "active" and bench.get("claim") is None and bench.get("status") == "available"


def scp_from(ip: str, remote: str, local: pathlib.Path, timeout: int = 300):
    return run(
        [
            "scp", "-i", str(KEY), "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
            f"glmrunner@{ip}:{remote}", str(local),
        ],
        capture_output=True, timeout=timeout,
    )


def scp_to(ip: str, local: pathlib.Path, remote: str, timeout: int = 300):
    return run(
        [
            "scp", "-i", str(KEY), "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
            str(local), f"glmrunner@{ip}:{remote}",
        ],
        capture_output=True, timeout=timeout,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--deadline-epoch", type=int, required=True)
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    events = root / "outer-events.jsonl"

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(json.dumps({"epoch": time.time(), "event": event, **fields}, sort_keys=True) + "\n")
            handle.flush()

    packet = PROJECT / PACKET_NAME
    manifest = PROJECT / MANIFEST_NAME
    if sha256(packet) != PACKET_SHA256 or sha256(manifest) != MANIFEST_SHA256:
        raise RuntimeError("project_local_immutable_identity_mismatch")
    with tarfile.open(packet, "r:gz") as archive:
        if MANIFEST_NAME not in archive.getnames():
            raise RuntimeError("project_local_packet_missing_manifest")

    deadline = min(
        args.deadline_epoch,
        int(time.time()) + int((AUTHORIZED_USD - PRIOR_SPEND_USD) * 3600 / RATE),
    )
    if deadline <= time.time() + 900:
        raise RuntimeError("typed_budget_boundary:insufficient_window")
    emit("queue_wait_started", predecessor=PREDECESSOR, deadline_epoch=deadline)
    while time.time() < deadline - 900 and not predecessor_released():
        time.sleep(30)
    if not predecessor_released():
        atomic(root / "QUEUE_BLOCKER.json", {
            "classification": "typed_external_queue_blocker",
            "required_bench": BENCH,
            "predecessor": PREDECESSOR,
            "deadline_epoch": deadline,
            "observed_bench": inventory_bench(),
        })
        emit("queue_deadline_without_release")
        return 76

    bench = inventory_bench()
    if bench["accelerator"] != "nvidia-l40s" or float(bench["hourly_cost_usd"]) != RATE:
        raise RuntimeError("typed_pool_boundary:bench_identity_changed")
    claimed = False
    stop = threading.Event()
    release_condition: str | None = None
    release_contents: dict[str, object] = {}
    claim_started = 0.0

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-1000:])

    thread = threading.Thread(target=heartbeat, daemon=True)
    try:
        lease = max(900, deadline - int(time.time()))
        result = pool("claim", "--project", NAME, "--bench", BENCH, "--lease-seconds", str(lease))
        claimed = True
        claim_started = time.time()
        emit("claimed", result=json.loads(result.stdout), lease_seconds=lease)
        thread.start()

        sys.path.insert(0, str(NEBIUS))
        from placement_control import extract_public_ipv4, get_instance
        from stock_control import run_ssh

        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip:
            raise RuntimeError("typed_provider_boundary:no_public_ip")
        identity = run_ssh(
            ip, KEY,
            "hostname; nvidia-smi --query-gpu=name,uuid,memory.total --format=csv,noheader; "
            "nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader; "
            "sudo docker image inspect " + shlex.quote(IMAGE) + " >/dev/null && printf image_present",
            timeout=90,
        )
        (root / "remote-identity.stdout").write_text(identity.stdout)
        (root / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_remote_boundary:identity_or_image_failed")
        identity_lines = identity.stdout.splitlines()
        compute_lines = [line for line in identity_lines if "MiB" in line and "NVIDIA L40S" not in line]
        if compute_lines:
            raise RuntimeError("typed_resident_state_boundary:predecessor_compute_process_remains")

        remote_packet = f"{REMOTE_ROOT}/packets/{PACKET_SHA256}.tar.gz"
        remote_part = remote_packet + ".part"
        remote_run = f"{REMOTE_ROOT}/runs/{PACKET_SHA256}"
        remote_output = f"{REMOTE_ROOT}/outputs/{root.name}"
        prepare = run_ssh(
            ip, KEY,
            "mkdir -p " + " ".join(shlex.quote(x) for x in (
                f"{REMOTE_ROOT}/packets", f"{REMOTE_ROOT}/runs", remote_output
            )),
            timeout=60,
        )
        if prepare.returncode:
            raise RuntimeError("typed_remote_boundary:prepare_failed")
        resident_output = f"{REMOTE_ROOT}/outputs/kv4-l40s-pointer-repair-20260724t0710z"
        resident_terminal = run_ssh(
            ip, KEY,
            f"test -f {shlex.quote(resident_output + '/COMPONENT_TERMINAL.json')}",
            timeout=60,
        )
        if resident_terminal.returncode == 0:
            resident_pack = run_ssh(
                ip, KEY,
                f"cd {shlex.quote(resident_output)} && rm -f resident-compact.tar.gz.part "
                "&& files=\"$(find . -maxdepth 1 -type f ! -name 'resident-compact.tar.gz' "
                "! -name 'resident-compact.tar.gz.part' -printf '%f ')\" && test -n \"$files\" "
                "&& tar -czf resident-compact.tar.gz.part $files "
                "&& mv resident-compact.tar.gz.part resident-compact.tar.gz",
                timeout=90,
            )
            if resident_pack.returncode:
                raise RuntimeError("typed_retrieval_boundary:resident_compact_pack_failed")
            resident_copy = scp_from(ip, f"{resident_output}/resident-compact.tar.gz", root / "resident-compact.tar.gz")
            if resident_copy.returncode:
                raise RuntimeError("typed_retrieval_boundary:resident_compact_scp_failed")
            with tarfile.open(root / "resident-compact.tar.gz", "r:gz") as archive:
                archive.extractall(root / "resident-retrieved", filter="data")
            terminal_path = root / "resident-retrieved/COMPONENT_TERMINAL.json"
            state_path = root / "resident-retrieved/INVOCATION_STATE.json"
            terminal = json.loads(terminal_path.read_text())
            state = json.loads(state_path.read_text()) if state_path.is_file() else None
            emit("resident_terminal_retrieved", classification=terminal.get("classification"), invocation=state)
            # A persisted decision-bearing terminal closes the component arm.
            # Counters below consume the same resident packet/output only when it passed.
            if terminal.get("classification") != "component_positive":
                release_condition = "ready"
                release_contents = {
                    "project": NAME,
                    "classification": terminal.get("classification"),
                    "artifacts": str(root.relative_to(PROJECT)),
                    "scientific_terminal": str(terminal_path.relative_to(PROJECT)),
                    "result": "Resident KV4 component terminal consumed; no replay or counters after a non-passing component.",
                    "server_state": "No component container remains; resident immutable packet and outputs retained.",
                }
                return 0
            remote_output = resident_output
            remote_packet = f"{REMOTE_ROOT}/packets/{PACKET_SHA256}.tar.gz"
            remote_run = f"{REMOTE_ROOT}/runs/{PACKET_SHA256}"
            metrics = ",".join((
                "dram__bytes_read.sum", "lts__t_sectors_op_read.sum",
                "sm__warps_active.avg.pct_of_peak_sustained_active",
                "launch__registers_per_thread", "smsp__sass_inst_executed_op_local_ld.sum",
                "smsp__sass_inst_executed_op_local_st.sum", "smsp__inst_executed_op_barrier.sum",
            ))
            for geometry in ("local", "global"):
                for target in ("control", "candidate"):
                    label = f"{geometry}-{target}"
                    profile = (
                        f"sudo docker run --rm --gpus all --ipc=host --cap-add SYS_ADMIN "
                        f"-v {shlex.quote(remote_run)}:/packet:ro -v {shlex.quote(remote_output)}:/output "
                        f"{shlex.quote(IMAGE)} bash -lc "
                        + shlex.quote(
                            f"export PYTHONPATH=/packet/inputs/exact_gemma_kv4; "
                            f"ncu --target-processes all --metrics {metrics} --csv --page raw "
                            f"python3 /packet/inputs/exact_gemma_kv4/kv4_component.py "
                            f"--artifact-root /output/profile-{label} --profile-only "
                            f"--geometry {geometry} --target {target} "
                            f">/output/profile-{label}.csv 2>/output/profile-{label}.stderr"
                        )
                    )
                    counter = run_ssh(ip, KEY, profile, timeout=max(300, deadline - int(time.time()) - 180))
                    emit("resident_counter_finished", label=label, returncode=counter.returncode)
                    if counter.returncode:
                        raise RuntimeError(f"typed_counter_boundary:ncu_failed:{label}")
            packed = run_ssh(
                ip, KEY,
                f"sudo tar -czf {shlex.quote(remote_output + '/retrieval.tar.gz')} "
                f"-C {shlex.quote(remote_output)} --exclude=retrieval.tar.gz . && "
                f"sudo chown glmrunner:glmrunner {shlex.quote(remote_output + '/retrieval.tar.gz')}",
                timeout=180,
            )
            if packed.returncode:
                raise RuntimeError("typed_retrieval_boundary:resident_bulk_pack_failed")
            bulk = scp_from(ip, f"{remote_output}/retrieval.tar.gz", root / "resident-remote-output.tar.gz")
            if bulk.returncode:
                raise RuntimeError("typed_retrieval_boundary:resident_bulk_scp_failed")
            release_condition = "ready"
            release_contents = {
                "project": NAME,
                "classification": terminal["classification"],
                "artifacts": str(root.relative_to(PROJECT)),
                "scientific_terminal": str(terminal_path.relative_to(PROJECT)),
                "candidate_cuda_started": bool(state and state.get("candidate_cuda_invocation_started")),
                "scientific_invocation_started": bool(state and state.get("candidate_scientific_invocation_started")),
                "result": "Resident exact D256-local/D512-global KV4 component terminal consumed and fixed counters completed.",
                "server_state": "No component container remains; immutable KV4 packet and Triton caches remain on disk.",
            }
            return 0
        matched = run_ssh(
            ip, KEY,
            f"test -f {shlex.quote(remote_packet)} && "
            f"test \"$(sha256sum {shlex.quote(remote_packet)} | awk '{{print $1}}')\" = {PACKET_SHA256}",
            timeout=60,
        )
        if matched.returncode:
            copied = scp_to(ip, packet, remote_part)
            (root / "packet-transfer.stderr").write_text(copied.stderr)
            if copied.returncode:
                raise RuntimeError("typed_transfer_boundary:packet_scp_failed")
            finalized = run_ssh(
                ip, KEY,
                f"test \"$(sha256sum {shlex.quote(remote_part)} | awk '{{print $1}}')\" = {PACKET_SHA256} "
                f"&& chmod 0444 {shlex.quote(remote_part)} && mv {shlex.quote(remote_part)} {shlex.quote(remote_packet)}",
                timeout=60,
            )
            if finalized.returncode:
                raise RuntimeError("typed_transfer_boundary:packet_finalize_failed")
        extracted = run_ssh(
            ip, KEY,
            f"if test -f {shlex.quote(remote_run + '/.PACKET_SHA256')} && "
            f"test \"$(cat {shlex.quote(remote_run + '/.PACKET_SHA256')})\" = {PACKET_SHA256}; then true; "
            f"else rm -rf {shlex.quote(remote_run + '.part')} && mkdir -p {shlex.quote(remote_run + '.part')} "
            f"&& tar -xzf {shlex.quote(remote_packet)} -C {shlex.quote(remote_run + '.part')} "
            f"&& printf %s {PACKET_SHA256} > {shlex.quote(remote_run + '.part/.PACKET_SHA256')} "
            f"&& mv {shlex.quote(remote_run + '.part')} {shlex.quote(remote_run)}; fi",
            timeout=120,
        )
        if extracted.returncode:
            raise RuntimeError("typed_transfer_boundary:packet_extract_failed")
        emit("immutable_packet_staged", packet_sha256=PACKET_SHA256, manifest_sha256=MANIFEST_SHA256)

        remote_command = (
            f"printf %s {int(time.time())} > {shlex.quote(remote_output + '/REMOTE_INVOCATION_INTENT.txt')}; "
            f"sudo docker run --rm --gpus all --ipc=host --network host "
            f"-v {shlex.quote(remote_run)}:/packet:ro -v {shlex.quote(remote_output)}:/output "
            f"{shlex.quote(IMAGE)} bash /packet/inputs/exact_gemma_kv4/run_component.sh "
            f"/packet /output >{shlex.quote(remote_output + '/worker.stdout')} "
            f"2>{shlex.quote(remote_output + '/worker.stderr')}"
        )
        emit("component_worker_started")
        worker = run_ssh(ip, KEY, remote_command, timeout=max(600, deadline - int(time.time()) - 420))
        atomic(root / "worker-ssh.json", {
            "returncode": worker.returncode, "stdout": worker.stdout[-4000:], "stderr": worker.stderr[-4000:]
        })

        # Retrieve the compact decision evidence before any optional bulk archive.
        compact = run_ssh(
            ip, KEY,
            f"cd {shlex.quote(remote_output)} && "
            "rm -f compact.tar.gz.part && "
            "files=\"$(find . -maxdepth 1 -type f "
            "! -name 'compact.tar.gz' ! -name 'compact.tar.gz.part' -printf '%f ')\" && "
            "test -n \"$files\" && "
            "tar -czf compact.tar.gz.part $files && "
            "mv compact.tar.gz.part compact.tar.gz",
            timeout=90,
        )
        if compact.returncode:
            raise RuntimeError("typed_retrieval_boundary:compact_pack_failed")
        retrieved = scp_from(ip, f"{remote_output}/compact.tar.gz", root / "compact.tar.gz")
        if retrieved.returncode:
            raise RuntimeError("typed_retrieval_boundary:compact_scp_failed")
        with tarfile.open(root / "compact.tar.gz", "r:gz") as archive:
            archive.extractall(root / "retrieved", filter="data")
        terminal_path = root / "retrieved/COMPONENT_TERMINAL.json"
        state_path = root / "retrieved/INVOCATION_STATE.json"
        terminal = json.loads(terminal_path.read_text()) if terminal_path.is_file() else None
        state = json.loads(state_path.read_text()) if state_path.is_file() else None
        emit("compact_retrieved", worker_returncode=worker.returncode,
             classification=terminal.get("classification") if terminal else None, invocation=state)

        if terminal is None:
            if state and not state.get("producer_completed") and not state.get("scientific_terminal_recorded"):
                atomic(root / "REPAIR_READY.json", {
                    "classification": "recoverable_pre_science_integration_failure",
                    "diagnostic": json.loads((root / "retrieved/ERROR_TERMINAL.json").read_text())
                    if (root / "retrieved/ERROR_TERMINAL.json").is_file() else {"worker_returncode": worker.returncode},
                    "absolute_repair_deadline_epoch": deadline,
                    "bench": BENCH,
                })
                emit("repair_ready")
                while time.time() < deadline - 300 and not (root / "REPAIR_REQUEST.json").is_file():
                    time.sleep(10)
                raise RuntimeError("typed_repair_boundary:repair_not_applied_by_deadline")
            raise RuntimeError("typed_scientific_boundary:invocation_without_terminal")

        # Minimum fixed counter packet. The report files remain remote and the
        # raw CSV is retrieved with the final archive.
        metrics = ",".join((
            "dram__bytes_read.sum",
            "lts__t_sectors_op_read.sum",
            "sm__warps_active.avg.pct_of_peak_sustained_active",
            "launch__registers_per_thread",
            "smsp__sass_inst_executed_op_local_ld.sum",
            "smsp__sass_inst_executed_op_local_st.sum",
            "smsp__inst_executed_op_barrier.sum",
        ))
        for geometry in ("local", "global"):
            for target in ("control", "candidate"):
                label = f"{geometry}-{target}"
                profile = (
                    f"sudo docker run --rm --gpus all --ipc=host --cap-add SYS_ADMIN "
                    f"-v {shlex.quote(remote_run)}:/packet:ro -v {shlex.quote(remote_output)}:/output "
                    f"{shlex.quote(IMAGE)} bash -lc "
                    + shlex.quote(
                        f"export PYTHONPATH=/packet/inputs/exact_gemma_kv4; "
                        f"ncu --target-processes all --metrics {metrics} --csv --page raw "
                        f"python3 /packet/inputs/exact_gemma_kv4/kv4_component.py "
                        f"--artifact-root /output/profile-{label} --profile-only "
                        f"--geometry {geometry} --target {target} "
                        f">/output/profile-{label}.csv 2>/output/profile-{label}.stderr"
                    )
                )
                counter = run_ssh(ip, KEY, profile, timeout=max(300, deadline - int(time.time()) - 180))
                emit("counter_finished", label=label, returncode=counter.returncode)
                if counter.returncode:
                    raise RuntimeError(f"typed_counter_boundary:ncu_failed:{label}")

        packed = run_ssh(
            ip, KEY,
            f"sudo tar -czf {shlex.quote(remote_output + '/retrieval.tar.gz')} "
            f"-C {shlex.quote(remote_output)} --exclude=retrieval.tar.gz . && "
            f"sudo chown glmrunner:glmrunner {shlex.quote(remote_output + '/retrieval.tar.gz')}",
            timeout=180,
        )
        if packed.returncode:
            raise RuntimeError("typed_retrieval_boundary:remote_pack_failed")
        bulk = scp_from(ip, f"{remote_output}/retrieval.tar.gz", root / "remote-output.tar.gz")
        if bulk.returncode:
            raise RuntimeError("typed_retrieval_boundary:bulk_scp_failed")
        release_condition = "ready"
        release_contents = {
            "project": NAME,
            "classification": terminal["classification"],
            "artifacts": str(root.relative_to(PROJECT)),
            "scientific_terminal": str(root.relative_to(PROJECT) / pathlib.Path("retrieved/COMPONENT_TERMINAL.json")),
            "candidate_cuda_started": bool(state and state.get("candidate_cuda_invocation_started")),
            "scientific_invocation_started": bool(state and state.get("candidate_scientific_invocation_started")),
            "result": "Exact D256-local/D512-global progressive-KV4 component and fixed minimum counters completed.",
            "server_state": "No component container remains; immutable KV4 packet and Triton caches remain on disk.",
        }
    except Exception as error:
        emit("outer_exception", type=type(error).__name__, message=str(error))
        if claimed and release_condition is None:
            release_condition = "maintenance"
            release_contents = {
                "project": NAME,
                "classification": "typed_outer_or_counter_boundary",
                "diagnostic": f"{type(error).__name__}:{error}",
                "artifacts": str(root.relative_to(PROJECT)),
                "server_state": "Compact evidence retrieved when available; director disposition required.",
            }
    finally:
        stop.set()
        if thread.is_alive():
            thread.join(timeout=5)
        exposure_seconds = max(0.0, time.time() - claim_started) if claimed else 0.0
        exposure = exposure_seconds * RATE / 3600
        atomic(root / "COST.json", {
            "schema_version": 1,
            "prior_spend_usd": PRIOR_SPEND_USD,
            "claim_exposure_seconds": exposure_seconds,
            "claim_exposure_usd": exposure,
            "cumulative_spend_usd": PRIOR_SPEND_USD + exposure,
            "rate_usd_per_hour": RATE,
        })
        if claimed and release_condition:
            contents = root / "FINAL_BENCH_CONTENTS.json"
            atomic(contents, release_contents)
            pool("update", "--project", NAME, "--contents", str(contents), check=False)
            released = pool(
                "release", "--project", NAME, "--condition", release_condition,
                "--contents", str(contents), check=False,
            )
            emit("released", condition=release_condition, returncode=released.returncode,
                 stdout=released.stdout[-2000:], stderr=released.stderr[-2000:])
    return 0 if release_condition == "ready" else 75


if __name__ == "__main__":
    raise SystemExit(main())
