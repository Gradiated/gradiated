#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


EXPECTED_SHA256 = "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989"
OLD = '''        qkv, _ = self.qkv_proj(hidden_states)
        q, k, v = qkv.split([self.q_size, self.kv_size, self.kv_size], dim=-1)

        # Fused Q/K/V RMSNorm: replaces three separate norm kernels with one.
        # Preconditions for the fused path: tensors on CUDA or XPU (the kernel
        # is pure Triton and lowers to both backends), q_norm/k_norm use the
        # standard norm*weight (scale_shift==0) and v_norm has weight=ones
        # (with_scale=False) — the canonical Gemma4 attention configuration.
        is_kv_shared = (
            self.is_kv_shared_layer and self.kv_shared_layer_index is not None
        )
        can_fuse_qkv_norm = (
            (q.is_cuda or q.is_xpu)
            and self.q_norm.scale_shift == 0.0
            and self.k_norm.scale_shift == 0.0
            and not self.v_norm.with_scale
        )
        if can_fuse_qkv_norm:
            if is_kv_shared:
                gemma_qkv_rmsnorm(
                    q,
                    None,
                    None,
                    self.q_norm.weight.data,
                    None,
                    num_q_heads=self.num_heads,
                    num_kv_heads=self.num_kv_heads,
                    head_dim=self.head_dim,
                    eps=self.q_norm.eps,
                )
                k = None
                v = None
            else:
                gemma_qkv_rmsnorm(
                    q,
                    k,
                    v,
                    self.q_norm.weight.data,
                    self.k_norm.weight.data,
                    num_q_heads=self.num_heads,
                    num_kv_heads=self.num_kv_heads,
                    head_dim=self.head_dim,
                    eps=self.q_norm.eps,
                )
                # Match the original norm path's output shapes: q stays 2D,
                # k/v become 3D so the subsequent `.flatten(-2, -1)` works.
                # Use reshape (not view) since k/v are strided slice views of
                # the qkv buffer and may not satisfy view's contiguity rules.
                k = k.reshape(-1, self.num_kv_heads, self.head_dim)
                v = v.reshape(-1, self.num_kv_heads, self.head_dim)
        else:
            q = q.unflatten(-1, (self.num_heads, self.head_dim))
            q = self.q_norm(q)
            q = q.flatten(-2, -1)
            if is_kv_shared:
                k = None
                v = None
            else:
                k = k.unflatten(-1, (self.num_kv_heads, self.head_dim))
                k = self.k_norm(k)
                v = v.unflatten(-1, (self.num_kv_heads, self.head_dim))
                v = self.v_norm(v)

        # Apply rotary embedding
        use_fused_kv = False
        if k is not None:
            k = k.flatten(-2, -1)
            # Fuse RoPE + KV-cache write for non-SWA layers with bf16 cache
            # DISABLED: causes accuracy regression in launch_server path
            can_fuse = False
            if can_fuse:
                fused_arg = create_fused_set_kv_buffer_arg(
                    value=v.flatten(-2, -1) if v.dim() == 3 else v,
                    layer=self.attn,
                    forward_batch=forward_batch,
                )
                use_fused_kv = True
            else:
                fused_arg = None
            q, k = self.rotary_emb(positions, q, k, fused_set_kv_buffer_arg=fused_arg)
            k = k.unflatten(-1, (self.num_kv_heads, self.head_dim))
        else:
            # Rotary embedding requires a key input; use zeros since KV is shared from another layer
            dummy_k = torch.zeros_like(q[:, : self.kv_size])
            q, _ = self.rotary_emb(positions, q, dummy_k)

        q = q.unflatten(-1, (self.num_heads, self.head_dim))
'''
NEW = '''        qkv, _ = self.qkv_proj(hidden_states)
        use_fused_kv = False
        if self.is_kv_shared_layer:
            raise RuntimeError("QKV epilogue candidate excludes KV-shared layers")
        from qkv_epilogue_discriminator import qkv_norm_rope_inplace

        qkv_norm_rope_inplace(
            qkv,
            self.q_norm.weight.data,
            self.k_norm.weight.data,
            positions,
            self.rotary_emb.cos_sin_cache,
            self.num_heads,
            self.num_kv_heads,
            self.head_dim,
            self.q_norm.eps,
        )
        q, k, v = qkv.split([self.q_size, self.kv_size, self.kv_size], dim=-1)
        q = q.unflatten(-1, (self.num_heads, self.head_dim))
        k = k.unflatten(-1, (self.num_kv_heads, self.head_dim))
        v = v.unflatten(-1, (self.num_kv_heads, self.head_dim))
'''


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=pathlib.Path,
        default=pathlib.Path(
            "/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py"
        ),
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    original = args.source.read_bytes()
    original_sha256 = digest(original)
    if original_sha256 != EXPECTED_SHA256:
        raise RuntimeError(
            f"pinned Gemma4 source mismatch: {original_sha256} != {EXPECTED_SHA256}"
        )
    text = original.decode()
    if text.count(OLD) != 1:
        raise RuntimeError("pinned Gemma4 forward block is not unique")
    patched = text.replace(OLD, NEW).encode()
    temporary = args.source.with_suffix(args.source.suffix + ".qkv-part")
    temporary.write_bytes(patched)
    temporary.replace(args.source)
    value = {
        "schema_version": 1,
        "pass": True,
        "source": str(args.source),
        "original_sha256": original_sha256,
        "patched_sha256": digest(patched),
        "candidate_import": "qkv_epilogue_discriminator.qkv_norm_rope_inplace",
    }
    output_temporary = args.output.with_suffix(args.output.suffix + ".part")
    output_temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    output_temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
