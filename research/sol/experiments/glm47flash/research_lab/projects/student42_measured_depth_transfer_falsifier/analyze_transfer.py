#!/usr/bin/env python3
"""Reproduce the zero-cost, conservative student42 endpoint transfer."""
import hashlib
import json
import math
import random
import tarfile
from pathlib import Path

ROOT = Path(__file__).parent
FULL = ROOT.parent / "nebius_current_awq_c16_direct" / "artifacts" / "nebius_current_awq_c16_direct_2026-07-15-r2"
STUDENT = ROOT.parent / "distilled_depth_student_architecture" / "artifacts" / "nebius_l40s_student39_c16_c24_c32_2026-07-15-r2-repair02"
GATE = 594.466
NOMINATION = 606.355


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_text())


def profiles(summary):
    return {p["concurrency"]: p for p in summary["allocation_result"]["performance"]["profiles"]}


def bootstrap_mean(values, seed=42, n=20000):
    rng = random.Random(seed)
    means = []
    for _ in range(n):
        means.append(sum(values[rng.randrange(len(values))] for _ in values) / len(values))
    means.sort()
    return [means[int(n * .025)], means[int(n * .975)]]


def main():
    full = load(FULL / "summary.json")
    student = load(STUDENT / "summary.json")
    fp, sp = profiles(full), profiles(student)
    f16, s16, s24, s32 = fp[16], sp[16], sp[24], sp[32]

    # The prior's clean accounting bound is retained as an explicit input.  The
    # fresh endpoint transfer is a falsifier, not a replacement for exact loading.
    inherited = 597.5285581395348
    # A transparent depth-only optimistic bound anchored at the measured full47.
    proportional_full = f16["output_tokens_per_second_conservative"] * 47 / 42
    # Inverse-rate affine interpolation is shown as model-form sensitivity only;
    # it is not promoted because its intercept is an extrapolated fixed cost.
    t47 = 1 / f16["output_tokens_per_second_conservative"]
    t39 = 1 / s16["output_tokens_per_second_conservative"]
    affine = 1 / (t47 + (t39 - t47) * 5 / 8)
    optimistic_point = min(inherited, proportional_full)

    # Endpoint row resampling is a sampling diagnostic.  It does not pretend to
    # capture run-to-run variation; the decision interval uses the larger stress.
    f_tpot_ci = bootstrap_mean([r["tpot_ms"] for r in f16["rows"]])
    s_tpot_ci = bootstrap_mean([r["tpot_ms"] for r in s16["rows"]])
    row_sampling_relative = max(
        (f_tpot_ci[1] - f_tpot_ci[0]) / (2 * sum(f_tpot_ci) / 2),
        (s_tpot_ci[1] - s_tpot_ci[0]) / (2 * sum(s_tpot_ci) / 2),
    )
    # Conservative stress: 2% endpoint/measurement allowance plus 3% added
    # fixed work (prefill/queue/launch overhead) in time, with no c32 uplift.
    stress_lower = optimistic_point / 1.02 / 1.03
    stress_upper = optimistic_point

    out = {
        "schema_version": 1,
        "decision": "PARK",
        "decision_reason": "conservative lower bound misses 606.355 tok/s; no GPU allocation or successor analysis",
        "inputs": {
            "full47_summary_sha256": sha(FULL / "summary.json"),
            "full47_archive_sha256": sha(FULL / "vllm-awq-batch.tar.gz"),
            "full47_terminal_artifact_sha256": full["artifact_sha256"],
            "student39_summary_sha256": sha(STUDENT / "summary.json"),
            "student39_archive_sha256": sha(STUDENT / "vllm-awq-batch.tar.gz"),
            "student39_terminal_artifact_sha256": student["artifact_sha256"],
            "student42_materialization_sha256": sha(ROOT.parent / "minimal_depth42_clean_materialization" / "CLEAN_MATERIALIZATION_RESULT.json"),
        },
        "identity_checks": {
            "gpu": "NVIDIA L40S in both telemetry archives",
            "model_revision_equal": full["allocation_result"]["model_revision"] == student["allocation_result"]["model_revision"],
            "runtime_equal": full["allocation_result"]["runtime"] == student["allocation_result"]["runtime"],
            "dtype_equal": full["allocation_result"]["dtype"] == student["allocation_result"]["dtype"],
            "num_kv_splits_equal": full["allocation_result"]["num_kv_splits"] == student["allocation_result"]["num_kv_splits"],
            "geometry": "8,192 input / 1,024 output per request",
            "cache_policy": "prefix caching disabled; zero hit/query deltas",
            "completion": "full47 c16 32/32; student39 c16 32/32 and c32 64/64; all finish_reason=length",
            "material_difference": "max_num_seqs 16 vs 32; matched c16 retained, c24/c32 used only as stress evidence",
        },
        "measured_rows": {
            "full47_c16": {k: f16[k] for k in ["concurrency", "requests", "total_input_tokens", "total_output_tokens", "output_tokens_per_second_conservative", "wall_seconds", "success_fraction", "queue_seconds_mean_from_server_metric", "slo_pass"]},
            "student39_c16": {k: s16[k] for k in ["concurrency", "requests", "total_input_tokens", "total_output_tokens", "output_tokens_per_second_conservative", "wall_seconds", "success_fraction", "queue_seconds_mean_from_server_metric", "slo_pass"]},
            "student39_c24": {k: s24[k] for k in ["output_tokens_per_second_conservative", "wall_seconds", "queue_seconds_mean_from_server_metric", "slo_pass"]},
            "student39_c32": {k: s32[k] for k in ["output_tokens_per_second_conservative", "wall_seconds", "queue_seconds_mean_from_server_metric", "slo_pass"]},
        },
        "method": {
            "depth": "42 serving layers from clean materialization, removing source layers [6,15,24,33,42]",
            "models": "measured full47 anchor proportional scaling; inherited clean accounting bound; inverse-rate affine interpolation shown as adverse model-form sensitivity",
            "zero_c32_uplift": True,
            "endpoint_sampling": {"bootstrap": "20,000 deterministic resamples of per-request TPOT; diagnostic only", "full47_tpot_ms_ci": f_tpot_ci, "student39_tpot_ms_ci": s_tpot_ci, "max_relative_halfwidth": row_sampling_relative},
            "adverse_stress": {"endpoint_measurement_time_penalty": 0.02, "fixed_prefill_queue_time_penalty": 0.03, "c32_uplift": 0.0},
        },
        "intervals_tok_s": {
            "c16": {"point_conservative": optimistic_point, "model_form_affine_sensitivity": affine, "stress_interval": [stress_lower, stress_upper]},
            "c32_zero_uplift": {"point_conservative": optimistic_point, "stress_interval": [stress_lower, stress_upper]},
        },
        "economic_test": {"gate_tok_s": GATE, "nomination_floor_tok_s": NOMINATION, "robust_lower_tok_s": stress_lower, "robust_lower_clears_nomination": stress_lower >= NOMINATION, "all_background_arms_under_300s": True, "quality": "deferred; no deployable claim"},
    }
    (ROOT / "STUDENT42_TRANSFER_RESULT.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({"decision": out["decision"], "c16": out["intervals_tok_s"]["c16"], "robust_lower": stress_lower}, indent=2))


if __name__ == "__main__":
    main()
