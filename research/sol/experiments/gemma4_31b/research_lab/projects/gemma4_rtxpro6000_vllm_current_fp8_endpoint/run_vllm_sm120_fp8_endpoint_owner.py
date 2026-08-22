#!/usr/bin/env python3
"""Retained-claim owner for one director-bound vLLM Gemma 4 FP8 c32 sample."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = "gemma4_rtxpro6000_vllm_current_fp8_endpoint"
BENCH = "rtxpro6000-gemma4-fp8-f4nbtoufbwf66f"
TOOLS = ROOT.parents[6] / "research" / "factory" / "tools"
PAIR, REPAIR = TOOLS / "lab-endpoint-pair", TOOLS / "repair-handshake"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
MANIFEST = "864f24f4631315cd17cc8a3ff1ea57b2725d2a24f29c45778b101f16b5228a4f"
WORKLOAD = "357f22f350a8c0f11df5e1a93f1cd19e4b2eb2d329c75ed993f8dda2cf72338c"
IDENTITY = "7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d"
PAYLOADS = "60630a80335d5a95ebae87dd2d852c6cb8749a0b92e8617261ec6750b64a794c"
VLLM_SOURCE_COMMIT = "6f00a1ae3bd4b86168667bce673998218f461c0f"
WORKLOAD_PATH = ROOT / "inputs" / "c32_requests.jsonl"
NATIVE_RUNTIME = Path("/workspace/vllm-sm120-native-runtime")
VLLM_VERSION = "0.26.0"
VLLM_WHEEL_NAME = "vllm-0.26.0+cu129-cp38-abi3-manylinux_2_28_x86_64.whl"
VLLM_WHEEL_URL = "https://github.com/vllm-project/vllm/releases/download/v0.26.0/vllm-0.26.0%2Bcu129-cp38-abi3-manylinux_2_28_x86_64.whl"
VLLM_WHEEL_SHA256 = "6ce4ca30616f0a35810391015622b197a7b8b267ed27f8716f0789db79ff578b"
ENDPOINT_PATH = "/v1/completions"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            result.update(chunk)
    return result.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"json_object_required:{path}")
    return value


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as file:
        json.dump(value, file, indent=2, sort_keys=True)
        file.write("\n")
        temporary = Path(file.name)
    temporary.replace(path)


def require_workload() -> Path:
    if not WORKLOAD_PATH.is_file() or WORKLOAD_PATH.stat().st_size != 893666:
        raise RuntimeError("authoritative_c32_workload_missing_or_size_invalid")
    if digest(WORKLOAD_PATH) != WORKLOAD:
        raise RuntimeError("authoritative_c32_workload_digest_invalid")
    return WORKLOAD_PATH


def require_native_offline_result() -> Path:
    result_path = ROOT / "NATIVE_VLLM_OWNER_OFFLINE_RESULT.json"
    result = load(result_path)
    distribution = result.get("distribution", {})
    owner = result.get("owner", {})
    if not (result.get("classification") == "supported_offline_native_runtime_prebinding" and owner.get("sha256") == digest(Path(__file__)) and distribution.get("wheel_url") == VLLM_WHEEL_URL and distribution.get("wheel_sha256") == VLLM_WHEEL_SHA256 and result.get("workload", {}).get("sha256") == WORKLOAD):
        raise RuntimeError("native_offline_result_identity_invalid")
    return result_path


def command(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, check=False, timeout=timeout)


def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return command([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args], 60)


def remaining(deadline: str) -> float:
    end = dt.datetime.fromisoformat(deadline.replace("Z", "+00:00"))
    return max(1, (end - dt.datetime.now(dt.timezone.utc)).total_seconds())


def save(artifact: Path, name: str, result: subprocess.CompletedProcess[str]) -> None:
    (artifact / f"{name}.stdout.log").write_text(result.stdout)
    (artifact / f"{name}.stderr.log").write_text(result.stderr)


def ssh(binding: dict[str, Any]) -> list[str]:
    resource = binding["bench"]["resource"]
    return ["ssh", "-p", str(resource["ssh_port"]), "-i", resource["ssh_identity_path"], "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={resource['known_hosts_namespace']}", f"{resource['ssh_user']}@{resource['public_ipv4']}"]


def remote(binding: dict[str, Any], script: str, timeout: float) -> subprocess.CompletedProcess[str]:
    return command([*ssh(binding), f"bash -lc {shlex.quote(script)}"], timeout)


def binding_contract(path: Path) -> dict[str, Any]:
    binding = load(path)
    bench = binding.get("bench", {})
    resource = bench.get("resource", {})
    native = binding.get("native_vllm", {})
    lifecycle = binding.get("lifecycle", {})
    valid = (binding.get("project") == PROJECT and binding.get("claim_allowed") is True and bench.get("id") == BENCH and bench.get("accelerator") == "nvidia-rtx-pro-6000-blackwell-workstation" and bench.get("sm") == "sm_120" and bench.get("checkpoint_revision") == REVISION and bench.get("checkpoint_manifest_sha256") == MANIFEST and isinstance(bench.get("resident_checkpoint_path"), str) and isinstance(bench.get("remote_root"), str) and isinstance(resource.get("public_ipv4"), str) and isinstance(resource.get("ssh_user"), str) and isinstance(resource.get("ssh_port"), int) and isinstance(resource.get("ssh_identity_path"), str) and isinstance(resource.get("known_hosts_namespace"), str) and isinstance(lifecycle.get("owner_deadline_utc"), str) and native.get("version") == VLLM_VERSION and native.get("wheel_url") == VLLM_WHEEL_URL and native.get("wheel_sha256") == VLLM_WHEEL_SHA256)
    if not valid:
        raise RuntimeError("director_bound_vllm_sm120_execution_contract_required")
    if not Path(resource["ssh_identity_path"]).is_file():
        raise RuntimeError("binding_ssh_identity_missing")
    return binding


def heartbeat(stop: threading.Event, artifact: Path) -> None:
    while not stop.wait(40):
        result = pool("heartbeat", "--project", PROJECT, "--bench", BENCH)
        atomic(artifact / "HEARTBEAT.json", {"at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "returncode": result.returncode, "stderr": result.stderr[-1200:]})


def repair(artifact: Path, deadline: str, failure: str, scope: str) -> str:
    repair_id = f"repair-{int(time.time())}"
    diagnostic = artifact / "RECOVERABLE_DIAGNOSTIC.json"
    atomic(diagnostic, {"classification": "recoverable_integration_defect", "failure": failure, "science_consumed": False, "candidate_cuda_invocation_started": False})
    result = command([str(REPAIR), "hold", "--root", str(artifact), "--repair-id", repair_id, "--deadline", deadline, "--failure-kind", "integration", "--diagnostic", str(diagnostic), "--retry-scope", scope], remaining(deadline))
    save(artifact, "repair-handshake", result)
    if result.returncode:
        raise RuntimeError("repair_handshake_wait_failed")
    try:
        request = json.loads(result.stdout)
        if request.get("state") != "requested" or request.get("request", {}).get("retry_scope") != scope:
            raise ValueError("unexpected_repair_request")
    except (json.JSONDecodeError, ValueError, TypeError) as error:
        raise RuntimeError("repair_handshake_request_invalid") from error
    return scope


def strict_absent_census(binding: dict[str, Any], artifact: Path) -> None:
    """Accept the already-stopped predecessor only after proving a quiescent GPU."""
    lines = ["set -euo pipefail", "test ! -e /proc/16036", "test -z \"$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | tr -d '[:space:]')\"", "used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 | tr -dc 0-9)", "test \"${used:-999999}\" -le 1024"]
    result = remote(binding, "\n".join(lines), 180)
    save(artifact, "strict-absent-census", result)
    if result.returncode:
        raise RuntimeError("predecessor_not_absent_or_gpu_not_quiescent")


def launch_native_vllm(binding: dict[str, Any], artifact: Path, reuse_runtime: bool = False) -> int:
    bench = binding["bench"]
    root, checkpoint = Path(bench["remote_root"]), Path(bench["resident_checkpoint_path"])
    port = int(bench.get("private_vllm_port", 19124))
    wheel, wheel_part = NATIVE_RUNTIME / VLLM_WHEEL_NAME, NATIVE_RUNTIME / f"{VLLM_WHEEL_NAME}.part"
    venv = NATIVE_RUNTIME / "venv"
    lines = ["set -euo pipefail", f"test -d {shlex.quote(str(checkpoint))}", f"mkdir -p {shlex.quote(str(root))} {shlex.quote(str(NATIVE_RUNTIME))}", f"test ! -e {shlex.quote(str(root / 'server.pid'))}"]
    if reuse_runtime:
        lines.extend([f"test -x {shlex.quote(str(venv / 'bin/vllm'))}", f"test -f {shlex.quote(str(root / 'NATIVE_RUNTIME_IDENTITY.json'))}"])
    else:
        lines.extend([f"if test -f {shlex.quote(str(wheel))}; then printf '%s  %s\\n' {shlex.quote(VLLM_WHEEL_SHA256)} {shlex.quote(str(wheel))} | sha256sum -c -; else curl --fail --location --retry 3 --continue-at - --output {shlex.quote(str(wheel_part))} {shlex.quote(VLLM_WHEEL_URL)}; printf '%s  %s\\n' {shlex.quote(VLLM_WHEEL_SHA256)} {shlex.quote(str(wheel_part))} | sha256sum -c -; mv {shlex.quote(str(wheel_part))} {shlex.quote(str(wheel))}; fi", f"/usr/bin/uv venv --python /usr/bin/python3.12 --system-site-packages {shlex.quote(str(venv))}", f"/usr/bin/uv pip install --python {shlex.quote(str(venv / 'bin/python'))} --no-cache {shlex.quote(str(wheel))}", f"VLLM_WHEEL_SHA256={shlex.quote(VLLM_WHEEL_SHA256)} {shlex.quote(str(venv / 'bin/python'))} - <<'PY' > {shlex.quote(str(root / 'NATIVE_RUNTIME_IDENTITY.json'))}\nimport importlib.metadata as metadata, json, os, torch, vllm\nprint(json.dumps(dict(wheel_sha256=os.environ['VLLM_WHEEL_SHA256'], vllm_version=metadata.version('vllm'), vllm_file=vllm.__file__, torch_version=torch.__version__, torch_cuda=torch.version.cuda), sort_keys=True))\nPY", f"{shlex.quote(str(venv / 'bin/python'))} - <<'PY' > {shlex.quote(str(root / 'NATIVE_IMPORT_PREFLIGHT.json'))}\nimport json, torch\nassert torch.cuda.is_available(), 'cuda_unavailable'\nfrom vllm.model_executor.models.gemma4 import Gemma4ForCausalLM\nfrom vllm.model_executor.layers.quantization.fp8 import Fp8Config\nprint(json.dumps(dict(gemma4_class=Gemma4ForCausalLM.__name__, fp8_config=Fp8Config.__name__, capability=torch.cuda.get_device_capability()), sort_keys=True))\nPY"])
    lines.extend([f"nvidia_libs=$(find {shlex.quote(str(venv / 'lib/python3.12/site-packages/nvidia'))} -type d -name lib -printf '%p:' | sed 's/:$//')", "test -n \"$nvidia_libs\"", "export LD_LIBRARY_PATH=\"$nvidia_libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}\"", f"nohup {shlex.quote(str(venv / 'bin/vllm'))} serve {shlex.quote(str(checkpoint))} --served-model-name google/gemma-4-31B-it --dtype bfloat16 --quantization fp8 --max-model-len 5000 --max-num-seqs 32 --max-num-batched-tokens 65536 --host 127.0.0.1 --port {port} > {shlex.quote(str(root / 'server.log'))} 2>&1 < /dev/null & echo $! > {shlex.quote(str(root / 'server.pid'))}", f"for n in $(seq 1 180); do curl -fsS http://127.0.0.1:{port}/v1/models > {shlex.quote(str(root / 'models.json'))} && exit 0; pid=$(cat {shlex.quote(str(root / 'server.pid'))}); kill -0 \"$pid\" 2>/dev/null || {{ tail -200 {shlex.quote(str(root / 'server.log'))} > {shlex.quote(str(root / 'server-fatal.log'))}; exit 44; }}; sleep 2; done", "exit 45"])
    result = remote(binding, "\n".join(lines), min(900, remaining(binding["lifecycle"]["owner_deadline_utc"])))
    save(artifact, "native-vllm-launch", result)
    if result.returncode:
        raise RuntimeError("native_vllm_runtime_or_server_launch_failed")
    return connect_tunnel(binding, artifact, port)


def connect_tunnel(binding: dict[str, Any], artifact: Path, remote_port: int) -> int:
    local_port = int(binding["bench"].get("controller_tunnel_port", 29124))
    tunnel_state = artifact / "TUNNEL.json"
    if tunnel_state.is_file():
        prior = load(tunnel_state)
        pid = prior.get("pid")
        if isinstance(pid, int):
            try:
                Path(f"/proc/{pid}").stat()
                return local_port
            except FileNotFoundError:
                pass
    tunnel = subprocess.Popen([*ssh(binding)[:-1], "-N", "-L", f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}", ssh(binding)[-1]], stdin=subprocess.DEVNULL, stdout=(artifact / "tunnel.stdout.log").open("w"), stderr=(artifact / "tunnel.stderr.log").open("w"), start_new_session=True)
    atomic(tunnel_state, {"pid": tunnel.pid, "local_port": local_port, "remote_port": remote_port})
    time.sleep(1)
    if tunnel.poll() is not None:
        raise RuntimeError("private_vllm_tunnel_failed")
    return local_port


def retained_server_port(binding: dict[str, Any], artifact: Path) -> int:
    bench = binding["bench"]
    root = Path(bench["remote_root"])
    port = int(bench.get("private_vllm_port", 19124))
    lines = ["set -euo pipefail", f"pid=$(cat {shlex.quote(str(root / 'server.pid'))})", "kill -0 \"$pid\"", f"curl -fsS http://127.0.0.1:{port}/v1/models > {shlex.quote(str(root / 'models.json'))}", "test -n \"$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | tr -d '[:space:]')\""]
    result = remote(binding, "\n".join(lines), 180)
    save(artifact, "retained-server-census", result)
    if result.returncode:
        raise RuntimeError("retained_native_vllm_server_not_healthy")
    return connect_tunnel(binding, artifact, port)


def write_terminal(pair_root: Path, artifact: Path, binding: dict[str, Any]) -> dict[str, Any]:
    run_json = load(pair_root / "run.json")
    progress = run_json.get("progress", {}).get("control", {})
    complete = progress.get("complete_requests") == 32 and progress.get("successful_requests") == 32
    result = {"schema_version": 1, "classification": "scientific_terminal" if complete else "invalid_endpoint_result", "science_consumed": complete, "science_started": True, "candidate_cuda_invocation_started": None, "application_error_aware": True, "workload": {"concurrency": 32, "prompt_tokens": 4214, "output_tokens": 358, "request_identity_sha256": IDENTITY, "payloads_sha256": PAYLOADS}, "pair_run": str(pair_root / "run.json"), "pair_run_sha256": digest(pair_root / "run.json"), "progress": progress, "experimental_rate_usd_per_hour": binding["bench"].get("metered_usd_per_hour")}
    atomic(artifact / "VLLM_SM120_FP8_ENDPOINT_TERMINAL.json", result)
    return result


def archive_partial_endpoint_root(pair_root: Path) -> Path:
    if not pair_root.exists():
        raise RuntimeError("endpoint_pair_output_missing")
    archived = pair_root.with_name(f"{pair_root.name}-invalid-{int(time.time())}")
    pair_root.replace(archived)
    return archived


def run_endpoint_consumer(pair_root: Path, port: int, deadline: str) -> subprocess.CompletedProcess[str]:
    endpoint = f"http://127.0.0.1:{port}{ENDPOINT_PATH}"
    return command([str(PAIR), "run", "--workload", str(require_workload()), "--output-dir", str(pair_root), "--control-url", endpoint, "--candidate-url", endpoint, "--arm-order", "control", "--concurrency", "32", "--timeout-seconds", "900"], min(3600, remaining(deadline)))


def image_consumer_terminal(artifact: Path, binding: dict[str, Any]) -> int:
    terminal = {"schema_version": 1, "classification": "external_runtime_image_consumer_unavailable", "science_consumed": False, "science_started": False, "candidate_cuda_invocation_started": False, "evidence": {"launch_stdout": str(artifact / "vllm-launch.stdout.log"), "launch_stderr": str(artifact / "vllm-launch.stderr.log"), "required_image": binding["bench"]["vllm_image"]}}
    atomic(artifact / "VLLM_SM120_FP8_ENDPOINT_TERMINAL.json", terminal)
    contents = artifact / "BENCH_CONTENTS.json"
    atomic(contents, {"checkpoint_manifest_sha256": MANIFEST, "checkpoint_revision": REVISION, "server_state": "No compatible local consumer exists for the director-bound vLLM image; checkpoint and CUDA caches retained for director inspection.", "vllm_image": binding["bench"]["vllm_image"]})
    released = pool("release", "--project", PROJECT, "--bench", BENCH, "--condition", "maintenance", "--contents", str(contents))
    save(artifact, "release", released)
    return 0 if released.returncode == 0 else 72


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-binding", type=Path)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--preclaim-only", action="store_true")
    parser.add_argument("--resume-claimed", action="store_true")
    parser.add_argument("--endpoint-consumer-only", action="store_true")
    args = parser.parse_args()
    if args.preclaim_only:
        if not all(path.is_file() for path in (PAIR, REPAIR)):
            raise RuntimeError("offline_owner_dependencies_missing")
        workload = require_workload()
        native_result = require_native_offline_result()
        print(json.dumps({"preclaim": "pass", "owner_sha256": digest(Path(__file__)), "native_offline_result": str(native_result), "vllm_source_commit": VLLM_SOURCE_COMMIT, "workload": str(workload), "workload_sha256": WORKLOAD, "gpu_pool_called": False}, sort_keys=True))
        return 0
    if args.execution_binding is None:
        raise RuntimeError("director_execution_binding_required")
    binding = binding_contract(args.execution_binding)
    require_workload()
    artifact = args.artifact_root.resolve()
    if args.resume_claimed:
        if not (artifact / "RECOVERABLE_DIAGNOSTIC.json").is_file():
            raise RuntimeError("resume_requires_retained_repair_artifact")
        artifact.mkdir(parents=True, exist_ok=True)
    else:
        artifact.mkdir(parents=True, exist_ok=False)
        claimed = pool("claim", "--project", PROJECT, "--bench", BENCH)
        save(artifact, "claim", claimed)
        if claimed.returncode:
            atomic(artifact / "VLLM_SM120_FP8_ENDPOINT_TERMINAL.json", {"classification": "atomic_claim_failed", "science_consumed": False})
            return 2
    stop = threading.Event()
    threading.Thread(target=heartbeat, args=(stop, artifact), daemon=True).start()
    try:
        if args.endpoint_consumer_only:
            if not args.resume_claimed:
                raise RuntimeError("endpoint_consumer_only_requires_retained_claim")
            port = retained_server_port(binding, artifact)
            pair_root = artifact / f"endpoint-pair-repair-{int(time.time())}"
            while True:
                result = run_endpoint_consumer(pair_root, port, binding["lifecycle"]["owner_deadline_utc"])
                save(artifact, "endpoint-pair", result)
                if result.returncode or not (pair_root / "run.json").is_file():
                    archived = archive_partial_endpoint_root(pair_root)
                    atomic(artifact / "ENDPOINT_CONSUMER_REPAIR.json", {"endpoint_path": ENDPOINT_PATH, "failure": "endpoint_pair_consumer_failed", "invalid_output_root": str(archived), "invalid_output_root_run_sha256": digest(archived / "run.json") if (archived / "run.json").is_file() else None, "retry_scope": "endpoint_consumer_only"})
                    repair(artifact, binding["lifecycle"]["owner_deadline_utc"], "endpoint_pair_consumer_failed", "endpoint_consumer_only")
                    pair_root = artifact / f"endpoint-pair-repair-{int(time.time())}"
                    continue
                terminal = write_terminal(pair_root, artifact, binding)
                if terminal["classification"] == "scientific_terminal":
                    break
                archived = archive_partial_endpoint_root(pair_root)
                atomic(artifact / "ENDPOINT_CONSUMER_REPAIR.json", {"endpoint_path": ENDPOINT_PATH, "failure": "incomplete_or_application_error_c32", "invalid_output_root": str(archived), "invalid_output_root_run_sha256": digest(archived / "run.json"), "retry_scope": "endpoint_consumer_only"})
                repair(artifact, binding["lifecycle"]["owner_deadline_utc"], "incomplete_or_application_error_c32", "endpoint_consumer_only")
                pair_root = artifact / f"endpoint-pair-repair-{int(time.time())}"
            contents = artifact / "BENCH_CONTENTS.json"
            atomic(contents, {"checkpoint_manifest_sha256": MANIFEST, "checkpoint_revision": REVISION, "server_state": "Healthy private native vLLM endpoint retained; director chooses reuse or removal.", "native_vllm_wheel_sha256": VLLM_WHEEL_SHA256})
            released = pool("release", "--project", PROJECT, "--bench", BENCH, "--condition", "maintenance", "--contents", str(contents))
            save(artifact, "release", released)
            return 0 if released.returncode == 0 else 72
        retry_scope: str | None = None
        while True:
            try:
                strict_absent_census(binding, artifact)
                port = launch_native_vllm(binding, artifact, reuse_runtime=retry_scope == "server_launch_or_health_only")
                break
            except RuntimeError as error:
                retry_scope = repair(artifact, binding["lifecycle"]["owner_deadline_utc"], str(error), "server_launch_or_health_only")
        atomic(artifact / "SCIENCE_STARTED.json", {"science_started": True, "at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "boundary": "immediately_before_single_c32_submission"})
        pair_root = artifact / "endpoint-pair"
        while True:
            result = run_endpoint_consumer(pair_root, port, binding["lifecycle"]["owner_deadline_utc"])
            save(artifact, "endpoint-pair", result)
            if result.returncode or not (pair_root / "run.json").is_file():
                archived = archive_partial_endpoint_root(pair_root)
                atomic(artifact / "ENDPOINT_CONSUMER_REPAIR.json", {"endpoint_path": ENDPOINT_PATH, "failure": "endpoint_pair_consumer_failed", "invalid_output_root": str(archived), "invalid_output_root_run_sha256": digest(archived / "run.json") if (archived / "run.json").is_file() else None, "retry_scope": "endpoint_consumer_only"})
                retry_scope = repair(artifact, binding["lifecycle"]["owner_deadline_utc"], "endpoint_pair_consumer_failed", "endpoint_consumer_only")
                if retry_scope != "endpoint_consumer_only":
                    raise RuntimeError("endpoint_consumer_retry_scope_invalid")
                pair_root = artifact / f"endpoint-pair-repair-{int(time.time())}"
                continue
            terminal = write_terminal(pair_root, artifact, binding)
            if terminal["classification"] == "scientific_terminal":
                break
            archived = archive_partial_endpoint_root(pair_root)
            atomic(artifact / "ENDPOINT_CONSUMER_REPAIR.json", {"endpoint_path": ENDPOINT_PATH, "failure": "incomplete_or_application_error_c32", "invalid_output_root": str(archived), "invalid_output_root_run_sha256": digest(archived / "run.json"), "retry_scope": "endpoint_consumer_only"})
            retry_scope = repair(artifact, binding["lifecycle"]["owner_deadline_utc"], "incomplete_or_application_error_c32", "endpoint_consumer_only")
            if retry_scope != "endpoint_consumer_only":
                raise RuntimeError("endpoint_consumer_retry_scope_invalid")
            pair_root = artifact / f"endpoint-pair-repair-{int(time.time())}"
        contents = artifact / "BENCH_CONTENTS.json"
        atomic(contents, {"checkpoint_manifest_sha256": MANIFEST, "checkpoint_revision": REVISION, "server_state": "Healthy private native vLLM endpoint retained; director chooses reuse or removal.", "native_vllm_wheel_sha256": VLLM_WHEEL_SHA256})
        released = pool("release", "--project", PROJECT, "--bench", BENCH, "--condition", "maintenance", "--contents", str(contents))
        save(artifact, "release", released)
        return 0 if released.returncode == 0 else 72
    finally:
        stop.set()


if __name__ == "__main__":
    raise SystemExit(main())
