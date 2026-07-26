#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import glob
import hashlib
import json
import math
import mmap
import os
import pathlib
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Iterable

import numpy as np


PROJECT = pathlib.Path(__file__).resolve().parent
CHECKPOINT = (
    PROJECT.parent
    / "gemma4_current_runtime_frontier"
    / "inputs"
    / "checkpoint"
)
MODEL = "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4"
CONFIG_SHA256 = "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1"
INDEX_SHA256 = "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2"
SHARD_SHA256 = {
    "model-00001-of-00002.safetensors": "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa",
    "model-00002-of-00002.safetensors": "018912220f559f7025d60333e0996183cd538aa77ad6f4988a89ce47be681f10",
}
EXPECTED_PARAMETERS = 29_396_828_160
BLOCK_BYTES = 4096
TOKEN_BYTES_PER_BLOCK = 2560
HEADER_BYTES = 64
DICTIONARY_BYTES = 32
ALIGNMENT = 256
FP8_MAX = 448.0
BASELINE_LINEAR_SECONDS = 0.363906344068055
FIXED_SECONDS = 0.23618874914322519
BASELINE_SECONDS = 0.6000950932112802
TARGET_SECONDS = 0.5910500600431771


def load_torch():
    try:
        import torch

        return torch
    except ModuleNotFoundError:
        candidates = sorted(
            glob.glob(
                "/root/.cache/uv/archive-v0/*/lib/python3.13/site-packages/torch"
            )
        )
        if not candidates:
            raise
        sys.path.insert(0, str(pathlib.Path(candidates[-1]).parent))
        import torch

        return torch


torch = load_torch()


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


def align_up(value: int, alignment: int = ALIGNMENT) -> int:
    return (value + alignment - 1) // alignment * alignment


def quantiles(values: np.ndarray) -> dict[str, float]:
    return {
        "minimum": float(np.min(values)),
        "p01": float(np.quantile(values, 0.01)),
        "p05": float(np.quantile(values, 0.05)),
        "p50": float(np.quantile(values, 0.50)),
        "p95": float(np.quantile(values, 0.95)),
        "p99": float(np.quantile(values, 0.99)),
        "maximum": float(np.max(values)),
        "mean": float(np.mean(values, dtype=np.float64)),
    }


@dataclass
class TensorRecord:
    path: pathlib.Path
    offset: int
    shape: tuple[int, int]
    dtype: str
    byte_count: int


class CheckpointReader:
    def __init__(self, root: pathlib.Path):
        self.root = root
        self.records: dict[str, TensorRecord] = {}
        self.files: dict[pathlib.Path, object] = {}
        self.maps: dict[pathlib.Path, mmap.mmap] = {}
        self.headers: dict[str, dict[str, object]] = {}
        for path in sorted(root.glob("model-*.safetensors")):
            handle = path.open("rb")
            header_bytes = struct.unpack("<Q", handle.read(8))[0]
            header = json.loads(handle.read(header_bytes))
            data_start = 8 + header_bytes
            for name, spec in header.items():
                if name == "__metadata__":
                    continue
                begin, end = spec["data_offsets"]
                self.records[name] = TensorRecord(
                    path=path,
                    offset=data_start + begin,
                    shape=tuple(spec["shape"]),
                    dtype=spec["dtype"],
                    byte_count=end - begin,
                )
            self.files[path] = handle
            self.maps[path] = mmap.mmap(
                handle.fileno(), 0, access=mmap.ACCESS_READ
            )
            self.headers[path.name] = {
                "header_bytes": header_bytes,
                "tensor_count": len(header) - int("__metadata__" in header),
                "payload_bytes": sum(
                    spec["data_offsets"][1] - spec["data_offsets"][0]
                    for name, spec in header.items()
                    if name != "__metadata__"
                ),
            }

    def tensor(self, name: str):
        record = self.records[name]
        if record.dtype != "BF16" or len(record.shape) != 2:
            raise RuntimeError(f"unsupported tensor {name}: {record}")
        value = torch.frombuffer(
            self.maps[record.path],
            dtype=torch.bfloat16,
            count=math.prod(record.shape),
            offset=record.offset,
        )
        return value.reshape(record.shape)

    def close(self) -> None:
        self.records.clear()
        for value in self.maps.values():
            value.close()
        for value in self.files.values():
            value.close()


def projection_modules(reader: CheckpointReader) -> list[dict[str, object]]:
    modules = []
    for layer in range(60):
        prefix = f"model.language_model.layers.{layer}"
        attention = f"{prefix}.self_attn"
        mlp = f"{prefix}.mlp"
        qkv = [
            f"{attention}.q_proj.weight",
            f"{attention}.k_proj.weight",
        ]
        v_name = f"{attention}.v_proj.weight"
        if v_name in reader.records:
            qkv.append(v_name)
        else:
            qkv.append(qkv[-1])
        modules.extend(
            [
                {"layer": layer, "kind": "qkv", "sources": qkv},
                {
                    "layer": layer,
                    "kind": "o",
                    "sources": [f"{attention}.o_proj.weight"],
                },
                {
                    "layer": layer,
                    "kind": "gate_up",
                    "sources": [
                        f"{mlp}.gate_proj.weight",
                        f"{mlp}.up_proj.weight",
                    ],
                },
                {
                    "layer": layer,
                    "kind": "down",
                    "sources": [f"{mlp}.down_proj.weight"],
                },
            ]
        )
    return modules


def compile_block_stats() -> tuple[ctypes.CDLL, str]:
    source = PROJECT / "block_stats.cpp"
    library = PROJECT / "block_stats.so"
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
    loaded.fp8_block_stats.argtypes = [
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_uint16),
    ]
    loaded.fp8_block_stats.restype = ctypes.c_int
    return loaded, sha256_file(library)


def pack_tokens(tokens: np.ndarray) -> np.ndarray:
    groups = tokens.reshape(-1, 8).astype(np.uint64)
    words = groups[:, 0].copy()
    for index in range(1, 8):
        words |= groups[:, index] << np.uint64(5 * index)
    packed = np.empty((len(words), 5), dtype=np.uint8)
    for index in range(5):
        packed[:, index] = (words >> np.uint64(8 * index)).astype(np.uint8)
    return packed.reshape(-1)


def unpack_tokens(packed: np.ndarray) -> np.ndarray:
    groups = packed.reshape(-1, 5).astype(np.uint64)
    words = groups[:, 0].copy()
    for index in range(1, 5):
        words |= groups[:, index] << np.uint64(8 * index)
    tokens = np.empty((len(words), 8), dtype=np.uint8)
    for index in range(8):
        tokens[:, index] = (
            (words >> np.uint64(5 * index)) & np.uint64(31)
        ).astype(np.uint8)
    return tokens.reshape(-1)


def analyze_module(
    reader: CheckpointReader,
    module: dict[str, object],
    block_library: ctypes.CDLL,
    chunk_blocks: int,
) -> tuple[dict[str, object], np.ndarray, np.ndarray]:
    started = time.perf_counter()
    names = list(module["sources"])
    sources = [reader.tensor(name) for name in names]
    k_values = {int(value.shape[1]) for value in sources}
    if len(k_values) != 1:
        raise RuntimeError(f"incompatible fused source shapes: {names}")
    fused = torch.cat(sources, dim=0) if len(sources) > 1 else sources[0]
    absmax = float(fused.abs().max().float().item())
    scale_tensor = torch.tensor(absmax, dtype=torch.float32) / FP8_MAX
    scale = float(scale_tensor.item())
    inverse_scale = float(scale_tensor.reciprocal().item())
    consumer = fused.t().contiguous()
    scaled = consumer.float()
    scaled.mul_(inverse_scale).clamp_(-FP8_MAX, FP8_MAX)
    quantized = scaled.to(torch.float8_e4m3fn)
    del scaled, consumer, fused, sources

    consumer_k, consumer_n = map(int, quantized.shape)
    if consumer_k % 32 or consumer_n % 128:
        raise RuntimeError(
            f"consumer shape is not 32x128 tile aligned: {quantized.shape}"
        )
    consumer_fp8 = quantized.view(torch.uint8).numpy().reshape(-1)
    runtime_fp8_hash = hashlib.sha256(consumer_fp8).hexdigest()
    tiled = (
        quantized.view(torch.uint8)
        .reshape(consumer_k // 32, 32, consumer_n // 128, 128)
        .permute(0, 2, 1, 3)
        .contiguous()
    )
    fp8 = tiled.numpy().reshape(-1)
    histogram = np.bincount(fp8, minlength=256).astype(np.uint64)
    ranking = sorted(range(256), key=lambda value: (-int(histogram[value]), value))
    dictionary = np.asarray(ranking[:31], dtype=np.uint8)
    code_index = np.full(256, 31, dtype=np.uint8)
    code_index[dictionary] = np.arange(31, dtype=np.uint8)
    dictionary_storage = np.concatenate(
        [dictionary, np.asarray([0], dtype=np.uint8)]
    )

    block_count = len(fp8) // BLOCK_BYTES
    if block_count * BLOCK_BYTES != len(fp8):
        raise RuntimeError(f"module is not block aligned: {module}")
    entropy_parts = []
    escape_parts = []
    encoded_source_hash = hashlib.sha256()
    token_hash = hashlib.sha256()
    literal_hash = hashlib.sha256()
    decoded_bytes = 0

    for begin_block in range(0, block_count, chunk_blocks):
        end_block = min(block_count, begin_block + chunk_blocks)
        begin = begin_block * BLOCK_BYTES
        end = end_block * BLOCK_BYTES
        chunk = fp8[begin:end]
        entropy = np.empty(end_block - begin_block, dtype=np.float32)
        escapes = np.empty(end_block - begin_block, dtype=np.uint16)
        status = block_library.fp8_block_stats(
            chunk.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
            len(entropy),
            code_index.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
            entropy.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            escapes.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16)),
        )
        if status != 0:
            raise RuntimeError(f"block stats failed with status {status}")
        entropy_parts.append(entropy)
        escape_parts.append(escapes)

        tokens = code_index[chunk]
        packed = pack_tokens(tokens)
        literals = chunk[tokens == 31]
        decoded_tokens = unpack_tokens(packed)
        decoded = dictionary_storage[decoded_tokens]
        decoded[decoded_tokens == 31] = literals
        if not np.array_equal(decoded, chunk):
            mismatch = int(np.flatnonzero(decoded != chunk)[0])
            raise RuntimeError(
                f"bitwise decode mismatch in {module} at byte {begin + mismatch}"
            )
        decoded_bytes += len(decoded)
        encoded_source_hash.update(chunk)
        token_hash.update(packed)
        literal_hash.update(literals)

    entropies = np.concatenate(entropy_parts)
    escape_counts = np.concatenate(escape_parts)
    literal_prefix_u64 = np.concatenate(
        [
            np.zeros(1, dtype=np.uint64),
            np.cumsum(escape_counts, dtype=np.uint64),
        ]
    )
    if int(literal_prefix_u64[-1]) > np.iinfo(np.uint32).max:
        raise RuntimeError("tensor literal stream exceeds uint32 directory")
    literal_prefix = literal_prefix_u64.astype("<u4")
    directory_bytes = literal_prefix.tobytes()
    directory_hash = hashlib.sha256(directory_bytes).hexdigest()
    token_bytes = block_count * TOKEN_BYTES_PER_BLOCK
    literal_bytes = int(literal_prefix[-1])
    header_offset = 0
    dictionary_offset = align_up(header_offset + HEADER_BYTES)
    directory_offset = align_up(dictionary_offset + DICTIONARY_BYTES)
    token_offset = align_up(directory_offset + len(directory_bytes))
    literal_offset = align_up(token_offset + token_bytes)
    encoded_bytes = literal_offset + literal_bytes
    padding_bytes = (
        dictionary_offset
        - HEADER_BYTES
        + directory_offset
        - (dictionary_offset + DICTIONARY_BYTES)
        + token_offset
        - (directory_offset + len(directory_bytes))
        + literal_offset
        - (token_offset + token_bytes)
    )
    composite = hashlib.sha256()
    for label, length, digest in (
        ("dictionary", len(dictionary_storage), hashlib.sha256(dictionary_storage).hexdigest()),
        ("directory", len(directory_bytes), directory_hash),
        ("tokens", token_bytes, token_hash.hexdigest()),
        ("literals", literal_bytes, literal_hash.hexdigest()),
    ):
        composite.update(label.encode())
        composite.update(struct.pack("<Q", length))
        composite.update(bytes.fromhex(digest))

    block_encoded = (
        TOKEN_BYTES_PER_BLOCK + escape_counts.astype(np.uint32) + 4
    )
    result = {
        "layer": module["layer"],
        "kind": module["kind"],
        "source_tensors": names,
        "source_shapes": [list(reader.records[name].shape) for name in names],
        "consumer_layout": "KxN row-major after runtime transpose",
        "encoded_block_layout": "K-major then N-major 32x128 tiles, row-major within tile",
        "consumer_shape": [int(quantized.shape[0]), int(quantized.shape[1])],
        "parameters": len(fp8),
        "scale_fp32": scale,
        "inverse_scale_fp32": inverse_scale,
        "absmax_bf16_promoted_fp32": absmax,
        "byte_histogram": histogram.tolist(),
        "byte_entropy_bits": float(
            -sum(
                (count / len(fp8)) * math.log2(count / len(fp8))
                for count in histogram
                if count
            )
        ),
        "dictionary": dictionary.tolist(),
        "top31_mass": float(histogram[dictionary].sum() / len(fp8)),
        "block_count": block_count,
        "block_entropy_bits": quantiles(entropies),
        "block_encoded_bytes_including_directory_entry": quantiles(block_encoded),
        "incompressible_blocks": int(np.count_nonzero(block_encoded >= BLOCK_BYTES)),
        "expanding_blocks": int(np.count_nonzero(block_encoded > BLOCK_BYTES)),
        "escape_literals": literal_bytes,
        "storage": {
            "raw_fp8_bytes": len(fp8),
            "header_bytes": HEADER_BYTES,
            "dictionary_bytes": DICTIONARY_BYTES,
            "directory_bytes": len(directory_bytes),
            "token_bytes": token_bytes,
            "literal_bytes": literal_bytes,
            "alignment_padding_bytes": padding_bytes,
            "encoded_bytes": encoded_bytes,
            "ratio": encoded_bytes / len(fp8),
        },
        "hashes": {
            "runtime_fp8_sha256": runtime_fp8_hash,
            "encoded_tile_order_fp8_sha256": encoded_source_hash.hexdigest(),
            "dictionary_sha256": hashlib.sha256(dictionary_storage).hexdigest(),
            "directory_sha256": directory_hash,
            "token_stream_sha256": token_hash.hexdigest(),
            "literal_stream_sha256": literal_hash.hexdigest(),
            "encoded_segment_manifest_sha256": composite.hexdigest(),
        },
        "decode": {
            "bitwise_equal": decoded_bytes == len(fp8),
            "decoded_bytes": decoded_bytes,
            "mismatched_bytes": 0,
        },
        "elapsed_seconds": time.perf_counter() - started,
    }
    del tiled, quantized
    return result, entropies, block_encoded


def validate_bindings(reader: CheckpointReader) -> dict[str, object]:
    config = CHECKPOINT / "config.json"
    index = CHECKPOINT / "model.safetensors.index.json"
    observed_config = sha256_file(config)
    observed_index = sha256_file(index)
    if observed_config != CONFIG_SHA256 or observed_index != INDEX_SHA256:
        raise RuntimeError("config or index binding mismatch")
    index_value = json.loads(index.read_text())
    missing = [
        name
        for name, shard in index_value["weight_map"].items()
        if name not in reader.records
        or reader.records[name].path.name != shard
    ]
    if missing:
        raise RuntimeError(f"index/header mapping mismatch: {missing[:3]}")
    shards = {}
    for name, expected in SHARD_SHA256.items():
        path = CHECKPOINT / name
        observed = sha256_file(path)
        if observed != expected:
            raise RuntimeError(f"shard binding mismatch: {name} {observed}")
        stat = path.stat()
        shards[name] = {
            "sha256": observed,
            "size_bytes": stat.st_size,
            "inode": stat.st_ino,
            "hardlink_count": stat.st_nlink,
            "mode_octal": oct(stat.st_mode & 0o777),
            **reader.headers[name],
        }
    return {
        "config": {"path": str(config), "sha256": observed_config},
        "index": {
            "path": str(index),
            "sha256": observed_index,
            "mapped_tensors": len(index_value["weight_map"]),
        },
        "shards": shards,
    }


def aggregate_results(
    rows: list[dict[str, object]],
    all_entropies: Iterable[np.ndarray],
    all_block_encoded: Iterable[np.ndarray],
) -> dict[str, object]:
    entropies = np.concatenate(list(all_entropies))
    block_encoded = np.concatenate(list(all_block_encoded))
    parameters = sum(int(row["parameters"]) for row in rows)
    encoded = sum(int(row["storage"]["encoded_bytes"]) for row in rows)
    raw = sum(int(row["storage"]["raw_fp8_bytes"]) for row in rows)
    if parameters != EXPECTED_PARAMETERS or raw != EXPECTED_PARAMETERS:
        raise RuntimeError(
            f"transformer parameter count mismatch: {parameters} {raw}"
        )
    aggregate_histogram = np.sum(
        np.asarray([row["byte_histogram"] for row in rows], dtype=np.uint64),
        axis=0,
    )
    entropy = -sum(
        (count / raw) * math.log2(count / raw)
        for count in aggregate_histogram
        if count
    )
    ratio = encoded / raw
    optimistic_linear = BASELINE_LINEAR_SECONDS * ratio
    optimistic_request = FIXED_SECONDS + optimistic_linear
    required_ratio = (TARGET_SECONDS - FIXED_SECONDS) / BASELINE_LINEAR_SECONDS
    encoded_manifest = hashlib.sha256()
    for row in rows:
        encoded_manifest.update(
            bytes.fromhex(row["hashes"]["encoded_segment_manifest_sha256"])
        )
    return {
        "runtime_modules": len(rows),
        "transformer_parameters": parameters,
        "runtime_fp8_bytes": raw,
        "encoded_bytes": encoded,
        "encoded_tensor_manifest_sha256": encoded_manifest.hexdigest(),
        "compression_ratio": ratio,
        "bytes_avoided": raw - encoded,
        "aggregate_byte_histogram": aggregate_histogram.tolist(),
        "aggregate_byte_entropy_bits": float(entropy),
        "all_block_entropy_bits": quantiles(entropies),
        "all_block_encoded_bytes_including_directory_entry": quantiles(
            block_encoded
        ),
        "block_count": len(block_encoded),
        "incompressible_blocks": int(np.count_nonzero(block_encoded >= BLOCK_BYTES)),
        "expanding_blocks": int(np.count_nonzero(block_encoded > BLOCK_BYTES)),
        "worst_layer_by_ratio": max(
            rows, key=lambda row: float(row["storage"]["ratio"])
        )["layer"],
        "worst_module_by_ratio": max(
            rows, key=lambda row: float(row["storage"]["ratio"])
        )["kind"],
        "economics": {
            "baseline_seconds_per_request": BASELINE_SECONDS,
            "baseline_transformer_linear_seconds": BASELINE_LINEAR_SECONDS,
            "fixed_non_transformer_seconds": FIXED_SECONDS,
            "target_seconds_per_request": TARGET_SECONDS,
            "maximum_admissible_compressed_path_ratio_before_decode_cost": required_ratio,
            "zero_decode_cost_hbm_proportional_linear_seconds": optimistic_linear,
            "zero_decode_cost_hbm_proportional_request_seconds": optimistic_request,
            "zero_decode_cost_margin_seconds": TARGET_SECONDS - optimistic_request,
            "decode_and_integration_budget_seconds": max(
                0.0, TARGET_SECONDS - optimistic_request
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=PROJECT / "FULL_CHECKPOINT_STREAM_RESULT.json",
    )
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--chunk-blocks", type=int, default=2048)
    args = parser.parse_args()
    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    started_wall = time.perf_counter()
    started_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    reader = CheckpointReader(CHECKPOINT)
    try:
        bindings = validate_bindings(reader)
        artifact_root = PROJECT / "artifacts" / "full-checkpoint-pass"
        artifact_root.mkdir(parents=True, exist_ok=True)
        atomic_json(
            artifact_root / "BINDINGS.json",
            {
                "schema_version": 1,
                "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "bindings": bindings,
            },
        )
        modules = projection_modules(reader)
        parameter_count = sum(
            sum(math.prod(reader.records[name].shape) for name in module["sources"])
            for module in modules
        )
        if parameter_count != EXPECTED_PARAMETERS:
            raise RuntimeError(f"module map count mismatch: {parameter_count}")
        library, library_hash = compile_block_stats()
        rows = []
        entropy_parts = []
        encoded_parts = []
        for index, module in enumerate(modules):
            stem = f"{index:03d}-layer{module['layer']:02d}-{module['kind']}"
            row_path = artifact_root / f"{stem}.json"
            arrays_path = artifact_root / f"{stem}.npz"
            if row_path.exists() and arrays_path.exists():
                row = json.loads(row_path.read_text())
                with np.load(arrays_path) as stored:
                    entropies = stored["entropies"]
                    block_encoded = stored["block_encoded"]
                resumed = True
            else:
                row, entropies, block_encoded = analyze_module(
                    reader, module, library, args.chunk_blocks
                )
                temporary_arrays = arrays_path.with_suffix(".npz.part")
                with temporary_arrays.open("wb") as handle:
                    np.savez_compressed(
                        handle,
                        entropies=entropies,
                        block_encoded=block_encoded,
                    )
                    handle.flush()
                    os.fsync(handle.fileno())
                temporary_arrays.replace(arrays_path)
                atomic_json(row_path, row)
                resumed = False
            rows.append(row)
            entropy_parts.append(entropies)
            encoded_parts.append(block_encoded)
            print(
                json.dumps(
                    {
                        "module": index + 1,
                        "of": len(modules),
                        "layer": row["layer"],
                        "kind": row["kind"],
                        "ratio": row["storage"]["ratio"],
                        "top31_mass": row["top31_mass"],
                        "seconds": row["elapsed_seconds"],
                        "resumed": resumed,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        aggregate = aggregate_results(rows, entropy_parts, encoded_parts)
        result = {
            "schema_version": 1,
            "result": "full_checkpoint_lossless_code_measurement",
            "model": MODEL,
            "started_at_utc": started_utc,
            "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "elapsed_seconds": time.perf_counter() - started_wall,
            "threads": args.threads,
            "checkpoint_access": "read-only mmap; no checkpoint bytes copied or persisted",
            "bindings": bindings,
            "runtime_quantization": {
                "producer": "vLLM Fp8PerTensorOnlineLinearMethod.process_weights_after_loading -> ops.scaled_fp8_quant(layer.weight, scale=None)",
                "consumer": "ROCmFP8ScaledMMLinearKernel -> rocm_per_tensor_float_w8a8_scaled_mm_impl -> wvSplitKQ or torch._scaled_mm",
                "format": "OCP E4M3FN",
                "scale": "FP32 max(abs(BF16 fused runtime tensor))/448",
                "layout": "fused checkpoint output rows, quantized, then transposed to KxN consumer layout",
                "cpu_reproducer": f"torch {torch.__version__} CPU float8_e4m3fn",
                "gpu_producer_equivalence": "source-bound but not target-executed; target gfx950 bench unavailable",
            },
            "codec": json.loads(
                (PROJECT / "PREREGISTERED_BLOCK_CODE.json").read_text()
            ),
            "block_stats_helper": {
                "source": "block_stats.cpp",
                "source_sha256": sha256_file(PROJECT / "block_stats.cpp"),
                "binary_sha256": library_hash,
            },
            "aggregate": aggregate,
            "modules": rows,
        }
        atomic_json(args.output, result)
        print(json.dumps({"terminal": str(args.output), "aggregate": aggregate}))
        return 0
    finally:
        reader.close()


if __name__ == "__main__":
    raise SystemExit(main())
