#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import struct
from typing import Any

import numpy as np


AWQ_ORDER = np.asarray((0, 4, 1, 5, 2, 6, 3, 7), dtype=np.int64)
GROUP_SIZE = 128
PREFIX = "model.language_model.layers.0.mlp"
PROJECTIONS = {
    "gate_proj": (5376, 21504),
    "up_proj": (5376, 21504),
    "down_proj": (21504, 5376),
}


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: Any) -> None:
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
        tuple(
            (unsigned >> np.uint32(4 * index)) & np.uint32(15)
            for index in range(8)
        ),
        axis=-1,
    )
    return (
        unpacked[..., AWQ_ORDER]
        .reshape(words.shape[0], words.shape[1] * 8)
        .astype(np.uint8)
    )


def qserve_pack_codes(codes_nk: np.ndarray) -> np.ndarray:
    output_features, input_features = codes_nk.shape
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
    packed = (reordered[..., 1] << np.uint8(4)) | reordered[..., 0]
    return packed.reshape(output_features, input_features // 2).view(np.int8)


def qserve_unpack_codes(packed: np.ndarray) -> np.ndarray:
    output_features, packed_input_features = packed.shape
    input_features = packed_input_features * 2
    pairs = np.stack(
        (
            packed.view(np.uint8) & np.uint8(15),
            packed.view(np.uint8) >> np.uint8(4),
        ),
        axis=-1,
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
        first.transpose(0, 4, 6, 2, 1, 5, 3, 7)
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


def write_projection(
    source: SafeTensorFile,
    output: pathlib.Path,
    projection: str,
    chunk_outputs: int,
) -> dict[str, Any]:
    input_features, output_features = PROJECTIONS[projection]
    groups = input_features // GROUP_SIZE
    base = f"{PREFIX}.{projection}"
    expected = {
        "qweight": ([input_features, output_features // 8], "I32"),
        "qzeros": ([groups, output_features // 8], "I32"),
        "scales": ([groups, output_features], "BF16"),
    }
    for suffix, (shape, dtype) in expected.items():
        observed = source.metadata(f"{base}.{suffix}")
        if observed["shape"] != shape or observed["dtype"] != dtype:
            raise RuntimeError(
                f"{projection}:{suffix}:expected={shape}/{dtype}:"
                f"observed={observed['shape']}/{observed['dtype']}"
            )

    qweight_source = source.tensor(f"{base}.qweight")
    qzeros_source = source.tensor(f"{base}.qzeros")
    scales_source = source.tensor(f"{base}.scales")
    qweight_path = output / f"{projection}.qweight.npy"
    zeros_path = output / f"{projection}.zeros.npy"
    scales_path = output / f"{projection}.scales_bf16_bits.npy"
    qweight = np.lib.format.open_memmap(
        qweight_path,
        mode="w+",
        dtype=np.int8,
        shape=(output_features, input_features // 2),
    )
    codes_equal = True
    for start in range(0, output_features, chunk_outputs):
        stop = min(start + chunk_outputs, output_features)
        source_codes = unpack_awq_words(
            qweight_source[:, start // 8 : stop // 8]
        )
        packed = qserve_pack_codes(source_codes.T)
        qweight[start:stop] = packed
        codes_equal &= np.array_equal(
            qserve_unpack_codes(packed).T,
            source_codes,
        )
    qweight.flush()
    del qweight

    original_zeros = unpack_awq_words(qzeros_source)
    reordered_zeros = qserve_reorder_group_metadata(original_zeros.T)
    np.save(zeros_path, reordered_zeros, allow_pickle=False)
    zeros_equal = np.array_equal(
        qserve_restore_group_metadata(reordered_zeros).T,
        original_zeros,
    )
    np.save(scales_path, np.asarray(scales_source), allow_pickle=False)
    scales_equal = np.array_equal(
        np.load(scales_path, mmap_mode="r", allow_pickle=False),
        scales_source,
    )
    files = {}
    for name, path in (
        ("qweight", qweight_path),
        ("zeros", zeros_path),
        ("scales_bf16_bits", scales_path),
    ):
        files[name] = {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    return {
        "projection": projection,
        "input_features": input_features,
        "output_features": output_features,
        "groups": groups,
        "codes_equal": bool(codes_equal),
        "zeros_equal": bool(zeros_equal),
        "scale_bits_equal": bool(scales_equal),
        "files": files,
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
    observed_source = sha256(args.source)
    if observed_source != args.source_sha256:
        raise RuntimeError(
            f"source_hash_mismatch:{args.source_sha256}:{observed_source}"
        )
    args.output.mkdir(parents=True, exist_ok=False)
    source = SafeTensorFile(args.source)
    rows = [
        write_projection(
            source,
            args.output,
            projection,
            args.chunk_outputs,
        )
        for projection in PROJECTIONS
    ]
    passed = all(
        row["codes_equal"] and row["zeros_equal"] and row["scale_bits_equal"]
        for row in rows
    )
    terminal = {
        "schema_version": 1,
        "classification": (
            "exact_awq_qserve_compute_layout"
            if passed
            else "producer_round_trip_reject"
        ),
        "pass": passed,
        "source": {
            "path": str(args.source.resolve()),
            "sha256": observed_source,
        },
        "group_size": GROUP_SIZE,
        "calibration": False,
        "requantization": False,
        "projections": rows,
    }
    atomic_json(args.output / "PREPARE_TERMINAL.json", terminal)
    return 0 if passed else 20


if __name__ == "__main__":
    raise SystemExit(main())
