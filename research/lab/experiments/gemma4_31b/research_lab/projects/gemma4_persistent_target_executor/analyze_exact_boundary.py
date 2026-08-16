from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import pathlib


TRACE_SHA256 = "37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b"
PRIOR_TERMINAL_SHA256 = (
    "a08190cc600cca336c5d0ebe04f4d9353797e01ed0fd026011da462ddb847d34"
)
ACTIVATION = "act_and_mul_kernel"
QUANT = "per_token_quant_fp8_small_batch_kernel"
GEMM = "cutlass_3x_gemm_sm90_fp8"
RESIDUAL = "_gemma_rmsnorm_residual_kernel"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=pathlib.Path, required=True)
    parser.add_argument("--prior-terminal", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if sha256(args.trace) != TRACE_SHA256:
        raise RuntimeError("current trace identity mismatch")
    if sha256(args.prior_terminal) != PRIOR_TERMINAL_SHA256:
        raise RuntimeError("prior real-consumer terminal identity mismatch")

    with gzip.open(args.trace, "rt", encoding="utf-8") as handle:
        events = json.load(handle)["traceEvents"]
    complete = [
        event
        for event in events
        if event.get("ph") == "X"
        and isinstance(event.get("ts"), (int, float))
        and isinstance(event.get("dur"), (int, float))
    ]
    semantic = [
        event for event in complete if "ngram." in str(event.get("name"))
    ]
    window_start = min(event["ts"] for event in semantic)
    window_end = max(event["ts"] + event["dur"] for event in semantic)
    window_us = window_end - window_start
    gpu = sorted(
        [
            event
            for event in complete
            if window_start <= event["ts"] < window_end
            and str(event.get("cat", "")).lower()
            in {"kernel", "gpu_memcpy", "gpu_memset"}
        ],
        key=lambda event: event["ts"],
    )

    seams = []
    for index, event in enumerate(gpu):
        if ACTIVATION not in str(event.get("name")):
            continue
        previous_quant = gpu[index - 2]
        gate_up = gpu[index - 1]
        down_quant = gpu[index + 1]
        down = gpu[index + 2]
        residual = gpu[index + 3]
        names = [
            str(previous_quant.get("name")),
            str(gate_up.get("name")),
            str(down_quant.get("name")),
            str(down.get("name")),
            str(residual.get("name")),
        ]
        if not (
            QUANT in names[0]
            and GEMM in names[1]
            and QUANT in names[2]
            and GEMM in names[3]
            and RESIDUAL in names[4]
        ):
            raise RuntimeError(f"exact MLP adjacency mismatch:{names}")
        correlations = {
            row.get("args", {}).get("correlation")
            for row in (
                previous_quant,
                gate_up,
                event,
                down_quant,
                down,
                residual,
            )
        }
        streams = {
            row.get("args", {}).get("stream")
            for row in (
                previous_quant,
                gate_up,
                event,
                down_quant,
                down,
                residual,
            )
        }
        if len(correlations) != 1 or len(streams) != 1:
            raise RuntimeError("MLP chain crosses correlation or stream")
        seams.append(
            {
                "activation_us": event["dur"],
                "down_gemm_us": down["dur"],
                "down_quant_us": down_quant["dur"],
                "full_block_interval_us": (
                    residual["ts"] + residual["dur"] - previous_quant["ts"]
                ),
                "gate_up_gemm_us": gate_up["dur"],
                "launch_gap_us": (
                    down_quant["ts"] - (event["ts"] + event["dur"])
                    + down["ts"]
                    - (down_quant["ts"] + down_quant["dur"])
                ),
                "removable_seam_upper_us": down["ts"] - event["ts"],
                "residual_us": residual["dur"],
            }
        )
    if len(seams) != 900:
        raise RuntimeError(f"expected 15*60 MLP seams, got {len(seams)}")

    sums = {
        key: sum(row[key] for row in seams)
        for key in seams[0]
    }
    prior = json.loads(args.prior_terminal.read_text())
    prior_rows = {row["tokens"]: row for row in prior["rows"]}
    if (
        prior.get("consumer_symbol")
        != "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm"
        or prior["weight_metadata"]["consumer_weight_shape"] != [21504, 5376]
        or prior["weight_metadata"]["consumer_weight_stride"] != [1, 21504]
    ):
        raise RuntimeError("prior real-consumer binding mismatch")

    elements_per_invocation = 384 * 21504
    bytes_removed_per_invocation = elements_per_invocation * 6
    removable_fraction = sums["removable_seam_upper_us"] / window_us
    target_fraction = 0.10
    result = {
        "binding": {
            "prior_real_consumer_terminal_sha256": PRIOR_TERMINAL_SHA256,
            "runtime_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "trace_sha256": TRACE_SHA256,
        },
        "candidate": {
            "baseline": (
                "GeluAndMul(BF16) -> per-token E4M3 quant -> "
                "fp8_scaled_mm down projection"
            ),
            "consumer": (
                "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm"
            ),
            "geometry": {
                "down_weight": [21504, 5376],
                "gate_up_output": [384, 43008],
                "quantized_activation": [384, 21504],
            },
            "implementation": "fused_swiglu_quant.cu",
            "mechanism": (
                "one CTA per row retains the once-rounded BF16 SwiGLU "
                "intermediate in 43,008 shared-memory bytes for row amax and "
                "E4M3 conversion, then feeds the unchanged column-major down GEMM"
            ),
            "semantics_repair": (
                "removed the prior extra BF16 rounding between GELU and multiply"
            ),
        },
        "decision": {
            "reason_code": "measured_removable_wall_share_below_target",
            "result": "typed_none",
            "target_fraction": target_fraction,
            "target_us_in_trace_window": target_fraction * window_us,
            "upper_bound_fraction_of_target": removable_fraction / target_fraction,
            "whole_request_reduction_fraction_upper": removable_fraction,
        },
        "evidence_labels": {
            "adjacency_and_time": "measured",
            "candidate_dataflow": "implemented",
            "consumer_compatibility": "measured_prior_exact_consumer",
            "whole_request_bound": "derived_conservative_upper",
        },
        "materialization": {
            "bf16_bytes_removed_per_invocation": bytes_removed_per_invocation,
            "bf16_bytes_removed_trace": bytes_removed_per_invocation * len(seams),
            "launches_removed_trace": len(seams),
            "shared_memory_bytes_per_cta": 21504 * 2,
        },
        "measured_trace": {
            "activation_launches": len(seams),
            "expected_layers_times_steps": "60*15",
            "non_attention_selected_block_fraction": (
                sums["full_block_interval_us"] / window_us
            ),
            "sums_us": sums,
            "target_verification_window_us": window_us,
        },
        "prior_real_consumer": {
            "classification": prior["classification"],
            "consumer_weight_shape": prior["weight_metadata"][
                "consumer_weight_shape"
            ],
            "consumer_weight_stride": prior["weight_metadata"][
                "consumer_weight_stride"
            ],
            "old_candidate_m2048_component_ms": prior_rows[2048][
                "candidate_component_ms"
            ],
            "old_candidate_m32_component_ms": prior_rows[32][
                "candidate_component_ms"
            ],
            "scope_note": (
                "Used only as actual-consumer/path evidence; M32/M2048 timing "
                "and the extra-rounding numerical negative are not transferred "
                "to the corrected M384 candidate."
            ),
        },
        "schema_version": 1,
    }
    atomic(args.output, result)


if __name__ == "__main__":
    main()
