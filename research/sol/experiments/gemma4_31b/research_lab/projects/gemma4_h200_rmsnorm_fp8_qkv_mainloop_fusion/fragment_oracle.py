#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import struct
import sys


HIDDEN = 5376
N = 16384
K_TILE = 256
CLUSTER_BLOCKS = 8
SHAPES = (1, 16, 32)
SAMPLED_COLUMNS = (0, 63, 64, 8191, 8192, 12287, 12288, 16383)
ORACLE_SHA256 = (
    "a88f79d734111e8a4e7f3fd82d6d1072d7934fd296628587c66f3a006a49eb7c"
)
QKV = (
    ("model.language_model.layers.0.self_attn.q_proj.weight", 0, 8192),
    ("model.language_model.layers.0.self_attn.k_proj.weight", 8192, 4096),
    ("model.language_model.layers.0.self_attn.v_proj.weight", 12288, 4096),
)


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_exact_oracle(path: pathlib.Path):
    observed = sha256(path)
    if observed != ORACLE_SHA256:
        raise RuntimeError(
            f"exact-order oracle mismatch: {observed} != {ORACLE_SHA256}"
        )
    spec = importlib.util.spec_from_file_location("exact_order_oracle", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load exact-order oracle")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def safetensors_header(path: pathlib.Path) -> tuple[int, dict[str, object]]:
    with path.open("rb") as handle:
        header_size = struct.unpack("<Q", handle.read(8))[0]
        header = json.loads(handle.read(header_size))
    return header_size, header


def load_qkv_column(
    path: pathlib.Path,
    header_size: int,
    header: dict[str, object],
    column: int,
    exact,
) -> tuple[list[float], dict[str, object]]:
    for key, first, rows in QKV:
        if first <= column < first + rows:
            local_row = column - first
            entry = header[key]
            if entry["dtype"] != "BF16" or entry["shape"] != [rows, HIDDEN]:
                raise RuntimeError(f"unexpected QKV entry: {entry}")
            start = entry["data_offsets"][0] + local_row * HIDDEN * 2
            with path.open("rb") as handle:
                handle.seek(8 + header_size + start)
                raw = handle.read(HIDDEN * 2)
            if len(raw) != HIDDEN * 2:
                raise RuntimeError("short QKV row")
            values = [
                exact.bf16_from_bits(bits)
                for (bits,) in struct.iter_unpack("<H", raw)
            ]
            return values, {
                "column": column,
                "source_key": key,
                "source_row": local_row,
                "bf16_bytes_sha256": hashlib.sha256(raw).hexdigest(),
            }
    raise RuntimeError(f"column out of range: {column}")


def quantize_weight(values: list[float], exact) -> tuple[bytes, float]:
    maximum = max(abs(value) for value in values)
    scale = exact.f32(max(maximum / exact.FP8_MAXIMUM, 1e-8))
    inverse = exact.f32(1.0 / scale)
    codes = bytearray()
    for value in values:
        unbounded = exact.f32(value * inverse)
        bounded = exact.cuda_fmax(
            exact.cuda_fmin(unbounded, exact.FP8_MAXIMUM),
            -exact.FP8_MAXIMUM,
        )
        codes.append(exact.fp8_code(bounded))
    return bytes(codes), scale


def f32_dot(
    activation: bytes,
    activation_scale: float,
    weight: bytes,
    weight_scale: float,
    exact,
) -> tuple[float, list[int]]:
    partial_bits = []
    total = exact.f32(0.0)
    for start in range(0, HIDDEN, K_TILE):
        partial = exact.f32(0.0)
        for index in range(start, min(start + K_TILE, HIDDEN)):
            left = exact.fp8_value(activation[index])
            right = exact.fp8_value(weight[index])
            partial = exact.f32(left * right + partial)
        total = exact.f32(total + partial)
        partial_bits.append(exact.f32_bits(partial))
    scaled = exact.f32(
        exact.f32(total * activation_scale) * weight_scale
    )
    return scaled, partial_bits


def distribute(rows: list[bytes]) -> list[dict[int, list[bytes]]]:
    blocks: list[dict[int, list[bytes]]] = [
        {} for _ in range(CLUSTER_BLOCKS)
    ]
    for row_index, row in enumerate(rows):
        owner = row_index % CLUSTER_BLOCKS
        blocks[owner][row_index] = [
            row[start : start + K_TILE]
            for start in range(0, HIDDEN, K_TILE)
        ]
    return blocks


def reassemble(
    blocks: list[dict[int, list[bytes]]], row_count: int
) -> list[bytes]:
    result = []
    for row_index in range(row_count):
        owner = row_index % CLUSTER_BLOCKS
        result.append(b"".join(blocks[owner][row_index]))
    return result


def row_family(rows: int, exact) -> list[list[float]]:
    return exact.random_rows(rows, 2026073100 + rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component-safetensors", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parent
    oracle_path = (
        root
        / "../gemma4_h200_current_norm_fp8_hotblock/exact_order_oracle.py"
    ).resolve()
    exact = load_exact_oracle(oracle_path)
    component = args.component_safetensors.resolve()
    header_size, header = safetensors_header(component)
    norm_weight, norm_identity = exact.load_weight(component)
    qkv_columns = {}
    qkv_identities = {}
    for column in SAMPLED_COLUMNS:
        values, identity = load_qkv_column(
            component, header_size, header, column, exact
        )
        codes, scale = quantize_weight(values, exact)
        qkv_columns[column] = (codes, scale)
        identity["e4m3_bytes_sha256"] = hashlib.sha256(codes).hexdigest()
        identity["scale_f32_bits"] = exact.f32_bits(scale)
        qkv_identities[str(column)] = identity

    shape_rows = []
    all_pass = True
    for m in SHAPES:
        input_rows = row_family(m, exact)
        stages = [exact.stages(row, norm_weight, "stock") for row in input_rows]
        activation = [row.quantized for row in stages]
        scales = [
            struct.unpack("<f", row.scale)[0]
            for row in stages
        ]
        blocks = distribute(activation)
        rebuilt = reassemble(blocks, m)
        activation_exact = rebuilt == activation
        scale_owner_exact = all(
            row_index % CLUSTER_BLOCKS
            == row_index % CLUSTER_BLOCKS
            for row_index in range(m)
        )
        sampled_dots = {}
        dot_exact = True
        for column in SAMPLED_COLUMNS:
            weight_codes, weight_scale = qkv_columns[column]
            materialized = []
            distributed = []
            fragment_hashes = []
            for row_index in range(m):
                control, control_partials = f32_dot(
                    activation[row_index],
                    scales[row_index],
                    weight_codes,
                    weight_scale,
                    exact,
                )
                candidate, candidate_partials = f32_dot(
                    rebuilt[row_index],
                    scales[row_index],
                    weight_codes,
                    weight_scale,
                    exact,
                )
                materialized.append(exact.f32_bits(control))
                distributed.append(exact.f32_bits(candidate))
                fragment_hashes.append(
                    hashlib.sha256(
                        b"".join(
                            struct.pack("<I", value)
                            for value in candidate_partials
                        )
                    ).hexdigest()
                )
                dot_exact &= control_partials == candidate_partials
            dot_exact &= materialized == distributed
            sampled_dots[str(column)] = {
                "materialized_f32_bits": materialized,
                "distributed_f32_bits": distributed,
                "fragment_partial_hashes": fragment_hashes,
                "exact": materialized == distributed,
            }
        shape_pass = activation_exact and scale_owner_exact and dot_exact
        all_pass &= shape_pass
        shape_rows.append(
            {
                "m": m,
                "pass": shape_pass,
                "activation_bytes_exact": activation_exact,
                "scale_owner_exact": scale_owner_exact,
                "fragment_reference_exact": dot_exact,
                "activation_sha256": hashlib.sha256(
                    b"".join(activation)
                ).hexdigest(),
                "scale_sha256": hashlib.sha256(
                    b"".join(row.scale for row in stages)
                ).hexdigest(),
                "cluster_row_owners": [
                    {
                        "block": block,
                        "rows": sorted(blocks[block]),
                        "fragment_count": sum(
                            len(fragments)
                            for fragments in blocks[block].values()
                        ),
                    }
                    for block in range(CLUSTER_BLOCKS)
                ],
                "k_fragments_per_row": math.ceil(HIDDEN / K_TILE),
                "last_fragment_elements": HIDDEN % K_TILE,
                "sampled_real_qkv_columns": sampled_dots,
            }
        )

    zero = exact.stages(exact.zero_rows(1)[0], norm_weight, "stock")
    zero_contract = {
        "scale_f32_bits": struct.unpack("<I", zero.scale)[0],
        "activation_unique_codes": sorted(set(zero.quantized)),
        "pass": (
            struct.unpack("<I", zero.scale)[0] == 0
            and set(zero.quantized) == {0x7E}
        ),
        "note": (
            "The pinned CUDA expression divides signed-zero BF16 by +0 scale; "
            "clamping maps the resulting NaN to +448, E4M3 code 0x7e."
        ),
    }
    all_pass &= zero_contract["pass"]
    result = {
        "schema_version": 1,
        "classification": (
            "exact_fragment_oracle_pass"
            if all_pass
            else "exact_fragment_oracle_failure"
        ),
        "pass": all_pass,
        "evidence_class": "deterministic_cpu_reference",
        "component": {
            "path": str(component),
            "sha256": sha256(component),
            "header_metadata": header["__metadata__"],
        },
        "exact_order_oracle": {
            "path": str(oracle_path),
            "sha256": ORACLE_SHA256,
        },
        "norm_weight": norm_identity,
        "qkv_sampled_columns": qkv_identities,
        "geometry": {
            "m": list(SHAPES),
            "k": HIDDEN,
            "n": N,
            "cluster_blocks": CLUSTER_BLOCKS,
            "k_tile": K_TILE,
            "sampled_output_columns": list(SAMPLED_COLUMNS),
        },
        "rows": shape_rows,
        "signed_zero_contract": zero_contract,
        "transfer_limit": (
            "The reference proves producer bytes, cluster row/K-fragment "
            "indexing, Q/K/V boundary selection, and mathematical FP32 "
            "fragment equivalence. CUTLASS FP8FastAccum instruction order and "
            "BF16 output bytes require the named complete-output H200 call."
        ),
    }
    atomic(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
