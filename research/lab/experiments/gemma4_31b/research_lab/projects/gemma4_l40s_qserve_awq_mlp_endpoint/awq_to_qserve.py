#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import struct
from typing import Any

import numpy as np


AWQ_ORDER = np.asarray((0, 4, 1, 5, 2, 6, 3, 7), dtype=np.int64)
GROUP_SIZE = 128
PROJECTIONS = {
    "gate_proj": (5376, 21504),
    "up_proj": (5376, 21504),
    "down_proj": (21504, 5376),
}
PREFIX = "model.language_model.layers.0.mlp"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


class SafeTensorFile:
    def __init__(self, path: pathlib.Path):
        self.path = path
        with path.open("rb") as handle:
            header_length = struct.unpack("<Q", handle.read(8))[0]
            self.header = json.loads(handle.read(header_length))
        self.data_offset = 8 + header_length

    def tensor(self, name: str) -> np.memmap:
        metadata = self.header[name]
        dtype = {"I32": "<i4", "BF16": "<u2"}[metadata["dtype"]]
        start, _ = metadata["data_offsets"]
        return np.memmap(
            self.path,
            dtype=dtype,
            mode="r",
            offset=self.data_offset + start,
            shape=tuple(metadata["shape"]),
        )

    def metadata(self, name: str) -> dict[str, Any]:
        return self.header[name]


def unpack_awq_words(words: np.ndarray) -> np.ndarray:
    unsigned = words.view(np.uint32)
    unpacked = np.stack(
        tuple((unsigned >> np.uint32(4 * index)) & np.uint32(15) for index in range(8)),
        axis=-1,
    )
    return unpacked[..., AWQ_ORDER].reshape(words.shape[0], words.shape[1] * 8).astype(
        np.uint8
    )


def qserve_pack_codes(codes_nk: np.ndarray) -> np.ndarray:
    output_features, input_features = codes_nk.shape
    if output_features % 32 or input_features % 32:
        raise ValueError("QServe packing requires N%32==0 and K%32==0")
    reordered = (
        codes_nk.reshape(
            output_features // 32,
            2,
            2,
            8,
            input_features // 32,
            2,
            4,
            4,
        )
        .transpose(0, 4, 3, 6, 1, 5, 2, 7)
        .copy()
        .transpose(0, 1, 2, 3, 5, 6, 7, 4)
        .copy()
    )
    packed = (reordered[..., 1].astype(np.uint8) << 4) | reordered[
        ..., 0
    ].astype(np.uint8)
    return packed.reshape(output_features, input_features // 2).view(np.int8)


def qserve_unpack_codes(packed: np.ndarray) -> np.ndarray:
    output_features, packed_input_features = packed.shape
    input_features = packed_input_features * 2
    pairs = np.stack(
        (packed.view(np.uint8) & np.uint8(15), packed.view(np.uint8) >> 4), axis=-1
    )
    reordered = pairs.reshape(
        output_features // 32,
        input_features // 32,
        8,
        4,
        2,
        2,
        4,
        2,
    )
    first = reordered.transpose(0, 1, 2, 3, 7, 4, 5, 6).copy()
    return (
        first.transpose(0, 4, 5, 2, 1, 6, 3, 7)
        .copy()
        .reshape(output_features, input_features)
    )


def qserve_reorder_group_metadata(tensor_ng: np.ndarray) -> np.ndarray:
    output_features, groups = tensor_ng.shape
    return (
        tensor_ng.T.copy()
        .reshape(groups, output_features // 32, 4, 8)
        .transpose(0, 1, 3, 2)
        .copy()
        .reshape(groups, output_features)
    )


def qserve_restore_group_metadata(tensor_gn: np.ndarray) -> np.ndarray:
    groups, output_features = tensor_gn.shape
    return (
        tensor_gn.reshape(groups, output_features // 32, 8, 4)
        .transpose(0, 1, 3, 2)
        .copy()
        .reshape(groups, output_features)
        .T.copy()
    )


def bfloat16_to_float64(bits: np.ndarray) -> np.ndarray:
    return (bits.astype(np.uint32) << np.uint32(16)).view(np.float32).astype(np.float64)


def exact_progressive_factor(
    scale_bits_gn: np.ndarray,
    active_gn: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    exponents = ((scale_bits_gn >> np.uint16(7)) & np.uint16(255)).astype(np.int32)
    mantissas = (np.uint64(128) + (scale_bits_gn & np.uint16(127))).astype(np.uint64)
    if np.any(active_gn & ((exponents == 0) | (exponents == 255))):
        raise ValueError("active scale is zero, subnormal, or nonfinite")
    masked_exponents = np.where(active_gn, exponents, 255)
    minimum_exponents = masked_exponents.min(axis=0)
    exponent_offsets = np.where(active_gn, exponents - minimum_exponents, 0)
    exact_integers = mantissas << exponent_offsets.astype(np.uint64)
    exact_integers = np.where(active_gn, exact_integers, np.uint64(0))
    common_divisors = np.gcd.reduce(exact_integers, axis=0)
    ratios = np.floor_divide(
        exact_integers,
        common_divisors[None, :],
        out=np.ones_like(exact_integers),
        where=active_gn,
    )
    bases = np.ldexp(common_divisors.astype(np.float64), minimum_exponents - 134)
    fp16_bases = bases.astype(np.float16)
    reconstructed = fp16_bases.astype(np.float64)[None, :] * ratios.astype(np.float64)
    target = bfloat16_to_float64(scale_bits_gn)
    exact = np.all((~active_gn) | (reconstructed == target), axis=0)
    return fp16_bases, ratios, exact


def projection_analysis(
    source: SafeTensorFile,
    projection: str,
    chunk_outputs: int,
) -> tuple[dict[str, Any], dict[str, np.ndarray] | None]:
    input_features, output_features = PROJECTIONS[projection]
    groups = input_features // GROUP_SIZE
    base = f"{PREFIX}.{projection}"
    qweight = source.tensor(f"{base}.qweight")
    qzeros_words = source.tensor(f"{base}.qzeros")
    scale_bits = source.tensor(f"{base}.scales")
    expected = {
        "qweight": ([input_features, output_features // 8], "I32"),
        "qzeros": ([groups, output_features // 8], "I32"),
        "scales": ([groups, output_features], "BF16"),
    }
    for suffix, (shape, dtype) in expected.items():
        observed = source.metadata(f"{base}.{suffix}")
        if observed["shape"] != shape or observed["dtype"] != dtype:
            raise ValueError(
                f"{projection}:{suffix}:expected={shape}/{dtype}:"
                f"observed={observed['shape']}/{observed['dtype']}"
            )

    zero_points = unpack_awq_words(qzeros_words)
    max_required = np.zeros(output_features, dtype=np.uint64)
    exact_scale = np.zeros(output_features, dtype=bool)
    stage1_range = np.zeros(output_features, dtype=bool)
    active_counts = np.zeros(output_features, dtype=np.int32)
    required_stage1_absmax = np.zeros(output_features, dtype=np.int64)
    required_zero_absmax = np.zeros(output_features, dtype=np.int64)
    stage2_all = np.zeros((groups, output_features), dtype=np.uint64)
    s1_all = np.zeros(output_features, dtype=np.float16)
    qserve_weight = np.empty((output_features, input_features // 2), dtype=np.int8)

    for output_start in range(0, output_features, chunk_outputs):
        output_stop = min(output_start + chunk_outputs, output_features)
        packed_start = output_start // 8
        packed_stop = output_stop // 8
        codes_kn = unpack_awq_words(qweight[:, packed_start:packed_stop])
        zeros_gn = zero_points[:, output_start:output_stop]
        active_gn = np.any(
            codes_kn.reshape(groups, GROUP_SIZE, output_stop - output_start)
            != zeros_gn[:, None, :],
            axis=1,
        )
        s1, stage2, exact = exact_progressive_factor(
            scale_bits[:, output_start:output_stop], active_gn
        )
        centered = codes_kn.reshape(groups, GROUP_SIZE, output_stop - output_start).astype(
            np.int16
        ) - zeros_gn[:, None, :].astype(np.int16)
        stage1 = centered.astype(np.int64) * stage2[:, None, :].astype(np.int64)
        zero_terms = -zeros_gn.astype(np.int64) * stage2.astype(np.int64)
        in_range = (
            (stage1.min(axis=(0, 1)) >= -128)
            & (stage1.max(axis=(0, 1)) <= 127)
            & (zero_terms.min(axis=0) >= -128)
            & (zero_terms.max(axis=0) <= 127)
            & (stage2.max(axis=0) <= 127)
        )
        active_counts[output_start:output_stop] = active_gn.sum(axis=0)
        max_required[output_start:output_stop] = stage2.max(axis=0)
        exact_scale[output_start:output_stop] = exact
        stage1_range[output_start:output_stop] = in_range
        required_stage1_absmax[output_start:output_stop] = np.abs(stage1).max(
            axis=(0, 1)
        )
        required_zero_absmax[output_start:output_stop] = np.abs(zero_terms).max(axis=0)
        stage2_all[:, output_start:output_stop] = stage2
        s1_all[output_start:output_stop] = s1
        if np.all(exact & in_range):
            qserve_weight[output_start:output_stop] = qserve_pack_codes(codes_kn.T)

    convertible = exact_scale & stage1_range
    best = int(np.argmin(max_required))
    worst = int(np.argmax(max_required))
    report = {
        "projection": projection,
        "input_features": input_features,
        "output_features": output_features,
        "groups": groups,
        "active_group_count_min": int(active_counts.min()),
        "active_group_count_max": int(active_counts.max()),
        "convertible_output_channels": int(convertible.sum()),
        "exact_scale_output_channels": int(exact_scale.sum()),
        "stage1_range_output_channels": int(stage1_range.sum()),
        "minimum_required_max_stage2": {
            "minimum": int(max_required.min()),
            "median": float(np.median(max_required)),
            "maximum": int(max_required.max()),
        },
        "required_stage1_absolute_maximum": {
            "minimum": int(required_stage1_absmax.min()),
            "median": float(np.median(required_stage1_absmax)),
            "maximum": int(required_stage1_absmax.max()),
        },
        "required_scaled_zero_absolute_maximum": {
            "minimum": int(required_zero_absmax.min()),
            "median": float(np.median(required_zero_absmax)),
            "maximum": int(required_zero_absmax.max()),
        },
        "best_witness": {
            "output_channel": best,
            "required_max_stage2": int(max_required[best]),
            "active_groups": int(active_counts[best]),
        },
        "worst_witness": {
            "output_channel": worst,
            "required_max_stage2": int(max_required[worst]),
            "active_groups": int(active_counts[worst]),
        },
        "pass": bool(np.all(convertible)),
    }
    if not report["pass"]:
        return report, None

    zeros_scaled = -zero_points.astype(np.int64) * stage2_all.astype(np.int64)
    converted = {
        f"{projection}.qweight": qserve_weight,
        f"{projection}.s2_scales": qserve_reorder_group_metadata(
            stage2_all.T.astype(np.int8)
        ),
        f"{projection}.s2_zeros": qserve_reorder_group_metadata(
            zeros_scaled.T.astype(np.int8)
        ),
        f"{projection}.s1_scales": s1_all,
    }
    return report, converted


def verify_round_trip(
    source: SafeTensorFile,
    projection: str,
    converted: dict[str, np.ndarray],
) -> dict[str, Any]:
    input_features, output_features = PROJECTIONS[projection]
    groups = input_features // GROUP_SIZE
    base = f"{PREFIX}.{projection}"
    original_codes = unpack_awq_words(source.tensor(f"{base}.qweight"))
    zero_points = unpack_awq_words(source.tensor(f"{base}.qzeros"))
    scales = bfloat16_to_float64(source.tensor(f"{base}.scales"))
    restored_codes = qserve_unpack_codes(converted[f"{projection}.qweight"]).T
    restored_stage2 = qserve_restore_group_metadata(
        converted[f"{projection}.s2_scales"]
    ).T.astype(np.int64)
    restored_zeros = qserve_restore_group_metadata(
        converted[f"{projection}.s2_zeros"]
    ).T.astype(np.int64)
    s1 = converted[f"{projection}.s1_scales"].astype(np.float64)
    original = (
        original_codes.reshape(groups, GROUP_SIZE, output_features).astype(np.int64)
        - zero_points[:, None, :].astype(np.int64)
    ) * scales[:, None, :]
    restored = (
        restored_codes.reshape(groups, GROUP_SIZE, output_features).astype(np.int64)
        * restored_stage2[:, None, :]
        + restored_zeros[:, None, :]
    ) * s1[None, None, :]
    return {
        "codes_equal": bool(np.array_equal(restored_codes, original_codes)),
        "dequantized_equal": bool(np.array_equal(restored, original)),
        "maximum_absolute_error": float(np.max(np.abs(restored - original))),
        "nonfinite_count": int((~np.isfinite(restored)).sum()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--chunk-outputs", type=int, default=512)
    args = parser.parse_args()
    if args.chunk_outputs % 32:
        raise ValueError("chunk outputs must be divisible by 32")
    observed_source_sha256 = sha256(args.source)
    if observed_source_sha256 != args.source_sha256:
        raise RuntimeError(
            f"source_hash_mismatch:{args.source_sha256}:{observed_source_sha256}"
        )
    args.output.mkdir(parents=True, exist_ok=False)
    source = SafeTensorFile(args.source)
    reports = []
    all_converted: dict[str, np.ndarray] = {}
    for projection in PROJECTIONS:
        report, converted = projection_analysis(source, projection, args.chunk_outputs)
        reports.append(report)
        if converted is not None:
            all_converted.update(converted)

    representation_pass = all(report["pass"] for report in reports)
    round_trips = []
    if representation_pass:
        from safetensors.numpy import save_file

        converted_path = args.output / "layer0_qserve.safetensors"
        save_file(all_converted, converted_path)
        for projection in PROJECTIONS:
            round_trips.append(verify_round_trip(source, projection, all_converted))
        representation_pass = all(
            row["codes_equal"]
            and row["dequantized_equal"]
            and row["nonfinite_count"] == 0
            for row in round_trips
        )
    classification = (
        "layer0_exact_awq_qserve_round_trip"
        if representation_pass
        else "fixed_qserve_progressive_scale_incompatibility"
    )
    terminal = {
        "schema_version": 1,
        "classification": classification,
        "pass": representation_pass,
        "gpu_admission": representation_pass,
        "source": {
            "path": str(args.source.resolve()),
            "sha256": observed_source_sha256,
            "format": "AWQ W4 group_size=128 zero_point=true GEMM",
        },
        "consumer": {
            "layout": "QServe W4A8 per-group compute-aware SM89",
            "s1_scale_dtype": "float16",
            "s2_scale_dtype": "int8",
            "stage1_weight_dtype": "int8",
        },
        "projections": reports,
        "round_trips": round_trips,
        "interpretation": (
            "The bound tensors map without semantic change."
            if representation_pass
            else "At least one active AWQ scale set cannot be represented by the fixed "
            "QServe FP16-per-output times integer-per-group scale contract. "
            "Approximation would be requantization and is outside the admitted scope."
        ),
    }
    atomic_json(args.output / "ROUND_TRIP_TERMINAL.json", terminal)
    return 0 if representation_pass else 20


if __name__ == "__main__":
    raise SystemExit(main())
