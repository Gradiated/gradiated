#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


EXPECTED_GEMMA4_CAUSAL_SHA256 = (
    "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989"
)
IMPORT_ANCHOR = (
    "from sglang.srt.model_loader.weight_utils import (\n"
    "    default_weight_loader,\n"
    "    maybe_remap_kv_scale_name,\n"
    ")\n"
)
IMPORT_REPLACEMENT = (
    IMPORT_ANCHOR
    + "from fused_qkv_kv_cache import (\n"
    + "    qkv_norm_rope_cache_store,\n"
    + "    resolve_cache_destination,\n"
    + ")\n"
)
FORWARD_START = "        qkv, _ = self.qkv_proj(hidden_states)\n"
FORWARD_END = "        q = q.unflatten(-1, (self.num_heads, self.head_dim))\n"
ATTENTION_SAVE = (
    "            save_kv_cache=not self.is_kv_shared_layer and not use_fused_kv,\n"
)
CANDIDATE_FORWARD = """        qkv, _ = self.qkv_proj(hidden_states)
        is_kv_shared = (
            self.is_kv_shared_layer and self.kv_shared_layer_index is not None
        )
        if is_kv_shared:
            raise RuntimeError("fused QKV cache commit does not admit shared-KV layers")
        if self.attn.k_scale is None or self.attn.v_scale is None:
            raise RuntimeError("fused QKV cache commit requires explicit KV scales")
        destination = resolve_cache_destination(self.attn, forward_batch)
        qkv_norm_rope_cache_store(
            qkv,
            self.q_norm.weight.data,
            self.k_norm.weight.data,
            positions,
            self.rotary_emb.cos_sin_cache,
            destination,
            num_q_heads=self.num_heads,
            num_kv_heads=self.num_kv_heads,
            head_dim=self.head_dim,
            eps=self.q_norm.eps,
            k_scale=self.attn.k_scale,
            v_scale=self.attn.v_scale,
        )
        q, k, v = qkv.split([self.q_size, self.kv_size, self.kv_size], dim=-1)
        q = q.unflatten(-1, (self.num_heads, self.head_dim))
        k = k.unflatten(-1, (self.num_kv_heads, self.head_dim))
        v = v.unflatten(-1, (self.num_kv_heads, self.head_dim))
"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_source(source: bytes) -> bytes:
    actual = sha256_bytes(source)
    if actual != EXPECTED_GEMMA4_CAUSAL_SHA256:
        raise ValueError(
            f"gemma4_causal.py hash mismatch: expected "
            f"{EXPECTED_GEMMA4_CAUSAL_SHA256}, found {actual}"
        )
    text = source.decode()
    if text.count(IMPORT_ANCHOR) != 1:
        raise ValueError("pinned import anchor is not unique")
    class_start = text.index("class Gemma4Attention")
    forward_start = text.index(FORWARD_START, class_start)
    forward_end = text.index(FORWARD_END, forward_start) + len(FORWARD_END)
    decoder_start = text.index("class Gemma4DecoderLayer", forward_end)
    attention_region = text[forward_end:decoder_start]
    if attention_region.count(ATTENTION_SAVE) != 1:
        raise ValueError("pinned save_kv_cache anchor is not unique")

    text = text.replace(IMPORT_ANCHOR, IMPORT_REPLACEMENT, 1)
    text = text[:forward_start] + CANDIDATE_FORWARD + text[forward_end:]
    decoder_start = text.index("class Gemma4DecoderLayer", forward_start)
    prefix = text[:decoder_start]
    suffix = text[decoder_start:]
    prefix = prefix.replace(ATTENTION_SAVE, "            save_kv_cache=False,\n", 1)
    if ATTENTION_SAVE in prefix:
        raise ValueError("unpatched attention save anchor remains")
    return (prefix + suffix).encode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    source = args.source.read_bytes()
    patched = patch_source(source)
    result = {
        "schema_version": 1,
        "source": str(args.source.resolve()),
        "source_sha256": sha256_bytes(source),
        "patched_sha256": sha256_bytes(patched),
        "candidate_import_installed": True,
        "save_kv_cache_disabled_after_candidate_commit": True,
    }
    if args.check:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    if args.output is None:
        raise SystemExit("--output is required unless --check is set")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_bytes(patched)
    temporary.replace(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
