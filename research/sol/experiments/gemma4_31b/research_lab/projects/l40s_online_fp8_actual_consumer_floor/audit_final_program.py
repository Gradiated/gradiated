#!/usr/bin/env python3
"""Bind the two staged consumers to the image and shared retained controller."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
NEBIUS = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
CONTROLLER = NEBIUS / "mla_microbench_control.py"
FILES = tuple(PROJECT / name for name in ("fp8_actual.py", "w4_actual.py", "remote_stage.sh", "assert_identity.py", "l40s_fp8_owner.py")) + (CONTROLLER,)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fp8 = (PROJECT / "fp8_actual.py").read_text()
    w4 = (PROJECT / "w4_actual.py").read_text()
    remote = (PROJECT / "remote_stage.sh").read_text()
    controller = CONTROLLER.read_text()
    probe = subprocess.run([
        "docker", "run", "--rm", "--network=none", "--entrypoint", "python3", IMAGE, "-c",
        "import hashlib,inspect,json,vllm; from vllm.model_executor.layers.quantization.fp8 import Fp8LinearMethod,Fp8OnlineLinearMethod,Fp8KVCacheMethod; from vllm.model_executor.layers.quantization.awq_marlin import AWQMarlinLinearMethod; print(json.dumps({'vllm':vllm.__version__,'fp8':hashlib.sha256(inspect.getsource(Fp8LinearMethod).encode()).hexdigest(),'online':hashlib.sha256(inspect.getsource(Fp8OnlineLinearMethod).encode()).hexdigest(),'kv':hashlib.sha256(inspect.getsource(Fp8KVCacheMethod).encode()).hexdigest(),'w4':hashlib.sha256(inspect.getsource(AWQMarlinLinearMethod).encode()).hexdigest()}))",
    ], capture_output=True, text=True, timeout=180)
    observed = None
    for line in reversed(probe.stdout.splitlines()):
        try:
            observed = json.loads(line)
            break
        except json.JSONDecodeError:
            pass
    checks = {
        "exact_image_import_and_consumer_hashes": probe.returncode == 0 and isinstance(observed, dict) and observed.get("fp8") == "1d6ef3182fb5c72808414cdf14177131121f2b8fb6e94012696f0fdde4f74c48" and observed.get("w4") == "721bb23b98cd678232b87a24757317cc9066bfa13f983ca2bf71a3afbaf6ed97",
        "fp8_actual_producer_consumer_oracle": all(x in fp8 for x in ("Fp8OnlineLinearMethod", "process_weights_after_loading", "fp8_method.apply", "UnquantizedLinearMethod", "oracle_from_timed_outputs", "Fp8KVCacheMethod", "reshape_and_cache_flash")),
        "fp8_geometry_timing_and_aggregation": all(x in fp8 for x in ("5376, 16384, 50", "5376, 20480, 10", "5376, 43008, 60", "8192, 5376, 50", "16384, 5376, 10", "21504, 5376, 60", "DECODE_MS = (12, 14)", "PREFILL_MS = (3679, 8730)", "358/{concurrency} exactly once", "torch.cuda.Event", "peak_reserved_bytes")),
        "w4_actual_marlin_matched_oracle": all(x in w4 for x in ("AWQMarlinLinearMethod", "ops.awq_dequantize", "method.process_weights_after_loading", "w4_method.apply", "fp8_method.apply", "oracle_from_timed_outputs", "MS = (14, 16)", "w4_to_fp8_reduction")),
        "typed_stage_archive_and_telemetry": all(x in remote + controller for x in ("stage-terminal.json", "manifest.json", "telemetry.csv", "exit \"$rc\"", "VerifiedRetainedOwner", "start_independent_watchdog", "conditional_trigger", "stage_retrieved")),
        "no_placeholder_or_empty_stage": "NotImplemented" not in fp8 + w4 and "raise RuntimeError(\"placeholder" not in fp8 + w4 and "for case in CASES" in fp8 + w4,
        "all_transitive_staged_files_present": all(path.is_file() for path in FILES),
    }
    result = {"schema_version": 1, "type": "l40s_online_fp8_final_staged_program_audit", "image": IMAGE, "image_probe_returncode": probe.returncode, "image_probe_stderr_tail": probe.stderr[-2000:], "observed_runtime": observed, "staged_files": {path.name: digest(path) for path in FILES if path.is_file()}, "checks": checks, "pass": all(checks.values())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
