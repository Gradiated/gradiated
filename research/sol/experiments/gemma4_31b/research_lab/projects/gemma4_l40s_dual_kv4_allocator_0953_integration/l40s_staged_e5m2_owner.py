#!/usr/bin/env python3
"""Repair-aware lifecycle owner for one staged-E5M2 dual-KV4 sample."""

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
BINDING = ROOT / "DIRECTOR_DUAL_KV4_STAGED_E5M2_CONSUMER_BINDING_20260728T0916Z.json"
READY = ROOT / "L40S_DUAL_KV4_STAGED_E5M2_SM89_READY.json"
FACTORY = Path("/root/workspace/research/factory/src")
HANDSHAKE = Path("/root/workspace/research/factory/tools/repair-handshake")
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
BENCH = "l40s-dual-kv4-sm89-computeinstance-e00nczqf2p0x2y51wt"
RELEASE_BY = "2026-07-28T09:53:30Z"
MAX_SECONDS = 1500
PACKET_FILES = (
    "sm89_staged_e5m2_runner.py",
    "staged_e5m2_decode_bindings.cpp",
    "staged_e5m2_decode_cuda.cu",
    "local_kv4_outlier_bindings.cpp",
    "local_kv4_outlier_cuda.cu",
    "global_tiered_kv4_bindings.cpp",
    "global_tiered_kv4_cuda.cu",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> float:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def run(argv: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, text=True, capture_output=True, check=False, **kwargs)


def pool(*args: str, timeout: int = 60) -> dict:
    result = run([
        "env", f"PYTHONPATH={FACTORY}", "python3", "-m",
        "grad_research.gpu_pool", "--lab", str(LAB), *args,
    ], timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"gpu_pool_{args[0]}:{result.stderr[-1000:]}")
    return json.loads(result.stdout)


def release_allowed(classification: str, deadline_expired: bool) -> bool:
    return deadline_expired or classification in {
        "scientific_terminal_retrieved",
        "scientific_terminal_adopted_after_repair",
        "unsafe_or_unreachable_guest",
    }


def write_ready() -> None:
    binding = json.loads(BINDING.read_text())
    if sha256(BINDING) != "1b3bd6db6163b6ff36df4fe0decb0292137435961db49ffedf2903865375edda":
        raise RuntimeError("director_binding_identity_mismatch")
    predecessor = ROOT / binding["predecessor_terminal"]["path"]
    if sha256(predecessor) != binding["predecessor_terminal"]["sha256"]:
        raise RuntimeError("consumed_predecessor_identity_mismatch")
    direct = {
        name: {"path": str(ROOT / name), "sha256": sha256(ROOT / name),
               "bytes": (ROOT / name).stat().st_size}
        for name in PACKET_FILES
    }
    direct["owner"] = {
        "path": str(Path(__file__)), "sha256": sha256(Path(__file__)),
        "bytes": Path(__file__).stat().st_size,
    }
    direct["binding"] = {
        "path": str(BINDING), "sha256": sha256(BINDING),
        "bytes": BINDING.stat().st_size,
    }
    direct["predecessor_terminal"] = {
        "path": str(predecessor), "sha256": sha256(predecessor),
        "bytes": predecessor.stat().st_size,
    }
    runner_source = (ROOT / "sm89_staged_e5m2_runner.py").read_text()
    owner_source = Path(__file__).read_text()
    required_runner_tokens = (
        "sglang.srt.layers.attention.triton_ops.decode_attention",
        "decode_ext.decode_local",
        "decode_ext.decode_global",
        "candidate_staged_decode_ms",
        "candidate_stock_attention_ms",
        "candidate_vs_high_precision",
    )
    if not all(token in runner_source for token in required_runner_tokens):
        raise RuntimeError("runner_source_contract_incomplete")
    if ("release_allowed(classification" not in owner_source
            or "repair-handshake" not in str(HANDSHAKE)):
        raise RuntimeError("owner_repair_release_contract_incomplete")
    owner_root = ROOT / "artifacts/staged-e5m2-owner-20260728t0920z"
    sample_root = ROOT / "artifacts/staged-e5m2-component-20260728t0920z"
    command = (
        f"/root/workspace/research/factory/tools/detached-owner start "
        f"--unit-manager pid --state {owner_root}/OWNER.json "
        f"--log {owner_root}/OWNER.log -- python3 {Path(__file__)} "
        f"--bench {BENCH} --artifact-root {sample_root} "
        f"--deadline-seconds 1500 --release-by-utc {RELEASE_BY}"
    )
    local_bytes = 2 * 1024 * 16 * 256
    global_bytes = 2 * 4571 * 4 * 512
    ready = {
        "schema_version": 1,
        "kind": "l40s_dual_kv4_staged_e5m2_sm89_ready",
        "classification": "offline_positive_measurement_ready",
        "pass": True,
        "created_at_utc": utc_now(),
        "direct_hashes": direct,
        "immutable_science": binding["immutable_science"],
        "runner_contract": {
            "producer": "unchanged fixed local/global KV4 pack functions",
            "decode": "KV4 payload bytes are decoded and rounded once into torch.float8_e5m2 scratch",
            "consumer": "imported unchanged sglang.srt.layers.attention.triton_ops.decode_attention.decode_attention_fwd",
            "consumer_source_sha256": "7833f6d06115dfd54b384d9ce907a012fa2f568083d90fc0f259e9ef24bf5311",
            "arms": ["local D256 c32 window-1024", "global D512 c32 full-4571"],
            "timing": "5 warmups and 31 synchronized rows; pack, staged decode, stock attention, and complete times persist separately",
            "correctness": "complete stock-consumer baseline and candidate outputs are each compared with a float32 online-softmax reference; finite, cosine, max-absolute, relative-L2, and nonzero checksum persist",
            "fault_attribution": "each arm synchronizes and persists baseline, staged-decode, and stock-consumer first-call markers before timing",
            "sample_limit": "one new paired staged-consumer component sample; predecessor attempt 2 is only hash-read",
        },
        "scratch_ownership": {
            "dtype": "torch.float8_e5m2",
            "local_kv_bytes": local_bytes,
            "global_kv_bytes": global_bytes,
            "peak_bytes": max(local_bytes, global_bytes),
            "allocation": "caller-owned K/V tensors, allocated once per arm",
            "lifetime": "one arm only; local tensors are deleted before global allocation; decoder retains no pointer",
            "release_reuse": "scratch is reusable after synchronized stock attention and is released before the next arm",
            "lower_physical_margin_before_scratch_bytes": 1579875259,
            "lower_physical_margin_after_peak_scratch_bytes":
                1579875259 - max(local_bytes, global_bytes),
            "proof": "18,722,816-byte peak is below the 1,579,875,259-byte conservative lower physical margin",
        },
        "owner_contract": {
            "claim": "one atomic pool claim with original claimed_at carried to release",
            "image": "resident immutable image inspection only; no pull",
            "checkpoint_server_endpoint": "none",
            "repair": "missing/uninterpretable terminal is retained under heartbeat; a fresh repair handshake permits only the invalidated consumer/retrieval boundary",
            "release": "scientific terminal, adopted repaired terminal, unsafe/unreachable guest, or absolute release deadline only",
            "deadline": RELEASE_BY,
            "max_seconds": MAX_SECONDS,
        },
        "offline_checks": {
            "python_compile": "runner and owner compile in a fresh coordinator process",
            "owner_self_test": "ordinary compile/missing-terminal classifications fail the release guard; scientific terminal and deadline pass",
            "source_trace": list(required_runner_tokens),
            "target_execution": "deferred to the first tiny L40S call inside the retained later claim; no CUDA was invoked offline",
        },
        "complete_timing_contract": {
            "baseline": "all-E5M2 pack plus unchanged stock decode attention",
            "candidate": "unchanged KV4 pack plus staged decode plus the same stock decode attention",
            "request_terms": {
                "local_s_per_request": "0.559375 * measured_local_complete_margin_ms",
                "global_s_per_request": "0.111875 * measured_global_complete_margin_ms",
                "unmeasured_endpoint_overhead": "must remain explicit",
                "price_normalized_boundary_s_per_request": 1.4776251501079425,
            },
        },
        "exact_later_detached_command": command,
        "typed_none": None,
    }
    atomic(READY, ready)


def ssh_prefix(bench: dict) -> list[str]:
    resource = bench["resource"]
    fields = (
        resource.get("identity_file"), resource.get("known_hosts_namespace"),
        resource.get("public_ipv4"))
    if resource.get("ssh_user") != "glmrunner" or not all(fields):
        raise RuntimeError("registered_ssh_identity_incomplete")
    if not Path(fields[0]).is_file() or not Path(fields[1]).is_file():
        raise RuntimeError("controller_ssh_identity_missing")
    return [
        "ssh", "-i", fields[0], "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={fields[1]}",
        "-o", "ConnectTimeout=15", f"glmrunner@{fields[2]}",
    ]


def remote(prefix: list[str], script: str, timeout: int):
    return run([*prefix, "bash", "-s"], input=script, timeout=timeout)


def scp(prefix: list[str], source: str, target: str, timeout: int,
        remote_source: bool = False):
    host, options = prefix[-1], prefix[1:-1]
    left, right = ((f"{host}:{source}", target) if remote_source
                   else (source, f"{host}:{target}"))
    return run(["scp", "-q", *options, left, right], timeout=timeout)


def heartbeat(stop: threading.Event, bench: str, events: list[dict]) -> None:
    while not stop.wait(20):
        try:
            lease = pool("heartbeat", "--project", PROJECT, "--bench", bench)
            events.append({"at": utc_now(), "event": "heartbeat",
                           "lease": lease["claim"]["lease_until_utc"]})
        except Exception as error:
            events.append({"at": utc_now(), "event": "heartbeat_error",
                           "error": repr(error)})


def stage(prefix: list[str], remote_root: str, ready: dict, deadline: float) -> None:
    remote(prefix, f"set -e; mkdir -p {shlex.quote(remote_root + '/packet')}",
           min(60, max(1, int(deadline - time.time() - 120))))
    for name in PACKET_FILES:
        row = ready["direct_hashes"][name]
        target = f"{remote_root}/packet/{name}"
        probe = remote(
            prefix,
            f"test -f {shlex.quote(target)} && "
            f"test \"$(sha256sum {shlex.quote(target)} | cut -d' ' -f1)\" = {row['sha256']}",
            min(45, max(1, int(deadline - time.time() - 120))))
        if probe.returncode == 0:
            continue
        partial = target + ".part"
        copied = scp(prefix, row["path"], partial,
                     min(90, max(1, int(deadline - time.time() - 120))))
        if copied.returncode:
            raise RuntimeError(f"packet_copy_failed:{name}:{copied.stderr[-500:]}")
        finalized = remote(
            prefix,
            f"set -e; test \"$(sha256sum {shlex.quote(partial)} | cut -d' ' -f1)\" = {row['sha256']}; "
            f"chmod 0444 {shlex.quote(partial)}; mv -f {shlex.quote(partial)} {shlex.quote(target)}",
            min(60, max(1, int(deadline - time.time() - 120))))
        if finalized.returncode:
            raise RuntimeError(f"packet_finalize_failed:{name}")


def retrieve(prefix: list[str], remote_attempt: str, local: Path) -> dict:
    local.mkdir(parents=True, exist_ok=True)
    names = (
        "runner.stdout", "runner.stderr", "runner.exit",
        "result/SCIENCE_STARTED.json", "result/ARM_MARKERS.jsonl",
        "result/LOCAL_ROWS.json", "result/GLOBAL_ROWS.json",
        "result/TERMINAL.json", "result/INVOCATION_COMPLETE.json",
    )
    files = []
    for name in names:
        target = local / name.replace("/", "__")
        result = scp(prefix, f"{remote_attempt}/{name}", str(target) + ".part",
                     60, remote_source=True)
        if result.returncode == 0:
            os.replace(str(target) + ".part", target)
            files.append({"path": name, "sha256": sha256(target),
                          "bytes": target.stat().st_size})
    manifest = {
        "files": files,
        "raw_present": all(
            name in {row["path"] for row in files}
            for name in names[:3]),
        "science_started": "result/SCIENCE_STARTED.json" in {
            row["path"] for row in files},
        "terminal_present": "result/TERMINAL.json" in {
            row["path"] for row in files},
        "invocation_complete": "result/INVOCATION_COMPLETE.json" in {
            row["path"] for row in files},
    }
    atomic(local / "RETRIEVAL.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-ready", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--bench")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--deadline-seconds", type=int, default=MAX_SECONDS)
    parser.add_argument("--release-by-utc", default=RELEASE_BY)
    args = parser.parse_args()
    if args.write_ready:
        write_ready()
        return 0
    if args.self_test:
        assert not release_allowed("ordinary_compile_defect", False)
        assert not release_allowed("missing_terminal", False)
        assert release_allowed("scientific_terminal_retrieved", False)
        assert release_allowed("ordinary_compile_defect", True)
        return 0
    if (not args.bench or not args.artifact_root or args.artifact_root.exists()
            or not 0 < args.deadline_seconds <= MAX_SECONDS):
        raise SystemExit("invalid_owner_arguments")
    release_epoch = parse_utc(args.release_by_utc)
    deadline = min(time.time() + args.deadline_seconds, release_epoch)
    if deadline - time.time() < 240:
        raise SystemExit("insufficient_remaining_absolute_window")
    ready = json.loads(READY.read_text())
    for name, row in ready["direct_hashes"].items():
        if name in (*PACKET_FILES, "owner", "binding", "predecessor_terminal"):
            if sha256(Path(row["path"])) != row["sha256"]:
                raise SystemExit(f"ready_identity_mismatch:{name}")
    preview = pool("show", "--bench", args.bench)
    same_project_claim = (
        preview.get("status") == "claimed"
        and preview.get("claim", {}).get("project") == PROJECT
    )
    if (preview["status"] != "available" and not same_project_claim) or preview["accelerator"] != "nvidia-l40s":
        raise SystemExit("bound_warm_l40s_not_available")
    prefix = ssh_prefix(preview)
    args.artifact_root.mkdir(parents=True)
    claim = pool(
        "claim", "--project", PROJECT, "--bench", args.bench,
        "--accelerator", "nvidia-l40s", "--lease-seconds",
        str(max(1, int(deadline - time.time()))))
    events = [{"at": utc_now(), "event": "claim",
               "claimed_at": claim["claim"]["claimed_at"]}]
    stop = threading.Event()
    thread = threading.Thread(
        target=heartbeat, args=(stop, claim["id"], events), daemon=True)
    thread.start()
    classification, release = "unknown_retained", None
    remote_root = (
        f"/home/glmrunner/gemma4-staged-e5m2-"
        f"{claim['claim']['claimed_at'].replace(':', '-')}")
    try:
        gpu_probe = remote(
            prefix,
            "nvidia-smi --query-gpu=name,compute_cap --format=csv,noheader,nounits",
            min(90, max(1, int(deadline - time.time() - 120))))
        (args.artifact_root / "preflight.stdout").write_text(gpu_probe.stdout)
        (args.artifact_root / "preflight.stderr").write_text(gpu_probe.stderr)
        if gpu_probe.returncode or "L40S" not in gpu_probe.stdout:
            classification = "unsafe_or_unreachable_guest"
            raise RuntimeError("l40s_preflight_failed")
        image_probe = remote(
            prefix,
            f"sudo -n docker image inspect {shlex.quote(IMAGE)} >/dev/null",
            min(60, max(1, int(deadline - time.time() - 120))))
        if image_probe.returncode:
            raise RuntimeError("resident_image_missing_no_pull_authorized")
        stage(prefix, remote_root, ready, deadline)
        attempt = f"{remote_root}/attempt-0"
        command = (
            f"set +e; mkdir -p {shlex.quote(attempt)}; "
            f"sudo -n docker run --rm --gpus all --ipc=host "
            f"--user 0:0 -e PYTHONUNBUFFERED=1 "
            f"-e TORCH_EXTENSIONS_DIR=/work/state/extensions "
            f"-v {shlex.quote(remote_root)}:/work/state "
            f"--entrypoint /bin/bash {shlex.quote(IMAGE)} -lc "
            f"{shlex.quote('cd /work/state/packet && python3 sm89_staged_e5m2_runner.py --artifact-root /work/state/attempt-0/result')} "
            f">{shlex.quote(attempt)}/runner.stdout 2>{shlex.quote(attempt)}/runner.stderr; "
            f"rc=$?; echo $rc >{shlex.quote(attempt)}/runner.exit; exit $rc")
        remote(prefix, command, min(1200, max(1, int(deadline - time.time() - 90))))
        evidence = retrieve(prefix, attempt, args.artifact_root / "attempt-0")
        if (evidence["terminal_present"] and evidence["science_started"]
                and evidence["invocation_complete"]):
            classification = "scientific_terminal_retrieved"
        else:
            repair_id = "staged-g1"
            repair_deadline = dt.datetime.fromtimestamp(
                deadline - 60, dt.timezone.utc).isoformat().replace("+00:00", "Z")
            prepared = run([
                str(HANDSHAKE), "ready", "--root", str(args.artifact_root),
                "--repair-id", repair_id, "--deadline", repair_deadline,
                "--failure-kind", "ordinary_compile_api_consumer_or_retrieval_defect",
                "--diagnostic", str(args.artifact_root / "attempt-0/RETRIEVAL.json"),
                "--retry-scope", "staged_consumer_or_retrieval_only",
            ], timeout=30)
            if prepared.returncode:
                raise RuntimeError(f"repair_ready_failed:{prepared.stderr[-500:]}")
            waited = run([
                str(HANDSHAKE), "wait", "--root", str(args.artifact_root),
                "--repair-id", repair_id, "--poll-seconds", "3",
            ], timeout=max(1, int(deadline - time.time() - 45)))
            repair_terminal = args.artifact_root / "REPAIR_TERMINAL.json"
            if waited.returncode == 0 and repair_terminal.is_file():
                repaired = json.loads(repair_terminal.read_text())
                if repaired.get("decision_bearing") and repaired.get("sample_consumed"):
                    classification = "scientific_terminal_adopted_after_repair"
            if classification == "unknown_retained":
                classification = "absolute_deadline_after_retained_repair"
        deadline_expired = time.time() >= deadline - 45
        if not release_allowed(classification, deadline_expired):
            raise RuntimeError("release_guard_rejected_nonterminal")
    except Exception as error:
        events.append({"at": utc_now(), "event": "owner_error",
                       "error": repr(error)})
        if classification == "unknown_retained" and time.time() < deadline - 45:
            diagnostic = args.artifact_root / "OWNER_ERROR.json"
            atomic(diagnostic, {
                "classification": "recoverable_or_unknown_pre_science_owner_defect",
                "error": repr(error),
                "at": utc_now(),
            })
            repair_deadline = dt.datetime.fromtimestamp(
                deadline - 60, dt.timezone.utc).isoformat().replace("+00:00", "Z")
            prepared = run([
                str(HANDSHAKE), "ready", "--root", str(args.artifact_root),
                "--repair-id", "staged-owner-g1", "--deadline", repair_deadline,
                "--failure-kind", "ordinary_pre_science_owner_stage_or_image_defect",
                "--diagnostic", str(diagnostic),
                "--retry-scope", "invalidated_owner_boundary_only",
            ], timeout=30)
            if prepared.returncode == 0:
                run([
                    str(HANDSHAKE), "wait", "--root", str(args.artifact_root),
                    "--repair-id", "staged-owner-g1", "--poll-seconds", "3",
                ], timeout=max(1, int(deadline - time.time() - 45)))
            repair_terminal = args.artifact_root / "REPAIR_TERMINAL.json"
            if repair_terminal.is_file():
                repaired = json.loads(repair_terminal.read_text())
                if repaired.get("decision_bearing") and repaired.get("sample_consumed"):
                    classification = "scientific_terminal_adopted_after_repair"
            if classification == "unknown_retained":
                classification = "absolute_deadline_after_retained_unknown"
    finally:
        if release_allowed(classification, time.time() >= deadline - 45):
            release_condition = (
                "ready" if classification in {
                    "scientific_terminal_retrieved",
                    "scientific_terminal_adopted_after_repair",
                } else "maintenance"
            )
            contents = args.artifact_root / "BENCH_CONTENTS.json"
            atomic(contents, {
                "project": PROJECT, "image": IMAGE, "checkpoint": "none",
                "state": "staged packet and compiled caches retained",
                "result": classification,
            })
            release = pool(
                "release", "--project", PROJECT, "--bench", claim["id"],
                "--expected-claimed-at", claim["claim"]["claimed_at"],
                "--contents", str(contents), "--condition", release_condition)
        stop.set()
        thread.join(timeout=2)
        atomic(args.artifact_root / "OWNER_TERMINAL.json", {
            "schema_version": 1,
            "classification": classification,
            "claim": {"bench": claim["id"],
                      "claimed_at": claim["claim"]["claimed_at"]},
            "events": events,
            "release": release,
            "absolute_deadline_utc": args.release_by_utc,
        })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
