from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pathlib
import tarfile

import numpy as np
from tokenizers import Tokenizer


PROJECT = pathlib.Path(__file__).resolve().parent
PAIR = "artifacts/mixed-local-m384-20260725t165205Z/pair"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def member_bytes(archive: pathlib.Path, name: str) -> bytes:
    with tarfile.open(archive, "r:gz") as bundle:
        handle = bundle.extractfile(name)
        if handle is None:
            raise RuntimeError(f"missing_archive_member:{name}")
        return handle.read()


def response_text(raw: bytes) -> tuple[str, str]:
    fragments = []
    for line in raw.splitlines():
        if not line.startswith(b"data: ") or line.strip() == b"data: [DONE]":
            continue
        item = json.loads(line[6:])
        choice = (item.get("choices") or [{}])[0]
        text = choice.get("text") or ""
        if text:
            fragments.append(text)
    return (fragments[0] if fragments else "", "".join(fragments))


def guard_localization(archive: pathlib.Path, tokenizer_path: pathlib.Path) -> dict:
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    rows = []
    for index in range(32):
        control_raw = member_bytes(
            archive, f"{PAIR}/guard-control/response-{index:02d}.sse"
        )
        candidate_raw = member_bytes(
            archive, f"{PAIR}/guard-candidate/response-{index:02d}.sse"
        )
        control_first, control_text = response_text(control_raw)
        candidate_first, candidate_text = response_text(candidate_raw)
        control_ids = tokenizer.encode(control_text, add_special_tokens=False).ids
        candidate_ids = tokenizer.encode(candidate_text, add_special_tokens=False).ids
        shared = 0
        while (
            shared < len(control_ids)
            and shared < len(candidate_ids)
            and control_ids[shared] == candidate_ids[shared]
        ):
            shared += 1
        first_difference = (
            None
            if shared == len(control_ids) == len(candidate_ids)
            else shared
        )
        rows.append(
            {
                "request": index,
                "first_difference_reconstructed_token_index": first_difference,
                "control_first_fragment": control_first,
                "candidate_first_fragment": candidate_first,
                "control_first_reconstructed_id": (
                    control_ids[0] if control_ids else None
                ),
                "candidate_first_reconstructed_id": (
                    candidate_ids[0] if candidate_ids else None
                ),
                "control_reconstructed_ids": control_ids,
                "candidate_reconstructed_ids": candidate_ids,
            }
        )
    divergent = [
        row
        for row in rows
        if row["first_difference_reconstructed_token_index"] is not None
    ]
    difference_histogram: dict[str, int] = {}
    for row in divergent:
        key = str(row["first_difference_reconstructed_token_index"])
        difference_histogram[key] = difference_histogram.get(key, 0) + 1
    return {
        "evidence": "persisted exact 32/32 guard SSE decoded with pinned checkpoint tokenizer",
        "tokenizer_path": str(tokenizer_path),
        "tokenizer_sha256": sha256(tokenizer_path),
        "raw_token_ids_were_returned": False,
        "reconstructed_ids_are_debug_localization_not_raw_server_ids": True,
        "divergent_requests": len(divergent),
        "first_difference_reconstructed_token_histogram": difference_histogram,
        "first_divergent_request": min(
            divergent,
            key=lambda row: (
                row["first_difference_reconstructed_token_index"],
                row["request"],
            ),
        ),
        "rows": rows,
    }


def ncu_local_rows(archive: pathlib.Path) -> dict:
    raw = member_bytes(
        archive,
        "artifacts/mixed-local-m384-20260725t165205Z/counters/ncu.csv",
    ).decode(errors="replace")
    lines = raw.splitlines()
    header = next(
        index for index, line in enumerate(lines) if line.startswith('"ID","Process ID"')
    )
    rows = [
        row
        for row in csv.DictReader(lines[header:])
        if (row.get("ID") or "").isdigit()
    ]

    def selected(index: int) -> dict:
        row = rows[index]
        return {
            "registers_per_thread": int(row["launch__registers_per_thread"]),
            "dynamic_shared_ncu_kbyte": float(
                row["launch__shared_mem_per_block_dynamic"]
            ),
            "dynamic_shared_bytes": int(
                1000 * float(row["launch__shared_mem_per_block_dynamic"])
            ),
            "waves_per_sm": float(row["launch__waves_per_multiprocessor"]),
            "gpu_time_ms": float(row["gpu__time_duration.sum"]),
            "dram_read_gib": float(row["dram__bytes_read.sum"]),
            "dram_write_mib": float(row["dram__bytes_write.sum"]),
            "lts_bytes_gib": float(row["lts__t_bytes.sum"]),
        }

    return {"stock_local": selected(0), "rejected_m8_local": selected(2)}


def first_line(lines: list[str], *needles: str) -> str:
    return next(line for line in lines if all(needle in line for needle in needles))


def accumulation_localization(compile_result: dict) -> dict:
    stock = compile_result["stock"]["dot_lowering_lines"]
    rejected = compile_result["rejected_m8"]["dot_lowering_lines"]
    candidate = compile_result["candidate"]["dot_lowering_lines"]
    return {
        "earliest_affected_model_boundary": (
            "layer 0 sliding-attention prefix-QK accumulation; pinned layer_types[0] "
            "is sliding_attention and this is the first model operation mounted with "
            "the local-only candidate"
        ),
        "stock_prefix_qk": first_line(
            stock, "warp_group_dot", "64x256xf8E5M2", "256x64xf8E5M2"
        ),
        "rejected_m8_prefix_qk": first_line(
            rejected, "tt.dot", "8x256xf16", "256x64xf16"
        ),
        "stock_order_candidate_prefix_qk": first_line(
            candidate, "warp_group_dot", "64x256xf8E5M2", "256x64xf8E5M2"
        ),
        "interpretation": (
            "M8 ceases to use stock's FP8 warp-group QK dot: Triton widens both "
            "operands to FP16 and lowers a different 8-row dot before the first "
            "online-softmax max/sum. The new value-stripe schedule restores the "
            "stock M64 FP8 warp-group QK boundary."
        ),
    }


def f32(value: float) -> np.float32:
    return np.float32(value)


def online_attention(scores: np.ndarray, values: np.ndarray, stripe: int) -> np.ndarray:
    rows, keys = scores.shape
    width = values.shape[1]
    output = np.empty((rows, width), dtype=np.float32)
    for begin_d in range(0, width, stripe):
        end_d = min(begin_d + stripe, width)
        for row in range(rows):
            maximum = f32(-np.inf)
            denominator = f32(0)
            accumulator = np.zeros(end_d - begin_d, dtype=np.float32)
            for begin_n in range(0, keys, 8):
                tile = scores[row, begin_n : begin_n + 8]
                tile_max = f32(max(float(value) for value in tile))
                next_max = f32(max(float(maximum), float(tile_max)))
                rescale = f32(np.exp(f32(maximum - next_max)))
                probability = [
                    f32(np.exp(f32(value - next_max))) for value in tile
                ]
                tile_sum = f32(0)
                for value in probability:
                    tile_sum = f32(tile_sum + value)
                denominator = f32(f32(denominator * rescale) + tile_sum)
                for feature in range(begin_d, end_d):
                    dot = f32(0)
                    for offset, probability_value in enumerate(probability):
                        dot = f32(
                            dot
                            + f32(
                                probability_value
                                * values[begin_n + offset, feature]
                            )
                        )
                    accumulator[feature - begin_d] = f32(
                        f32(accumulator[feature - begin_d] * rescale) + dot
                    )
                maximum = next_max
            for feature in range(begin_d, end_d):
                output[row, feature] = f32(
                    accumulator[feature - begin_d] / denominator
                )
    return output


def cpu_fixture() -> dict:
    scores = np.fromfunction(
        lambda row, key: ((row * 29 + key * 17) % 41 - 20) / 13,
        (12, 24),
        dtype=int,
    ).astype(np.float32)
    values = np.fromfunction(
        lambda key, feature: ((key * 19 + feature * 7) % 53 - 26) / 17,
        (24, 32),
        dtype=int,
    ).astype(np.float32)
    stock = online_attention(scores, values, stripe=32)
    candidate = online_attention(scores, values, stripe=8)
    bitwise = bool(np.array_equal(stock.view(np.uint32), candidate.view(np.uint32)))
    if not bitwise:
        raise RuntimeError("cpu_stock_order_fixture_diverged")
    return {
        "kind": "deterministic_float32_online_softmax_value_stripe_fixture",
        "rows": 12,
        "keys": 24,
        "value_width": 32,
        "stock_stripe": 32,
        "candidate_stripe": 8,
        "bitwise_equal": bitwise,
        "output_sha256": hashlib.sha256(stock.tobytes()).hexdigest(),
        "claim": (
            "With identical score tiles, N-tile order, per-feature dot order, "
            "rescale order, and denominator order, partitioning only independent "
            "value features preserves each scalar FP32 operation sequence."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=pathlib.Path, required=True)
    parser.add_argument("--tokenizer", type=pathlib.Path, required=True)
    parser.add_argument("--compile-result", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    compile_result = json.loads(args.compile_result.read_text())
    measured_ncu = ncu_local_rows(args.archive)
    candidate_source = PROJECT / "intervention/extend_attention_stock_order_dv64.py"
    result = {
        "schema_version": 1,
        "kind": "offline_guard_localization_and_stock_order_candidate_fixture",
        "guard": guard_localization(args.archive, args.tokenizer),
        "accumulation_localization": accumulation_localization(compile_result),
        "cpu_fixture": cpu_fixture(),
        "candidate_source": {
            "path": str(candidate_source.relative_to(PROJECT)),
            "sha256": sha256(candidate_source),
        },
        "sm90_compile": {
            "path": str(args.compile_result.relative_to(PROJECT)),
            "sha256": sha256(args.compile_result),
            "stock": {
                "generic_signature_ptxas_registers": compile_result["stock"][
                    "maximum_registers_per_thread"
                ],
                "dynamic_shared_bytes": compile_result["stock"]["metadata"]["shared"],
                "stack_bytes": int(
                    compile_result["stock"]["resource_usage"]
                    .split("STACK:", 1)[1]
                    .split()[0]
                ),
            },
            "candidate": {
                "generic_signature_ptxas_registers": compile_result["candidate"][
                    "maximum_registers_per_thread"
                ],
                "dynamic_shared_bytes": compile_result["candidate"]["metadata"][
                    "shared"
                ],
                "stack_bytes": int(
                    compile_result["candidate"]["resource_usage"]
                    .split("STACK:", 1)[1]
                    .split()[0]
                ),
            },
        },
        "pressure_decision": {
            "measured_ncu": measured_ncu,
            "candidate_compiled_dynamic_shared_kib": (
                compile_result["candidate"]["metadata"]["shared"] / 1024
            ),
            "candidate_predicted_waves_per_sm": (32 * 32 * 4) / 132,
            "candidate_dynamic_shared_change_vs_m8_bytes": (
                compile_result["candidate"]["metadata"]["shared"]
                - measured_ncu["rejected_m8_local"]["dynamic_shared_bytes"]
            ),
            "candidate_waves_change_vs_m8": (
                (32 * 32 * 4) / 132
                - measured_ncu["rejected_m8_local"]["waves_per_sm"]
            ),
            "candidate_pressure_gate_pass": False,
            "reason": (
                "The only source-complete stock-QK-order schedule compiles to "
                "80 KiB dynamic shared memory, 43 KiB above M8, and doubles "
                "M8 grid waves. It therefore does not reduce the admitted "
                "173-register/37.888-KiB realization pressure."
            ),
        },
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
