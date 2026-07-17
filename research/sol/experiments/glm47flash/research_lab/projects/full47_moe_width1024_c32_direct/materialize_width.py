#!/usr/bin/env python3
"""Build checksum-closed full-serving W4 roots with a narrower MoE width."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = Path("/root/.cache/glm47flash-awq-ab31d120")
REVISION = "ab31d120fbe79988fe2a0259993cf3c222aa8881"
CONFIG_SHA = "079f8fcd477b07378deafc21ecc5c3b974bf109ce5c9115854d97f88fa7622b9"
INDEX_SHA = "b9c53433e94f2fe7870cdbc3fcb6ed1431eb500c5242a039de93fef4bb988695"
PAYLOAD = (".gitattributes", "README.md", "chat_template.jinja", "config.json", "generation_config.json", "model-00001-of-00004.safetensors", "model-00002-of-00004.safetensors", "model-00003-of-00004.safetensors", "model-00004-of-00004.safetensors", "model.safetensors.index.json", "tokenizer.json", "tokenizer_config.json")
CONTROLS = ("model-files-manifest.json", "model-files.sha256")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def header(path: Path) -> tuple[int, dict]:
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        return 8 + n, json.loads(f.read(n))


def layer(name: str) -> int | None:
    p = "model.layers."
    if not name.startswith(p): return None
    value = name[len(p):].split(".", 1)[0]
    return int(value) if value.isdigit() else None


def is_width_tensor(name: str) -> bool:
    return ".mlp.experts." in name or ".mlp.shared_experts." in name


def slice_spec(name: str, item: dict, width: int) -> tuple[int, int] | None:
    """Return (axis, kept columns/rows), or None for an unchanged tensor."""
    if not is_width_tensor(name): return None
    shape = item["shape"]
    if name.endswith(("gate_proj.weight_packed", "up_proj.weight_packed", "gate_proj.weight_scale", "up_proj.weight_scale", "shared_experts.gate_proj.weight", "shared_experts.up_proj.weight")):
        return (0, width)
    if name.endswith("down_proj.weight_packed"):
        return (1, width // 8)
    if name.endswith("down_proj.weight_scale"):
        return (1, width // 32)
    if name.endswith("shared_experts.down_proj.weight"):
        return (1, width)
    if name.endswith("weight_shape"):
        return (2, width)
    raise ValueError(f"unexpected MoE tensor {name} shape={shape}")


def dtype_bytes(dtype: str) -> int:
    return {"BF16": 2, "F32": 4, "I32": 4, "I64": 8}[dtype]


def sliced_item(item: dict, spec: tuple[int, int] | None) -> dict:
    value = {k: v for k, v in item.items() if k != "data_offsets"}
    if spec is not None and spec[0] != 2:
        axis, size = spec
        shape = list(value["shape"])
        shape[axis] = size
        value["shape"] = shape
    return value


def copy_tensor(src, out, offset: int, name: str, item: dict, spec: tuple[int, int] | None) -> int:
    start, end = map(int, item["data_offsets"])
    src.seek(offset + start)
    if spec is None:
        remaining = end - start
        while remaining:
            b = src.read(min(1 << 20, remaining))
            if not b: raise IOError("truncated source tensor")
            out.write(b); remaining -= len(b)
        return end - start
    axis, keep = spec
    if axis == 2:
        if not item["dtype"] == "I64" or item["shape"] != [2]:
            raise AssertionError("unexpected packed weight_shape representation")
        src.seek(offset + start)
        old = struct.unpack("<qq", src.read(16))
        new = (old[0], keep) if ".down_proj." in name else (keep, old[1])
        out.write(struct.pack("<qq", *new))
        return 16
    shape = item["shape"]
    elem = dtype_bytes(item["dtype"])
    if axis == 0:
        count = keep
        row = (end - start) // int(shape[0])
        remaining = count * row
        while remaining:
            b = src.read(min(1 << 20, remaining))
            if not b: raise IOError("truncated row slice")
            out.write(b); remaining -= len(b)
        return count * row
    rows, cols = map(int, shape)
    row_bytes, kept = cols * elem, keep * elem
    written = 0
    for _ in range(rows):
        b = src.read(kept)
        if len(b) != kept: raise IOError("truncated column slice")
        out.write(b); written += kept
        src.seek(row_bytes - kept, 1)
    return written


def write_shard(source: Path, destination: Path, names: list[str], items: dict[str, dict], width: int) -> dict[str, dict]:
    offset, original = header(source)
    new: dict[str, dict] = {"__metadata__": original.get("__metadata__", {})}
    cursor = 0
    specs = {}
    for name in names:
        spec = slice_spec(name, items[name], width)
        value = sliced_item(items[name], spec)
        shape = value["shape"]
        size = dtype_bytes(value["dtype"])
        for dim in shape: size *= int(dim)
        value["data_offsets"] = [cursor, cursor + size]
        cursor += size; new[name] = value; specs[name] = spec
    encoded = json.dumps(new, sort_keys=True, separators=(",", ":")).encode()
    encoded += b" " * ((8 - ((len(encoded) + 8) % 8)) % 8)
    with source.open("rb") as src, destination.open("wb") as out:
        out.write(struct.pack("<Q", len(encoded))); out.write(encoded)
        for name in names:
            copied = copy_tensor(src, out, offset, name, items[name], specs[name])
            if copied != new[name]["data_offsets"][1] - new[name]["data_offsets"][0]:
                raise AssertionError(f"payload size mismatch for {name}")
    return new


def rows(root: Path) -> list[dict]:
    return [{"path": name, "bytes": (root / name).stat().st_size, "sha256": sha(root / name)} for name in PAYLOAD]


def materialize(width: int) -> dict:
    if width not in (768, 1024): raise ValueError("only preregistered widths are legal")
    if sha(SOURCE / "config.json") != CONFIG_SHA or sha(SOURCE / "model.safetensors.index.json") != INDEX_SHA: raise RuntimeError("source identity drift")
    index = json.loads((SOURCE / "model.safetensors.index.json").read_text())
    headers, items = {}, {}
    for shard in sorted(set(index["weight_map"].values())):
        _, h = header(SOURCE / shard); headers[shard] = h
        items.update({n: {**v, "shard": shard} for n, v in h.items() if n != "__metadata__"})
    if set(items) != set(index["weight_map"]): raise AssertionError("source header/index mismatch")
    retained = [name for name in index["weight_map"] if layer(name) != 47]
    if any(layer(name) == 47 for name in retained): raise AssertionError("MTP leak")
    contract = {"schema_version": 1, "source_revision": REVISION, "source_config_sha256": CONFIG_SHA, "source_index_sha256": INDEX_SHA, "serving_layer_ids": list(range(47)), "mtp_payload_excluded": 47, "moe_width": width, "routed_experts": 64, "top_k": 4, "shared_expert": True, "quantization": "symmetric_group32_w4a16", "payload_allowlist": list(PAYLOAD), "builder_sha256": sha(Path(__file__))}
    contract_sha = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    root = Path(f"/root/.cache/glm47flash-awq-full47-width{width}-{contract_sha[:12]}")
    if not root.exists():
        temp = Path(tempfile.mkdtemp(prefix=f"glm47-width{width}-", dir="/root/.cache"))
        try:
            grouped = {s: [] for s in sorted(set(index["weight_map"].values()))}
            for name in retained: grouped[index["weight_map"][name]].append(name)
            output_map, output_headers = {}, {}
            for ordinal, shard in enumerate(sorted(grouped), 1):
                out = f"model-{ordinal:05d}-of-00004.safetensors"
                h = write_shard(SOURCE / shard, temp / out, grouped[shard], items, width)
                output_headers.update(h)
                output_map.update({name: out for name in grouped[shard]})
            config = json.loads((SOURCE / "config.json").read_text())
            config["moe_intermediate_size"] = width; config["num_nextn_predict_layers"] = 0
            config["mlp_layer_types"] = config["mlp_layer_types"][:47]
            (temp / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
            total = sum(int(h["data_offsets"][1] - h["data_offsets"][0]) for n, h in output_headers.items() if n != "__metadata__")
            (temp / "model.safetensors.index.json").write_text(json.dumps({"metadata": {"total_size": total}, "weight_map": dict(sorted(output_map.items()))}, indent=2, sort_keys=True) + "\n")
            for name in PAYLOAD:
                if name not in {"config.json", "model.safetensors.index.json"} and not name.endswith(".safetensors"): shutil.copy2(SOURCE / name, temp / name)
            payload = rows(temp)
            manifest = {"schema_version": 2, "repository": "local-derived/glm47flash-full47-moe-width", "revision": REVISION, "policy": "served-payload-allowlist-12-files", "shard_count": 4, "weight_bytes": sum(r["bytes"] for r in payload if r["path"].endswith(".safetensors")), "files": payload}
            (temp / CONTROLS[0]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            (temp / CONTROLS[1]).write_text("".join(f"{r['sha256']}  {r['path']}\n" for r in payload))
            os.replace(temp, root)
        except Exception:
            shutil.rmtree(temp, ignore_errors=True); raise
    payload = rows(root); manifest = json.loads((root / CONTROLS[0]).read_text()); config = json.loads((root / "config.json").read_text()); outindex = json.loads((root / "model.safetensors.index.json").read_text())
    expected = set(retained)
    if set(outindex["weight_map"]) != expected or config["moe_intermediate_size"] != width or config["num_nextn_predict_layers"] != 0 or len(config["mlp_layer_types"]) != 47 or manifest["files"] != payload or any(p.is_symlink() for p in root.iterdir()): raise AssertionError("candidate closure mismatch")
    for name, item in items.items():
        if name not in expected: continue
        spec = slice_spec(name, item, width)
        if spec is not None and spec[0] != 2 and output_shape(root, outindex["weight_map"][name], name)[spec[0]] != spec[1]: raise AssertionError(f"shape mismatch {name}")
    return {"status": "PASS", "width": width, "root": str(root), "contract_sha256": contract_sha, "manifest_sha256": sha(root / CONTROLS[0]), "checksum_list_sha256": sha(root / CONTROLS[1]), "config_sha256": sha(root / "config.json"), "index_sha256": sha(root / "model.safetensors.index.json"), "weight_bytes": manifest["weight_bytes"], "tensor_count": len(expected), "no_symlinks": True, "idempotent": True, "dispatch_contract": {"runtime": "vllm-0.15.0", "ordinary_marlin": "compressed-tensors W4 group32 selected by unchanged LinearBase tensors", "fused_moe": "Glm4MoeLite config moe_intermediate_size with 64 experts/top4"}}


def output_shape(root: Path, shard: str, name: str) -> list[int]:
    _, h = header(root / shard)
    return h[name]["shape"]


if __name__ == "__main__":
    result = {str(width): materialize(width) for width in (1024, 768)}
    (HERE / "MATERIALIZATION.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
