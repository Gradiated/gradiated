#!/usr/bin/env python3
"""Durable, retained-claim owner for one stock RTX PRO 6000 FP8 c32 endpoint."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import shlex
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = "gemma4_rtxpro6000_fp8_endpoint"
PAIR = ROOT.parents[6] / "research" / "factory" / "tools" / "lab-endpoint-pair"
REPAIR = ROOT.parents[6] / "research" / "factory" / "tools" / "repair-handshake"
CHECKPOINT_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
CHECKPOINT_MANIFEST = "864f24f4631315cd17cc8a3ff1ea57b2725d2a24f29c45778b101f16b5228a4f"
TOKENIZER = "cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f"
IDENTITY = "7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d"
PAYLOADS = "60630a80335d5a95ebae87dd2d852c6cb8749a0b92e8617261ec6750b64a794c"
TRANSFER_ROOT = ROOT.parent / "exact_h200_vllm_baseline_shared_runner" / "artifacts" / "corrected-transfer-view"
TRANSFER_MANIFEST = TRANSFER_ROOT / "model-files.sha256"
TRANSFER_MANIFEST_SHA256 = "e9da34db5ed8e7dce27e242088733cbf09ad489de451f8634b4afbe671a8f8b1"
SETTLED_STAGE_SHA256 = "d0a64c9dc5d04aa1888aed53662f532d9a15d748cb065dcb99e0a172ae525ded"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"json_object_required:{path}")
    return value


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def command(args: list[str], *, timeout: float, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout, cwd=cwd)


def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return command([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args], timeout=60)


def packet_manifest(packet: Path, *, repaired_owner: bool) -> dict[str, Any]:
    manifest = load(packet)
    required = {
        "checkpoint_revision": CHECKPOINT_REVISION,
        "checkpoint_manifest_sha256": CHECKPOINT_MANIFEST,
        "tokenizer_sha256": TOKENIZER,
        "request_identity_sha256": IDENTITY,
        "payloads_sha256": PAYLOADS,
        "concurrency": 32,
        "maximum_canonical_samples": 1,
    }
    if any(manifest.get(key) != value for key, value in required.items()):
        raise RuntimeError("immutable_execution_packet_contract_invalid")
    for member in manifest.get("files", []):
        if repaired_owner and member["path"] == Path(__file__).name:
            continue
        path = ROOT / member["path"]
        if not path.is_file() or path.stat().st_size != member["bytes"] or sha256(path) != member["sha256"]:
            raise RuntimeError(f"packet_member_hash_mismatch:{member['path']}")
    if not PAIR.is_file() or not REPAIR.is_file():
        raise RuntimeError("shared_endpoint_or_repair_tool_missing")
    return manifest


def binding_contract(path: Path, *, already_claimed: bool = False) -> dict[str, Any]:
    binding = load(path)
    bench = binding.get("bench", {})
    lifecycle = binding.get("lifecycle", {})
    resource = bench.get("resource", {})
    required = (
        binding.get("project") == PROJECT,
        binding.get("claim_allowed") is True,
        bench.get("provider") == "runpod",
        bench.get("accelerator") == "nvidia-rtx-pro-6000-blackwell-workstation",
        bench.get("sm") == "sm_120",
        bench.get("gpu_count") == 1,
        bool(bench.get("id")),
        bool(resource.get("public_ipv4")),
        bool(resource.get("ssh_user")),
        bool(resource.get("known_hosts_namespace")),
        bool(resource.get("ssh_identity_path")),
        isinstance(resource.get("ssh_port"), int),
        resource.get("ssh_port") > 0,
        resource.get("ssh_port") < 65536,
        bool(bench.get("checkpoint_reconcile_command")),
        bool(bench.get("server_launch_command")),
        bool(lifecycle.get("claim_start_by_utc")),
        bool(lifecycle.get("owner_deadline_utc")),
    )
    if not all(required):
        raise RuntimeError("director_registered_runpod_sm120_binding_required")
    identity = Path(resource["ssh_identity_path"])
    if not identity.is_file():
        raise RuntimeError("binding_ssh_identity_missing")
    start_by = dt.datetime.fromisoformat(lifecycle["claim_start_by_utc"].replace("Z", "+00:00"))
    # The director's start fence applies to acquisition, not a continuation
    # which inherited the original pool claim after a pre-science repair.
    if not already_claimed and dt.datetime.now(dt.timezone.utc) >= start_by:
        raise RuntimeError("binding_claim_start_fence_expired")
    return binding


def ssh_base(binding: dict[str, Any]) -> list[str]:
    resource = binding["bench"]["resource"]
    return ["ssh", "-p", str(resource["ssh_port"]), "-i", resource["ssh_identity_path"], "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={resource['known_hosts_namespace']}", f"{resource['ssh_user']}@{resource['public_ipv4']}"]


def scp_base(binding: dict[str, Any]) -> list[str]:
    resource = binding["bench"]["resource"]
    return ["scp", "-P", str(resource["ssh_port"]), "-i", resource["ssh_identity_path"], "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={resource['known_hosts_namespace']}"]


def remote(binding: dict[str, Any], script: str, timeout: float) -> subprocess.CompletedProcess[str]:
    # ssh joins trailing argv into a remote shell command.  Keep the complete
    # bash -lc payload as one quoted remote argument; otherwise `bash -lc`
    # receives only the first word (the observed `mkdir: missing operand`).
    return command([*ssh_base(binding), f"bash -lc {shlex.quote(script)}"], timeout=timeout)


def stage_checkpoint(binding: dict[str, Any], artifact: Path) -> Path:
    if not TRANSFER_MANIFEST.is_file() or sha256(TRANSFER_MANIFEST) != TRANSFER_MANIFEST_SHA256:
        raise RuntimeError("controller_model_files_manifest_binding_invalid")
    destination = Path(binding["staging_contract"]["destination"])
    resource = binding["bench"]["resource"]
    target = f"{resource['ssh_user']}@{resource['public_ipv4']}"
    prepare = remote(binding, f"mkdir -p {shlex.quote(str(destination))} && rm -f {shlex.quote(str(destination))}/.model-files.sha256.part", 120)
    (artifact / "stage-prepare.stdout.log").write_text(prepare.stdout); (artifact / "stage-prepare.stderr.log").write_text(prepare.stderr)
    if prepare.returncode: raise RuntimeError("remote_stage_root_prepare_failed")
    copied: list[str] = []
    for line in TRANSFER_MANIFEST.read_text().splitlines():
        digest, name = line.split("  ", 1)
        check = remote(binding, f"test -f {shlex.quote(str(destination / name))} && test \"$(sha256sum {shlex.quote(str(destination / name))} | awk '{{print $1}}')\" = {shlex.quote(digest)}", 120)
        if check.returncode == 0: continue
        source = TRANSFER_ROOT / name
        transfer = command([*scp_base(binding), str(source), f"{target}:{destination}/{name}.part"], timeout=3600)
        (artifact / f"stage-{name}.stdout.log").write_text(transfer.stdout); (artifact / f"stage-{name}.stderr.log").write_text(transfer.stderr)
        if transfer.returncode: raise RuntimeError(f"checkpoint_transfer_failed:{name}")
        finalize = remote(binding, f"test \"$(sha256sum {shlex.quote(str(destination / (name + '.part')))} | awk '{{print $1}}')\" = {shlex.quote(digest)} && mv -f {shlex.quote(str(destination / (name + '.part')))} {shlex.quote(str(destination / name))}", 300)
        if finalize.returncode: raise RuntimeError(f"checkpoint_transfer_verify_failed:{name}")
        copied.append(name)
    manifest_transfer = command([*scp_base(binding), str(TRANSFER_MANIFEST), f"{target}:{destination}/model-files.sha256.part"], timeout=120)
    if manifest_transfer.returncode: raise RuntimeError("remote_model_manifest_transfer_failed")
    verify = remote(binding, f"mv -f {shlex.quote(str(destination / 'model-files.sha256.part'))} {shlex.quote(str(destination / 'model-files.sha256'))} && cd {shlex.quote(str(destination))} && sha256sum -c model-files.sha256", 1800)
    (artifact / "stage-verify.stdout.log").write_text(verify.stdout); (artifact / "stage-verify.stderr.log").write_text(verify.stderr)
    if verify.returncode: raise RuntimeError("remote_model_manifest_verify_failed")
    atomic(artifact / "STAGE_TERMINAL.json", {"classification": "checkpoint_stage_complete", "manifest_sha256": TRANSFER_MANIFEST_SHA256, "destination": str(destination), "copied": copied, "science_consumed": False})
    return destination


def adopt_settled_stage(binding: dict[str, Any], artifact: Path) -> Path:
    """Adopt the completed producer without reopening remote checkpoint bytes."""
    terminal_path = artifact / "STAGE_TERMINAL.json"
    terminal = load(terminal_path)
    expected_destination = binding["staging_contract"]["destination"]
    if (
        sha256(terminal_path) != SETTLED_STAGE_SHA256
        or terminal.get("classification") != "checkpoint_stage_complete"
        or terminal.get("manifest_sha256") != TRANSFER_MANIFEST_SHA256
        or terminal.get("destination") != expected_destination
        or terminal.get("science_consumed") is not False
    ):
        raise RuntimeError("settled_checkpoint_stage_adoption_invalid")
    return Path(expected_destination)


def runtime_import(binding: dict[str, Any], artifact: Path) -> dict[str, Any]:
    """Exercise the installed CUDA runtime once, before server launch or HTTP."""
    probe = """NVRTC_DIR=$(python3 - <<'PY'
import importlib.metadata as metadata
from pathlib import Path
dist = metadata.distribution('nvidia-cuda-nvrtc')
libraries = sorted({str(Path(dist.locate_file(item)).parent) for item in dist.files or [] if Path(item).name == 'libnvrtc.so.13'})
if len(libraries) != 1:
    raise RuntimeError(f'expected_one_libnvrtc_so_13_directory:{libraries}')
print(libraries[0])
PY
)
export LD_LIBRARY_PATH="$NVRTC_DIR:${LD_LIBRARY_PATH:-}"
python3 - <<'PY'
import importlib.metadata as metadata
import json
import os
import sgl_kernel
from sglang.kernels.ops.quantization import fp8_kernel
import torch
print(json.dumps({
    'nvrtc_dir': os.environ['LD_LIBRARY_PATH'].split(':', 1)[0],
    'nvidia_cuda_nvrtc': metadata.version('nvidia-cuda-nvrtc'),
    'sglang': metadata.version('sglang'),
    'sglang_kernel': metadata.version('sglang-kernel'),
    'torch': metadata.version('torch'),
    'cuda_version': torch.version.cuda,
    'compute_capability': list(torch.cuda.get_device_capability()),
    'imports': ['sgl_kernel', 'sglang.kernels.ops.quantization.fp8_kernel'],
}, sort_keys=True))
PY"""
    result = remote(binding, probe, 180)
    (artifact / "runtime-import.stdout.log").write_text(result.stdout)
    (artifact / "runtime-import.stderr.log").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("runtime_target_gpu_import_failed")
    try:
        identity = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise RuntimeError(f"runtime_import_identity_unparseable:{error}") from error
    if identity.get("compute_capability") != [12, 0] or identity.get("nvidia_cuda_nvrtc") != "13.0.88":
        raise RuntimeError("runtime_target_gpu_identity_invalid")
    atomic(artifact / "RUNTIME_IMPORT_TERMINAL.json", {"classification": "target_gpu_runtime_import_complete", "science_consumed": False, **identity})
    return identity


def cuda13_nvcc(binding: dict[str, Any], artifact: Path) -> dict[str, Any]:
    """Provide the CUDA-13 compiler required by SGLang's SM120 RoPE JIT only."""
    probe = """python3 - <<'PY'
import importlib.metadata as metadata
import json
import subprocess
import sys
from pathlib import Path
try:
    version = metadata.version('nvidia-cuda-nvcc')
except metadata.PackageNotFoundError:
    version = None
if version != '13.0.88':
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--break-system-packages', '--no-cache-dir', 'nvidia-cuda-nvcc==13.0.88'], check=True)
dist = metadata.distribution('nvidia-cuda-nvcc')
nvcc = [Path(dist.locate_file(item)) for item in dist.files or [] if Path(item).as_posix().endswith('nvidia/cuda_nvcc/bin/nvcc')]
if len(nvcc) != 1 or not nvcc[0].is_file():
    raise RuntimeError(f'expected_one_cuda13_nvcc:{nvcc}')
version_text = subprocess.run([str(nvcc[0]), '--version'], check=True, capture_output=True, text=True).stdout
if 'release 13.0' not in version_text:
    raise RuntimeError(f'cuda13_nvcc_version_invalid:{version_text}')
print(json.dumps({'nvidia_cuda_nvcc': metadata.version('nvidia-cuda-nvcc'), 'nvcc': str(nvcc[0]), 'cuda_home': str(nvcc[0].parents[1]), 'version': version_text.strip()}, sort_keys=True))
PY"""
    result = remote(binding, probe, 900)
    (artifact / "cuda13-nvcc.stdout.log").write_text(result.stdout)
    (artifact / "cuda13-nvcc.stderr.log").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("cuda13_nvcc_scope_repair_failed")
    try:
        identity = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cuda13_nvcc_identity_unparseable:{error}") from error
    if identity.get("nvidia_cuda_nvcc") != "13.0.88" or not identity.get("nvcc") or not identity.get("cuda_home"):
        raise RuntimeError("cuda13_nvcc_identity_invalid")
    atomic(artifact / "CUDA13_NVCC_TERMINAL.json", {"classification": "sm120_jit_compiler_ready", "science_consumed": False, **identity})
    return identity


def launch_and_wait(binding: dict[str, Any], artifact: Path, checkpoint: Path) -> None:
    resource, remote_root = binding["bench"]["resource"], Path(binding["bench"]["remote_root"])
    log, pid = remote_root / "server.log", remote_root / "server.pid"
    identity = runtime_import(binding, artifact)
    nvrtc_dir = identity["nvrtc_dir"]
    compiler = cuda13_nvcc(binding, artifact)
    cuda_home = compiler["cuda_home"]
    launch = f"mkdir -p {shlex.quote(str(remote_root))} && export CUDA_HOME={shlex.quote(cuda_home)} NVCC={shlex.quote(compiler['nvcc'])} PATH={shlex.quote(cuda_home)}/bin:${{PATH}} LD_LIBRARY_PATH={shlex.quote(nvrtc_dir)}:${{LD_LIBRARY_PATH:-}} && (nohup python3 -m sglang.launch_server --model-path {shlex.quote(str(checkpoint))} --tokenizer-path {shlex.quote(str(checkpoint))} --served-model-name google/gemma-4-31B-it --quantization fp8 --dtype bfloat16 --tp-size 1 --host 127.0.0.1 --port 19123 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.70 --disable-cuda-graph --skip-server-warmup >{shlex.quote(str(log))} 2>&1 & echo $! > {shlex.quote(str(pid))})"
    started = remote(binding, launch, 1800)
    (artifact / "server-launch.stdout.log").write_text(started.stdout); (artifact / "server-launch.stderr.log").write_text(started.stderr)
    if started.returncode: raise RuntimeError("direct_pod_server_launch_failed")
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        health = remote(binding, f"test -s {shlex.quote(str(pid))} && kill -0 $(cat {shlex.quote(str(pid))}) && curl -fsS http://127.0.0.1:19123/health", 45)
        if health.returncode == 0:
            (artifact / "server-health.json").write_text(health.stdout)
            return
        state = remote(binding, f"test -f {shlex.quote(str(pid))} && {{ child=$(cat {shlex.quote(str(pid))}); if kill -0 $child 2>/dev/null; then echo CHILD_ALIVE:$child; else echo CHILD_DEAD:$child; fi; tail -n 100 {shlex.quote(str(log))}; }} || true", 45)
        (artifact / "server-health-probe.log").write_text(state.stdout + state.stderr)
        if "CHILD_DEAD:" in state.stdout:
            raise RuntimeError("direct_pod_server_child_died_before_health")
        time.sleep(5)
    raise RuntimeError("direct_pod_server_health_timeout")


def runtime_manifest(path: Path, packet: Path) -> dict[str, Any]:
    manifest = load(path)
    expected = {
        "project": PROJECT,
        "packet_sha256": sha256(packet),
        "owner_sha256": sha256(Path(__file__)),
        "accelerator": "nvidia-rtx-pro-6000-blackwell-workstation",
        "sm": "sm_120",
        "ssh_port": 40070,
        "checkpoint_revision": CHECKPOINT_REVISION,
        "checkpoint_manifest_sha256": CHECKPOINT_MANIFEST,
        "tokenizer_sha256": TOKENIZER,
        "request_identity_sha256": IDENTITY,
        "payloads_sha256": PAYLOADS,
        "concurrency": 32,
        "maximum_canonical_samples": 1,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise RuntimeError("workstation_preclaim_runtime_manifest_invalid")
    return manifest


def heartbeat(stop: threading.Event, artifact: Path, bench: str) -> None:
    while not stop.wait(40):
        result = pool("heartbeat", "--project", PROJECT, "--bench", bench)
        atomic(artifact / "HEARTBEAT.json", {"at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "returncode": result.returncode, "stderr": result.stderr[-1200:]})


def terminal_from_pair(pair_root: Path, artifact: Path, binding: dict[str, Any]) -> dict[str, Any]:
    run = load(pair_root / "run.json")
    progress = run.get("progress", {}).get("control", {})
    complete = progress.get("complete_requests") == 32 and progress.get("successful_requests") == 32
    terminal = {
        "schema_version": 1,
        "classification": "scientific_terminal" if complete else "invalid_endpoint_result",
        "science_consumed": complete,
        "candidate_cuda_invocation_started": None,
        "science_started": True,
        "workload": {"concurrency": 32, "request_identity_sha256": IDENTITY, "payloads_sha256": PAYLOADS},
        "pair_run": str(pair_root / "run.json"),
        "pair_run_sha256": sha256(pair_root / "run.json"),
        "progress": progress,
        "production_planning_rate_usd_per_hour": 1.55,
        "experimental_rate_usd_per_hour": binding["bench"].get("metered_usd_per_hour"),
    }
    atomic(artifact / "RTXPRO6000_FP8_ENDPOINT_TERMINAL.json", terminal)
    return terminal


def retained_repair(artifact: Path, deadline: str, failure: str, retry_scope: str) -> dict[str, Any]:
    repair_id = f"repair-{int(time.time())}"
    diagnostic = artifact / "RECOVERABLE_DIAGNOSTIC.json"
    atomic(diagnostic, {"classification": "recoverable_pre_science_or_consumer_defect", "failure": failure, "science_consumed": False})
    result = command([str(REPAIR), "hold", "--root", str(artifact), "--repair-id", repair_id, "--deadline", deadline, "--failure-kind", "integration", "--diagnostic", str(diagnostic), "--retry-scope", retry_scope], timeout=max(1, (dt.datetime.fromisoformat(deadline.replace("Z", "+00:00")) - dt.datetime.now(dt.timezone.utc)).total_seconds()))
    (artifact / "repair-handshake.stdout.log").write_text(result.stdout)
    (artifact / "repair-handshake.stderr.log").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("repair_handshake_wait_failed")
    request = load(artifact / ".repair-handshakes" / repair_id / "REPAIR_REQUEST.json")
    if request.get("retry_scope") != retry_scope:
        raise RuntimeError("repair_request_scope_binding_invalid")
    return request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-packet", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--execution-binding", type=Path)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--preclaim-only", action="store_true")
    parser.add_argument("--resume-claimed", action="store_true")
    args = parser.parse_args()
    runtime = runtime_manifest(args.runtime_manifest, args.execution_packet)
    manifest = packet_manifest(args.execution_packet, repaired_owner=True)
    if args.preclaim_only:
        print(json.dumps({"preclaim": "pass", "packet_sha256": sha256(args.execution_packet), "runtime_manifest_sha256": sha256(args.runtime_manifest), "concurrency": manifest["concurrency"], "ssh_port": runtime["ssh_port"]}, sort_keys=True))
        return 0
    if args.execution_binding is None:
        raise RuntimeError("director_registered_execution_binding_required")
    binding = binding_contract(args.execution_binding, already_claimed=args.resume_claimed)
    artifact = args.artifact_root.resolve()
    artifact.mkdir(parents=True, exist_ok=args.resume_claimed)
    bench = binding["bench"]["id"]
    if not args.resume_claimed:
        claim = pool("claim", "--project", PROJECT, "--bench", bench)
        (artifact / "claim.stdout.log").write_text(claim.stdout)
        (artifact / "claim.stderr.log").write_text(claim.stderr)
        if claim.returncode:
            atomic(artifact / "RTXPRO6000_FP8_ENDPOINT_TERMINAL.json", {"classification": "atomic_claim_failed", "science_consumed": False})
            return 2
    stop = threading.Event()
    threading.Thread(target=heartbeat, args=(stop, artifact, bench), daemon=True).start()
    try:
        checkpoint = adopt_settled_stage(binding, artifact) if args.resume_claimed else stage_checkpoint(binding, artifact)
        while True:
            try:
                launch_and_wait(binding, artifact, checkpoint)
                break
            except RuntimeError as error:
                retained_repair(artifact, binding["lifecycle"]["owner_deadline_utc"], str(error), "server_launch_or_health_only")
        marker = {"science_started": True, "boundary": "immediately_before_first_c32_request_submission", "at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
        atomic(artifact / "SCIENCE_STARTED.json", marker)
        endpoint = binding["bench"]["endpoint_url"]
        pair_root = artifact / "endpoint-pair"
        run = command([str(PAIR), "run", "--workload", str(ROOT / "inputs/c32_requests.jsonl"), "--output-dir", str(pair_root), "--control-url", endpoint, "--candidate-url", endpoint, "--arm-order", "control", "--concurrency", "32", "--timeout-seconds", "900"], timeout=3600)
        (artifact / "endpoint-pair.stdout.log").write_text(run.stdout)
        (artifact / "endpoint-pair.stderr.log").write_text(run.stderr)
        if run.returncode or not (pair_root / "run.json").is_file():
            retained_repair(artifact, binding["lifecycle"]["owner_deadline_utc"], "endpoint_pair_consumer_failed", "endpoint_consumer_only")
        terminal = terminal_from_pair(pair_root, artifact, binding)
        if terminal["classification"] != "scientific_terminal":
            retained_repair(artifact, binding["lifecycle"]["owner_deadline_utc"], "incomplete_c32_result", "endpoint_consumer_only")
        contents = artifact / "BENCH_CONTENTS.json"
        atomic(contents, {"checkpoint_manifest_sha256": CHECKPOINT_MANIFEST, "checkpoint_revision": CHECKPOINT_REVISION, "packet_sha256": sha256(args.execution_packet), "server_state": "Leave healthy endpoint resident for a director-selected compatible successor; otherwise maintenance."})
        release = pool("release", "--project", PROJECT, "--bench", bench, "--condition", "maintenance", "--contents", str(contents))
        (artifact / "release.stdout.log").write_text(release.stdout)
        (artifact / "release.stderr.log").write_text(release.stderr)
        return 0 if release.returncode == 0 else 72
    finally:
        stop.set()


if __name__ == "__main__":
    raise SystemExit(main())
