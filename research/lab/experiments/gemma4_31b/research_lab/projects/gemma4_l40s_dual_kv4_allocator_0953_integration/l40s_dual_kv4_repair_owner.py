#!/usr/bin/env python3
"""Continuous-claim g2 owner for the fixed checkpoint-free dual-KV component."""

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


ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = ROOT.name
BINDING = ROOT / "DIRECTOR_DUAL_KV4_SM89_REPAIR_OWNER_BINDING_20260728T0900Z.json"
READY = ROOT / "L40S_DUAL_KV4_SM89_REPAIR_OWNER_READY.json"
FACTORY = Path("/root/workspace/research/factory/src")
HANDSHAKE = Path("/root/workspace/research/factory/tools/repair-handshake")
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
FILES = ("sm89_dual_kv4_runner.py", "local_kv4_outlier_cuda.cu", "global_tiered_kv4_cuda.cu")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(argv: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, check=False, **kwargs)


def load_binding() -> dict:
    value = json.loads(BINDING.read_text())
    repair = value["repair"]
    expected = {
        "sm89_dual_kv4_runner.py": repair["runner_sha256"],
        "local_kv4_outlier_cuda.cu": repair["local_cuda_sha256"],
        "global_tiered_kv4_cuda.cu": repair["global_cuda_sha256"],
    }
    for name, digest in expected.items():
        if sha256(ROOT / name) != digest:
            raise RuntimeError(f"bound_g2_identity_mismatch:{name}")
    predecessor = ROOT / value["predecessor"]["artifact_root"]
    if sha256(predecessor / "OWNER_TERMINAL.json") != value["predecessor"]["owner_terminal_sha256"]:
        raise RuntimeError("predecessor_owner_terminal_identity_mismatch")
    if sha256(ROOT / value["repair"]["prepared_artifact"]) != value["repair"]["prepared_artifact_sha256"]:
        raise RuntimeError("prepared_g2_repair_identity_mismatch")
    return value


def release_allowed(classification: str, deadline_expired: bool) -> bool:
    return deadline_expired or classification in {
        "scientific_terminal_retrieved", "unsafe_or_unreachable_guest"
    }


def next_repair_id(number: int, prior: str | None) -> str:
    candidate = f"g{number}"
    if prior == candidate:
        raise RuntimeError("repair_generation_reuse")
    return candidate


def self_test() -> None:
    assert release_allowed("scientific_terminal_retrieved", False)
    assert release_allowed("unsafe_or_unreachable_guest", False)
    assert release_allowed("ordinary_compile_defect", True)
    assert not release_allowed("ordinary_compile_defect", False)
    assert not release_allowed("missing_terminal", False)
    assert next_repair_id(3, "g2") == "g3"
    try:
        next_repair_id(3, "g3")
    except RuntimeError:
        pass
    else:
        raise AssertionError("repair generation collision accepted")


def write_ready() -> None:
    self_test()
    binding = load_binding()
    owner_hash = sha256(Path(__file__))
    repair = binding["repair"]
    value = {
        "schema_version": 1,
        "kind": "l40s_dual_kv4_sm89_repair_owner_ready",
        "classification": "offline_ready_continuous_claim_replacement_owner",
        "pass": True,
        "direct_hashes": {
            "binding": {"path": str(BINDING), "sha256": sha256(BINDING)},
            "owner": {"path": str(Path(__file__)), "sha256": owner_hash},
            "runner": {"path": str(ROOT / "sm89_dual_kv4_runner.py"), "sha256": repair["runner_sha256"]},
            "local_cuda": {"path": str(ROOT / "local_kv4_outlier_cuda.cu"), "sha256": repair["local_cuda_sha256"]},
            "global_cuda": {"path": str(ROOT / "global_tiered_kv4_cuda.cu"), "sha256": repair["global_cuda_sha256"]},
            "prepared_g2_repair": {"path": str(ROOT / repair["prepared_artifact"]), "sha256": repair["prepared_artifact_sha256"]},
        },
        "focused_mocked_checks": {
            "release_generation": "release_allowed permits only scientific terminal, unsafe/unreachable guest, or absolute deadline; ordinary compile and missing-terminal paths retain the claim",
            "repair_generation": "fresh gN identifiers reject reuse",
            "predecessor": "attempts 0/1 are only read and never used as an output root",
        },
        "fixed_science": binding["fixed_science"],
        "owner_contract": {
            "claim": "one atomic claim; every release passes --expected-claimed-at from that claim",
            "repair": "each recoverable attempt publishes a fresh repair-handshake gN and waits while heartbeat continues",
            "retry": "attempts begin at 2 and only stage hash-bound g2 runner/CUDA files into the predecessor remote packet",
            "prohibited": ["checkpoint", "model server", "endpoint", "parameter sweep", "provider create"],
        },
        "exact_later_command": binding["replacement_owner"]["exact_later_command"],
        "claim_gate": binding["claim_gate"],
    }
    atomic(READY, value)


def pool(*args: str) -> dict:
    result = run(["env", f"PYTHONPATH={FACTORY}", "python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args], timeout=90)
    if result.returncode:
        raise RuntimeError(f"gpu_pool_{args[0]}:{result.stderr[-1000:]}")
    return json.loads(result.stdout)


def heartbeat(stop: threading.Event, bench: str, events: list[dict]) -> None:
    while not stop.wait(25):
        try:
            events.append({"at": now(), "kind": "heartbeat", "lease": pool("heartbeat", "--project", PROJECT, "--bench", bench)["claim"]["lease_until_utc"]})
        except Exception as error:
            events.append({"at": now(), "kind": "heartbeat_error", "error": repr(error)})


def ssh(claim: dict) -> list[str]:
    resource = claim["resource"]
    identity, known, host = resource.get("identity_file"), resource.get("known_hosts_namespace"), resource.get("public_ipv4")
    if resource.get("ssh_user") != "glmrunner" or not all(isinstance(x, str) and x for x in (identity, known, host)):
        raise RuntimeError("registered_ssh_identity_missing")
    if not Path(identity).is_file() or not Path(known).is_file():
        raise RuntimeError("controller_ssh_identity_missing")
    return ["ssh", "-i", identity, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known}", f"glmrunner@{host}"]


def remote(prefix: list[str], script: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return run([*prefix, "bash", "-s"], input=script, timeout=timeout)


def stage_g2(prefix: list[str], remote_packet: str, deadline: float) -> None:
    for name in FILES:
        local, target = ROOT / name, f"{remote_packet}/{name}"
        partial = target + ".g2.part"
        copied = run(["scp", "-q", *prefix[1:-1], str(local), f"{prefix[-1]}:{partial}"], timeout=max(30, min(300, int(deadline - time.time() - 180))))
        if copied.returncode:
            raise RuntimeError(f"g2_stage_copy_failed:{name}")
        finalized = remote(prefix, f"set -e; test \"$(sha256sum {shlex.quote(partial)} | cut -d' ' -f1)\" = {sha256(local)}; chmod 0444 {shlex.quote(partial)}; mv -f {shlex.quote(partial)} {shlex.quote(target)}", max(30, min(120, int(deadline-time.time()-150))))
        if finalized.returncode:
            raise RuntimeError(f"g2_stage_finalize_failed:{name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-ready", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--bench")
    parser.add_argument("--predecessor-root", type=Path)
    parser.add_argument("--prepared-repair", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--deadline-seconds", type=int)
    args = parser.parse_args()
    if args.self_test:
        self_test(); return 0
    if args.write_ready:
        write_ready(); return 0
    binding = load_binding()
    if not all((args.bench, args.predecessor_root, args.prepared_repair, args.artifact_root, args.deadline_seconds)):
        raise SystemExit("execution_arguments_required")
    if args.deadline_seconds <= 0 or args.deadline_seconds > binding["replacement_owner"]["max_deadline_seconds"] or args.artifact_root.exists():
        raise SystemExit("invalid_replacement_owner_window_or_artifact_root")
    if args.bench != binding["bench"]["id"] or sha256(args.prepared_repair) != binding["repair"]["prepared_artifact_sha256"]:
        raise SystemExit("binding_identity_mismatch")
    claim = pool("claim", "--project", PROJECT, "--bench", args.bench, "--accelerator", "nvidia-l40s", "--lease-seconds", str(args.deadline_seconds))
    args.artifact_root.mkdir(parents=True)
    started, deadline = time.time(), time.time() + args.deadline_seconds
    events = [{"at": now(), "kind": "claim", "claimed_at": claim["claim"]["claimed_at"], "predecessor_claimed_at": binding["predecessor"]["claim_generation"]}]
    stop = threading.Event(); thread = threading.Thread(target=heartbeat, args=(stop, claim["id"], events), daemon=True); thread.start()
    classification, release, generation, attempt = "unknown_retained", None, 3, 2
    try:
        prefix = ssh(claim)
        old_remote = f"/home/glmrunner/gemma4-dual-kv4-{binding['predecessor']['claim_generation'].replace(':', '-')}"
        stage_g2(prefix, old_remote + "/packet", deadline)
        while time.time() < deadline - 180:
            remote_attempt = f"{old_remote}/attempt-{attempt}"
            command = f"set +e; mkdir -p {shlex.quote(remote_attempt)}; printf '%s\\n' '{{\"state\":\"launch_attempted\"}}' > {shlex.quote(remote_attempt)}/LAUNCH_ATTEMPTED.json; sudo -n docker run --rm --gpus all --ipc=host --user \"$(id -u):$(id -g)\" -e PYTHONUNBUFFERED=1 -e TORCH_EXTENSIONS_DIR=/work/state/extensions -v {shlex.quote(old_remote)}:/work/state --entrypoint /bin/bash {shlex.quote(IMAGE)} -lc {shlex.quote(f'cd /work/state/packet && python3 sm89_dual_kv4_runner.py --artifact-root /work/state/attempt-{attempt}/result')} >{shlex.quote(remote_attempt)}/runner.stdout 2>{shlex.quote(remote_attempt)}/runner.stderr; rc=$?; echo $rc > {shlex.quote(remote_attempt)}/runner.exit; exit $rc"
            remote(prefix, command, max(60, min(2700, int(deadline-time.time()-150))))
            local_attempt = args.artifact_root / f"attempt-{attempt}"
            local_attempt.mkdir()
            for name in ("runner.stdout", "runner.stderr", "runner.exit", "LAUNCH_ATTEMPTED.json", "result/SCIENCE_STARTED.json", "result/ARM_FIRST_CALL_MARKERS.jsonl", "result/TERMINAL.json", "result/INVOCATION_COMPLETE.json"):
                target = local_attempt / name.replace("/", "__")
                fetched = run(["scp", "-q", *prefix[1:-1], f"{prefix[-1]}:{remote_attempt}/{name}", str(target)+".part"], timeout=120)
                if fetched.returncode == 0: os.replace(str(target)+".part", target)
            terminal = local_attempt / "result__TERMINAL.json"
            complete = local_attempt / "result__INVOCATION_COMPLETE.json"
            if terminal.exists() and complete.exists():
                classification = "scientific_terminal_retrieved"; break
            repair_id = next_repair_id(generation, f"g{generation-1}" if generation > 3 else None)
            diagnostic = local_attempt / "runner.stderr"
            repair_deadline = dt.datetime.fromtimestamp(deadline-120, dt.timezone.utc).isoformat().replace("+00:00", "Z")
            ready = run([str(HANDSHAKE), "ready", "--root", str(args.artifact_root), "--repair-id", repair_id, "--deadline", repair_deadline, "--failure-kind", "ordinary_pre_science_or_retrieval_defect", "--diagnostic", str(diagnostic), "--retry-scope", "narrow_hash_bound_patch"], timeout=30)
            if ready.returncode: raise RuntimeError("repair_ready_failed")
            waited = run([str(HANDSHAKE), "wait", "--root", str(args.artifact_root), "--repair-id", repair_id, "--poll-seconds", "3"], timeout=max(1, int(deadline-time.time()-100)))
            if waited.returncode: classification = "repair_deadline_expired"; break
            events.append({"at": now(), "kind": "repair_request_consumed", "repair_id": repair_id})
            generation += 1; attempt += 1
        if time.time() >= deadline - 180 and classification == "unknown_retained": classification = "absolute_deadline"
    except Exception as error:
        classification = "unsafe_or_unreachable_guest" if "ssh" in repr(error).lower() else "ordinary_owner_defect_retained"
        events.append({"at": now(), "kind": "error", "error": repr(error)})
    finally:
        expired = time.time() >= deadline - 180 or classification == "absolute_deadline"
        if release_allowed(classification, expired):
            contents = args.artifact_root / "BENCH_CONTENTS.json"; atomic(contents, {"project": PROJECT, "result": classification, "checkpoint": "none", "image": IMAGE, "predecessor": str(args.predecessor_root)})
            release = pool("release", "--project", PROJECT, "--bench", claim["id"], "--expected-claimed-at", claim["claim"]["claimed_at"], "--contents", str(contents), "--condition", "ready" if classification == "scientific_terminal_retrieved" else "maintenance")
        stop.set(); thread.join(timeout=2)
        atomic(args.artifact_root / "OWNER_TERMINAL.json", {"schema_version": 1, "classification": classification, "release": release, "claim": {"bench": claim["id"], "claimed_at": claim["claim"]["claimed_at"], "predecessor_claimed_at": binding["predecessor"]["claim_generation"], "claim_seconds": max(0, time.time()-started)}, "events": events})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
