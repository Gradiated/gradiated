#!/usr/bin/env python3

"""Independent terminal reconciliation for the c32 prefill compute floor.

This intentionally does not import calculate_prefill_floor.py. It re-expresses
the shape, cache, and service arithmetic so agreement is not a shared-code
round trip.
"""

import hashlib
import json
from decimal import Decimal, getcontext
from fractions import Fraction
from pathlib import Path


getcontext().prec = 50
HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
WORKSPACE = next(parent for parent in HERE.parents if parent.name == "workspace")

PATHS = {
    "floor": HERE / "PREFILL_COMPUTE_FLOOR.json",
    "manifest": HERE / "SOURCE_MANIFEST.json",
    "calculator": HERE / "calculate_prefill_floor.py",
    "geometry": LAB / "projects/exact_geometry_runtime_opportunities/GEOMETRY.json",
    "linears": LAB / "projects/h200_bf16_exact_linear_floor/artifacts/RECONCILED_TERMINAL.json",
    "inventory": WORKSPACE / "research/factory/data/accelerator_inventory.json",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def decimal(value: Fraction) -> Decimal:
    return Decimal(value.numerator) / Decimal(value.denominator)


def pairs(cache: int):
    fresh = 4214 - cache
    sliding = sum(min(1024, cache + j) for j in range(1, fresh + 1))
    global_ = fresh * cache + fresh * (fresh + 1) // 2
    return fresh, sliding, global_


def main():
    floor = load(PATHS["floor"])
    manifest = load(PATHS["manifest"])
    geometry = load(PATHS["geometry"])
    linears = load(PATHS["linears"])
    inventory = load(PATHS["inventory"])

    assert floor["status"] == "complete"
    assert floor["decision"] == "c32_preserved_with_attention_threshold"
    assert manifest["calculator"]["sha256"] == sha256(PATHS["calculator"])
    for name in ("geometry", "linears_head_terminal", "accelerator_inventory"):
        local_name = {
            "linears_head_terminal": "linears",
            "accelerator_inventory": "inventory",
        }.get(name, name)
        assert manifest["sources"][name]["sha256"] == sha256(PATHS[local_name])

    measured = geometry["target_text_geometry_measured_from_config"]
    assert measured["num_hidden_layers"] == 60
    assert measured["attention_pattern"]["sliding_attention_layers"] == 50
    assert measured["attention_pattern"]["full_attention_layers"] == 10
    assert measured["hidden_size"] == 5376
    assert measured["intermediate_size"] == 21504
    assert measured["num_attention_heads"] == 32
    assert measured["head_dim_sliding"] == 256
    assert measured["num_key_value_heads_sliding"] == 16
    assert measured["global_head_dim"] == 512
    assert measured["num_global_key_value_heads"] == 4
    assert measured["sliding_window_tokens"] == 1024

    c32 = next(row for row in linears["combined_cuda_event_component_floor"] if row["m"] == 32)
    decode = Decimal(str(c32["combined_seconds_per_request_358_steps"]))
    assert decode == Decimal("0.22476958992984145")

    h200 = next(row for row in inventory["accelerators"] if row["id"] == "nvidia-h200-sxm")
    dense_bf16_tflops = Fraction(str(h200["peak_math"]["bf16_tflops"]))
    assert dense_bf16_tflops == Fraction(1979, 2)
    assert Fraction(str(h200["peak_math"]["fp8_tflops"])) == 2 * dense_bf16_tflops
    peak = dense_bf16_tflops * 10**12

    sliding_macs = 50 * sum(
        a * b
        for a, b in ((5376, 16384), (8192, 5376), (5376, 43008), (21504, 5376))
    )
    global_macs = 10 * sum(
        a * b
        for a, b in ((5376, 20480), (16384, 5376), (5376, 43008), (21504, 5376))
    )
    macs_per_token = sliding_macs + global_macs
    assert macs_per_token == 29_396_828_160
    fresh = Fraction(4214) * Fraction(873, 1000)
    assert fresh == Fraction(1_839_411, 500)
    prefill_flops = 2 * macs_per_token * fresh
    prefill_seconds = prefill_flops / peak

    weights = {535: Fraction(411, 500), 536: Fraction(89, 500)}
    assert sum(weights.values()) == 1
    assert sum(weights[c] * pairs(c)[0] for c in weights) == fresh
    sliding_pairs = sum(weights[c] * pairs(c)[1] for c in weights)
    global_pairs = sum(weights[c] * pairs(c)[2] for c in weights)
    qk_av_flops = 4 * (
        50 * 32 * 256 * sliding_pairs + 10 * 32 * 512 * global_pairs
    )
    qk_av_seconds = qk_av_flops / peak

    artifact_prefill = floor["exact_transformer_linear_algebra"][
        "prefill_linear_floor_seconds_per_request"
    ]
    assert prefill_seconds == Fraction(artifact_prefill["numerator"], artifact_prefill["denominator"])
    artifact_attention = floor["fresh_query_qk_av_sensitivity"]["primary"][
        "impossible_ideal_seconds_per_request"
    ]
    assert qk_av_seconds == Fraction(
        artifact_attention["numerator"], artifact_attention["denominator"]
    )
    assert floor["exact_transformer_linear_algebra"]["batching_guard"][
        "divided_by_concurrency_32"
    ] is False
    assert floor["double_count_guards"]["decode_linears_plus_head_added_exactly_once"] is True
    assert floor["double_count_guards"]["analytical_decode_kv_floor_added"] is False

    ceilings = {
        "strict": Decimal("0.47201182295214134"),
        "lenient": Decimal("0.47751364375858635"),
    }
    service = {}
    for name, ceiling in ceilings.items():
        primary_threshold = ceiling - decode - decimal(prefill_seconds)
        sensitivity_threshold = primary_threshold - decimal(qk_av_seconds)
        row = floor["service_comparison"][name]
        assert primary_threshold == Decimal(
            row["maximum_actual_decode_attention_seconds_per_request_if_every_other_omission_were_zero"]
        )
        assert sensitivity_threshold == Decimal(
            row[
                "maximum_actual_decode_attention_seconds_per_request_after_qk_av_sensitivity_if_every_other_omission_were_zero"
            ]
        )
        assert primary_threshold > 0 and sensitivity_threshold > 0
        service[name] = {
            "primary_decode_attention_threshold_seconds_per_request": str(primary_threshold),
            "threshold_after_qk_av_sensitivity_seconds_per_request": str(sensitivity_threshold),
        }

    result = {
        "schema_version": 1,
        "status": "complete",
        "decision": "c32_preserved_with_attention_threshold",
        "independent_reconciliation": "pass",
        "identities": {
            "model": "google/gemma-4-31B-it",
            "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "runtime_image": floor["scope"]["runtime"],
            "source_hashes": {name: sha256(path) for name, path in PATHS.items()},
        },
        "algebra": {
            "macs_per_fresh_prompt_token": macs_per_token,
            "fresh_prompt_tokens_per_request": str(decimal(fresh)),
            "prefill_linear_flops_per_request": str(decimal(prefill_flops)),
            "prefill_linear_floor_seconds_per_request": str(decimal(prefill_seconds)),
            "qk_av_sensitivity_flops_per_request": str(decimal(qk_av_flops)),
            "qk_av_sensitivity_seconds_per_request": str(decimal(qk_av_seconds)),
            "concurrency_double_division": False,
        },
        "peak_guard": {
            "h200_dense_bf16_tflops_used": float(dense_bf16_tflops),
            "h200_dense_fp8_tflops_not_used": h200["peak_math"]["fp8_tflops"],
            "h200_two_to_four_sparse_bf16_tflops_not_used": float(2 * dense_bf16_tflops),
            "checkpoint_sparsity_assumed": False,
        },
        "disjointness": {
            "measured_decode_linears_head_seconds_per_request": str(decode),
            "prefill_linears_are_fresh_prompt_phase_only": True,
            "decode_kv_analytical_floor_added": False,
            "qk_av_is_sensitivity_not_primary_floor": True,
        },
        "service_thresholds": service,
        "claim_boundary": "Exact arithmetic under an impossible dense-BF16 peak denominator; not achieved throughput, endpoint, quality, or production evidence.",
        "resources": {
            "provider_queries": 0,
            "provider_mutations": 0,
            "gpu_seconds": 0,
            "spend_usd": 0,
        },
    }
    out = HERE / "RECONCILIATION.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"artifact": str(out), "sha256": sha256(out), "decision": result["decision"]}))


if __name__ == "__main__":
    main()
