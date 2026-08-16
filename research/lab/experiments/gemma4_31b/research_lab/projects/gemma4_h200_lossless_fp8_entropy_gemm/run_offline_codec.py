#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import struct
import subprocess
import sys
import time

import numpy as np


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
SOURCE_PROJECT = (
    PROJECT.parent / "gemma4_mi355x_lossless_fp8_weight_stream_codesign"
)
SOURCE_RESULT = SOURCE_PROJECT / "FULL_CHECKPOINT_STREAM_RESULT.json"
SOURCE_RESULT_SHA256 = (
    "16950c9160918898b9f74f727335862a84c9a5f6f10ee3edad34fe2c2e6618f5"
)
PREREGISTRATION = PROJECT / "PREREGISTERED_CODEC.json"
ARTIFACT_ROOT = PROJECT / "artifacts" / "full-checkpoint-huffman12"
RESULT_PATH = PROJECT / "FULL_CHECKPOINT_HUFFMAN12_RESULT.json"
EXPECTED_BYTES = 29_396_828_160
EXPECTED_MODULES = 240
EXPECTED_TILES = 7_176_960
ROWS = 32
COLUMNS = 128
TILE_BYTES = ROWS * COLUMNS
MAX_CODE_LENGTH = 12
HEADER_BYTES = 256
CODE_LENGTH_BYTES = 256
DECODE_TABLE_BYTES = 4096 * 2
SEGMENT_ALIGNMENT = 256


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def sha256_file(path: pathlib.Path, chunk_bytes: int = 64 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        while data := handle.read(chunk_bytes):
            digest.update(data)
    return digest.hexdigest()


def align_up(value: int, alignment: int = SEGMENT_ALIGNMENT) -> int:
    return (value + alignment - 1) // alignment * alignment


def load_source_module():
    path = SOURCE_PROJECT / "lossless_fp8_stream_screen.py"
    specification = importlib.util.spec_from_file_location(
        "bound_lossless_fp8_source", path
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load bound source {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def optimal_length_limited_code(
    histogram: np.ndarray, maximum_length: int
) -> np.ndarray:
    if histogram.shape != (256,):
        raise ValueError("histogram must cover 256 byte symbols")
    weights = np.maximum(histogram.astype(object), 1)
    order = sorted(range(256), key=lambda symbol: (-weights[symbol], symbol))
    ordered = [int(weights[symbol]) for symbol in order]
    prefix = [0]
    for weight in ordered:
        prefix.append(prefix[-1] + weight)

    states: dict[tuple[int, int], tuple[int, tuple[int, ...]]] = {
        (0, 2): (0, ())
    }
    for depth in range(1, maximum_length + 1):
        next_states: dict[tuple[int, int], tuple[int, tuple[int, ...]]] = {}
        for (assigned, slots), (cost, counts) in states.items():
            remaining = 256 - assigned
            if depth == maximum_length:
                choices = (slots,) if slots == remaining else ()
            else:
                choices = range(min(slots, remaining) + 1)
            for leaves in choices:
                next_assigned = assigned + leaves
                next_slots = 2 * (slots - leaves)
                next_remaining = 256 - next_assigned
                if depth < maximum_length:
                    if next_slots == 0:
                        if next_remaining != 0:
                            continue
                    elif not (
                        next_slots
                        <= next_remaining
                        <= next_slots * (1 << (maximum_length - depth - 1))
                    ):
                        continue
                elif next_remaining != 0 or next_slots != 0:
                    continue
                added = depth * (prefix[next_assigned] - prefix[assigned])
                candidate = (cost + added, counts + (leaves,))
                key = (next_assigned, next_slots)
                current = next_states.get(key)
                if current is None or candidate[0] < current[0]:
                    next_states[key] = candidate
        states = next_states
    terminal = states.get((256, 0))
    if terminal is None:
        raise RuntimeError("no bounded prefix tree exists")
    counts = terminal[1]
    lengths = np.zeros(256, dtype=np.uint8)
    cursor = 0
    for depth, count in enumerate(counts, start=1):
        for symbol in order[cursor : cursor + count]:
            lengths[symbol] = depth
        cursor += count
    if cursor != 256:
        raise RuntimeError("bounded prefix tree did not assign every symbol")
    kraft_numerator = sum(
        1 << (maximum_length - int(length)) for length in lengths
    )
    if kraft_numerator != 1 << maximum_length:
        raise RuntimeError(f"invalid Kraft sum {kraft_numerator}")
    return lengths


def reverse_bits(value: int, width: int) -> int:
    result = 0
    for _ in range(width):
        result = (result << 1) | (value & 1)
        value >>= 1
    return result


def canonical_tables(
    lengths: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    ordered = sorted(range(256), key=lambda symbol: (int(lengths[symbol]), symbol))
    codes = np.zeros(256, dtype=np.uint16)
    code = 0
    previous_length = 0
    for symbol in ordered:
        length = int(lengths[symbol])
        code <<= length - previous_length
        if code >= 1 << length:
            raise RuntimeError("canonical code overflow")
        codes[symbol] = reverse_bits(code, length)
        code += 1
        previous_length = length
    table = np.zeros(4096, dtype="<u2")
    populated = np.zeros(4096, dtype=np.bool_)
    for symbol in range(256):
        length = int(lengths[symbol])
        reversed_code = int(codes[symbol])
        for suffix in range(1 << (MAX_CODE_LENGTH - length)):
            index = reversed_code | (suffix << length)
            if populated[index]:
                raise RuntimeError(f"decode table collision at {index}")
            table[index] = np.uint16((length << 8) | symbol)
            populated[index] = True
    if not bool(np.all(populated)):
        raise RuntimeError("decode table is incomplete")
    return codes, table


def compile_helper() -> tuple[ctypes.CDLL, dict[str, str]]:
    source = PROJECT / "huffman_tile_codec.cpp"
    library = ARTIFACT_ROOT / "huffman_tile_codec.so"
    command = [
        "g++",
        "-O3",
        "-march=native",
        "-fopenmp",
        "-shared",
        "-fPIC",
        str(source),
        "-o",
        str(library),
    ]
    subprocess.run(command, check=True)
    loaded = ctypes.CDLL(str(library))
    loaded.huffman_plan.argtypes = [
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint64),
    ]
    loaded.huffman_plan.restype = ctypes.c_int
    loaded.huffman_encode_decode.argtypes = [
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint64),
    ]
    loaded.huffman_encode_decode.restype = ctypes.c_int
    return loaded, {
        "source": str(source.relative_to(PROJECT)),
        "source_sha256": sha256_file(source),
        "binary": str(library.relative_to(PROJECT)),
        "binary_sha256": sha256_file(library),
        "compile_command": " ".join(command),
    }


def zeros(digest: hashlib._Hash, count: int) -> None:
    block = bytes(1024 * 1024)
    while count:
        take = min(count, len(block))
        digest.update(block[:take])
        count -= take


def module_header(
    layer: int,
    kind_index: int,
    k: int,
    n: int,
    tile_count: int,
    directory_offset: int,
    payload_offset: int,
    encoded_bytes: int,
    scale: float,
) -> bytes:
    prefix = struct.pack(
        "<8sIIIIIIQQQf",
        b"HF12R32\0",
        1,
        layer,
        kind_index,
        k,
        n,
        tile_count,
        directory_offset,
        payload_offset,
        encoded_bytes,
        scale,
    )
    if len(prefix) > HEADER_BYTES:
        raise RuntimeError("module header exceeds registered size")
    return prefix + bytes(HEADER_BYTES - len(prefix))


def quantiles(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "minimum": float(np.min(array)),
        "p01": float(np.quantile(array, 0.01)),
        "p05": float(np.quantile(array, 0.05)),
        "p50": float(np.quantile(array, 0.50)),
        "p95": float(np.quantile(array, 0.95)),
        "p99": float(np.quantile(array, 0.99)),
        "maximum": float(np.max(array)),
        "mean": float(np.mean(array)),
    }


def analyze_module(
    source,
    reader,
    module: dict[str, object],
    bound_row: dict[str, object],
    helper: ctypes.CDLL,
) -> dict[str, object]:
    started = time.perf_counter()
    names = list(module["sources"])
    tensors = [reader.tensor(name) for name in names]
    fused = source.torch.cat(tensors, dim=0) if len(tensors) > 1 else tensors[0]
    absmax = float(fused.abs().max().float().item())
    scale_tensor = source.torch.tensor(absmax, dtype=source.torch.float32) / 448.0
    scale = float(scale_tensor.item())
    inverse_scale = float(scale_tensor.reciprocal().item())
    consumer = fused.t().contiguous()
    scaled = consumer.float()
    scaled.mul_(inverse_scale).clamp_(-448.0, 448.0)
    quantized = scaled.to(source.torch.float8_e4m3fn)
    del scaled, consumer, fused, tensors

    k, n = map(int, quantized.shape)
    if k % ROWS or n % COLUMNS:
        raise RuntimeError(f"consumer shape is not 32x128 aligned: {(k, n)}")
    consumer_bytes = quantized.view(source.torch.uint8).numpy().reshape(-1)
    runtime_hash = hashlib.sha256(consumer_bytes).hexdigest()
    tiled_tensor = (
        quantized.view(source.torch.uint8)
        .reshape(k // ROWS, ROWS, n // COLUMNS, COLUMNS)
        .permute(0, 2, 1, 3)
        .contiguous()
    )
    tiled = tiled_tensor.numpy().reshape(-1)
    tiled_hash = hashlib.sha256(tiled).hexdigest()
    histogram = np.bincount(tiled, minlength=256).astype(np.uint64)
    if runtime_hash != bound_row["hashes"]["runtime_fp8_sha256"]:
        raise RuntimeError(f"runtime FP8 binding mismatch for {module}")
    if tiled_hash != bound_row["hashes"]["encoded_tile_order_fp8_sha256"]:
        raise RuntimeError(f"tile-order FP8 binding mismatch for {module}")
    if histogram.tolist() != bound_row["byte_histogram"]:
        raise RuntimeError(f"histogram binding mismatch for {module}")

    lengths = optimal_length_limited_code(histogram, MAX_CODE_LENGTH)
    codes, table = canonical_tables(lengths)
    tile_count = len(tiled) // TILE_BYTES
    offsets = np.zeros(tile_count + 1, dtype="<u4")
    totals = np.zeros(5, dtype=np.uint64)
    status = helper.huffman_plan(
        tiled.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        tile_count,
        lengths.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        offsets.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)),
        totals.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)),
    )
    if status != 0:
        raise RuntimeError(f"huffman_plan failed with status {status}")
    tile_storage_bytes = int(totals[3])
    encoded = np.zeros(tile_storage_bytes, dtype=np.uint8)
    mismatches = ctypes.c_uint64(0)
    status = helper.huffman_encode_decode(
        tiled.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        tile_count,
        codes.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16)),
        lengths.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        table.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16)),
        offsets.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)),
        encoded.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        tile_storage_bytes,
        ctypes.byref(mismatches),
    )
    if status != 0 or mismatches.value != 0:
        raise RuntimeError(
            f"huffman_encode_decode failed: status={status} mismatches={mismatches.value}"
        )

    code_lengths_offset = align_up(HEADER_BYTES)
    decode_table_offset = align_up(code_lengths_offset + CODE_LENGTH_BYTES)
    directory_offset = align_up(decode_table_offset + DECODE_TABLE_BYTES)
    directory = offsets.tobytes()
    payload_offset = align_up(directory_offset + len(directory))
    encoded_bytes = payload_offset + tile_storage_bytes
    header = module_header(
        int(module["layer"]),
        ["qkv", "o", "gate_up", "down"].index(str(module["kind"])),
        k,
        n,
        tile_count,
        directory_offset,
        payload_offset,
        encoded_bytes,
        scale,
    )
    stream_hash = hashlib.sha256()
    stream_hash.update(header)
    zeros(stream_hash, code_lengths_offset - len(header))
    stream_hash.update(lengths.tobytes())
    zeros(
        stream_hash,
        decode_table_offset - (code_lengths_offset + CODE_LENGTH_BYTES),
    )
    stream_hash.update(table.tobytes())
    zeros(
        stream_hash,
        directory_offset - (decode_table_offset + DECODE_TABLE_BYTES),
    )
    stream_hash.update(directory)
    zeros(stream_hash, payload_offset - (directory_offset + len(directory)))
    stream_hash.update(encoded)
    if encoded_bytes != (
        len(header)
        + (code_lengths_offset - len(header))
        + CODE_LENGTH_BYTES
        + (decode_table_offset - (code_lengths_offset + CODE_LENGTH_BYTES))
        + DECODE_TABLE_BYTES
        + (directory_offset - (decode_table_offset + DECODE_TABLE_BYTES))
        + len(directory)
        + (payload_offset - (directory_offset + len(directory)))
        + len(encoded)
    ):
        raise RuntimeError("module storage accounting does not close")

    weighted_bits = int(
        sum(int(histogram[symbol]) * int(lengths[symbol]) for symbol in range(256))
    )
    if weighted_bits != int(totals[0]):
        raise RuntimeError("payload bit count does not match histogram")
    result = {
        "layer": int(module["layer"]),
        "kind": str(module["kind"]),
        "source_tensors": names,
        "consumer_shape_k_n": [k, n],
        "runtime_fp8_bytes": len(tiled),
        "tile_count": tile_count,
        "scale_fp32": scale,
        "absmax_bf16_promoted_fp32": absmax,
        "code": {
            "maximum_length": int(np.max(lengths)),
            "minimum_length": int(np.min(lengths)),
            "length_histogram": np.bincount(lengths, minlength=13).tolist(),
            "weighted_payload_bits": weighted_bits,
            "weighted_payload_bits_per_byte": weighted_bits / len(tiled),
            "code_lengths_sha256": hashlib.sha256(lengths).hexdigest(),
            "decode_table_sha256": hashlib.sha256(table).hexdigest(),
        },
        "storage": {
            "header_bytes": HEADER_BYTES,
            "code_lengths_bytes": CODE_LENGTH_BYTES,
            "decode_table_bytes": DECODE_TABLE_BYTES,
            "directory_bytes": len(directory),
            "row_length_bytes": tile_count * ROWS,
            "row_payload_bytes": int(totals[1]),
            "row_byte_rounding_bits": int(totals[1]) * 8 - weighted_bits,
            "tile_alignment_padding_bytes": int(totals[2]),
            "segment_alignment_padding_bytes": (
                code_lengths_offset
                - HEADER_BYTES
                + decode_table_offset
                - (code_lengths_offset + CODE_LENGTH_BYTES)
                + directory_offset
                - (decode_table_offset + DECODE_TABLE_BYTES)
                + payload_offset
                - (directory_offset + len(directory))
            ),
            "tile_storage_bytes": tile_storage_bytes,
            "encoded_bytes": encoded_bytes,
            "compression_ratio": encoded_bytes / len(tiled),
        },
        "decode": {
            "decoded_bytes": len(tiled),
            "mismatched_bytes": int(mismatches.value),
            "bitwise_equal": mismatches.value == 0,
        },
        "hashes": {
            "runtime_fp8_sha256": runtime_hash,
            "tile_order_fp8_sha256": tiled_hash,
            "directory_sha256": hashlib.sha256(directory).hexdigest(),
            "tile_storage_sha256": hashlib.sha256(encoded).hexdigest(),
            "encoded_module_sha256": stream_hash.hexdigest(),
        },
        "elapsed_seconds": time.perf_counter() - started,
    }
    del encoded, offsets, tiled, tiled_tensor, quantized, consumer_bytes
    return result


def validate_checkpoint_state(
    source_result: dict[str, object], checkpoint: pathlib.Path
) -> dict[str, object]:
    observed = {}
    for name, binding in source_result["bindings"]["shards"].items():
        path = checkpoint / name
        stat = path.stat()
        if stat.st_size != binding["size_bytes"]:
            raise RuntimeError(f"checkpoint size mismatch: {name}")
        if stat.st_mode & 0o222:
            raise RuntimeError(f"checkpoint shard is writable: {path}")
        observed[name] = {
            "path": str(path),
            "sha256": binding["sha256"],
            "sha256_evidence": "consumed bound full-checkpoint result",
            "size_bytes": stat.st_size,
            "inode": stat.st_ino,
            "hardlink_count": stat.st_nlink,
            "mode_octal": oct(stat.st_mode & 0o777),
        }
    return observed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--limit-modules", type=int)
    parser.add_argument("--aggregate-only", action="store_true")
    args = parser.parse_args()
    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    if sha256_file(SOURCE_RESULT) != SOURCE_RESULT_SHA256:
        raise RuntimeError("bound full-checkpoint result hash mismatch")
    preregistration_hash = sha256_file(PREREGISTRATION)
    source_result = json.loads(SOURCE_RESULT.read_text())
    checkpoint = pathlib.Path(source_result["bindings"]["config"]["path"]).parent
    checkpoint_state = validate_checkpoint_state(source_result, checkpoint)
    rows = []
    if args.aggregate_only:
        if args.limit_modules is not None:
            raise RuntimeError("--aggregate-only cannot be combined with --limit-modules")
        row_paths = sorted(ARTIFACT_ROOT.glob("[0-9][0-9][0-9]-*.json"))
        if len(row_paths) != EXPECTED_MODULES:
            raise RuntimeError(
                f"aggregation recovery requires {EXPECTED_MODULES} rows, found {len(row_paths)}"
            )
        rows = [json.loads(path.read_text()) for path in row_paths]
        started_utc = dt.datetime.fromtimestamp(
            min(path.stat().st_mtime for path in row_paths), dt.timezone.utc
        ).isoformat()
        started = None
        helper_source = PROJECT / "huffman_tile_codec.cpp"
        helper_library = ARTIFACT_ROOT / "huffman_tile_codec.so"
        helper_binding = {
            "source": str(helper_source.relative_to(PROJECT)),
            "source_sha256": sha256_file(helper_source),
            "binary": str(helper_library.relative_to(PROJECT)),
            "binary_sha256": sha256_file(helper_library),
            "compile_command": (
                f"g++ -O3 -march=native -fopenmp -shared -fPIC "
                f"{helper_source} -o {helper_library}"
            ),
        }
    else:
        source = load_source_module()
        source.torch.set_num_threads(args.threads)
        source.torch.set_num_interop_threads(1)
        helper, helper_binding = compile_helper()
        started_utc = dt.datetime.now(dt.timezone.utc).isoformat()
        started = time.perf_counter()
        reader = source.CheckpointReader(source.CHECKPOINT)
        try:
            modules = source.projection_modules(reader)
            if len(modules) != EXPECTED_MODULES:
                raise RuntimeError(f"unexpected module count {len(modules)}")
            if args.limit_modules is not None:
                modules = modules[: args.limit_modules]
            for index, module in enumerate(modules):
                row = analyze_module(
                    source, reader, module, source_result["modules"][index], helper
                )
                row_path = (
                    ARTIFACT_ROOT
                    / f"{index:03d}-layer{row['layer']:02d}-{row['kind']}.json"
                )
                atomic_json(row_path, row)
                rows.append(row)
                print(
                    json.dumps(
                        {
                            "module": index + 1,
                            "modules": len(modules),
                            "layer": row["layer"],
                            "kind": row["kind"],
                            "ratio": row["storage"]["compression_ratio"],
                            "elapsed_seconds": row["elapsed_seconds"],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
        finally:
            reader.close()

    raw_bytes = sum(row["runtime_fp8_bytes"] for row in rows)
    tile_count = sum(row["tile_count"] for row in rows)
    encoded_bytes = sum(row["storage"]["encoded_bytes"] for row in rows)
    decoded_bytes = sum(row["decode"]["decoded_bytes"] for row in rows)
    mismatches = sum(row["decode"]["mismatched_bytes"] for row in rows)
    if args.limit_modules is None:
        if (raw_bytes, tile_count, len(rows)) != (
            EXPECTED_BYTES,
            EXPECTED_TILES,
            EXPECTED_MODULES,
        ):
            raise RuntimeError(
                f"full coverage mismatch: {raw_bytes} {tile_count} {len(rows)}"
            )
        if decoded_bytes != EXPECTED_BYTES or mismatches != 0:
            raise RuntimeError(
                f"full decode mismatch: {decoded_bytes} {mismatches}"
            )
    manifest = hashlib.sha256()
    for row in rows:
        manifest.update(bytes.fromhex(row["hashes"]["encoded_module_sha256"]))
    result = {
        "schema_version": 1,
        "project": PROJECT.name,
        "result": (
            "full_checkpoint_huffman12_measurement"
            if args.limit_modules is None
            else "bounded_smoke_measurement"
        ),
        "started_at_utc": started_utc,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "elapsed_seconds": (
            time.perf_counter() - started
            if started is not None
            else sum(row["elapsed_seconds"] for row in rows)
        ),
        "aggregation_recovery": (
            {
                "used": True,
                "reason": "post-producer Python boolean literal defect",
                "producer_rows_replayed": 0
            }
            if args.aggregate_only
            else {"used": False}
        ),
        "threads": args.threads,
        "bindings": {
            "preregistration": str(PREREGISTRATION.relative_to(PROJECT)),
            "preregistration_sha256": preregistration_hash,
            "source_full_checkpoint_result": str(SOURCE_RESULT),
            "source_full_checkpoint_result_sha256": SOURCE_RESULT_SHA256,
            "checkpoint_shards": checkpoint_state,
            "helper": helper_binding,
        },
        "codec": json.loads(PREREGISTRATION.read_text())["codec"],
        "coverage": {
            "runtime_modules": len(rows),
            "runtime_fp8_bytes": raw_bytes,
            "tile_count": tile_count,
            "decoded_bytes": decoded_bytes,
            "mismatched_bytes": mismatches,
            "bitwise_equal": decoded_bytes == raw_bytes and mismatches == 0,
        },
        "storage": {
            "raw_fp8_bytes": raw_bytes,
            "encoded_bytes": encoded_bytes,
            "bytes_avoided": raw_bytes - encoded_bytes,
            "compression_ratio": encoded_bytes / raw_bytes,
            "bits_per_weight_all_overheads": 8 * encoded_bytes / raw_bytes,
            "encoded_module_manifest_sha256": manifest.hexdigest(),
            "components": {
                key: sum(row["storage"][key] for row in rows)
                for key in (
                    "header_bytes",
                    "code_lengths_bytes",
                    "decode_table_bytes",
                    "directory_bytes",
                    "row_length_bytes",
                    "row_payload_bytes",
                    "tile_alignment_padding_bytes",
                    "segment_alignment_padding_bytes",
                )
            },
            "module_ratio_quantiles": quantiles(
                [row["storage"]["compression_ratio"] for row in rows]
            ),
        },
        "modules": rows,
        "checkpoint_access": "read-only mmap; no shard bytes copied, mutated, or persisted",
        "provider_spend_usd": 0.0,
        "gpu_claimed": False,
    }
    atomic_json(RESULT_PATH, result)
    print(
        json.dumps(
            {
                "result_path": str(RESULT_PATH),
                "encoded_bytes": encoded_bytes,
                "compression_ratio": encoded_bytes / raw_bytes,
                "decoded_bytes": decoded_bytes,
                "mismatches": mismatches,
                "elapsed_seconds": result["elapsed_seconds"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
