#!/usr/bin/env python3
"""Streaming, CPU-only AWQ writer; invoked only by the durable local owner."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import traceback
import time
from pathlib import Path

import torch
from safetensors import safe_open

GROUP = 128
PACK = 8
ORDER = torch.tensor([0, 2, 4, 6, 1, 3, 5, 7], dtype=torch.long)


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(16 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def header(path: Path) -> dict[str, object]:
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        return json.loads(f.read(n))


def byte_count(dtype: str, shape: list[int]) -> int:
    bits = {"BF16": 2, "F16": 2, "F32": 4, "I32": 4, "I64": 8, "I16": 2, "I8": 1, "U8": 1}[dtype]
    n = 1
    for x in shape:
        n *= x
    return n * bits


def raw(t: torch.Tensor) -> bytes:
    t = t.detach().contiguous().cpu()
    if t.dtype == torch.bfloat16:
        t = t.view(torch.uint16)
    return t.numpy().tobytes()


def is_linear(name: str, item: dict[str, object]) -> bool:
    shape = item["shape"]
    return (
        name.startswith("model.language_model.layers.")
        and name.endswith(".weight")
        and isinstance(shape, list) and len(shape) == 2
        and int(shape[1]) % GROUP == 0 and int(shape[0]) % PACK == 0
    )


def descriptors(source_headers: dict[str, dict[str, object]]) -> tuple[dict[str, list[dict[str, object]]], dict[str, list[str]]]:
    out: dict[str, list[dict[str, object]]] = {}
    accounting: dict[str, list[str]] = {}
    for file, items in source_headers.items():
        rows = []
        for name, item in items.items():
            if name == "__metadata__":
                continue
            if is_linear(name, item):
                n, k = map(int, item["shape"])
                g = k // GROUP
                names = [name[:-7] + suffix for suffix in (".qweight", ".qzeros", ".scales")]
                rows.extend([
                    {"name": names[0], "dtype": "I32", "shape": [k, n // PACK], "source": name, "kind": "qweight"},
                    {"name": names[1], "dtype": "I32", "shape": [g, n // PACK], "source": name, "kind": "qzeros"},
                    {"name": names[2], "dtype": "BF16", "shape": [g, n], "source": name, "kind": "scales"},
                ])
                accounting[name] = names
            else:
                rows.append({"name": name, "dtype": item["dtype"], "shape": item["shape"], "source": name, "kind": "copy"})
                accounting[name] = [name]
        out[file] = rows
    return out, accounting


def write_header(target: Path, rows: list[dict[str, object]]) -> None:
    offset = 0
    data = {"__metadata__": {"format": "pt"}}
    for row in rows:
        size = byte_count(str(row["dtype"]), list(row["shape"]))
        data[str(row["name"])] = {"dtype": row["dtype"], "shape": row["shape"], "data_offsets": [offset, offset + size]}
        offset += size
    encoded = json.dumps(data, separators=(",", ":")).encode()
    with target.open("wb") as f:
        f.write(struct.pack("<Q", len(encoded)))
        f.write(encoded)


def write_quantized(f, handle, name: str, n: int, k: int) -> dict[str, float]:
    source = handle.get_slice(name)
    scales = torch.empty((k // GROUP, n), dtype=torch.bfloat16)
    zeros = torch.empty((k // GROUP, n // PACK), dtype=torch.int32)
    nontrivial = 0.0
    for g0 in range(0, k, GROUP):
        g1 = g0 + GROUP
        scale_row = torch.empty((n,), dtype=torch.bfloat16)
        zero_row = torch.empty((n,), dtype=torch.int32)
        for n0 in range(0, n, 256):
            n1 = min(n, n0 + 256)
            w = source[n0:n1, g0:g1].to(torch.float32)
            lo, hi = w.amin(dim=1), w.amax(dim=1)
            s = ((hi - lo) / 15).clamp_min(1e-8)
            z = torch.round(-lo / s).clamp(0, 15).to(torch.int32)
            q = torch.round(w / s[:, None]).to(torch.int32) + z[:, None]
            q = q.clamp(0, 15).transpose(0, 1).contiguous()
            packed = (q.reshape(GROUP, (n1 - n0) // PACK, PACK)[:, :, ORDER] << (4 * torch.arange(PACK, dtype=torch.int32))).sum(dim=2, dtype=torch.int32)
            f.write(raw(packed))
            scale_row[n0:n1] = s.to(torch.bfloat16)
            zero_row[n0:n1] = z
            nontrivial = max(nontrivial, float(s.max()))
        scales[g0 // GROUP] = scale_row
        qz = zero_row.reshape(n // PACK, PACK)[:, ORDER]
        zeros[g0 // GROUP] = (qz << (4 * torch.arange(PACK, dtype=torch.int32))).sum(dim=1, dtype=torch.int32)
    f.write(raw(zeros))
    f.write(raw(scales))
    return {"max_scale": nontrivial, "finite": bool(torch.isfinite(scales.float()).all())}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--deadline-epoch", type=float, required=True)
    args = p.parse_args()
    terminal = args.output.parent / "QUANTIZER_TERMINAL.json"
    try:
        if time.time() >= args.deadline_epoch:
            raise TimeoutError("deadline expired")
        source_files = sorted(args.source.glob("*.safetensors"))
        source_headers = {x.name: header(x) for x in source_files}
        rows_by_file, accounting = descriptors(source_headers)
        args.output.mkdir(parents=True, exist_ok=False)
        oracle = []
        outputs = []
        for source_path in source_files:
            if time.time() >= args.deadline_epoch:
                raise TimeoutError("deadline expired during tensor conversion")
            target = args.output / source_path.name
            rows = rows_by_file[source_path.name]
            write_header(target, rows)
            by_source: dict[str, list[dict[str, object]]] = {}
            for row in rows:
                by_source.setdefault(str(row["source"]), []).append(row)
            with safe_open(source_path, framework="pt", device="cpu") as handle, target.open("ab") as f:
                for source_name in handle.keys():
                    group = by_source[source_name]
                    if group[0]["kind"] == "copy":
                        f.write(raw(handle.get_tensor(source_name)))
                    else:
                        item = source_headers[source_path.name][source_name]
                        n, k = map(int, item["shape"])
                        result = write_quantized(f, handle, source_name, n, k)
                        if len(oracle) < 12:
                            oracle.append({"source": source_name, **result})
            outputs.append({"path": target.name, "bytes": target.stat().st_size, "sha256": sha(target)})
        index = {"metadata": {"format": "pt"}, "weight_map": {out: file for file, rows in rows_by_file.items() for row in rows for out in [row["name"]]}}
        (args.output / "model.safetensors.index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
        config = json.loads((args.source / "config.json").read_text())
        config["quantization_config"] = {"quant_method": "awq", "bits": 4, "group_size": GROUP, "zero_point": True, "version": "gemm", "modules_to_not_convert": ["model.language_model.embed_tokens", "lm_head", "model.embed_vision"]}
        (args.output / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
        (args.output / "quant_config.json").write_text(json.dumps({"w_bit": 4, "q_group_size": GROUP, "zero_point": True, "version": "GEMM"}, indent=2, sort_keys=True) + "\n")
        for name in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "processor_config.json"):
            shutil.copy2(args.source / name, args.output / name)
        expected = {name for items in source_headers.values() for name in items if name != "__metadata__"}
        probe = subprocess.run([
            sys.executable, "-c",
            "from vllm.config import ModelConfig; "
            f"c=ModelConfig(model={str(args.output)!r},tokenizer={str(args.output)!r},dtype='bfloat16',quantization='awq',max_model_len=12000); "
            "print(c.quantization)",
        ], text=True, capture_output=True, timeout=180)
        (args.output.parent / "loader-metadata.stdout.log").write_text(probe.stdout[-12000:])
        (args.output.parent / "loader-metadata.stderr.log").write_text(probe.stderr[-12000:])
        passed = set(accounting) == expected and all(len(v) in (1, 3) for v in accounting.values()) and all(x["finite"] and x["max_scale"] > 0 for x in oracle) and probe.returncode == 0
        atomic(terminal, {"schema_version": 1, "classification": "streaming_awq_w4_quantizer", "pass": passed, "source_tensor_count": len(expected), "accounted_tensor_count": len(accounting), "output_files": outputs, "oracle_samples": oracle, "accounting": accounting, "quantization": {"bits": 4, "group_size": GROUP, "zero_point": True, "pack_order": ORDER.tolist()}, "exact_image_loader_metadata_parse": {"returncode": probe.returncode, "stdout_tail": probe.stdout[-2000:], "stderr_sha256": hashlib.sha256(probe.stderr.encode()).hexdigest()}})
        return 0 if passed else 2
    except Exception as e:
        atomic(terminal, {"schema_version": 1, "classification": "streaming_awq_w4_quantizer_failure", "pass": False, "error_type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc()[-8000:]})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
