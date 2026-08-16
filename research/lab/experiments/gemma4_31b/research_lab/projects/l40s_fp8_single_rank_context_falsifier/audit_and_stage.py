#!/usr/bin/env python3
import ast
import hashlib
import json
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
PREDECESSOR = PROJECT.parent / "l40s_online_fp8_actual_consumer_floor"
NEBIUS = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
REMOTE_FILES = {
    "fp8_single_rank.py": PROJECT / "fp8_single_rank.py",
    "w4_single_rank.py": PROJECT / "w4_single_rank.py",
    "fp8_actual.py": PREDECESSOR / "fp8_actual.py",
    "w4_actual.py": PREDECESSOR / "w4_actual.py",
}
LOCAL_FILES = {
    **REMOTE_FILES,
    "remote_stage.sh": PROJECT / "remote_stage.sh",
    "assert_identity.py": PROJECT / "assert_identity.py",
    "DIRECTOR_IDENTITY_ASSERTION.json": PROJECT / "artifacts/DIRECTOR_IDENTITY_ASSERTION.json",
    "mla_microbench_control.py": NEBIUS / "mla_microbench_control.py",
    "placement_control.py": NEBIUS / "placement_control.py",
    "owner.py": PROJECT / "owner.py",
}

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    identity = json.loads((PROJECT / "artifacts/DIRECTOR_IDENTITY_ASSERTION.json").read_text())
    files_exist = all(path.is_file() for path in LOCAL_FILES.values())
    manifest = {name: sha(path) for name, path in REMOTE_FILES.items()} if files_exist else {}
    manifest_path = PROJECT / "STAGED_MANIFEST.json"
    manifest_path.write_text(json.dumps({"schema_version": 1, "remote_files": manifest}, indent=2, sort_keys=True) + "\n")
    fp8 = (PROJECT / "fp8_single_rank.py").read_text() if (PROJECT / "fp8_single_rank.py").is_file() else ""
    w4 = (PROJECT / "w4_single_rank.py").read_text() if (PROJECT / "w4_single_rank.py").is_file() else ""
    remote = (PROJECT / "remote_stage.sh").read_text() if (PROJECT / "remote_stage.sh").is_file() else ""
    compile_probe = subprocess.run(["docker", "run", "--rm", "--network=none", "--entrypoint", "python3", IMAGE, "-c", "import inspect,json,vllm; from vllm.distributed.parallel_state import init_distributed_environment,ensure_model_parallel_initialized,destroy_model_parallel,destroy_distributed_environment; from vllm.model_executor.layers.quantization.fp8 import Fp8LinearMethod,Fp8OnlineLinearMethod; from vllm.model_executor.layers.quantization.awq_marlin import AWQMarlinLinearMethod; print(json.dumps({'vllm':vllm.__version__,'init':str(inspect.signature(init_distributed_environment)),'ensure':str(inspect.signature(ensure_model_parallel_initialized)),'destroy_mp':str(inspect.signature(destroy_model_parallel)),'destroy_dist':str(inspect.signature(destroy_distributed_environment)),'fp8':f'{Fp8LinearMethod.__module__}.{Fp8LinearMethod.__name__}','online':f'{Fp8OnlineLinearMethod.__module__}.{Fp8OnlineLinearMethod.__name__}','w4':f'{AWQMarlinLinearMethod.__module__}.{AWQMarlinLinearMethod.__name__}'}))"], capture_output=True, text=True, timeout=180)
    observed = next((json.loads(line) for line in reversed(compile_probe.stdout.splitlines()) if line.startswith("{")), None)
    required_init = "(world_size: int = -1, rank: int = -1, distributed_init_method: str = 'env://', local_rank: int = -1, backend: str = 'nccl'"
    checks = {
        "corrected_identity": identity.get("pass") is True and sha(PROJECT / "artifacts/DIRECTOR_IDENTITY_ASSERTION.json") == "489d59c30ad1fb4766cbb814efdb79de5b1040b6e922cc10686c9e62fec105e8",
        "immutable_staged_files": files_exist and bool(manifest),
        "exact_image_group_api": compile_probe.returncode == 0 and isinstance(observed, dict) and required_init in observed.get("init", "") and "tensor_model_parallel_size" in observed.get("ensure", "") and observed.get("fp8") == "vllm.model_executor.layers.quantization.fp8.Fp8LinearMethod" and observed.get("online") == "vllm.model_executor.layers.quantization.fp8.Fp8OnlineLinearMethod" and observed.get("w4") == "vllm.model_executor.layers.quantization.awq_marlin.AWQMarlinLinearMethod",
        "primary_real_context_sentinel_full": all(token in fp8 for token in ("init_distributed_environment", "ensure_model_parallel_initialized(1, 1, 1, 1", "torch.distributed.all_reduce", "sentinel.json", "run_linear(CASES[0], PRIMARY_M)", "for case in CASES", "run_head(PRIMARY_M)", "run_kv", "aggregate(", "destroy_model_parallel", "destroy_distributed_environment")),
        "conditional_real_context_and_evaluator": all(token in w4 for token in ("single_rank_context", "for case in CASES", "MS = (12, 16)", "W4_DECISION", "at_least_20_percent_faster")),
        "stage_executes_typed_terminal_and_telemetry": all(token in remote for token in ("STAGED_MANIFEST.json", "MICROBENCH_PATH", "telemetry.csv", "stage-terminal.json", "sentinel")),
        "programs_parse": all(not ast.parse(path.read_text()) is None for path in REMOTE_FILES.values()),
    }
    output = {"schema_version": 1, "type": "l40s_fp8_single_rank_final_behavioral_audit", "image": IMAGE, "observed_exact_image": observed, "image_probe_returncode": compile_probe.returncode, "image_probe_stderr_tail": compile_probe.stderr[-1500:], "remote_files": manifest, "staged_files": {name: sha(path) for name, path in LOCAL_FILES.items() if path.is_file()} | {"STAGED_MANIFEST.json": sha(manifest_path)}, "checks": checks, "pass": all(checks.values())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    raise SystemExit(0 if output["pass"] else 1)

if __name__ == "__main__": main()
