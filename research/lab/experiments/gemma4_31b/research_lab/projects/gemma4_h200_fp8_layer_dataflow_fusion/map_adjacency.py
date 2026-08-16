#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sqlite3
from collections import Counter


QUANT_PATTERN = "void per_token_quant_fp8_small_batch_kernel%"
ACTIVATION_PATTERN = "%act_and_mul_kernel%"
PROJECTIONS = ("qkv_proj", "o_proj", "gate_up_proj", "down_proj")
EXACT_INTERMEDIATE = 21504


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", type=pathlib.Path, required=True)
    parser.add_argument("--gemma3-source", type=pathlib.Path, required=True)
    parser.add_argument("--fp8-source", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    gemma_source = args.gemma3_source.read_text()
    exact_forward = """    def forward(self, x: torch.Tensor) -> torch.Tensor:
        gate_up, _ = self.gate_up_proj(x)
        x = self.act_fn(gate_up)
        x, _ = self.down_proj(x)
        return x
"""
    if gemma_source.count(exact_forward) != 1:
        raise RuntimeError("bound Gemma3MLP adjacency is not unique")
    fp8_source = args.fp8_source.read_text()
    if fp8_source.count("qinput, x_scale = sglang_per_token_quant_fp8(input_2d)") != 1:
        raise RuntimeError("bound CUDA dynamic-FP8 producer is not unique")

    connection = sqlite3.connect(f"file:{args.sqlite}?mode=ro", uri=True)
    quant_rows = connection.execute(
        """
        SELECT k.start, k.end-k.start, k.gridX
        FROM CUPTI_ACTIVITY_KIND_KERNEL k
        JOIN StringIds s ON s.id=k.demangledName
        WHERE s.value LIKE ?
        ORDER BY k.start
        """,
        (QUANT_PATTERN,),
    ).fetchall()
    if len(quant_rows) % len(PROJECTIONS):
        raise RuntimeError("FP8 launch stream does not divide into four projections")
    projection_rows = []
    for index, projection in enumerate(PROJECTIONS):
        rows = quant_rows[index:: len(PROJECTIONS)]
        projection_rows.append(
            {
                "projection": projection,
                "launches": len(rows),
                "seconds": sum(row[1] for row in rows) / 1e9,
                "token_rows": sum(row[2] for row in rows),
                "grid_x_histogram": dict(sorted(Counter(row[2] for row in rows).items())),
            }
        )

    activation = connection.execute(
        """
        SELECT COUNT(*), SUM(k.end-k.start)
        FROM CUPTI_ACTIVITY_KIND_KERNEL k
        JOIN StringIds s ON s.id=k.demangledName
        WHERE s.value LIKE ?
        """,
        (ACTIVATION_PATTERN,),
    ).fetchone()
    down = projection_rows[-1]
    removed_bytes = int(down["token_rows"]) * EXACT_INTERMEDIATE * 6
    value = {
        "schema_version": 1,
        "pass": True,
        "evidence_class": {
            "source_adjacency": "source-backed",
            "kernel_time_and_geometry": "measured",
            "bytes_removed": "derived from measured token rows and exact dtype widths",
        },
        "inputs": {
            "sqlite": str(args.sqlite.resolve()),
            "sqlite_sha256": sha256(args.sqlite),
            "gemma3_source": str(args.gemma3_source.resolve()),
            "gemma3_source_sha256": sha256(args.gemma3_source),
            "fp8_source": str(args.fp8_source.resolve()),
            "fp8_source_sha256": sha256(args.fp8_source),
        },
        "exact_geometry": {
            "layers": 60,
            "hidden_size": 5376,
            "intermediate_size": EXACT_INTERMEDIATE,
            "gate_up_size": EXACT_INTERMEDIATE * 2,
            "activation": "gelu_pytorch_tanh_and_mul",
            "activation_dtype": "bfloat16",
            "dynamic_quantization": "per-token float8_e4m3fn",
        },
        "producer_adjacency": [
            {
                "producer": "RMSNorm",
                "consumer": "qkv_proj or gate_up_proj dynamic FP8 quantization",
                "reuse_constraint": "normalization output participates in residual/model dataflow; fusion has broader ownership",
            },
            {
                "producer": "attention output",
                "consumer": "o_proj dynamic FP8 quantization",
                "reuse_constraint": "attention backend owns the producer and exact layout varies by local/global layer",
            },
            {
                "producer": "Gemma3MLP.act_fn(gate_up): GELU(tanh)-and-mul",
                "consumer": "down_proj dynamic per-token FP8 quantization",
                "reuse_constraint": "single consumer; exact contiguous [M,21504] intermediate",
                "selected": True,
            },
        ],
        "measured_quantization": projection_rows,
        "measured_activation": {
            "launches": int(activation[0]),
            "seconds": activation[1] / 1e9,
        },
        "selected_boundary": {
            "name": "gelu_tanh_and_mul_to_down_fp8",
            "eligible_wall_seconds_upper_bound": activation[1] / 1e9 + down["seconds"],
            "dynamic_quant_seconds": down["seconds"],
            "dynamic_quant_fraction": down["seconds"]
            / sum(row["seconds"] for row in projection_rows),
            "profile_launches_removed": down["launches"],
            "profile_bfloat16_hbm_bytes_removed": removed_bytes,
            "physical_mechanism": "keep the activated BF16 row in CTA shared memory through max reduction, then write only FP8 and its scale",
            "falsifier": "the exact H200 fused component fails numerical proof or does not beat activation plus quantization and the shared down-GEMM consumer",
        },
    }
    atomic(args.output, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
