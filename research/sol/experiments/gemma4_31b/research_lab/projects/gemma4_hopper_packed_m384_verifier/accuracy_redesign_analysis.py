"""Zero-cost numerical and physical analysis for the FP32 partitioned candidate.

The numerical experiment uses the exact head dimensions, prefix lengths,
12-row sequence geometry, GQA ratios, page-size-one gather, causal/sliding
mask rules, and BF16/FP8 producer boundaries.  Four representative query heads
are evaluated per production fixture; this is explicitly a sampled synthetic
falsifier, not a replacement for the prohibited H100 component measurement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


BATCH = 32
HEADS = 32
ROWS_PER_SEQUENCE = 12
BLOCK_M = 16
BLOCK_N = 64
PARTITION_N = 512
VALUE_BLOCK_V2 = 64
VALUE_BLOCK_NEW = 32
H100_SMS = 132
H100_HBM_BYTES_PER_SECOND = 3_350_000_000_000
PRIOR = {
    "local": {
        "control_ms": 1.3924800157546997,
        "candidate_ms": 0.4918079972267151,
        "relative_l2": 0.026936529204249382,
        "max_abs": 0.00927734375,
    },
    "global": {
        "control_ms": 3.2703680992126465,
        "candidate_ms": 2.910111904144287,
        "relative_l2": 0.029003974050283432,
        "max_abs": 0.0047607421875,
    },
}


def bf16(value: np.ndarray) -> np.ndarray:
    """Round float32 to BF16, preserving round-to-nearest-even."""
    value = np.asarray(value, dtype=np.float32)
    bits = value.view(np.uint32)
    bias = np.uint32(0x7FFF) + ((bits >> 16) & np.uint32(1))
    return ((bits + bias) & np.uint32(0xFFFF0000)).view(np.float32)


def e4m3fn(value: np.ndarray) -> np.ndarray:
    """Quantize finite float32 values to the E4M3FN lattice."""
    value = np.asarray(value, dtype=np.float32)
    sign = np.sign(value)
    magnitude = np.minimum(np.abs(value), np.float32(448.0))
    output = np.zeros_like(magnitude)
    subnormal = (magnitude > 0) & (magnitude < np.float32(2.0**-6))
    output[subnormal] = (
        np.rint(magnitude[subnormal] / np.float32(2.0**-9))
        * np.float32(2.0**-9)
    )
    normal = magnitude >= np.float32(2.0**-6)
    if np.any(normal):
        exponent = np.floor(np.log2(magnitude[normal])).astype(np.int32)
        step = np.exp2(exponent - 3).astype(np.float32)
        output[normal] = np.rint(magnitude[normal] / step) * step
    return sign * np.minimum(output, np.float32(448.0))


def relative_l2(actual: np.ndarray, reference: np.ndarray) -> float:
    delta = actual.astype(np.float64) - reference.astype(np.float64)
    denominator = np.linalg.norm(reference.astype(np.float64).ravel())
    return float(np.linalg.norm(delta.ravel()) / denominator)


def metrics(actual: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    delta = actual.astype(np.float64) - reference.astype(np.float64)
    return {
        "relative_l2": relative_l2(actual, reference),
        "max_abs": float(np.max(np.abs(delta))),
        "mean_abs": float(np.mean(np.abs(delta))),
    }


def stable_output(
    score: np.ndarray,
    value: np.ndarray,
    *,
    dtype: np.dtype,
) -> np.ndarray:
    score = score.astype(dtype)
    value = value.astype(dtype)
    maximum = np.max(score, axis=-1, keepdims=True)
    weight = np.exp(score - maximum)
    weight = np.where(np.isfinite(score), weight, 0)
    return (weight @ value) / np.sum(weight, axis=-1, keepdims=True)


def partitioned_output(
    score: np.ndarray,
    value: np.ndarray,
    *,
    state_dtype: np.dtype,
) -> np.ndarray:
    """Mirror the new partition max/sum/numerator and final rescaling."""
    partial_max: list[np.ndarray] = []
    partial_sum: list[np.ndarray] = []
    partial_numerator: list[np.ndarray] = []
    for start in range(0, score.shape[-1], PARTITION_N):
        stop = min(start + PARTITION_N, score.shape[-1])
        part_score = score[:, start:stop].astype(state_dtype)
        part_value = value[start:stop].astype(state_dtype)
        part_maximum = np.max(part_score, axis=-1, keepdims=True)
        weight = np.exp(part_score - part_maximum)
        weight = np.where(np.isfinite(part_score), weight, 0)
        partial_max.append(part_maximum)
        partial_sum.append(np.sum(weight, axis=-1, keepdims=True))
        partial_numerator.append(weight @ part_value)
    maxima = np.concatenate(partial_max, axis=-1)
    global_max = np.max(maxima, axis=-1, keepdims=True)
    rescale = np.exp(maxima - global_max)
    denominator = sum(
        part_sum * rescale[:, index : index + 1]
        for index, part_sum in enumerate(partial_sum)
    )
    numerator = sum(
        part_numerator * rescale[:, index : index + 1]
        for index, part_numerator in enumerate(partial_numerator)
    )
    return numerator / denominator


def v2_proxy(score: np.ndarray, value: np.ndarray) -> np.ndarray:
    """Mirror V2's BF16 score persistence and FP8 probability dot input."""
    persisted_score = bf16(score.astype(np.float32))
    maximum = np.max(persisted_score, axis=-1, keepdims=True)
    probability_fp32 = np.exp(persisted_score - maximum).astype(np.float32)
    probability_fp32 = np.where(
        np.isfinite(persisted_score), probability_fp32, 0
    )
    # V2's max/sum producer retains this denominator in FP32, while the
    # downstream value dot independently quantizes probabilities to FP8.
    probability_fp8 = e4m3fn(probability_fp32)
    numerator = probability_fp8 @ value.astype(np.float32)
    denominator = np.sum(probability_fp32, axis=-1, keepdims=True)
    return numerator / denominator


def make_fixture(
    *,
    name: str,
    head_dim: int,
    kv_heads: int,
    prefix: int,
    sliding_window: int,
    extreme_scale: float,
    seed: int,
) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    sampled_heads = 4
    q = bf16(
        rng.normal(
            0.0, 0.08 * extreme_scale, (sampled_heads, ROWS_PER_SEQUENCE, head_dim)
        ).astype(np.float32)
    )
    k_logical = e4m3fn(
        rng.normal(0.0, 0.08, (kv_heads, prefix, head_dim)).astype(np.float32)
    )
    v_logical = e4m3fn(
        rng.normal(0.0, 0.08, (kv_heads, prefix, head_dim)).astype(np.float32)
    )
    k_extend = bf16(
        rng.normal(0.0, 0.08, (kv_heads, ROWS_PER_SEQUENCE, head_dim)).astype(
            np.float32
        )
    )
    v_extend = bf16(
        rng.normal(0.0, 0.08, (kv_heads, ROWS_PER_SEQUENCE, head_dim)).astype(
            np.float32
        )
    )

    # Real page-size-one producer semantics: logical indices gather a shuffled
    # physical cache.  The analysis reconstructs exactly what the kernel sees.
    physical_order = rng.permutation(prefix)
    inverse = np.empty_like(physical_order)
    inverse[physical_order] = np.arange(prefix)
    k_physical = k_logical[:, physical_order]
    v_physical = v_logical[:, physical_order]
    gathered_k = k_physical[:, inverse]
    gathered_v = v_physical[:, inverse]
    assert np.array_equal(gathered_k, k_logical)
    assert np.array_equal(gathered_v, v_logical)

    outputs: dict[str, list[np.ndarray]] = {
        "reference": [],
        "stock_aa": [],
        "v2_proxy": [],
        "redesign": [],
    }
    scale = np.float64(1.0 / math.sqrt(head_dim))
    kv_group = HEADS // kv_heads
    for sampled_head in range(sampled_heads):
        query_head = sampled_head * (HEADS // sampled_heads)
        kv_head = query_head // kv_group
        prefix_score = (
            q[sampled_head].astype(np.float64)
            @ gathered_k[kv_head].astype(np.float64).T
        ) * scale
        extend_score = (
            q[sampled_head].astype(np.float64)
            @ k_extend[kv_head].astype(np.float64).T
        ) * scale
        for row in range(ROWS_PER_SEQUENCE):
            if sliding_window > 0:
                prefix_score[row, :row] = -np.inf
            extend_score[row, row + 1 :] = -np.inf
        score = np.concatenate([prefix_score, extend_score], axis=-1)
        value = np.concatenate(
            [gathered_v[kv_head], v_extend[kv_head]], axis=0
        )
        outputs["reference"].append(
            stable_output(score, value, dtype=np.float64)
        )
        outputs["stock_aa"].append(
            partitioned_output(
                score.astype(np.float32),
                value.astype(np.float32),
                state_dtype=np.float32,
            )
        )
        outputs["v2_proxy"].append(v2_proxy(score, value))
        outputs["redesign"].append(
            bf16(
                partitioned_output(
                    score.astype(np.float32),
                    value.astype(np.float32),
                    state_dtype=np.float32,
                )
            )
        )

    arrays = {key: np.stack(value) for key, value in outputs.items()}
    return {
        "name": name,
        "geometry": {
            "batch": BATCH,
            "query_rows_total": BATCH * ROWS_PER_SEQUENCE,
            "query_rows_per_sequence": ROWS_PER_SEQUENCE,
            "query_heads": HEADS,
            "sampled_query_heads": sampled_heads,
            "head_dim": head_dim,
            "kv_heads": kv_heads,
            "prefix_tokens": prefix,
            "page_size": 1,
            "partition_tokens": PARTITION_N,
            "sliding_window": sliding_window,
            "extreme_q_scale": extreme_scale,
        },
        "coverage": {
            "complete_rows_for_sampled_heads": True,
            "complete_head_coverage": False,
            "physical_page_permutation_gathered": True,
            "last_partition_tokens": prefix % PARTITION_N,
            "padded_score_stride": prefix + BLOCK_N,
        },
        "stock_aa_vs_fp64": metrics(arrays["stock_aa"], arrays["reference"]),
        "v2_proxy_vs_fp64": metrics(arrays["v2_proxy"], arrays["reference"]),
        "redesign_vs_fp64": metrics(arrays["redesign"], arrays["reference"]),
        "redesign_vs_stock_aa": metrics(
            arrays["redesign"], arrays["stock_aa"]
        ),
    }


def physical_case(
    *, name: str, head_dim: int, prefix: int
) -> dict[str, object]:
    partitions = math.ceil(prefix / PARTITION_N)
    v2_splits = math.ceil(head_dim / VALUE_BLOCK_V2)
    new_splits = math.ceil(head_dim / VALUE_BLOCK_NEW)
    score_elements = BATCH * HEADS * ROWS_PER_SEQUENCE * (prefix + BLOCK_N)
    v2_score_bytes = score_elements * 2 * (1 + v2_splits)
    new_score_bytes = score_elements * 4 * (1 + new_splits)
    partial_numerator_bytes = (
        partitions
        * BATCH
        * HEADS
        * ROWS_PER_SEQUENCE
        * head_dim
        * 4
        * 2
    )
    additional_bytes = new_score_bytes + partial_numerator_bytes - v2_score_bytes
    hbm_lower_bound_ms = (
        additional_bytes / H100_HBM_BYTES_PER_SECOND * 1000.0
    )
    prior_saved_ms = PRIOR[name]["control_ms"] - PRIOR[name]["candidate_ms"]
    allowed_loss_ms = prior_saved_ms * 0.2
    score_ctas = BATCH * HEADS * partitions
    value_ctas = BATCH * HEADS * partitions * new_splits
    merge_ctas = BATCH * HEADS * new_splits
    attention_flops = (
        4
        * BATCH
        * HEADS
        * ROWS_PER_SEQUENCE
        * (prefix + ROWS_PER_SEQUENCE)
        * head_dim
    )
    return {
        "name": name,
        "partitions": partitions,
        "value_splits": new_splits,
        "flops_attention_score_plus_value": attention_flops,
        "compulsory_bytes": {
            "v2_score_workspace_write_plus_reads": v2_score_bytes,
            "new_fp32_score_workspace_write_plus_reads": new_score_bytes,
            "new_partial_numerator_write_plus_read": partial_numerator_bytes,
            "additional_over_v2": additional_bytes,
        },
        "grid": {
            "score_ctas": score_ctas,
            "partition_value_ctas": value_ctas,
            "value_merge_ctas": merge_ctas,
            "score_waves_at_132_sm": score_ctas / H100_SMS,
            "partition_value_waves_at_132_sm": value_ctas / H100_SMS,
            "value_merge_waves_at_132_sm": merge_ctas / H100_SMS,
        },
        "h100_hbm_peak_lower_bound_additional_ms": hbm_lower_bound_ms,
        "maximum_admitted_loss_ms": allowed_loss_ms,
        "lower_bound_over_admitted_loss": hbm_lower_bound_ms / allowed_loss_ms,
        "physically_credible_from_nonoverlapping_bound": (
            hbm_lower_bound_ms <= allowed_loss_ms
        ),
        "compile_dependent": {
            "registers_per_thread": None,
            "shared_memory_bytes": None,
            "spill_bytes": None,
            "reason": "No GPU claim or SM90 compiler was authorized.",
            "source_live_value_tile": [BLOCK_M, VALUE_BLOCK_NEW],
            "v2_source_live_value_tile": [BLOCK_M, VALUE_BLOCK_V2],
        },
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixtures = [
        make_fixture(
            name="production_local_page_boundary",
            head_dim=256,
            kv_heads=16,
            prefix=1024,
            sliding_window=1024,
            extreme_scale=1.0,
            seed=384256,
        ),
        make_fixture(
            name="production_global_padded_partition_page_boundary",
            head_dim=512,
            kv_heads=4,
            prefix=4214,
            sliding_window=-1,
            extreme_scale=1.0,
            seed=384512,
        ),
        make_fixture(
            name="extreme_local_q8",
            head_dim=256,
            kv_heads=16,
            prefix=1024,
            sliding_window=1024,
            extreme_scale=8.0,
            seed=8256,
        ),
    ]
    physical = [
        physical_case(name="local", head_dim=256, prefix=1024),
        physical_case(name="global", head_dim=512, prefix=4214),
    ]
    report = {
        "schema_version": 1,
        "type": "packed_m384_accuracy_redesign_offline_analysis",
        "evidence_class": {
            "numerical": "measured_synthetic_cpu",
            "physical": "analytical_lower_bound",
            "prior_timings": "measured_h100_closed_v2_evidence",
            "accelerator_specs": "vendor_inventory",
        },
        "candidate": {
            "source": "packed_m384_attention_fp32_partitioned.py",
            "source_sha256": sha256(
                Path(__file__).with_name(
                    "packed_m384_attention_fp32_partitioned.py"
                )
            ),
            "algorithm": (
                "FP32 persisted scores and online state; one FP32 numerator "
                "per 512-token partition and 32-value tile; FP32 rescaled "
                "merge; BF16 only at unchanged output boundary"
            ),
        },
        "fixtures": fixtures,
        "limitations": [
            "Four representative query heads, not all 32 heads, were evaluated.",
            "The CPU proxy does not reproduce Hopper dot/exp instruction rounding.",
            "No endpoint archive contains downstream target-logit margins.",
            "No SM90 compile or GPU sample was authorized.",
        ],
        "numerical_gate": {
            "definition": (
                "redesign relative-L2 <= max(10x stock-A/A proxy envelope, "
                "one tenth closed-V2 relative-L2), plus endpoint token-margin "
                "clearance on every request"
            ),
            "endpoint_margin_gate_evaluable": False,
            "reason": (
                "The immutable consumed endpoint archive persists tokens and "
                "timings but not target-logit vectors or winner margins."
            ),
        },
        "physical": {
            "h100_sxm": {
                "sms": H100_SMS,
                "peak_hbm_bytes_per_second": H100_HBM_BYTES_PER_SECOND,
            },
            "cases": physical,
            "weighted_50_local_10_global": {
                "additional_hbm_lower_bound_ms": (
                    50
                    * physical[0]["h100_hbm_peak_lower_bound_additional_ms"]
                    + 10
                    * physical[1]["h100_hbm_peak_lower_bound_additional_ms"]
                ),
                "maximum_admitted_loss_ms": (
                    50 * physical[0]["maximum_admitted_loss_ms"]
                    + 10 * physical[1]["maximum_admitted_loss_ms"]
                ),
            },
        },
    }
    report["numerical_gate"]["fixture_results"] = [
        {
            "fixture": fixture["name"],
            "relative_l2_limit": max(
                10.0 * fixture["stock_aa_vs_fp64"]["relative_l2"],
                (
                    PRIOR["global" if fixture["geometry"]["head_dim"] == 512 else "local"][
                        "relative_l2"
                    ]
                    / 10.0
                ),
            ),
            "observed_relative_l2": fixture["redesign_vs_fp64"]["relative_l2"],
        }
        for fixture in fixtures
    ]
    report["numerical_gate"]["sampled_proxy_pass"] = all(
        item["observed_relative_l2"] <= item["relative_l2_limit"]
        for item in report["numerical_gate"]["fixture_results"]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(args.output), "fixtures": len(fixtures)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
