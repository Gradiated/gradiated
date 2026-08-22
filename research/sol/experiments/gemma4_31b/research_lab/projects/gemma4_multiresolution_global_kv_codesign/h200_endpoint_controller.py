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
ARTIFACT = pathlib.Path(os.environ["H200_ARTIFACT_ROOT"])
DEADLINE = dt.datetime.fromisoformat(os.environ["H200_RELEASE_BY_UTC"].replace("Z", "+00:00"))
NAME = "gemma4_multiresolution_global_kv_codesign"
BENCH = "h200-global-kv-computeinstance-e00f01gpfve0e49wb3"
FACTORY = "/root/workspace/research/factory/src"
REMOTE = "/home/glmrunner/gemma4-multiresolution-global-kv"
MANIFEST = PROJECT / "inputs" / "CHECKPOINT_MANIFEST.json"
CHECKPOINT = PROJECT / "inputs" / "checkpoint"
FILES = [
    PROJECT / "inputs" / "exact_runner.py",
    PROJECT / "global_kv_sglang_hook.py",
    PROJECT / "sitecustomize.py",
    PROJECT / "h200_endpoint_pair.py",
]
SCOPE = os.environ.get("H200_ENTRY_SCOPE", "endpoint_only")


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(16 << 20), b""):
            value.update(block)
    return value.hexdigest()


def command(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout)


def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return command(
        ["env", f"PYTHONPATH={FACTORY}", "python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args],
        120,
    )


def main() -> int:
    component = pathlib.Path(os.environ["H200_ADOPT_COMPONENT_RESULT"])
    if digest(component) != "c4374f2b6e24a5d20438fd39548c00a307ac7d98d859a66fa7171f8a2211407d":
        raise RuntimeError("adopted_component_digest_mismatch")
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    raw_benches = inventory["benches"]
    benches = list(raw_benches.values()) if isinstance(raw_benches, dict) else raw_benches
    bench = next(row for row in benches if row["id"] == BENCH)
    if (bench.get("claim") or {}).get("project") != NAME:
        raise RuntimeError("continuous_claim_missing")
    resource = bench["resource"]
    ssh = [
        "ssh", "-i", resource["identity_file"], "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={resource['known_hosts_namespace']}",
        f"{resource['ssh_user']}@{resource['public_ipv4']}",
    ]
    scp = [
        "scp", "-p", "-i", resource["identity_file"], "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={resource['known_hosts_namespace']}",
    ]
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(45):
            pool("heartbeat", "--project", NAME)

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        adopted = {"artifact": str(component), "sha256": digest(component), "adopted_without_replay": True}
        atomic(ARTIFACT / "ENDPOINT_COMPONENT_ADOPTION.json", adopted)
        if SCOPE not in {"endpoint_only", "endpoint_repair2", "endpoint_activation_repair3", "endpoint_activation_repair4"}:
            raise RuntimeError(f"unsupported_entry_scope:{SCOPE}")
        archive = pathlib.Path(os.environ.get("H200_ADOPT_ENDPOINT_ARCHIVE", ARTIFACT / "endpoint-compact.tar.gz"))
        if SCOPE == "endpoint_repair2" and digest(archive) != "94d553d3080834a64cb997f22ff7989e5332f775737386089ede317cd083c325":
            raise RuntimeError("adopted_endpoint_archive_digest_mismatch")
        remote_out = f"{REMOTE}/endpoint-artifacts-repair4" if SCOPE == "endpoint_activation_repair4" else (f"{REMOTE}/endpoint-artifacts-repair3" if SCOPE == "endpoint_activation_repair3" else f"{REMOTE}/endpoint-artifacts")
        prepare = command([*ssh, f"install -d {REMOTE}/endpoint-input {shlex.quote(remote_out)}"], 60)
        if prepare.returncode:
            raise RuntimeError("remote_endpoint_roots_failed")
        if SCOPE in {"endpoint_activation_repair3", "endpoint_activation_repair4"}:
            stock = ARTIFACT / "endpoint-retrieved" / "endpoint-artifacts" / "STOCK_TERMINAL.json"
            if digest(stock) != "90e389320a2faf0730d9a4916de3a12df1c593c141bb2f8382810914852ec3bc":
                raise RuntimeError("preserved_stock_terminal_digest_mismatch")
            copied_stock = command([*scp, str(stock), f"{resource['ssh_user']}@{resource['public_ipv4']}:{remote_out}/STOCK_TERMINAL.json.part"], 120)
            finalized_stock = command([*ssh, f"test $(sha256sum {shlex.quote(remote_out + '/STOCK_TERMINAL.json.part')} | cut -d' ' -f1) = 90e389320a2faf0730d9a4916de3a12df1c593c141bb2f8382810914852ec3bc && mv {shlex.quote(remote_out + '/STOCK_TERMINAL.json.part')} {shlex.quote(remote_out + '/STOCK_TERMINAL.json')}"], 120)
            if copied_stock.returncode or finalized_stock.returncode:
                raise RuntimeError("preserved_stock_terminal_stage_failed")
        manifest = json.loads(MANIFEST.read_text())
        staged = []
        for row in ([] if SCOPE in {"endpoint_repair2", "endpoint_activation_repair3", "endpoint_activation_repair4"} else manifest["files"]):
            source = CHECKPOINT / row["name"]
            target = f"{REMOTE}/checkpoint/{row['name']}"
            check = command([*ssh, f"test -f {shlex.quote(target)} && test $(stat -c %s {shlex.quote(target)}) = {row['bytes']} && test $(sha256sum {shlex.quote(target)} | cut -d' ' -f1) = {row['sha256']}"], 1800)
            reused = check.returncode == 0
            if not reused:
                partial = f"{target}.{row['sha256']}.part"
                transfer = command([*scp, str(source), f"{resource['ssh_user']}@{resource['public_ipv4']}:{partial}"], min(3600, max(300, int(row["bytes"]) // 15_000_000 + 180)))
                if transfer.returncode:
                    (ARTIFACT / f"{row['name']}.scp.stderr").write_text(transfer.stderr)
                    raise RuntimeError(f"checkpoint_transfer_failed:{row['name']}")
                finalize = command([*ssh, f"test $(stat -c %s {shlex.quote(partial)}) = {row['bytes']} && test $(sha256sum {shlex.quote(partial)} | cut -d' ' -f1) = {row['sha256']} && chmod 0444 {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {shlex.quote(target)}"], 1800)
                if finalize.returncode:
                    raise RuntimeError(f"checkpoint_finalize_failed:{row['name']}")
            staged.append({**row, "reused": reused, "remote": target})
            atomic(ARTIFACT / "ENDPOINT_STAGING_PROGRESS.json", {"files": staged})
        for source in FILES:
            target = f"{REMOTE}/endpoint-input/{source.name}"
            partial = f"{target}.{digest(source)}.part"
            check = command([*ssh, f"test -f {target} && test $(sha256sum {target} | cut -d' ' -f1) = {digest(source)}"], 120)
            if check.returncode:
                transfer = command([*scp, str(source), f"{resource['ssh_user']}@{resource['public_ipv4']}:{partial}"], 300)
                if transfer.returncode:
                    raise RuntimeError(f"code_transfer_failed:{source.name}")
                finalize = command([*ssh, f"test $(sha256sum {partial} | cut -d' ' -f1) = {digest(source)} && chmod 0444 {partial} && mv -f {partial} {target}"], 120)
                if finalize.returncode:
                    raise RuntimeError(f"code_finalize_failed:{source.name}")
        atomic(ARTIFACT / "ENDPOINT_STAGING_TERMINAL.json", {"checkpoint_manifest_sha256": digest(MANIFEST), "checkpoint_total_bytes": manifest["total_bytes"], "files": staged, "scope": SCOPE})
        remaining = int((DEADLINE - dt.datetime.now(dt.timezone.utc)).total_seconds()) - 120
        if remaining <= 0:
            raise RuntimeError("endpoint_deadline_exhausted_before_candidate")
        remote = command([*ssh, f"cd {REMOTE} && H200_ENTRY_SCOPE={shlex.quote(SCOPE)} GLOBAL_KV_OUTPUT_ROOT={shlex.quote(remote_out)} python3 endpoint-input/h200_endpoint_pair.py"], remaining)
        (ARTIFACT / "endpoint-worker.stdout").write_text(remote.stdout)
        (ARTIFACT / "endpoint-worker.stderr").write_text(remote.stderr)
        bundle_name = pathlib.PurePosixPath(remote_out).name
        bundle_remote = f"{REMOTE}/endpoint-repair4-compact.tar.gz" if SCOPE == "endpoint_activation_repair4" else (f"{REMOTE}/endpoint-repair3-compact.tar.gz" if SCOPE == "endpoint_activation_repair3" else f"{REMOTE}/endpoint-compact.tar.gz")
        pack = command([*ssh, f"cd {REMOTE} && tar -czf {shlex.quote(pathlib.PurePosixPath(bundle_remote).name + '.part')} {shlex.quote(bundle_name)} && mv {shlex.quote(pathlib.PurePosixPath(bundle_remote).name + '.part')} {shlex.quote(pathlib.PurePosixPath(bundle_remote).name)} && sha256sum {shlex.quote(pathlib.PurePosixPath(bundle_remote).name)}"], 900)
        if pack.returncode:
            raise RuntimeError("endpoint_retrieval_pack_failed")
        archive_name = "endpoint-repair4-compact.tar.gz" if SCOPE == "endpoint_activation_repair4" else ("endpoint-repair3-compact.tar.gz" if SCOPE == "endpoint_activation_repair3" else "endpoint-compact.tar.gz")
        partial = ARTIFACT / f".{archive_name}.part"
        copied = command([*scp, f"{resource['ssh_user']}@{resource['public_ipv4']}:{bundle_remote}", str(partial)], 1800)
        if copied.returncode or digest(partial) != pack.stdout.split()[0]:
            raise RuntimeError("endpoint_retrieval_copy_or_hash_failed")
        archive = ARTIFACT / archive_name
        partial.replace(archive)
        retrieved = ARTIFACT / "endpoint-retrieved"
        retrieved.mkdir(exist_ok=True)
        with tarfile.open(archive) as bundle:
            bundle.extractall(retrieved, filter="data")
        terminal = retrieved / bundle_name / "ENDPOINT_PAIR_TERMINAL.json"
        if remote.returncode or not terminal.is_file():
            raise RuntimeError(f"endpoint_worker_failed:{remote.returncode}")
        result = json.loads(terminal.read_text())
        if result.get("classification") != "scientific_terminal":
            raise RuntimeError("endpoint_terminal_invalid")
        atomic(ARTIFACT / "ENDPOINT_PAIR_TERMINAL.json", result)
        pool("update", "--project", NAME, "--contents", json.dumps({
            "schema_version": 1, "project": NAME,
            "checkpoint": f"Verified {manifest['total_bytes']}-byte Gemma 4 checkpoint at {REMOTE}/checkpoint",
            "image": "Pinned SGLang image resident", "server_state": "No server; endpoint pair complete",
            "artifacts": "Endpoint pair terminal retrieved", "state": "ready",
        }))
        released = pool("release", "--project", NAME, "--condition", "maintenance")
        if released.returncode:
            raise RuntimeError("pool_release_failed")
        return 0
    except Exception as exc:
        atomic(ARTIFACT / "REPAIR_READY_ENDPOINT2.json", {
            "schema_version": 1, "repair_id": "h200-global-kv-endpoint-repair-2",
            "predecessor_repair_id": "h200-global-kv-repair-1",
            "classification": "recoverable_endpoint_integration_defect",
            "diagnostic": f"{type(exc).__name__}: {exc}",
            "science_consumed": "unknown", "claim_retained": True,
            "absolute_repair_deadline_utc": os.environ["H200_RELEASE_BY_UTC"],
        })
        while dt.datetime.now(dt.timezone.utc) < DEADLINE:
            time.sleep(20)
        return 75
    finally:
        stop.set()


if __name__ == "__main__":
    raise SystemExit(main())
