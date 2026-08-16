#!/usr/bin/env python3
"""Retained-claim owner for the bound packed-M384 H100 component run."""
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
import textwrap


PROJECT = "gemma4_hopper_packed_m384_verifier"
BENCH = "h100-paged-fp8-e00mkpyvykfak0bg1m"
ROOT = pathlib.Path(__file__).resolve().parent
LAB = ROOT.parent.parent
INVENTORY = LAB / "runtime" / "gpus.json"
IDENTITY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
DEADLINE = dt.datetime.fromisoformat("2026-07-26T17:32:01.095093+00:00")
ARTIFACTS = ROOT / "artifacts" / "h100-component"


def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)


def pool(action: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return run([
        sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), action,
        "--project", PROJECT, "--bench", BENCH, *extra,
    ], cwd="/root/workspace", env={**os.environ, "PYTHONPATH": "research/factory/src"})


def bench_record() -> dict[str, object]:
    benches = json.loads(INVENTORY.read_text())["benches"]
    if isinstance(benches, dict):
        bench = benches.get(BENCH)
    else:
        bench = next((item for item in benches if item["id"] == BENCH), None)
    if not isinstance(bench, dict):
        raise RuntimeError("bench_missing")
    return bench


def claimed_connection() -> tuple[str, str]:
    bench = bench_record()
    claim = bench.get("claim") or {}
    if bench.get("status") != "claimed" or claim.get("project") != PROJECT:
        raise RuntimeError("claim_not_owned")
    resource = bench["resource"]
    if resource["ssh_user"] != "glmrunner" or resource["known_hosts_namespace"] != str(KNOWN_HOSTS):
        raise RuntimeError("unexpected_ssh_binding")
    return resource["ssh_user"], resource["public_ipv4"]


def ssh_base(user: str, host: str) -> list[str]:
    return ["ssh", "-i", str(IDENTITY), "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes", f"{user}@{host}"]


def heartbeat(stop: threading.Event) -> None:
    while not stop.wait(60):
        completed = pool("heartbeat")
        atomic(ROOT / "OWNER_HEARTBEAT.json", {"at_utc": now().isoformat(), "exit": completed.returncode, "stdout": completed.stdout[-2000:], "stderr": completed.stderr[-2000:]})


def remote_stage(user: str, host: str) -> None:
    manifest = json.loads((ROOT / "INPUT_MANIFEST.json").read_text())
    for row in manifest["files"]:
        path = ROOT / row["path"]
        if sha256(path) != row["sha256"]:
            raise RuntimeError(f"local_manifest_mismatch:{row['path']}")
    packet = ROOT / "artifacts" / "packet.tar"
    packed = run(["/root/workspace/research/factory/tools/manifest-pack", "--root", str(ROOT), "--manifest", str(ROOT / "INPUT_MANIFEST.json"), "--archive", str(packet)])
    if packed.returncode:
        raise RuntimeError(f"packet_pack_failed:{packed.stderr[-1000:]}")
    remote_root = f"/home/{user}/{PROJECT}"
    prepared = run(ssh_base(user, host) + [f"mkdir -p {shlex.quote(remote_root)} {shlex.quote(remote_root + '/artifacts')}"])
    if prepared.returncode:
        raise RuntimeError(f"remote_root_prepare_failed:{prepared.stderr[-1000:]}")
    verifier = textwrap.dedent(
        """
        import hashlib, json, os, pathlib, sys
        root = pathlib.Path(sys.argv[1])
        expected_manifest = sys.argv[2]
        def digest(path):
            value = hashlib.sha256()
            with path.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    value.update(chunk)
            return value.hexdigest()
        def verified(directory):
            manifest_path = directory / 'INPUT_MANIFEST.json'
            if not manifest_path.is_file() or digest(manifest_path) != expected_manifest:
                return False
            manifest = json.loads(manifest_path.read_text())
            for row in manifest['files']:
                relative = pathlib.PurePosixPath(row['path'])
                if relative.is_absolute() or '..' in relative.parts or not relative.parts:
                    return False
                member = directory.joinpath(*relative.parts)
                if member.is_symlink() or not member.is_file() or digest(member) != row['sha256']:
                    return False
            return True
        packet = root / 'packet'
        temporary = root / 'packet.tmp'
        if verified(packet):
            print('matched_packet')
        elif verified(temporary):
            os.replace(temporary, packet)
            print('reused_packet_tmp')
        else:
            print('stage_required')
        """
    )
    manifest_digest = sha256(ROOT / "INPUT_MANIFEST.json")
    check = run(ssh_base(user, host) + [
        shlex.join(["python3", "-c", verifier, remote_root, manifest_digest]),
    ])
    if check.returncode:
        raise RuntimeError(f"packet_reconcile_failed:{check.stderr[-1000:]}")
    state = check.stdout.strip()
    if state in {"matched_packet", "reused_packet_tmp"}:
        atomic(ROOT / "STAGING.json", {"at_utc": now().isoformat(), "packet_sha256": sha256(packet), "manifest_sha256": manifest_digest, "remote_root": remote_root, "verified": True, "remote_state": state})
        return
    if state != "stage_required":
        raise RuntimeError(f"packet_reconcile_unrecognized:{state}")
    scp = run(["scp", "-i", str(IDENTITY), "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes", str(packet), f"{user}@{host}:{remote_root}/packet.tar"])
    if scp.returncode:
        raise RuntimeError(f"packet_copy_failed:{scp.stderr[-1000:]}")
    installer = textwrap.dedent(
        """
        import os, pathlib, shutil, subprocess, sys, tempfile
        root = pathlib.Path(sys.argv[1])
        archive = root / 'packet.tar'
        stage = pathlib.Path(tempfile.mkdtemp(prefix='packet.stage.', dir=root))
        try:
            subprocess.run(['tar', '-xf', str(archive), '-C', str(stage)], check=True)
            os.replace(stage, root / 'packet.tmp')
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        """
    )
    staged = run(ssh_base(user, host) + [
        shlex.join(["python3", "-c", installer, remote_root]),
    ])
    if staged.returncode:
        raise RuntimeError(f"packet_extract_failed:{staged.stderr[-1600:]}")
    checked = run(ssh_base(user, host) + [
        shlex.join(["python3", "-c", verifier, remote_root, manifest_digest]),
    ])
    if checked.returncode or checked.stdout.strip() != "reused_packet_tmp":
        raise RuntimeError(f"packet_staged_manifest_mismatch:{checked.stdout[-300:]}:{checked.stderr[-1000:]}")
    atomic(ROOT / "STAGING.json", {"at_utc": now().isoformat(), "packet_sha256": sha256(packet), "manifest_sha256": manifest_digest, "remote_root": remote_root, "verified": True, "remote_state": "staged_then_verified"})


def retrieve(user: str, host: str, remote_root: str) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    for name in ("PACKED_M384_VERIFIER_RESULT.json", "INVOCATION_STATE.json", "CANDIDATE_PATH.jsonl", "stdout.log", "stderr.log"):
        run(["scp", "-i", str(IDENTITY), "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes", f"{user}@{host}:{remote_root}/artifacts/h100-component/{name}", str(ARTIFACTS / name)])


def main() -> int:
    if now() >= DEADLINE:
        raise RuntimeError("release_deadline_elapsed_before_owner")
    if not IDENTITY.is_file() or not KNOWN_HOSTS.is_file():
        raise RuntimeError("ssh_identity_or_known_hosts_missing")
    user, host = claimed_connection()
    stop = threading.Event()
    thread = threading.Thread(target=heartbeat, args=(stop,), daemon=True)
    thread.start()
    remote_root = f"/home/{user}/{PROJECT}"
    terminal: dict[str, object] = {"started_at_utc": now().isoformat(), "bench": BENCH, "claimed_at": bench_record()["claim"]["claimed_at"]}
    try:
        remote_stage(user, host)
        command = json.loads((ROOT / "EXACT_START_COMMAND.json").read_text())["command"]
        remote_command = f"mkdir -p {shlex.quote(remote_root)}/artifacts/h100-component && set -o pipefail; {command} > {shlex.quote(remote_root)}/artifacts/h100-component/stdout.log 2> {shlex.quote(remote_root)}/artifacts/h100-component/stderr.log"
        completed = run(ssh_base(user, host) + [
            shlex.join(["bash", "-lc", remote_command]),
        ])
        terminal.update({"worker_exit": completed.returncode, "ssh_stdout": completed.stdout[-2000:], "ssh_stderr": completed.stderr[-2000:]})
        retrieve(user, host, remote_root)
        result_path = ARTIFACTS / "PACKED_M384_VERIFIER_RESULT.json"
        invocation_path = ARTIFACTS / "INVOCATION_STATE.json"
        terminal["invocation"] = json.loads(invocation_path.read_text()) if invocation_path.exists() else None
        terminal["result"] = json.loads(result_path.read_text()) if result_path.exists() else None
        if terminal["result"] is None:
            diagnostic = ROOT / "RECOVERABLE_DIAGNOSTIC.json"
            atomic(diagnostic, terminal)
            repair = run(["/root/workspace/research/factory/tools/repair-handshake", "ready", "--root", str(ROOT), "--repair-id", "initial", "--deadline", DEADLINE.isoformat().replace("+00:00", "Z"), "--failure-kind", "integration", "--diagnostic", str(diagnostic), "--retry-scope", "repair only the failed staging, launcher, compile, API, or retrieval operation; preserve packet and unconsumed science contract"])
            terminal["repair_ready"] = repair.returncode == 0
            atomic(ROOT / "OWNER_TERMINAL.json", terminal)
            if repair.returncode == 0:
                run(["/root/workspace/research/factory/tools/repair-handshake", "wait", "--root", str(ROOT), "--repair-id", "initial"], timeout=max(1, int((DEADLINE - now()).total_seconds())))
            return 1
        terminal["classification"] = "scientific_terminal_retrieved"
        atomic(ROOT / "OWNER_TERMINAL.json", terminal)
        contents = json.dumps({"project": PROJECT, "result": terminal["result"].get("result"), "candidate_cuda_started": bool((terminal["invocation"] or {}).get("candidate_cuda_invocation_started")), "artifacts": str(ARTIFACTS), "image": "Pinned vLLM image retained; no server left resident.", "server_state": "No container retained; image and compiler caches remain resident."})
        released = pool("release", "--condition", "ready", "--contents", contents)
        terminal["release_exit"] = released.returncode
        terminal["release_stdout"] = released.stdout[-2000:]
        atomic(ROOT / "OWNER_TERMINAL.json", terminal)
        return 0
    except Exception as error:
        terminal["exception"] = repr(error)
        diagnostic = ROOT / "RECOVERABLE_DIAGNOSTIC.json"
        atomic(diagnostic, terminal)
        repair = run([
            "/root/workspace/research/factory/tools/repair-handshake", "ready",
            "--root", str(ROOT), "--repair-id", "initial", "--deadline",
            DEADLINE.isoformat().replace("+00:00", "Z"), "--failure-kind",
            "integration", "--diagnostic", str(diagnostic), "--retry-scope",
            "repair only the failed staging, launcher, compile, API, or retrieval operation; preserve packet and unconsumed science contract",
        ])
        terminal["repair_ready"] = repair.returncode == 0
        atomic(ROOT / "OWNER_TERMINAL.json", terminal)
        if repair.returncode == 0:
            run([
                "/root/workspace/research/factory/tools/repair-handshake", "wait",
                "--root", str(ROOT), "--repair-id", "initial",
            ], timeout=max(1, int((DEADLINE - now()).total_seconds())))
        return 1
    finally:
        stop.set()


if __name__ == "__main__":
    raise SystemExit(main())
