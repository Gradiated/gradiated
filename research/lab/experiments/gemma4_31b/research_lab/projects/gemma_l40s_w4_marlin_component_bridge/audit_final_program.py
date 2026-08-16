#!/usr/bin/env python3
"""Fail-closed audit for the exact files staged by the shared controller."""
import argparse
import hashlib
import json
import py_compile
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
CONTROLLER = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py")
FILES = (
    "vllm_w4_fp8_microbench.py",
    "remote_w4_fp8_stage.sh",
    "vllm_parallel_lm_head_bench.py",
    "remote_parallel_lm_head_stage.sh",
)
DEPENDENCIES = (
    Path("../gemma_l40s_w4_c16_economic_bound/W4_C16_BOUND_V2.json"),
    Path("../gemma_l40s_w4_c16_economic_bound/W4_COMPONENT_PACKET.json"),
    Path("../gemma_l40s_vllm_fp8_consumer_bridge/IDENTITY_ASSERTION.json"),
    Path("../fp8_kv_contract_reconciliation/KV_CONTRACT.json"),
    Path("../l40s_saturation_economic_gate/SATURATION_GATE.json"),
    Path("../tied_vocab_projection_cost_bound/VOCAB_BOUND.json"),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    primary = (PROJECT / "vllm_w4_fp8_microbench.py").read_text()
    remote = (PROJECT / "remote_w4_fp8_stage.sh").read_text()
    conditional = (PROJECT / "vllm_parallel_lm_head_bench.py").read_text()
    controller = CONTROLLER.read_text()
    for name in ("vllm_w4_fp8_microbench.py", "vllm_parallel_lm_head_bench.py"):
        py_compile.compile(PROJECT / name, doraise=True)
    checks = {
        "all_six_shapes_and_m_1_2_4_8_16": all(text in primary for text in ("16384, 50", "20480, 10", "8192, 5376, 50", "16384, 5376, 10", "43008, 60", "21504, 5376, 60", "MS = (1, 2, 4, 8, 16)")),
        "actual_w4_method_and_marlin_kernel_gate": all(text in primary for text in ("AWQMarlinLinearMethod", "awq_marlin", "method.apply(layer, x)", "selected non-Marlin kernel")),
        "actual_fp8_method_same_config_context": all(text in primary for text in ("Fp8LinearMethod", "set_current_vllm_config", "method.apply(layer, x)")),
        "oracle_consumes_timed_consumer_output": all(text in primary for text in ("output = method.apply(layer, x)", "error = (output.float() - oracle.float()).abs()", "timed(lambda: method.apply(layer, x))")),
        "timing_memory_and_useful_gpu_required": all(text in primary for text in ("torch.cuda.Event", "peak_allocated_bytes", "peak_reserved_bytes", "useful_gpu_seconds")),
        "aggregate_and_25_percent_gate": all(text in primary for text in ("aggregate(result[\"rows\"], \"w4_marlin\")", "reduction >= 0.25", "architecture_multiplicity")),
        "nonzero_typed_failures": "return 0 if result[\"pass\"] else 1" in primary and "exit \"$rc\"" in remote,
        "stage_terminal_and_internal_manifest": all(text in remote for text in ("stage-terminal.json", "manifest.json", "telemetry.csv", "useful_gpu_seconds")),
        "conditional_parallel_lm_head_real_consumer": all(text in conditional for text in ("ParallelLMHead", "head.quant_method.apply(head,x,None)", "for m in (1,2,4,8,16)")),
        "shared_owner_sequences_typed_trigger_and_cleanup": all(text in controller for text in ("VerifiedRetainedOwner", "conditional_trigger(primary[\"terminal\"])", "primary_terminal_false_cleanup", "start_independent_watchdog")),
    }
    result = {
        "schema_version": 1,
        "classification": "final_staged_scientific_program_audit",
        "controller": str(CONTROLLER),
        "controller_sha256_current": digest(CONTROLLER),
        "controller_sha256_prior_project": "1c7448d956d9c65eaf64494bf3bbd16afcf813e30f57604a36affc873d23af2b",
        "controller_change_explanation": "Current shared upstream adds parameterized pinned image/staged files plus typed primary/conditional retrieval and VerifiedRetainedOwner cleanup required by this project.",
        "staged_files": {name: digest(PROJECT / name) for name in FILES},
        "authoritative_dependencies": {str(path): digest(PROJECT / path) for path in DEPENDENCIES},
        "checks": checks,
        "pass": all(checks.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
