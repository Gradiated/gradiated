#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
CONTROLLER = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py")
BENCH = PROJECT / "h200_bf16_linear_bench.py"
REMOTE = PROJECT / "remote_h200_bf16_linear_stage.sh"
HEAD_BENCH = PROJECT.parent / "gemma_l40s_parallel_lm_head_component" / "vllm_parallel_lm_head_bench.py"
HEAD_REMOTE = PROJECT.parent / "gemma_l40s_parallel_lm_head_component" / "remote_parallel_lm_head_stage.sh"
OWNER = PROJECT / "h200_linear_owner.py"
LIFECYCLE = tuple(CONTROLLER.parent / name for name in ("placement_control.py", "stock_control.py", "vllm_smoke_control.py", "awq_smoke_control.py"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = BENCH.read_text()
    remote = REMOTE.read_text()
    controller = CONTROLLER.read_text()
    probe = subprocess.run(
        ["docker", "run", "--rm", "--network=none", "--entrypoint", "python3", IMAGE, "-c", "import json,torch,vllm; print(json.dumps({'torch':torch.__version__,'vllm':vllm.__version__,'cuda':torch.version.cuda,'matmul':callable(torch.matmul)}))"],
        capture_output=True, text=True, timeout=180,
    )
    observed = None
    if probe.returncode == 0:
        for line in reversed(probe.stdout.splitlines()):
            try:
                observed = json.loads(line)
                break
            except json.JSONDecodeError:
                pass
    checks = {
        "exact_image_torch_matmul_import": probe.returncode == 0 and isinstance(observed, dict) and observed.get("matmul") is True,
        "all_exact_shapes_and_multiplicities": all(token in source for token in ("5376, 16384, 50", "5376, 20480, 10", "5376, 43008, 60", "8192, 5376, 50", "16384, 5376, 10", "21504, 5376, 60", "MS = (1, 4, 8, 16, 32)")),
        "actual_consumer_oracle": all(token in source for token in ("torch.matmul(activations, weight_t)", "timed torch.matmul output violated finite zero oracle", "checksum += float(output.float().sum())")),
        "timing_and_allocator": all(token in source for token in ("torch.cuda.Event", "wall_ms", "peak_allocated_bytes", "peak_reserved_bytes", "torch.cuda.synchronize()")),
        "cuda_event_economic_lower_bound": all(token in source for token in ("float(row[\"cuda_event_ms\"][\"p50\"]) * int(row[\"multiplicity\"])", "cuda_step_ms * STEPS / m / 1000.0", "economic_lower_bound_basis", "STEPS = 358")),
        "wall_is_diagnostic_not_classification": "synchronized isolated wall intervals are diagnostic only" in source and "linear_floor_exceeds_strict\": cuda_request_seconds" in source,
        "lenient_head_trigger": "head_could_change_classification\": any(row[\"cuda_request_seconds_358_steps\"] <= LENIENT_SECONDS" in source,
        "typed_nonzero_and_telemetry_manifest": all(token in source + remote for token in ("return 0 if result[\"pass\"] else 1", "stage-terminal.json", "manifest.json", "telemetry.csv", "telemetry-validation.json", "covers_sweep_start", "covers_sweep_end", "exit \"$rc\"")),
        "conditional_program_prepared": HEAD_BENCH.is_file() and HEAD_REMOTE.is_file() and "ParallelLMHead" in HEAD_BENCH.read_text() and "MS = (1, 2, 4, 8, 16, 32)" in HEAD_BENCH.read_text(),
        "shared_durable_retained_controller": all(token in controller for token in ("VerifiedRetainedOwner", "start_independent_watchdog", "validate_durable_owner", "execute_stage", "conditional_trigger")),
        "owner_and_transitive_lifecycle_bound": OWNER.is_file() and all(path.is_file() for path in LIFECYCLE),
    }
    result = {
        "schema_version": 1,
        "classification": "final_staged_h200_bf16_exact_linear_audit",
        "image": IMAGE,
        "image_probe_returncode": probe.returncode,
        "image_probe_stderr_tail": probe.stderr[-2000:],
        "observed_runtime": observed,
        "staged_files": {str(path): digest(path) for path in (BENCH, REMOTE, HEAD_BENCH, HEAD_REMOTE, OWNER, CONTROLLER, *LIFECYCLE)},
        "checks": checks,
        "pass": all(checks.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
