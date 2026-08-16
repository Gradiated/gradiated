#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any


getcontext().prec = 40

PROJECT = Path(__file__).resolve().parent
PROJECTS = PROJECT.parent
REPO = PROJECT.parents[6]
COMMIT = "6d4a8e6d204a9b2827544003b26321fff62923da"

INPUTS = {
    "h100_endpoint": (
        PROJECTS
        / "h100_w4_full_endpoint_background_frontier/artifacts/"
        "gemma-h100-w4-phased-20260718t07491784353752z/"
        "RECONCILED_ENDPOINT_TERMINAL.json",
        "94c0c8b2aa0a9699be530ddd33f74c85c6dd03e31cc3455b4519133d10c43f13",
    ),
    "h100_c128_raw": (
        PROJECTS
        / "h100_w4_full_endpoint_background_frontier/artifacts/"
        "gemma-h100-w4-phased-20260718t07491784353752z/"
        "c128_repaired_terminal.json",
        "f753e11a7ede119d3f0e703dee7aa56adf573d6af365f16b3bca5cd087c128a9",
    ),
    "h100_attention_kv": (
        PROJECTS / "h100_w4_decode_residual_mechanism/RECONCILED_TERMINAL.json",
        "54ca42212f01c3eb46359f7d8a7a7ff5289abf38c1e7bf03b1050d8ed40a0501",
    ),
    "h100_linear_head": (
        PROJECTS
        / "h100_w4_background_concurrency_frontier/artifacts/"
        "gemma-h100-w4-frontier-20260717t22121784319137z/"
        "RECONCILED_FRONTIER_TERMINAL.json",
        "63c3fa9dba6999926e663d229b96902b72d1e1d809a8664f37baedc332682c7e",
    ),
    "sm100_mechanism": (
        PROJECTS / "b200_exact_gemma_kernel_economic_mechanism/MECHANISM.json",
        "0ced5b18806b14f6fd0070f00c52640af5e9764886fed46752da43028f8b1119",
    ),
    "gpu_prices": (
        REPO / "research/factory/data/gpu_prices.json",
        "3f403d67a92fc91be85bbd27dede85f5f91c3fd2df25ef8dcef2a344acbd1e01",
    ),
}

UPSTREAM = {
    "sm100_selector": {
        "path": "vllm/platforms/cuda.py",
        "sha256": "b987bdd4d6156843d5a58e4731dd5496708b76e6dcb009f01abb4047d965e50c",
        "needles": [
            "if device_capability.major == 10:",
            "AttentionBackendEnum.FLASHINFER",
            "AttentionBackendEnum.TRITON_ATTN",
        ],
    },
    "flashinfer": {
        "path": "vllm/v1/attention/backends/flashinfer.py",
        "sha256": "e22db5ddadbd550083438946c4452b3227d98020c6c34285dd4b6917b39e2aae",
        "needles": [
            '"fp8_e4m3"',
            "return [64, 128, 256]",
            "capability.major == 10",
        ],
    },
    "flash_attention": {
        "path": "vllm/v1/attention/backends/flash_attn.py",
        "sha256": "38ae47c9eb4e6ab774ef4397015f45a2d05001f8b220a2347be86e57bbf54aa7",
        "needles": [
            "head_size % 8 == 0 and head_size <= 256",
            "kv_cache_dtype.startswith(\"fp8\")",
        ],
    },
    "triton_attention": {
        "path": "vllm/v1/attention/backends/triton_attn.py",
        "sha256": "0881156d666e81642879a943dc14fda1186060bc24676280497428a8e3c079a3",
        "needles": [
            '"fp8_e4m3"',
            "return head_size >= 32",
            "def supports_compute_capability",
        ],
    },
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_bound_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    values: dict[str, Any] = {}
    identities: dict[str, Any] = {}
    for name, (path, expected) in INPUTS.items():
        data = path.read_bytes()
        actual = digest(data)
        if actual != expected:
            raise ValueError(f"{name} digest {actual} != {expected}")
        values[name] = json.loads(data)
        identities[name] = {
            "path": str(path),
            "sha256": actual,
            "expected_sha256": expected,
            "pass": True,
        }
    return values, identities


def verify_upstream() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, contract in UPSTREAM.items():
        url = (
            "https://raw.githubusercontent.com/vllm-project/vllm/"
            f"{COMMIT}/{contract['path']}"
        )
        with urllib.request.urlopen(url, timeout=20) as response:
            data = response.read()
        actual = digest(data)
        text = data.decode()
        missing = [needle for needle in contract["needles"] if needle not in text]
        if actual != contract["sha256"] or missing:
            raise ValueError(
                f"upstream {name} failed: sha={actual}, missing={missing}"
            )
        result[name] = {
            "url": url,
            "path": contract["path"],
            "sha256": actual,
            "required_source_tokens": contract["needles"],
            "pass": True,
        }
    return result


def d(value: Any) -> Decimal:
    return Decimal(str(value))


def f(value: Decimal) -> float:
    return float(value)


def build(verify_source: bool) -> dict[str, Any]:
    inputs, identities = load_bound_inputs()
    endpoint = inputs["h100_endpoint"]
    raw = inputs["h100_c128_raw"]
    attention = inputs["h100_attention_kv"]
    frontier = inputs["h100_linear_head"]
    mechanism = inputs["sm100_mechanism"]
    prices = inputs["gpu_prices"]

    rows = raw["arms"][0]["rows"]
    ttfts = [d(row["ttft_ms"]) / 1000 for row in rows]
    walls = [d(row["wall_seconds"]) for row in rows]
    batch = d(endpoint["evidence"]["c128"]["concurrency"])
    endpoint_wall = d(attention["endpoint_reconciliation"]["endpoint_batch_wall_seconds"])
    max_ttft = max(ttfts)
    min_ttft = min(ttfts)
    earliest_completion = min(walls)
    post_last_ttft_tail = endpoint_wall - max_ttft

    c128 = frontier["combined_by_concurrency"]["128"]
    h100_linear_batch = d(c128["w4_decode_linear_seconds_per_request"]) * batch
    h100_head_batch = d(c128["actual_head_seconds_per_request"]) * batch
    h100_attention_batch = d(
        attention["measured_h100_c128"]["synchronized_mixed_loop"]["wall_seconds"]
    )

    priors = mechanism["economic_screen"]["vendor_prior_ratios"]
    attention_head_speedup = d(priors["b200_over_h100_hbm_bandwidth"])
    fp4_peak_speedup = d(priors["b200_fp4_over_h100_fp8_peak"])
    b200_decode_floor_per_request = d(
        mechanism["economic_screen"]
        ["impossible_ideal_b200_nvfp4_linear_floors_seconds_per_request"]
        ["decode_weight_only_by_concurrency"]["32"]
    )
    b200_linear_floor_per_request = d(
        mechanism["economic_screen"]
        ["impossible_ideal_b200_nvfp4_linear_floors_seconds_per_request"]
        ["prefill_plus_decode"]["32"]
    )

    h100_rate = d(mechanism["economic_screen"]["planning_rate_usd_per_gpu_hour"]["h100"])
    b200_rate = d(mechanism["economic_screen"]["planning_rate_usd_per_gpu_hour"]["b200"])
    h100_ceiling = d(mechanism["economic_screen"]["h100_planning_service_ceiling_seconds_per_request"])
    b200_ceiling = h100_ceiling * h100_rate / b200_rate
    b200_batch_hurdle = b200_ceiling * batch
    reopen_batch_threshold = b200_batch_hurdle * d("0.8")

    algebraic_tail_residual = (
        post_last_ttft_tail
        - h100_linear_batch
        - h100_head_batch
        - h100_attention_batch
    )
    if algebraic_tail_residual <= 0:
        raise ValueError("component credits exhaust the post-TTFT tail")

    scaled_attention = h100_attention_batch / attention_head_speedup
    scaled_head = h100_head_batch / attention_head_speedup

    impossible = algebraic_tail_residual + scaled_attention + scaled_head
    source_supported = impossible + b200_linear_floor_per_request * batch
    unsupported_fullstack_sensitivity = (
        algebraic_tail_residual / attention_head_speedup
        + scaled_attention
        + scaled_head
        + b200_linear_floor_per_request * batch
    )
    conservative_executable = (
        endpoint_wall
        - h100_linear_batch
        - h100_head_batch
        - h100_attention_batch
        + b200_decode_floor_per_request * batch
        + scaled_head
        + scaled_attention
    )

    base_residual_reduction = source_supported - b200_batch_hurdle
    reopen_residual_reduction = source_supported - reopen_batch_threshold

    source_trace = verify_upstream() if verify_source else {
        name: {
            "path": contract["path"],
            "sha256": contract["sha256"],
            "verification_skipped": True,
        }
        for name, contract in UPSTREAM.items()
    }

    return {
        "schema_version": 1,
        "classification": "source_supported_b200_fullstack_closure",
        "terminal_decision": "close_b200_fullstack",
        "identities": identities,
        "pinned_runtime_source": {
            "repository": "https://github.com/vllm-project/vllm",
            "commit": COMMIT,
            "verified_during_run": verify_source,
            "files": source_trace,
        },
        "workload": {
            "model": mechanism["identities"]["model"],
            "model_revision": mechanism["identities"]["model_revision"],
            "concurrency": int(batch),
            "prompt_tokens": raw["workload"]["prompt_tokens"],
            "output_tokens": raw["workload"]["output_tokens"],
            "local_global_layer_mix": attention["measured_h100_c128"]["layer_mix"],
        },
        "economics": {
            "price_source": "content-bound mechanism; current repository gpu_prices digest matches it",
            "h100_planning_usd_per_gpu_hour": f(h100_rate),
            "b200_planning_usd_per_gpu_hour": f(b200_rate),
            "b200_price_premium": f(b200_rate / h100_rate),
            "b200_seconds_per_request_hurdle": f(b200_ceiling),
            "b200_batch_seconds_hurdle": f(b200_batch_hurdle),
            "reopen_requires_20pct_headroom_seconds_per_request": f(b200_ceiling * d("0.8")),
            "reopen_requires_20pct_headroom_batch_seconds": f(reopen_batch_threshold),
        },
        "actual_attention_kv_discriminator": {
            "evidence_class": "measured H100 and pinned-source B200 route",
            "h100_consumer": "vllm.v1.attention.backends.triton_attn.TritonAttentionImpl",
            "local": attention["measured_h100_c128"]["routes"]["local"],
            "global": attention["measured_h100_c128"]["routes"]["global"],
            "sm100_route": {
                "local_d256": "FlashInfer is source-valid and prioritized; Triton is a common source-valid fallback",
                "global_d512": "FlashInfer and FlashAttention reject d512 at the pinned commit; Triton accepts FP8 KV, head_size>=32, and SM100",
                "bound_route": "Triton for both routes; grants the full 2.388x B200/H100 bandwidth prior only as an analytical optimistic credit",
            },
            "measured_h100_batch_seconds": f(h100_attention_batch),
            "optimistic_b200_batch_seconds": f(scaled_attention),
        },
        "partition": {
            "evidence_class": "derived closure-safe credit envelope",
            "endpoint_batch_wall_seconds": f(endpoint_wall),
            "min_ttft_seconds": f(min_ttft),
            "max_ttft_seconds": f(max_ttft),
            "earliest_completion_seconds": f(earliest_completion),
            "post_last_ttft_tail_seconds": f(post_last_ttft_tail),
            "measured_decode_linear_batch_seconds": f(h100_linear_batch),
            "measured_tied_bf16_head_batch_seconds": f(h100_head_batch),
            "measured_attention_kv_batch_seconds": f(h100_attention_batch),
            "algebraic_tail_residual_seconds": f(algebraic_tail_residual),
            "overlap_policy": (
                "Delete the entire start-to-last-TTFT envelope first, then assign each separately "
                "measured component exactly once against the remaining tail. This deliberately "
                "over-credits B200 because the deleted envelope contains overlapping decode work; "
                "no synchronized component duration is added to endpoint wall."
            ),
            "residual_contents": (
                "Unattributed norms, activations, rotary, sampling, runtime/service work, and any "
                "component mismatch. It is algebraic and not claimed as a measured kernel category."
            ),
        },
        "bounds": {
            "impossible_optimistic": {
                "evidence_class": "derived impossible lower-time envelope",
                "assumptions": [
                    "all 149.190 seconds through the last TTFT are free, including queue and overlapping decode",
                    "all measured decode linear time is zero",
                    "attention/KV and tied head each realize the full 2.388x HBM ratio",
                    "the algebraic non-linear/service tail residual does not improve",
                ],
                "batch_seconds": f(impossible),
                "seconds_per_request": f(impossible / batch),
                "misses_economic_hurdle_seconds": f(impossible - b200_batch_hurdle),
                "misses_reopen_threshold_seconds": f(impossible - reopen_batch_threshold),
                "passes_economic_hurdle": impossible <= b200_batch_hurdle,
                "passes_reopen_threshold": impossible <= reopen_batch_threshold,
            },
            "source_supported_optimistic": {
                "evidence_class": "source-derived plus analytical ideal floors",
                "assumptions": [
                    "same free queue/prefill envelope as the impossible bound",
                    "pinned SM100 NVFP4 exact-shape c32 prefill+decode ideal floor is added",
                    "pinned Triton FP8-KV d256/d512 route gets the full HBM ratio",
                    "tied BF16 head gets the full HBM ratio",
                    "no achieved B200 timing is claimed",
                ],
                "linear_floor_batch_seconds": f(b200_linear_floor_per_request * batch),
                "batch_seconds": f(source_supported),
                "seconds_per_request": f(source_supported / batch),
                "misses_economic_hurdle_seconds": f(source_supported - b200_batch_hurdle),
                "misses_reopen_threshold_seconds": f(source_supported - reopen_batch_threshold),
                "passes_economic_hurdle": source_supported <= b200_batch_hurdle,
                "passes_reopen_threshold": source_supported <= reopen_batch_threshold,
            },
            "conservative_executable": {
                "evidence_class": "inferred executable upper estimate",
                "assumptions": [
                    "retain observed endpoint scheduling, prefill, and unpartitioned service wall",
                    "replace measured H100 decode linears with the pinned c32 B200 ideal decode floor",
                    "scale measured attention/KV and tied head by the optimistic HBM ratio",
                    "do not credit unmeasured B200 prefill acceleration",
                ],
                "batch_seconds": f(conservative_executable),
                "seconds_per_request": f(conservative_executable / batch),
                "passes_economic_hurdle": conservative_executable <= b200_batch_hurdle,
                "passes_reopen_threshold": conservative_executable <= reopen_batch_threshold,
            },
            "unsupported_fullstack_sensitivity": {
                "evidence_class": "counterfactual; not source-supported for the unattributed residual",
                "assumptions": [
                    "start from the source-supported optimistic bound",
                    "also grant the entire algebraic service/non-linear residual the full HBM ratio",
                    "assume no small-kernel, launch, occupancy, or service limitation",
                ],
                "batch_seconds": f(unsupported_fullstack_sensitivity),
                "seconds_per_request": f(unsupported_fullstack_sensitivity / batch),
                "passes_economic_hurdle": unsupported_fullstack_sensitivity <= b200_batch_hurdle,
                "passes_reopen_threshold": unsupported_fullstack_sensitivity <= reopen_batch_threshold,
                "admissible_for_reopen": False,
                "reason": (
                    "The endpoint telemetry has no model-forward/kernel partition for this residual, "
                    "and the pinned mechanism supplies no representation, dispatch, or achieved bound "
                    "for norms, activations, rotary, sampling, and service/runtime work. Counting this "
                    "requires an independent full-stack intervention, not the staged NVFP4 component."
                ),
            },
        },
        "simultaneous_reduction_requirement": {
            "endpoint_to_reopen_total_reduction_fraction": f(
                (endpoint_wall - reopen_batch_threshold) / endpoint_wall
            ),
            "already_assumed": {
                "prefill_queue_envelope": "100% deleted",
                "measured_decode_linears": "replaced by the ideal SM100 NVFP4 floor",
                "attention_kv_reduction_fraction": f(1 - 1 / attention_head_speedup),
                "tied_head_reduction_fraction": f(1 - 1 / attention_head_speedup),
            },
            "additional_algebraic_residual_reduction_for_economic_hurdle_seconds": f(
                base_residual_reduction
            ),
            "additional_algebraic_residual_reduction_for_economic_hurdle_fraction": f(
                base_residual_reduction / algebraic_tail_residual
            ),
            "additional_algebraic_residual_reduction_for_reopen_seconds": f(
                reopen_residual_reduction
            ),
            "additional_algebraic_residual_reduction_for_reopen_fraction": f(
                reopen_residual_reduction / algebraic_tail_residual
            ),
            "interpretation": (
                "Even after impossible queue deletion and ideal source-supported component credits, "
                "the remaining service/non-linear envelope needs a separate 53.0% reduction to earn "
                "20% headroom. That intervention is neither the staged NVFP4 component mechanism nor "
                "an attention/KV backend substitution."
            ),
        },
        "scheduling_discriminator": {
            "evidence_class": "measured and derived",
            "queue_span_seconds": f(max_ttft - min_ttft),
            "earliest_completion_seconds": f(earliest_completion),
            "h100_target_batch_seconds": attention["endpoint_reconciliation"]["target_batch_wall_seconds"],
            "b200_batch_hurdle_seconds": f(b200_batch_hurdle),
            "interpretation": (
                "Queue removal is independent: earliest H100 completion already misses the H100 target, "
                "and the B200 closure bound gives the full queue/prefill envelope away yet still misses."
            ),
        },
        "staged_24_row_falsifier": {
            "identity": "b200_nvfp4_exact_shape_direct_falsifier/b200_nvfp4_evaluator.py",
            "disposition": "do_not_reopen",
            "reason": (
                "Even zero decode-linear time in the impossible full-stack envelope misses the B200 "
                "economic hurdle; component timing cannot supply the independent residual intervention."
            ),
        },
        "decision": {
            "terminal": "close_b200_fullstack",
            "reason": (
                "The impossible NVFP4-optimistic full-stack bound misses the price-normalized hurdle, "
                "and the source-supported bound misses the 20% reopen threshold. Passing requires an "
                "independent, unpartitioned residual speedup unsupported by the pinned mechanism."
            ),
            "provider_mutation": False,
            "gpu_seconds": 0,
            "spend_usd": 0,
        },
        "evidence_boundary": (
            "Measured H100 endpoint/component evidence, pinned-source runtime support, and analytical "
            "bounds only. No B200 timing, compilation, checkpoint, quality, endpoint, deployability, "
            "or provider-availability claim."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-upstream", action="store_true")
    parser.add_argument("--output", type=Path, default=PROJECT / "FULLSTACK_BOUND.json")
    args = parser.parse_args()
    result = build(args.verify_upstream)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
