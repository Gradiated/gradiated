#!/usr/bin/env python3
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


NAME = "gemma4_h200_mlp_width16384_codesign"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
LAB = pathlib.Path("/root/workspace/research/lab/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
REMOTE = "/home/glmrunner/gemma4-width16384"
CHECKPOINT_CANDIDATES = (
    "/home/glmrunner/gemma4-fp8-layer-fusion/checkpoint",
    "/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint",
)
RATE = 2.46
AUTHORIZED = 12.0
MAX_CLAIM_SECONDS = 120 * 60
RETRIEVAL_RESERVE_SECONDS = 10 * 60


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--absolute-deadline-epoch", type=int, required=True)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    events = args.artifact_root / "outer-events.jsonl"

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(json.dumps({"epoch": time.time(), "event": event, **fields}, sort_keys=True) + "\n")
            handle.flush()

    manifest = json.loads((PROJECT / "GPU_INPUT_MANIFEST.json").read_text())
    if manifest.get("pass") is not True:
        raise RuntimeError("project local input manifest invalid")
    for row in [
        manifest["selection"],
        manifest["settled_bound"],
        *manifest["bound_inputs"],
        *manifest["programs"],
    ]:
        path = PROJECT / row["path"]
        if not path.is_file() or path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            raise RuntimeError(f"project local snapshot invalid:{row['path']}")
    status = json.loads((PROJECT / "STATUS.json").read_text())
    prior_spend = float(status.get("actual_spend_usd", 0.0))
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    bench = inventory["benches"][BENCH]
    deadline = min(
        args.absolute_deadline_epoch,
        int(time.time()) + MAX_CLAIM_SECONDS,
        int(time.time()) + int((AUTHORIZED - prior_spend) * 3600 / RATE),
    )
    if deadline <= time.time() + RETRIEVAL_RESERVE_SECONDS + 600:
        raise RuntimeError("typed budget boundary:insufficient claim window")

    started = time.time()
    claimed = False
    terminal: dict[str, object] | None = None
    stop = threading.Event()
    release_condition = "ready"

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-1000:])

    thread = threading.Thread(target=heartbeat, daemon=True)
    try:
        lease = max(600, deadline - int(time.time()))
        claimed_result = pool("claim", "--project", NAME, "--bench", BENCH, "--lease-seconds", str(lease))
        claimed = True
        emit("claimed", result=json.loads(claimed_result.stdout))
        thread.start()
        sys.path.insert(0, str(NEBIUS))
        from placement_control import extract_public_ipv4, get_instance
        from stock_control import run_ssh

        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip:
            raise RuntimeError("typed provider boundary:no public IP")
        identity = run_ssh(
            ip,
            KEY,
            "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version",
            timeout=60,
        )
        (args.artifact_root / "remote-identity.stdout").write_text(identity.stdout)
        (args.artifact_root / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed remote boundary:ssh identity failed")
        prepared = run_ssh(ip, KEY, f"mkdir -p {REMOTE}/input {REMOTE}/artifacts", timeout=60)
        if prepared.returncode:
            raise RuntimeError("typed remote boundary:prepare failed")
        checkpoint_probe = run_ssh(
            ip,
            KEY,
            "for p in "
            + " ".join(shlex.quote(path) for path in CHECKPOINT_CANDIDATES)
            + "; do if test -d \"$p\" && test -r \"$p/model.safetensors.index.json\" && test \"$(stat -c%s \"$p/model-00001-of-00002.safetensors\" 2>/dev/null)\" = 49784788364 && test \"$(stat -c%s \"$p/model-00002-of-00002.safetensors\" 2>/dev/null)\" = 12761549884 && test \"$(sha256sum \"$p/model.safetensors.index.json\" | awk '{print $1}')\" = d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2; then printf '%s\\n' \"$p\"; exit 0; fi; done; exit 1",
            timeout=120,
        )
        if checkpoint_probe.returncode or not checkpoint_probe.stdout.strip():
            raise RuntimeError("typed remote boundary:immutable checkpoint unavailable")
        remote_checkpoint = checkpoint_probe.stdout.strip().splitlines()[-1]
        checkpoint = run_ssh(
            ip,
            KEY,
            f"ln -sfn {remote_checkpoint} {REMOTE}/checkpoint",
            timeout=120,
        )
        if checkpoint.returncode:
            raise RuntimeError("typed remote boundary:immutable checkpoint identity changed")
        emit("checkpoint_storage_identity_reused", bytes=manifest["checkpoint"]["bytes"])

        def copy_to(source: pathlib.Path, destination: str) -> None:
            expected = sha256(source)
            matched = run_ssh(
                ip,
                KEY,
                f"test -f {shlex.quote(destination)} && test \"$(sha256sum {shlex.quote(destination)} | awk '{{print $1}}')\" = {expected}",
                timeout=120,
            )
            if matched.returncode:
                partial = f"{destination}.{expected}.part"
                copied = run(
                    [
                        "scp", "-i", str(KEY), "-o", "BatchMode=yes",
                        "-o", "StrictHostKeyChecking=accept-new",
                        "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
                        str(source), f"glmrunner@{ip}:{partial}",
                    ],
                    capture_output=True,
                    timeout=max(120, deadline - int(time.time()) - RETRIEVAL_RESERVE_SECONDS),
                )
                if copied.returncode:
                    raise RuntimeError(f"typed transfer boundary:{source.name}:{copied.stderr[-1200:]}")
                mode = "0555" if source.suffix == ".sh" else "0444"
                finalized = run_ssh(
                    ip,
                    KEY,
                    f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {expected} && chmod {mode} {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {shlex.quote(destination)}",
                    timeout=300,
                )
                if finalized.returncode:
                    raise RuntimeError(f"typed transfer boundary:finalize:{source.name}")
            emit("input_staged", name=source.name, bytes=source.stat().st_size, sha256=expected)

        staged = [
            (PROJECT / "sitecustomize.py", f"{REMOTE}/input/sitecustomize.py"),
            (PROJECT / "remote_width16384.sh", f"{REMOTE}/input/remote_width16384.sh"),
            (PROJECT / manifest["selection"]["path"], f"{REMOTE}/input/JOINT_NORM_SELECTION.json"),
            (PROJECT / manifest["settled_bound"]["path"], f"{REMOTE}/input/SETTLED_BOUND.json"),
        ]
        staged.extend(
            (PROJECT / row["path"], f"{REMOTE}/input/{pathlib.Path(row['path']).name}")
            for row in manifest["bound_inputs"]
        )
        for source, destination in staged:
            copy_to(source, destination)
        emit("immutable_staging_complete", files=len(staged))

        timeout = max(60, deadline - int(time.time()) - RETRIEVAL_RESERVE_SECONDS)
        worker = run_ssh(
            ip,
            KEY,
            f"timeout --signal=TERM {timeout} bash {REMOTE}/input/remote_width16384.sh",
            timeout=timeout + 60,
        )
        (args.artifact_root / "remote-worker.stdout").write_text(worker.stdout)
        (args.artifact_root / "remote-worker.stderr").write_text(worker.stderr)
        emit("worker_returned", returncode=worker.returncode)

        def remote_json(remote_path: str, local_name: str) -> dict[str, object]:
            for attempt in range(3):
                result = run_ssh(ip, KEY, f"cat {shlex.quote(remote_path)}", timeout=30)
                if result.returncode == 0 and result.stdout.strip():
                    value = json.loads(result.stdout)
                    atomic(args.artifact_root / local_name, value)
                    return value
                time.sleep(5 * (attempt + 1))
            raise RuntimeError(f"typed retrieval boundary:{remote_path}")

        invocation = remote_json(f"{REMOTE}/artifacts/INVOCATION_STATE.json", "INVOCATION_STATE.json")
        worker_terminal = remote_json(f"{REMOTE}/artifacts/WORKER_TERMINAL.json", "REMOTE_WORKER_TERMINAL.json")
        archive = args.artifact_root / "compact.tar.gz.part"
        sidecar = args.artifact_root / "compact.tar.gz.sha256"
        for remote_path, local_path in (
            (f"{REMOTE}/width16384-compact.tar.gz", archive),
            (f"{REMOTE}/width16384-compact.tar.gz.sha256", sidecar),
        ):
            result = run(
                [
                    "scp", "-i", str(KEY), "-o", "BatchMode=yes",
                    "-o", "StrictHostKeyChecking=accept-new",
                    "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
                    f"glmrunner@{ip}:{remote_path}", str(local_path),
                ],
                capture_output=True,
                timeout=300,
            )
            if result.returncode:
                raise RuntimeError(f"typed retrieval boundary:archive:{result.stderr[-1200:]}")
        if sha256(archive) != sidecar.read_text().split()[0]:
            raise RuntimeError("typed retrieval boundary:archive hash mismatch")
        final_archive = args.artifact_root / "compact.tar.gz"
        os.replace(archive, final_archive)
        retrieved = args.artifact_root / "retrieved"
        retrieved.mkdir()
        with tarfile.open(final_archive, "r:gz") as bundle:
            bundle.extractall(retrieved, filter="data")
        decision_path = retrieved / "TERMINAL.json"
        if not decision_path.is_file():
            decision_path = retrieved / "BOUND.json"
        if not decision_path.is_file():
            decision_path = retrieved / "component/TERMINAL.json"
        if not decision_path.is_file():
            raise RuntimeError(f"typed scientific boundary:{worker_terminal.get('message')}")
        terminal = json.loads(decision_path.read_text())
        terminal["invocation_state"] = invocation
        terminal["provider_exposure_seconds"] = time.time() - started
        terminal["provider_spend_usd"] = terminal["provider_exposure_seconds"] * RATE / 3600
        terminal["cumulative_provider_spend_usd"] = prior_spend + terminal["provider_spend_usd"]
        if terminal["cumulative_provider_spend_usd"] > AUTHORIZED:
            terminal["classification"] = "budget_violation"
            terminal["pass"] = False
        atomic(args.artifact_root / "TERMINAL.json", terminal)
        return 0
    except Exception as error:
        terminal = {
            "schema_version": 1,
            "status": "terminal",
            "classification": "owner_failure",
            "pass": False,
            "error": {"type": type(error).__name__, "message": str(error)},
            "provider_exposure_seconds": time.time() - started if claimed else 0.0,
        }
        terminal["provider_spend_usd"] = terminal["provider_exposure_seconds"] * RATE / 3600
        terminal["cumulative_provider_spend_usd"] = prior_spend + terminal["provider_spend_usd"]
        atomic(args.artifact_root / "TERMINAL.json", terminal)
        emit("outer_error", error_type=type(error).__name__, message=str(error))
        if claimed and "ssh identity failed" in str(error):
            release_condition = "maintenance"
        return 1
    finally:
        stop.set()
        if thread.is_alive():
            thread.join(timeout=5)
        if claimed:
            contents = {
                "project": NAME,
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "checkpoint": "Exact immutable checkpoint unchanged; resolved owner-local symlink retained at /home/glmrunner/gemma4-width16384/checkpoint",
                "image": "Pinned SGLang v0.5.13 digest 6113665 retained",
                "runtime": f"Width-16384 quality-unsafe proxy terminal: {(terminal or {}).get('classification', 'owner_failure')}",
                "caches": "FP8, QKV, deferred-local-KV, and CUDA graph caches retained",
                "server_state": "Final width-16384 candidate server retained when healthy; otherwise checkpoint/image/caches retained",
                "artifacts": f"Remote immutable selection and compact terminal retained at {REMOTE}",
                "mlp_width16384_claim_cost_usd": (terminal or {}).get("provider_spend_usd", 0.0),
                "mlp_width16384_cumulative_cost_usd": (terminal or {}).get("cumulative_provider_spend_usd", prior_spend),
                "mlp_width16384_result": (terminal or {}).get("classification", "owner_failure"),
            }
            contents_path = args.artifact_root / "BENCH_CONTENTS.json"
            atomic(contents_path, contents)
            released = pool("release", "--project", NAME, "--condition", release_condition, "--contents", str(contents_path), check=False)
            emit("released", returncode=released.returncode, stderr=released.stderr[-1000:])


if __name__ == "__main__":
    raise SystemExit(main())
