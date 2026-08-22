#!/usr/bin/env python3
"""Stage and exercise the exact Gemma 4 attention producer without AutoModel.

The Hub revision is immutable.  This program obtains only safetensors header
and tensor intervals needed by one sliding and one full-attention layer, then
constructs the official attention modules directly.  It intentionally never
calls ``AutoModelForCausalLM.from_pretrained``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import urllib.request
from pathlib import Path

MODEL = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
BASE = f"https://huggingface.co/{MODEL}/resolve/{REVISION}"
LOCAL_LAYER, GLOBAL_LAYER = 0, 5
TENSORS = {
    LOCAL_LAYER: ("q_proj.weight", "q_norm.weight", "k_norm.weight", "k_proj.weight", "v_proj.weight", "o_proj.weight"),
    GLOBAL_LAYER: ("q_proj.weight", "q_norm.weight", "k_norm.weight", "k_proj.weight", "o_proj.weight"),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    json.loads(tmp.read_text())
    os.replace(tmp, path)


def get(url: str, byte_range: tuple[int, int] | None = None) -> bytes:
    headers = {"User-Agent": "gemma4-m384-selective-producer/1"}
    if byte_range is not None:
        headers["Range"] = f"bytes={byte_range[0]}-{byte_range[1]}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as response:
        body = response.read()
        if byte_range is not None and response.status != 206:
            raise RuntimeError(f"range request was not honored for {url}: status={response.status}")
    return body


def header(url: str) -> tuple[dict, int]:
    prefix = get(url, (0, 7))
    if len(prefix) != 8:
        raise RuntimeError(f"short safetensors prefix: {len(prefix)}")
    length = struct.unpack("<Q", prefix)[0]
    payload = get(url, (8, 8 + length - 1))
    if len(payload) != length:
        raise RuntimeError(f"short safetensors header: expected={length} got={len(payload)}")
    return json.loads(payload), 8 + length


def write_range(root: Path, name: str, source_url: str, absolute: tuple[int, int], meta: dict) -> dict:
    target = root / "weights" / f"{name}.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = absolute[1] - absolute[0] + 1
    if target.exists() and target.stat().st_size == expected:
        payload = target.read_bytes()
    else:
        payload = get(source_url, absolute)
        if len(payload) != expected:
            raise RuntimeError(f"short tensor range {name}: expected={expected} got={len(payload)}")
        tmp = target.with_name(f".{target.name}.{os.getpid()}.part")
        tmp.write_bytes(payload)
        os.replace(tmp, target)
    return {
        "path": str(target.relative_to(root)), "sha256": sha256(payload), "bytes": len(payload),
        "shape": meta["shape"], "dtype": meta["dtype"], "source_byte_range_inclusive": list(absolute),
    }


def stage(root: Path) -> dict:
    sources = root / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    config_bytes = get(f"{BASE}/config.json")
    index_bytes = get(f"{BASE}/model.safetensors.index.json")
    for filename, data in (("config.json", config_bytes), ("model.safetensors.index.json", index_bytes)):
        path = sources / filename
        tmp = path.with_name(f".{filename}.{os.getpid()}.part")
        tmp.write_bytes(data)
        os.replace(tmp, path)
    config, index = json.loads(config_bytes), json.loads(index_bytes)
    weight_map = index["weight_map"]
    needed = set()
    for layer, suffixes in TENSORS.items():
        needed.update(f"model.language_model.layers.{layer}.self_attn.{suffix}" for suffix in suffixes)
    embedding_key = "model.language_model.embed_tokens.weight"
    shards = sorted({weight_map[key] for key in needed | {embedding_key}})
    headers = {}
    shard_sources = {}
    for shard in shards:
        url = f"{BASE}/{shard}"
        parsed, data_start = header(url)
        headers[shard] = (parsed, data_start)
        shard_sources[shard] = {"resolve_url": url, "safetensors_header_bytes": data_start,
            "header_sha256": sha256(json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode())}
    outputs = {}
    for key in sorted(needed):
        shard = weight_map[key]
        entry = headers[shard][0][key]
        start, end = entry["data_offsets"]
        outputs[key] = write_range(root, key.replace(".", "_"), f"{BASE}/{shard}",
            (headers[shard][1] + start, headers[shard][1] + end - 1), entry)
    # The deterministic 384-row input construction consumes only this contiguous
    # prefix of the official embedding matrix, not its 2.8 GiB full tensor.
    embedding = headers[weight_map[embedding_key]][0][embedding_key]
    row_bytes = embedding["shape"][1] * 2
    start = headers[weight_map[embedding_key]][1] + embedding["data_offsets"][0]
    outputs["model.language_model.embed_tokens.first_384_rows"] = write_range(
        root, "model_language_model_embed_tokens_first_384_rows", f"{BASE}/{weight_map[embedding_key]}",
        (start, start + 384 * row_bytes - 1), {"shape": [384, embedding["shape"][1]], "dtype": embedding["dtype"]})
    return {"model": MODEL, "revision": REVISION, "config": {"path": "sources/config.json", "sha256": sha256(config_bytes)},
        "index": {"path": "sources/model.safetensors.index.json", "sha256": sha256(index_bytes)},
        "shards": shard_sources, "weights": outputs, "deterministic_input_ids": {"range": [0, 383], "shape": [32, 12]},
        "official_modules": {"local_layer": LOCAL_LAYER, "global_layer": GLOBAL_LAYER,
            "attention_class": "transformers.models.gemma4.modeling_gemma4.Gemma4TextAttention",
            "rotary_class": "transformers.models.gemma4.modeling_gemma4.Gemma4TextRotaryEmbedding",
            "no_automodel": True}}


def exercise(root: Path, manifest: dict) -> dict:
    import torch
    from transformers.models.gemma4.configuration_gemma4 import Gemma4TextConfig
    from transformers.models.gemma4.modeling_gemma4 import Gemma4TextAttention, Gemma4TextRotaryEmbedding

    cfg = Gemma4TextConfig(**json.loads((root / "sources/config.json").read_text())["text_config"])
    result = {"torch": torch.__version__, "transformers": __import__("transformers").__version__, "families": {}}
    for label, layer in (("local", LOCAL_LAYER), ("global", GLOBAL_LAYER)):
        attention = Gemma4TextAttention(cfg, layer).to(dtype=torch.bfloat16).eval()
        loaded = {}
        for key in attention.state_dict():
            model_key = f"model.language_model.layers.{layer}.self_attn.{key}"
            item = manifest["weights"][model_key]
            raw = (root / item["path"]).read_bytes()
            tensor = torch.frombuffer(bytearray(raw), dtype=torch.bfloat16).reshape(item["shape"]).clone()
            loaded[key] = tensor
        missing, unexpected = attention.load_state_dict(loaded, strict=True)
        if missing or unexpected:
            raise RuntimeError(f"state_dict mismatch for {label}: missing={missing} unexpected={unexpected}")
        ids = torch.arange(384, dtype=torch.long).reshape(32, 12)
        raw_embed = (root / manifest["weights"]["model.language_model.embed_tokens.first_384_rows"]["path"]).read_bytes()
        embed = torch.frombuffer(bytearray(raw_embed), dtype=torch.bfloat16).reshape(384, cfg.hidden_size)
        hidden = embed[ids].reshape(384, cfg.hidden_size)
        q_heads = attention.q_proj.out_features // attention.head_dim
        kv_heads = attention.k_proj.out_features // attention.head_dim
        q = attention.q_proj(hidden).reshape(384, q_heads, attention.head_dim)
        k = attention.k_proj(hidden).reshape(384, kv_heads, attention.head_dim)
        v_proj = getattr(attention, "v_proj", None)
        v = v_proj(hidden).reshape(384, kv_heads, attention.head_dim) if v_proj is not None else k
        q = attention.q_norm(q); k = attention.k_norm(k)
        layer_type = cfg.layer_types[layer]
        rope = Gemma4TextRotaryEmbedding(cfg, layer_type=layer_type)
        cos, sin = rope(v.unsqueeze(0), torch.arange(384).unsqueeze(0), layer_type=layer_type)
        # o_proj is exercised through its real matrix with a deterministic attention-shaped tensor.
        o = attention.o_proj(torch.zeros((384, attention.o_proj.in_features), dtype=torch.bfloat16))
        result["families"][label] = {"layer": layer, "layer_type": layer_type,
            "q_shape": list(q.shape), "k_shape": list(k.shape), "v_aliases_k": v_proj is None,
            "rotary_cos_shape": list(cos.shape), "rotary_sin_shape": list(sin.shape), "o_proj_shape": list(o.shape),
            "state_keys": sorted(loaded)}
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--stage-only", action="store_true")
    args = p.parse_args()
    root = args.root.resolve()
    manifest = stage(root)
    atomic_json(root / "SELECTIVE_ACQUISITION_MANIFEST.json", manifest)
    if args.stage_only:
        return 0
    result = exercise(root, manifest)
    atomic_json(root / "OFFICIAL_MODULE_EXERCISE.json", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
