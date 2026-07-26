#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib


PROJECT = pathlib.Path(__file__).resolve().parent
FULL = PROJECT / "FULL_CHECKPOINT_STREAM_RESULT.json"
OUTPUT = PROJECT / "LOSSLESS_FP8_WEIGHT_STREAM_SCREEN.json"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def main() -> int:
    measured = json.loads(FULL.read_text())
    aggregate = measured["aggregate"]
    rows = measured["modules"]
    decode_exact = all(row["decode"]["bitwise_equal"] for row in rows)
    decoded_bytes = sum(row["decode"]["decoded_bytes"] for row in rows)
    target = aggregate["economics"]["target_seconds_per_request"]
    zero_decode = aggregate["economics"][
        "zero_decode_cost_hbm_proportional_request_seconds"
    ]
    if not decode_exact or decoded_bytes != aggregate["transformer_parameters"]:
        gate = "bitwise_decode"
        rationale = "The CPU reference decoder did not reproduce every FP8 byte."
    elif zero_decode > target:
        gate = "entropy_and_economic"
        rationale = (
            "The preregistered exact code expands the exact runtime FP8 stream; "
            "even granting zero decode, branch, LDS, synchronization, register, "
            "occupancy, cache, and fallback cost misses the service target."
        )
    else:
        gate = "target_gfx950_discriminator_unavailable"
        rationale = (
            "The code passed the checkpoint lower bound, but no compatible "
            "shared gfx950 bench exists and zero spend/resource creation forbids "
            "a target execution."
        )

    result = {
        "schema_version": 1,
        "result": "typed_none",
        "typed_none": {
            "gate": gate,
            "rationale": rationale,
            "closes": "preregistered tensor_top31_u5_escape_v1 exact lossless FP8 weight-stream realization",
        },
        "model": measured["model"],
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "checkpoint": {
            "access": measured["checkpoint_access"],
            "bindings": measured["bindings"],
            "full_measurement": str(FULL.relative_to(PROJECT)),
            "full_measurement_sha256": sha256(FULL),
        },
        "runtime_weight_stream": {
            "logical_transformer_parameters": aggregate[
                "transformer_parameters"
            ],
            "runtime_modules": aggregate["runtime_modules"],
            "runtime_fp8_bytes": aggregate["runtime_fp8_bytes"],
            "global_k_equals_v_logical_duplication_bytes": 110100480,
            "quantization": measured["runtime_quantization"],
            "source_binding": {
                "artifact": "../gemma4_mi355x_fp8_runtime_codesign/SOURCE_BINDINGS.json",
                "artifact_sha256": "c7f08b334a36e88009b273535dcbddb64c2c3307dfc7d7cd5a1ee946a04dd1bd",
                "vllm_commit": "0164022c907014a27e81c514cd4dff6091904c2b",
                "online_fp8_source_sha256": "e7bbca668d3ce6134d24110ff3b5070f51d3fee21852a3fd90c1c83d4a04f2fc",
                "rocm_scaled_mm_source_sha256": "38e0ee3137127caea6c2cd0dc8e67506c339b55611060b40a18b3c79bebe9547",
            },
            "encoded_tensor_manifest_sha256": aggregate[
                "encoded_tensor_manifest_sha256"
            ],
        },
        "preregistered_code": {
            "artifact": "PREREGISTERED_BLOCK_CODE.json",
            "artifact_sha256": sha256(PROJECT / "PREREGISTERED_BLOCK_CODE.json"),
            "name": measured["codec"]["code"],
            "block_bytes": measured["codec"]["block_bytes"],
            "block_mapping": measured["codec"]["layout"]["block_mapping"],
            "codec_family_swept": False,
            "block_size_swept": False,
        },
        "measured_losslessness": {
            "bitwise_equal": decode_exact,
            "decoded_bytes": decoded_bytes,
            "mismatched_bytes": sum(
                row["decode"]["mismatched_bytes"] for row in rows
            ),
            "module_stream_hashes": [
                {
                    "layer": row["layer"],
                    "kind": row["kind"],
                    **row["hashes"],
                }
                for row in rows
            ],
        },
        "measured_compression": {
            key: aggregate[key]
            for key in (
                "encoded_bytes",
                "compression_ratio",
                "bytes_avoided",
                "aggregate_byte_entropy_bits",
                "all_block_entropy_bits",
                "all_block_encoded_bytes_including_directory_entry",
                "block_count",
                "incompressible_blocks",
                "expanding_blocks",
                "worst_layer_by_ratio",
                "worst_module_by_ratio",
            )
        },
        "charged_costs": {
            "metadata_alignment_tokens_and_literals": "included exactly in encoded_bytes and every module ratio",
            "decode_instructions": {
                "charged_seconds": 0.0,
                "evidence_type": "analytical best-case lower bound",
                "interpretation": "Real unpack, escape-rank, branch, and literal-load cost is nonnegative and can only worsen a failed bound.",
            },
            "resource_and_integration": {
                "charged_seconds": 0.0,
                "items": [
                    "gfx950 wave64 unpack",
                    "dictionary and uint32 directory loads",
                    "LDS staging of each 32x128 FP8 B tile",
                    "workgroup synchronization",
                    "register and accumulator pressure",
                    "occupancy loss",
                    "L2/cache pollution",
                    "unaligned escape-literal loads",
                    "fallback"
                ],
                "evidence_type": "analytical best-case lower bound",
                "interpretation": "All are constrained nonnegative; a zero-cost grant is stronger than any realizable charge and already misses.",
            },
            "fallback_bytes_or_seconds": 0,
            "fallback_allowed": False,
        },
        "gfx950_decode_to_gemm_binding": {
            "target": "AMD Instinct MI355X / gfx950 / CDNA4 / wave64",
            "primary_source": "https://rocm.docs.amd.com/projects/rocWMMA/en/docs-7.1.0/api-reference/api-reference-guide.html",
            "producer": "tensor_top31_u5_escape_v1 32x128 post-transpose KxN blocks",
            "first_consumer": "16x16x32 OCP-FP8 rocWMMA/MFMA tile inside the ROCmFP8ScaledMMLinearKernel replacement",
            "production_shapes": {
                "decode_rows": 32,
                "k_values": [5376, 8192, 16384, 21504],
                "n_values": [5376, 16384, 20480, 43008],
                "block_k": 32,
                "block_n": 128,
            },
            "physical_hypothesis": "Reduced compressed HBM traffic must repay per-tile 5-bit unpack and escape literals before the first FP8 MFMA.",
            "falsifying_observation": "Measured compressed HBM traffic exceeds the uncompressed FP8 traffic before any decode or MFMA instruction.",
            "source_complete_without_fallback": False,
            "target_discriminator": None,
            "target_discriminator_consumed": False,
            "reason_not_executed": "The earlier exact entropy/economic gate is decisive; additionally the shared inventory contains no compatible gfx950 bench.",
        },
        "economics": {
            **aggregate["economics"],
            "metadata_inclusive_ratio": aggregate["compression_ratio"],
            "passes_target_with_zero_decode_cost": zero_decode <= target,
            "shortfall_seconds_per_request": max(0.0, zero_decode - target),
        },
        "resource_accounting": {
            "provider_spend_usd": 0.0,
            "gpu_claimed": False,
            "provider_contacted": False,
            "checkpoint_copied_or_downloaded": False,
            "resource_created": False,
            "preserved_mi355x_lifecycle_altered": False,
        },
        "evidence_labels": {
            "compression_decode_and_checkpoint_hashes": "measured",
            "runtime_producer_consumer_symbols": "source-backed",
            "zero_decode_service_time": "derived optimistic lower bound",
            "gfx950_resource_cost_sign": "analytical",
            "target_gpu_timing": "unmeasured"
        },
    }
    atomic_json(OUTPUT, result)
    print(json.dumps({"output": str(OUTPUT), "sha256": sha256(OUTPUT)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
