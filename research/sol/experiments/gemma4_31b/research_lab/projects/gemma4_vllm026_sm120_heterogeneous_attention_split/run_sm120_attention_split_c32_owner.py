#!/usr/bin/env python3
"""Future, hash-bound cold-start owner for the SM120 c32 endpoint pair.

Preparation mode is strictly zero-GPU. A later director execution binding is
required before any pool, SSH, or provider-facing operation. The live owner
keeps the claim through repairs and releases only after a complete paired
terminal or an explicit unsafe/deadline boundary.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
REPO = HERE.parents[6]
PROJECT = "gemma4_vllm026_sm120_heterogeneous_attention_split"
PREPARATION = HERE / "DIRECTOR_SM120_ATTENTION_C32_ENDPOINT_PREPARATION_20260729T1110Z.json"
DISPOSITION = HERE / "SM120_ATTENTION_PATH_PROOF_CAUSAL_DISPOSITION.json"
ENDPOINT = HERE / "sm120_attention_split_c32_endpoint.py"
WORKLOAD = HERE.parent / "gemma4_rtxpro6000_vllm_current_fp8_endpoint" / "inputs" / "c32_requests.jsonl"
MANIFEST_AUTHORITY = HERE.parent / "gemma4_rtxpro6000_vllm_current_fp8_endpoint" / "NATIVE_VLLM_OWNER_OFFLINE_RESULT.json"
WORKLOAD_SHA256 = "357f22f350a8c0f11df5e1a93f1cd19e4b2eb2d329c75ed993f8dda2cf72338c"
MANIFEST_SHA256 = "864f24f4631315cd17cc8a3ff1ea57b2725d2a24f29c45778b101f16b5228a4f"
TRANSFER_MANIFEST_SHA256 = "e9da34db5ed8e7dce27e242088733cbf09ad489de451f8634b4afbe671a8f8b1"
DISPOSITION_SHA256 = "bc322c955bedf867e77e64ae3b315350d26eefd2544acd448ed22b3b366cef63"
WHEEL_SHA256 = "6ce4ca30616f0a35810391015622b197a7b8b267ed27f8716f0789db79ff578b"
WHEEL_URL = "https://github.com/vllm-project/vllm/releases/download/v0.26.0/vllm-0.26.0%2Bcu129-cp38-abi3-manylinux_2_28_x86_64.whl"
IMAGE = "docker.io/vllm/vllm-openai:nightly@sha256:494f9c118fb6684bcdd26bb37c687b16163278c0e18f5c157c9185c2584598b7"
CHECKPOINT = "/workspace/gemma4-31b-it-b9ea41a2887d8607f594846523f94c6cc75ac8a4"
TOOLS = REPO / "research/factory/tools"
REPAIR = TOOLS / "repair-handshake"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"json_object_required:{path}")
    return value


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write("\n")
        tmp = Path(f.name)
    json.loads(tmp.read_text())
    os.replace(tmp, path)


def cmd(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, check=False, timeout=timeout)


def remaining(deadline: str) -> float:
    end = dt.datetime.fromisoformat(deadline.replace("Z", "+00:00"))
    return max(1.0, (end - dt.datetime.now(dt.timezone.utc)).total_seconds())


def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return cmd([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args], 60)


def validate_preparation() -> None:
    if digest(PREPARATION) != "71656729f4d5de5c641126dc20aa47dc59dc0876a8dedd547273fa8baad2ceb4":
        raise RuntimeError("preparation_binding_digest_invalid")
    if digest(DISPOSITION) != DISPOSITION_SHA256:
        raise RuntimeError("causal_disposition_digest_invalid")
    if digest(ENDPOINT) == "" or not ENDPOINT.is_file() or not WORKLOAD.is_file():
        raise RuntimeError("endpoint_or_workload_missing")
    if digest(WORKLOAD) != WORKLOAD_SHA256 or WORKLOAD.stat().st_size != 893666:
        raise RuntimeError("workload_identity_invalid")
    authority = load(MANIFEST_AUTHORITY)
    if authority.get("immutable_scientific_contract", {}).get("checkpoint_manifest_sha256") != MANIFEST_SHA256:
        raise RuntimeError("checkpoint_manifest_authority_invalid")


def binding_contract(path: Path) -> dict[str, Any]:
    binding = load(path)
    if binding.get("project") != PROJECT or binding.get("classification") != "director_sm120_attention_split_c32_execution_binding":
        raise RuntimeError("future_endpoint_execution_binding_required")
    if binding.get("preparation_binding_sha256") != digest(PREPARATION) or binding.get("causal_disposition_sha256") != DISPOSITION_SHA256:
        raise RuntimeError("binding_chain_invalid")
    if binding.get("wheel_sha256") != WHEEL_SHA256 or binding.get("wheel_url") != WHEEL_URL or binding.get("runtime_image") != IMAGE:
        raise RuntimeError("runtime_identity_invalid")
    if binding.get("checkpoint", {}).get("revision") != "b9ea41a2887d8607f594846523f94c6cc75ac8a4" or binding.get("checkpoint", {}).get("manifest_sha256") != MANIFEST_SHA256:
        raise RuntimeError("checkpoint_identity_invalid")
    workload = binding.get("workload", {})
    if workload.get("sha256") != WORKLOAD_SHA256 or workload.get("concurrency") != 32 or workload.get("prompt_tokens") != 4214 or workload.get("output_tokens") != 358:
        raise RuntimeError("workload_contract_invalid")
    if binding.get("attention_config") != {"control_backend":"TRITON_ATTN", "candidate_backend_per_kind":{"sliding_window":"TRITON_ATTN", "full_attention":"FLEX_ATTENTION"}, "flex_block_m":16, "flex_block_n":16, "q_block_size":16, "kv_block_size":16}:
        raise RuntimeError("attention_config_contract_invalid")
    if binding.get("claim_allowed") is not True or not binding.get("bench_id") or not binding.get("absolute_release_deadline_utc"):
        raise RuntimeError("future_claim_and_deadline_required")
    if binding["bench_id"] != "rtxpro6000-sm120-attention-c32-3u5oyb8eazps50":
        raise RuntimeError("unexpected_bound_bench")
    transfer = binding.get("checkpoint", {})
    if transfer.get("transfer_manifest_sha256") != TRANSFER_MANIFEST_SHA256 or not transfer.get("transfer_manifest_path") or not transfer.get("transfer_source_root"):
        raise RuntimeError("checkpoint_transfer_manifest_contract_invalid")
    if binding.get("ssh", {}).get("identity_path") != "/root/.config/nebius/glm-campaign/ssh_ed25519" or not Path(binding["ssh"]["identity_path"]).is_file():
        raise RuntimeError("bound_ssh_identity_invalid")
    if remaining(binding["absolute_release_deadline_utc"]) <= 0:
        raise RuntimeError("future_release_deadline_expired")
    for mode in ("control", "candidate"):
        if not isinstance(binding.get("server_modes", {}).get(mode, {}).get("argv"), list):
            raise RuntimeError(f"server_mode_{mode}_argv_required")
    source = binding.get("no_fallback_source", {})
    if source.get("sha256") != "ec3a1b92b9b30e93c99d4d05177d912a0046ca12d76ba7e1d06d74a483137d52":
        raise RuntimeError("no_fallback_source_identity_invalid")
    return binding


def read_transfer_manifest(binding: dict[str, Any]) -> list[tuple[str, str]]:
    transfer = binding["checkpoint"]
    path = Path(transfer["transfer_manifest_path"])
    if not path.is_file() or digest(path) != TRANSFER_MANIFEST_SHA256:
        raise RuntimeError("transfer_manifest_identity_invalid")
    entries: list[tuple[str, str]] = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]) or "/" in parts[1] or parts[1].startswith("."):
            raise RuntimeError("transfer_manifest_entry_invalid")
        entries.append((parts[0], parts[1]))
    if len(entries) != 8 or len({name for _, name in entries}) != 8:
        raise RuntimeError("transfer_manifest_must_bind_eight_files")
    source = Path(transfer["transfer_source_root"])
    if any(not (source / name).is_file() for _, name in entries):
        raise RuntimeError("transfer_source_file_missing")
    return entries


def rsync_file(binding: dict[str, Any], source: Path, remote_path: str, artifact: Path, label: str, deadline: str) -> None:
    resource = binding["ssh"]
    ssh_options = " ".join(shlex.quote(part) for part in ssh_argv(binding))
    destination = f"{resource['user']}@{resource['host']}:{remote_path}"
    if shutil.which("rsync"):
        result = cmd(["rsync", "--partial", "--append-verify", "--checksum", "--protect-args", "-e", ssh_options, str(source), destination], min(900, remaining(deadline)))
        capture(artifact, f"transfer-{label}", result)
        if result.returncode:
            raise RuntimeError(f"checkpoint_transfer_failed:{label}")
        return
    probe = remote(binding, f"set -e; if test -f {shlex.quote(remote_path)}; then stat -c '%s' {shlex.quote(remote_path)}; else echo 0; fi", min(60, remaining(deadline)))
    capture(artifact, f"transfer-fallback-probe-{label}", probe)
    if probe.returncode:
        raise RuntimeError(f"checkpoint_transfer_probe_failed:{label}")
    try:
        offset = int(probe.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as error:
        raise RuntimeError(f"checkpoint_transfer_probe_unparseable:{label}") from error
    size = source.stat().st_size
    if offset < 0 or offset > size:
        reset = remote(binding, f"truncate -s 0 {shlex.quote(remote_path)}", min(60, remaining(deadline)))
        capture(artifact, f"transfer-fallback-reset-{label}", reset)
        if reset.returncode:
            raise RuntimeError(f"checkpoint_transfer_reset_failed:{label}")
        offset = 0
    if offset < size:
        tail = subprocess.Popen(["tail", "-c", f"+{offset + 1}", str(source)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        sink = subprocess.Popen([*ssh_argv(binding), f"bash -lc {shlex.quote('cat >> ' + shlex.quote(remote_path))}"], stdin=tail.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert tail.stdout is not None
        tail.stdout.close()
        try:
            sink_out, sink_err = sink.communicate(timeout=min(900, remaining(deadline)))
            tail_out, tail_err = tail.communicate(timeout=min(60, remaining(deadline)))
        except subprocess.TimeoutExpired:
            sink.kill()
            tail.kill()
            sink_out, sink_err = sink.communicate()
            tail_out, tail_err = tail.communicate()
            raise RuntimeError(f"checkpoint_transfer_timeout:{label}")
        result = subprocess.CompletedProcess(["ssh", "append", label], sink.returncode or tail.returncode, sink_out.decode(errors="replace"), (sink_err + tail_err).decode(errors="replace"))
        capture(artifact, f"transfer-fallback-{label}", result)
        if result.returncode:
            raise RuntimeError(f"checkpoint_transfer_failed:{label}")


LARGE_CHECKPOINT_NAMES = frozenset({
    "model-00001-of-00002.safetensors",
    "model-00002-of-00002.safetensors",
})


def parallel_transfer_plan(
    entries: list[tuple[str, str]],
    offsets: dict[str, int],
    source_root: Path,
    resident_root: str,
) -> list[dict[str, Any]]:
    """Build the immutable, pre-probed work list before any stream starts."""
    plan: list[dict[str, Any]] = []
    for expected, name in entries:
        if name not in LARGE_CHECKPOINT_NAMES:
            continue
        source = source_root / name
        size = source.stat().st_size
        offset = offsets[name]
        if offset < 0 or offset > size:
            raise RuntimeError(f"parallel_offset_invalid:{name}:{offset}:{size}")
        plan.append({
            "expected_sha256": expected,
            "name": name,
            "source": str(source),
            "remote_part": f"{resident_root}/{name}.part",
            "remote_final": f"{resident_root}/{name}",
            "offset": offset,
            "size": size,
        })
    if len(plan) > 2:
        raise RuntimeError("parallel_large_file_limit_exceeded")
    if len({job["remote_part"] for job in plan}) != len(plan):
        raise RuntimeError("parallel_destination_collision")
    return plan


def terminate_and_wait(processes: list[subprocess.Popen[bytes]]) -> None:
    """Stop a stream pair and reap both processes, including after timeout."""
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def parallel_stream_worker(
    binding: dict[str, Any],
    artifact: Path,
    job: dict[str, Any],
    generation: str,
    deadline: str,
    state: dict[str, Any],
) -> None:
    """Append one already-bound suffix, then verify and atomically finalize it."""
    label = str(job["name"])
    capture_label = f"{generation}-{label}"
    deadline_at = dt.datetime.fromisoformat(deadline.replace("Z", "+00:00"))
    if dt.datetime.now(dt.timezone.utc) >= deadline_at:
        raise RuntimeError(f"parallel_child_absolute_deadline:{label}")
    if job["offset"] == job["size"]:
        verified = remote(
            binding,
            f"set -euo pipefail; printf '%s  %s\\n' {job['expected_sha256']} {shlex.quote(job['remote_part'])} | sha256sum -c - >/dev/null; mv {shlex.quote(job['remote_part'])} {shlex.quote(job['remote_final'])}; printf '%s\\n' FINALIZED",
            min(240, remaining(deadline)),
        )
        capture(artifact, f"{capture_label}-verify", verified)
        if verified.returncode:
            raise RuntimeError(f"parallel_checkpoint_hash_failed:{label}")
        return

    processes: list[subprocess.Popen[bytes]] = []
    try:
        tail = subprocess.Popen(
            ["tail", "-c", f"+{job['offset'] + 1}", job["source"]],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        processes.append(tail)
        sink = subprocess.Popen(
            [*ssh_argv(binding), f"bash -lc {shlex.quote('cat >> ' + shlex.quote(job['remote_part']))}"],
            stdin=tail.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        processes.append(sink)
        assert tail.stdout is not None
        tail.stdout.close()
        with state["lock"]:
            state["children"][label] = processes
        sink_out = b""
        sink_err = b""
        tail_out = b""
        tail_err = b""
        while True:
            if state["abort"].is_set():
                raise RuntimeError(f"parallel_sibling_cancelled:{label}")
            timeout = min(5.0, (deadline_at - dt.datetime.now(dt.timezone.utc)).total_seconds())
            if timeout <= 0:
                raise RuntimeError(f"parallel_child_absolute_deadline:{label}")
            try:
                sink_out, sink_err = sink.communicate(timeout=timeout)
                tail_out, tail_err = tail.communicate(timeout=min(10.0, remaining(deadline)))
                break
            except subprocess.TimeoutExpired:
                if dt.datetime.now(dt.timezone.utc) >= deadline_at:
                    raise RuntimeError(f"parallel_child_absolute_deadline:{label}")
        result = subprocess.CompletedProcess(
            ["ssh", "append", label],
            sink.returncode or tail.returncode,
            (sink_out + tail_out).decode(errors="replace"),
            (sink_err + tail_err).decode(errors="replace"),
        )
        capture(artifact, f"{capture_label}-append", result)
        if result.returncode:
            raise RuntimeError(f"parallel_checkpoint_transfer_failed:{label}")
        verified = remote(
            binding,
            f"set -euo pipefail; printf '%s  %s\\n' {job['expected_sha256']} {shlex.quote(job['remote_part'])} | sha256sum -c - >/dev/null; mv {shlex.quote(job['remote_part'])} {shlex.quote(job['remote_final'])}; printf '%s\\n' FINALIZED",
            min(240, remaining(deadline)),
        )
        capture(artifact, f"{capture_label}-verify", verified)
        if verified.returncode:
            raise RuntimeError(f"parallel_checkpoint_hash_failed:{label}")
    finally:
        with state["lock"]:
            state["children"].pop(label, None)
        if processes and any(process.poll() is None for process in processes):
            terminate_and_wait(processes)


def parallel_stage_large_files(
    binding: dict[str, Any],
    artifact: Path,
    entries: list[tuple[str, str]],
    source_root: Path,
    resident_root: str,
    deadline: str,
) -> list[str]:
    """Probe all large offsets first, then run no more than two distinct streams."""
    generation = f"parallel-staging-{int(time.time())}"
    offsets: dict[str, int] = {}
    probe_status: dict[str, str] = {}
    for expected, name in entries:
        if name not in LARGE_CHECKPOINT_NAMES:
            continue
        final = f"{resident_root}/{name}"
        part = f"{final}.part"
        probe = remote(
            binding,
            f"set -e; if test -f {shlex.quote(final)} && printf '%s  %s\\n' {expected} {shlex.quote(final)} | sha256sum -c - >/dev/null 2>&1; then echo FINAL_MATCH; elif test -f {shlex.quote(part)}; then stat -c '%s' {shlex.quote(part)}; else echo 0; fi",
            min(180, remaining(deadline)),
        )
        capture(artifact, f"{generation}-{name}-offset-probe", probe)
        if probe.returncode or not probe.stdout.strip():
            raise RuntimeError(f"parallel_offset_probe_failed:{name}")
        value = probe.stdout.strip().splitlines()[-1]
        if value == "FINAL_MATCH":
            probe_status[name] = "final_match"
            continue
        else:
            try:
                offsets[name] = int(value)
            except ValueError as error:
                raise RuntimeError(f"parallel_offset_probe_unparseable:{name}") from error
    plan = parallel_transfer_plan(entries, offsets, source_root, resident_root)
    atomic_json(artifact / f"{generation}-OFFSETS.json", {
        "schema_version": 1,
        "generation": generation,
        "max_concurrency": 2,
        "deadline_utc": deadline,
        "offsets": offsets,
        "probe_status": probe_status,
        "jobs": plan,
    })
    pending = plan
    state: dict[str, Any] = {"abort": threading.Event(), "children": {}, "lock": threading.Lock()}
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=min(2, len(pending)) or 1)
    futures = [executor.submit(parallel_stream_worker, binding, artifact, job, generation, deadline, state) for job in pending]
    try:
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except BaseException:
                state["abort"].set()
                with state["lock"]:
                    siblings = [process for pair in state["children"].values() for process in pair]
                terminate_and_wait(siblings)
                raise
    finally:
        state["abort"].set()
        with state["lock"]:
            siblings = [process for pair in state["children"].values() for process in pair]
        terminate_and_wait(siblings)
        executor.shutdown(wait=True, cancel_futures=True)
    return [job["name"] for job in plan]


def bootstrap_checkpoint_and_runtime(binding: dict[str, Any], artifact: Path) -> None:
    transfer = binding["checkpoint"]
    root = transfer["resident_path"]
    source = Path(transfer["transfer_source_root"])
    entries = read_transfer_manifest(binding)
    remote(binding, f"set -euo pipefail; mkdir -p {shlex.quote(root)}; test ! -e {shlex.quote(root + '/CHECKPOINT_TRANSFER_COMPLETE.json')}", min(120, remaining(binding["absolute_release_deadline_utc"])))
    completed: list[str] = []
    large_names = {name for _, name in entries if name in LARGE_CHECKPOINT_NAMES}
    for expected, name in entries:
        if name in large_names:
            continue
        final = f"{root}/{name}"
        part = f"{final}.part"
        probe = remote(binding, f"set -e; if test -f {shlex.quote(final)} && printf '%s  %s\\n' {expected} {shlex.quote(final)} | sha256sum -c - >/dev/null 2>&1; then echo MATCH; elif test -f {shlex.quote(part)} && printf '%s  %s\\n' {expected} {shlex.quote(part)} | sha256sum -c - >/dev/null 2>&1; then mv {shlex.quote(part)} {shlex.quote(final)}; echo FINALIZED_PART; else echo TRANSFER; fi", min(180, remaining(binding["absolute_release_deadline_utc"])))
        capture(artifact, f"transfer-probe-{name}", probe)
        decision = probe.stdout.strip().splitlines()[-1] if probe.stdout.strip() else ""
        if decision == "TRANSFER":
            rsync_file(binding, source / name, part, artifact, name, binding["absolute_release_deadline_utc"])
            verified = remote(binding, f"set -euo pipefail; printf '%s  %s\\n' {expected} {shlex.quote(part)} | sha256sum -c - >/dev/null; mv {shlex.quote(part)} {shlex.quote(final)}; printf '%s\\n' FINALIZED", min(240, remaining(binding["absolute_release_deadline_utc"])))
            capture(artifact, f"transfer-verify-{name}", verified)
            if verified.returncode:
                raise RuntimeError(f"checkpoint_file_hash_failed:{name}")
        elif decision not in {"MATCH", "FINALIZED_PART"}:
            raise RuntimeError(f"checkpoint_probe_invalid:{name}")
        completed.append(name)
    completed.extend(parallel_stage_large_files(binding, artifact, entries, source, root, binding["absolute_release_deadline_utc"]
    ))
    manifest_path = f"{root}/model-files.sha256"
    manifest_part = f"{manifest_path}.part"
    rsync_file(binding, Path(transfer["transfer_manifest_path"]), manifest_part, artifact, "manifest", binding["absolute_release_deadline_utc"])
    verified_manifest = remote(binding, f"set -euo pipefail; printf '%s  %s\\n' {TRANSFER_MANIFEST_SHA256} {shlex.quote(manifest_part)} | sha256sum -c - >/dev/null; mv {shlex.quote(manifest_part)} {shlex.quote(manifest_path)}; printf '%s\\n' FINALIZED", min(240, remaining(binding["absolute_release_deadline_utc"])))
    capture(artifact, "transfer-verify-manifest", verified_manifest)
    if verified_manifest.returncode:
        raise RuntimeError("checkpoint_manifest_hash_failed")
    complete = {"schema_version":1, "classification":"checkpoint_transfer_complete", "manifest_sha256":TRANSFER_MANIFEST_SHA256, "checkpoint_manifest_sha256":MANIFEST_SHA256, "resident_path":root, "files":completed, "expected_bytes":transfer["expected_bytes"]}
    atomic_json(artifact / "CHECKPOINT_TRANSFER.json", complete)
    atomic_json(artifact / "BOOTSTRAP_INTENT.json", {"checkpoint_transfer":complete, "wheel_sha256":WHEEL_SHA256, "wheel_url":WHEEL_URL, "runtime_image":IMAGE})
    bootstrap = remote(binding, f"set -euo pipefail; root=/workspace/vllm-sm120-native-runtime; mkdir -p \"$root\"; wheel=\"$root/vllm-0.26.0+cu129-cp38-abi3-manylinux_2_28_x86_64.whl\"; part=\"$wheel.part\"; if test -f \"$wheel\"; then printf '%s  %s\\n' {WHEEL_SHA256} \"$wheel\" | sha256sum -c -; elif test -f \"$part\"; then curl --fail --location --retry 3 --continue-at - --output \"$part\" {shlex.quote(WHEEL_URL)}; printf '%s  %s\\n' {WHEEL_SHA256} \"$part\" | sha256sum -c -; mv \"$part\" \"$wheel\"; else curl --fail --location --retry 3 --output \"$part\" {shlex.quote(WHEEL_URL)}; printf '%s  %s\\n' {WHEEL_SHA256} \"$part\" | sha256sum -c -; mv \"$part\" \"$wheel\"; fi; test -x /usr/bin/uv; if test ! -x \"$root/venv/bin/python\"; then /usr/bin/uv venv --python /usr/bin/python3.12 --system-site-packages \"$root/venv\"; fi; /usr/bin/uv pip install --python \"$root/venv/bin/python\" --no-cache \"$wheel\"; \"$root/venv/bin/python\" - <<'PY' > \"$root/RUNTIME_IDENTITY.json.part\"\nimport importlib.metadata as m, json, torch, vllm\nassert m.version('vllm') == '0.26.0'\nassert tuple(torch.cuda.get_device_capability()) == (12, 0)\nprint(json.dumps({'wheel_sha256': '{WHEEL_SHA256}', 'vllm_version': m.version('vllm'), 'torch_version': torch.__version__, 'capability': list(torch.cuda.get_device_capability()), 'vllm_file': vllm.__file__}, sort_keys=True))\nPY\npython3 -c 'import json; json.load(open(\"$root/RUNTIME_IDENTITY.json.part\"))'\nmv \"$root/RUNTIME_IDENTITY.json.part\" \"$root/RUNTIME_IDENTITY.json\"; cat \"$root/RUNTIME_IDENTITY.json\"", min(900, remaining(binding["absolute_release_deadline_utc"])))
    capture(artifact, "official-wheel-bootstrap", bootstrap)
    if bootstrap.returncode:
        raise RuntimeError("official_wheel_bootstrap_or_identity_failed")
    atomic_json(artifact / "BOOTSTRAP_COMPLETE.json", {"schema_version":1, "checkpoint_transfer":str(artifact / "CHECKPOINT_TRANSFER.json"), "wheel_sha256":WHEEL_SHA256, "vllm_version":"0.26.0", "torch_capability":[12,0], "official_wheel_url":WHEEL_URL, "runtime_image":IMAGE})


def heartbeat(stop: threading.Event, bench: str, artifact: Path) -> None:
    while not stop.wait(40):
        result = pool("heartbeat", "--project", PROJECT, "--bench", bench)
        atomic_json(artifact / "HEARTBEAT.json", {"at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "returncode": result.returncode, "stderr": result.stderr[-1000:]})


def ssh_argv(binding: dict[str, Any]) -> list[str]:
    resource = binding["ssh"]
    return ["ssh", "-p", str(resource["port"]), "-i", resource["identity_path"], "-c", "aes128-gcm@openssh.com", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={resource['known_hosts_namespace']}", f"{resource['user']}@{resource['host']}"]


def remote(binding: dict[str, Any], script: str, timeout: float) -> subprocess.CompletedProcess[str]:
    return cmd([*ssh_argv(binding), f"bash -lc {shlex.quote(script)}"], timeout)


def capture(artifact: Path, name: str, result: subprocess.CompletedProcess[str]) -> None:
    (artifact / f"{name}.stdout.log").write_text(result.stdout)
    (artifact / f"{name}.stderr.log").write_text(result.stderr)


def wait_repair(artifact: Path, binding: dict[str, Any], failure: str, scope: str) -> str:
    repair_id = f"c32-{int(time.time())}"
    diagnostic = artifact / f"{repair_id}-DIAGNOSTIC.json"
    atomic_json(diagnostic, {"classification":"recoverable_integration_defect", "failure":failure, "retry_scope":scope, "science_consumed":False})
    result = cmd([str(REPAIR), "hold", "--root", str(artifact), "--repair-id", repair_id, "--deadline", binding["absolute_release_deadline_utc"], "--failure-kind", "integration", "--diagnostic", str(diagnostic), "--retry-scope", scope], remaining(binding["absolute_release_deadline_utc"]))
    capture(artifact, f"{repair_id}-handshake", result)
    if result.returncode:
        raise RuntimeError("repair_handshake_failed")
    response = json.loads(result.stdout)
    if response.get("state") != "requested" or response.get("request", {}).get("retry_scope") != scope:
        raise RuntimeError("repair_request_scope_invalid")
    return scope


def run_mode(binding: dict[str, Any], artifact: Path, mode: str, generation: str) -> subprocess.CompletedProcess[str]:
    root = binding["remote_root"]
    spec = binding["server_modes"][mode]
    env = " ".join(f"{shlex.quote(str(k))}={shlex.quote(str(v))}" for k, v in spec.get("environment", {}).items())
    argv = " ".join(shlex.quote(str(x)) for x in spec["argv"])
    port = int(binding.get("remote_port", 19124))
    log = shlex.quote(root + "/server-" + generation + ".log")
    script = "set -euo pipefail\n" + f"test -d {shlex.quote(binding['checkpoint']['resident_path'])}\n" + f"mkdir -p {shlex.quote(root)}\n" + f"test ! -e {shlex.quote(root + '/server.pid')}\n" + f"{env} nohup {argv} --host 127.0.0.1 --port {port} > {log} 2>&1 < /dev/null & echo $! > {shlex.quote(root + '/server.pid')}\n" + f"for n in $(seq 1 180); do curl -fsS http://127.0.0.1:{port}/v1/models > {shlex.quote(root + '/models-' + generation + '.json')} && {{ tail -n 500 {log}; exit 0; }}; pid=$(cat {shlex.quote(root + '/server.pid')}); kill -0 \"$pid\" 2>/dev/null || {{ tail -n 500 {log}; exit 44; }}; sleep 2; done; tail -n 500 {log}; exit 45"
    result = remote(binding, script, min(900, remaining(binding["absolute_release_deadline_utc"])))
    capture(artifact, f"server-{mode}", result)
    return result


def stop_mode(binding: dict[str, Any], artifact: Path) -> None:
    root = binding["remote_root"]
    result = remote(binding, f"set -euo pipefail; test -f {shlex.quote(root + '/server.pid')}; pid=$(cat {shlex.quote(root + '/server.pid')}); kill -TERM \"$pid\"; for n in $(seq 1 60); do kill -0 \"$pid\" 2>/dev/null || exit 0; sleep 1; done; exit 44", 120)
    capture(artifact, "server-stop", result)
    if result.returncode:
        raise RuntimeError("server_generation_did_not_stop")


def connect_tunnel(binding: dict[str, Any], artifact: Path) -> subprocess.Popen[str]:
    local_port = int(binding.get("local_port", 29124))
    remote_port = int(binding.get("remote_port", 19124))
    stdout = (artifact / "tunnel.stdout.log").open("w")
    stderr = (artifact / "tunnel.stderr.log").open("w")
    process = subprocess.Popen([*ssh_argv(binding)[:-1], "-N", "-L", f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}", ssh_argv(binding)[-1]], stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, text=True, start_new_session=True)
    time.sleep(1)
    if process.poll() is not None:
        raise RuntimeError("endpoint_tunnel_failed")
    atomic_json(artifact / "TUNNEL.json", {"pid":process.pid, "local_port":local_port, "remote_port":remote_port})
    return process


def require_path_proof(artifact: Path) -> None:
    control = "\n".join((artifact / f"server-control.{suffix}.log").read_text() for suffix in ("stdout", "stderr") if (artifact / f"server-control.{suffix}.log").is_file())
    candidate = "\n".join((artifact / f"server-candidate.{suffix}.log").read_text() for suffix in ("stdout", "stderr") if (artifact / f"server-candidate.{suffix}.log").is_file())
    if "TRITON_ATTN" not in control:
        raise RuntimeError("control_triton_path_proof_missing")
    if "TRITON_ATTN" not in candidate or "FLEX_ATTENTION" not in candidate:
        raise RuntimeError("candidate_mixed_backend_path_proof_missing")
    atomic_json(artifact / "PATH_PROOF.json", {"control_triton":True, "candidate_triton":True, "candidate_flex":True, "search_streams":["stdout","stderr"], "source_sha256":"ec3a1b92b9b30e93c99d4d05177d912a0046ca12d76ba7e1d06d74a483137d52"})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-binding", type=Path)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--preclaim-only", action="store_true")
    args = parser.parse_args()
    if args.preclaim_only:
        validate_preparation()
        if args.execution_binding is not None:
            binding_contract(args.execution_binding)
            read_transfer_manifest(load(args.execution_binding))
        print(json.dumps({"preclaim":"pass", "owner_sha256":digest(Path(__file__)), "endpoint_sha256":digest(ENDPOINT), "workload_sha256":WORKLOAD_SHA256, "checkpoint_manifest_sha256":MANIFEST_SHA256, "causal_disposition_sha256":DISPOSITION_SHA256, "gpu_pool_called":False, "ssh_called":False}, sort_keys=True))
        return 0
    if args.execution_binding is None:
        raise RuntimeError("director_execution_binding_required")
    binding = binding_contract(args.execution_binding)
    artifact = args.artifact_root.resolve()
    # detached-owner creates the controller state directory before exec.
    # Preserve that immutable PID record and admit only the existing empty
    # controller root; all science outputs remain separate files below it.
    artifact.mkdir(parents=True, exist_ok=True)
    claimed = pool("claim", "--project", PROJECT, "--bench", binding["bench_id"])
    capture(artifact, "claim", claimed)
    if claimed.returncode:
        atomic_json(artifact / "TERMINAL.json", {"classification":"atomic_claim_failed", "science_consumed":False})
        return 2
    stop = threading.Event()
    threading.Thread(target=heartbeat, args=(stop, binding["bench_id"], artifact), daemon=True).start()
    try:
        atomic_json(artifact / "BINDING_SNAPSHOT.json", {"binding_sha256":digest(args.execution_binding), "checkpoint":binding["checkpoint"], "workload_sha256":WORKLOAD_SHA256, "wheel_sha256":WHEEL_SHA256, "runtime_image":IMAGE})
        bootstrap_checkpoint_and_runtime(binding, artifact)
        tunnel = connect_tunnel(binding, artifact)
        for mode, label in (("control", "control_all_triton"), ("candidate", "candidate_50_triton_10_flex")):
            result = run_mode(binding, artifact, mode, mode)
            if result.returncode:
                wait_repair(artifact, binding, f"server_{mode}_launch_failed", "server_launch_or_health_only")
                raise RuntimeError("repair_continuation_requires_new_owner_generation")
            atomic_json(artifact / f"SCIENCE_STARTED_{mode}.json", {"science_started":True, "arm":label, "at_utc":dt.datetime.now(dt.timezone.utc).isoformat()})
            arm_root = artifact / label
            result = cmd([sys.executable, str(ENDPOINT), "--url", f"http://127.0.0.1:{binding.get('local_port', 29124)}", "--arm", label, "--output", str(arm_root), "--timeout", "900"], min(3600, remaining(binding["absolute_release_deadline_utc"])))
            capture(artifact, f"endpoint-{mode}", result)
            terminal = load(arm_root / "ARM_TERMINAL.json") if (arm_root / "ARM_TERMINAL.json").is_file() else {}
            if result.returncode or terminal.get("classification") != "endpoint_arm_complete":
                wait_repair(artifact, binding, f"endpoint_{mode}_incomplete", "endpoint_consumer_only")
                raise RuntimeError("repair_continuation_requires_new_owner_generation")
            atomic_json(artifact / f"{mode.upper()}_TERMINAL.json", terminal)
            stop_mode(binding, artifact)
        require_path_proof(artifact)
        final = {"schema_version":1, "classification":"scientific_endpoint_terminal", "science_consumed":True, "control_terminal":str(artifact / "CONTROL_TERMINAL.json"), "candidate_terminal":str(artifact / "CANDIDATE_TERMINAL.json"), "workload_sha256":WORKLOAD_SHA256, "path_proof_required":True, "release_generation_fenced":True}
        atomic_json(artifact / "TERMINAL.json", final)
        contents = artifact / "BENCH_CONTENTS.json"
        atomic_json(contents, {"checkpoint_manifest_sha256":MANIFEST_SHA256, "checkpoint_revision":"b9ea41a2887d8607f594846523f94c6cc75ac8a4", "server_state":"No resident server; exact immutable checkpoint/runtime/cache state retained."})
        released = pool("release", "--project", PROJECT, "--bench", binding["bench_id"], "--condition", "maintenance", "--contents", str(contents))
        capture(artifact, "release", released)
        if tunnel.poll() is None:
            tunnel.terminate()
        return 0 if released.returncode == 0 else 72
    finally:
        stop.set()


if __name__ == "__main__":
    raise SystemExit(main())
