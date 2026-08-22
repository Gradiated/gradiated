#!/usr/bin/env python3
"""Run the exact selective Gemma-4 M384 stock/candidate component ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
from pathlib import Path

import torch
from torch.utils.cpp_extension import load


def atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tensor_from_stage(root: Path, item: dict) -> torch.Tensor:
    return torch.frombuffer(
        bytearray((root / item["path"]).read_bytes()), dtype=torch.bfloat16
    ).reshape(item["shape"]).clone()


def timed(call, repetitions: int = 8) -> list[float]:
    for _ in range(2):
        call()
    torch.cuda.synchronize()
    values = []
    for _ in range(repetitions):
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        start.record()
        call()
        end.record()
        end.synchronize()
        values.append(float(start.elapsed_time(end)))
    return values


def stock_call(tensors: dict) -> None:
    from sglang.srt.layers.attention.triton_ops.extend_attention import extend_attention_fwd

    extend_attention_fwd(
        tensors["q"], tensors["k"], tensors["v"], tensors["stock_o"],
        tensors["k_buffer"], tensors["v_buffer"], tensors["qo_indptr"],
        tensors["kv_indptr"], tensors["kv_indices"], None, True, None,
        tensors["max_len_extend"], 1.0, 1.0,
        sm_scale=None, logit_cap=0.0, skip_prefix_custom_mask=True,
        sliding_window_size=-1, sinks=None, window_kv_offsets=None,
        xai_temperature_len=-1,
    )


def candidate_call(candidate, tensors: dict) -> None:
    tensors["candidate_o"].copy_(candidate.launch(
        tensors["q"], tensors["k_buffer"], tensors["v_buffer"],
        tensors["page_indices"], tensors["request_ids"], tensors["key_rows"],
    ))


def build_family(stage: Path, manifest: dict, config, family: str, layer: int) -> tuple[object, dict]:
    from transformers.models.gemma4.modeling_gemma4 import (
        Gemma4TextAttention, Gemma4TextRotaryEmbedding, apply_rotary_pos_emb,
    )
    from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool

    attention = Gemma4TextAttention(config, layer).to(dtype=torch.bfloat16, device="cuda").eval()
    state = {
        key: tensor_from_stage(stage, manifest["weights"][f"model.language_model.layers.{layer}.self_attn.{key}"])
        for key in attention.state_dict()
    }
    attention.load_state_dict(state, strict=True)
    embeddings = tensor_from_stage(
        stage, manifest["weights"]["model.language_model.embed_tokens.first_384_rows"]
    ).to("cuda")
    hidden = embeddings[torch.arange(384, device="cuda").reshape(32, 12)].reshape(384, config.hidden_size)
    q = attention.q_norm(attention.q_proj(hidden).reshape(384, 32, attention.head_dim))
    k = attention.k_norm(attention.k_proj(hidden).reshape(384, attention.k_proj.out_features // attention.head_dim, attention.head_dim))
    value_projection = getattr(attention, "v_proj", None)
    v = value_projection(hidden).reshape_as(k) if value_projection is not None else k
    rope = Gemma4TextRotaryEmbedding(config, layer_type=config.layer_types[layer]).to("cuda")
    cos, sin = rope(v.unsqueeze(0), torch.arange(384, device="cuda").unsqueeze(0), layer_type=config.layer_types[layer])
    q, k = apply_rotary_pos_emb(q.unsqueeze(0), k.unsqueeze(0), (cos, sin))
    q, k = q.squeeze(0).contiguous(), k.squeeze(0).contiguous()

    # This is the installed SGLang pool path, not a manually assigned cache tensor.
    pool = MHATokenToKVPool(
        size=769, page_size=1, dtype=torch.bfloat16, head_num=k.shape[1],
        head_dim=k.shape[2], layer_num=1, device="cuda", enable_memory_saver=False,
        v_head_dim=v.shape[2], enable_alt_stream=False,
    )
    layer_proxy = type("Layer", (), {"layer_id": 0})()
    out_cache_loc = torch.arange(384, device="cuda", dtype=torch.int64)
    pool.set_kv_buffer(layer_proxy, out_cache_loc, k, v)
    qo_indptr = torch.arange(0, 385, 12, device="cuda", dtype=torch.int32)
    kv_indptr = torch.arange(0, 385, 12, device="cuda", dtype=torch.int32)
    request_ids = torch.arange(32, device="cuda", dtype=torch.int32).repeat_interleave(12)
    key_rows = torch.full((384, 12), -1, device="cuda", dtype=torch.int32)
    for request in range(32):
        first = request * 12
        for position in range(12):
            key_rows[first + position, : position + 1] = torch.arange(first, first + position + 1, device="cuda", dtype=torch.int32)
    return attention, {
        "family": family, "layer": layer, "q": q, "k": k.contiguous(), "v": v.contiguous(),
        "stock_o": torch.empty_like(q), "candidate_o": torch.empty_like(q),
        "k_buffer": pool.get_key_buffer(0), "v_buffer": pool.get_value_buffer(0),
        "qo_indptr": qo_indptr, "kv_indptr": kv_indptr, "kv_indices": out_cache_loc,
        "page_indices": out_cache_loc.to(torch.int32), "request_ids": request_ids,
        "key_rows": key_rows, "max_len_extend": 12,
        "metadata": {"batch_size": 32, "rows_per_request": 12, "page_size": 1,
                     "qo_indptr": "arange(0,385,12)", "kv_indptr": "arange(0,385,12)",
                     "kv_indices": "out_cache_loc", "causal": True, "custom_mask": None},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stage, output = args.stage, args.output
    manifest_bytes = (stage / "SELECTIVE_ACQUISITION_MANIFEST.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    from transformers.models.gemma4.configuration_gemma4 import Gemma4TextConfig
    config = Gemma4TextConfig(**json.loads((stage / "sources/config.json").read_text())["text_config"])
    candidate = load(name="m384_grouped_attention_sm90a", sources=[str(args.source)], verbose=False)
    prepared = [
        build_family(stage, manifest, config, family, layer)
        for family, layer in (("local", 0), ("global", 5))
    ]
    if not torch.cuda.is_available() or not hasattr(candidate, "launch"):
        raise RuntimeError("runtime_or_candidate_path_invalid_before_science")
    atomic(output.with_name("science_started.json"), {
        "stage_manifest_sha256": sha256(manifest_bytes),
        "candidate_source_sha256": sha256(args.source.read_bytes()),
        "stock_symbol": "sglang.srt.layers.attention.triton_ops.extend_attention.extend_attention_fwd",
        "candidate_symbol": "m384_grouped_attention_sm90a.launch",
        "families": [
            {"family": tensors["family"], "layer": tensors["layer"],
             "q_shape": list(tensors["q"].shape), "kv_shape": list(tensors["k"].shape),
             "metadata": tensors["metadata"]}
            for _, tensors in prepared
        ],
        "state": "science_started_immediately_before_first_stock_or_candidate_submission",
    })
    rows = []
    for attention, tensors in prepared:
        family, layer = tensors["family"], tensors["layer"]
        stock_call(tensors)
        candidate_call(candidate, tensors)
        torch.cuda.synchronize()
        stock_downstream = attention.o_proj(tensors["stock_o"].reshape(384, -1))
        candidate_downstream = attention.o_proj(tensors["candidate_o"].reshape(384, -1))
        output_error = (tensors["stock_o"].float() - tensors["candidate_o"].float()).abs()
        downstream_error = (stock_downstream.float() - candidate_downstream.float()).abs()
        stock_ms = timed(lambda: stock_call(tensors))
        candidate_ms = timed(lambda: candidate_call(candidate, tensors))
        row = {
            "family": family, "layer": layer, "producer": "official_selective_gemma4_module_qkv_norm_rope",
            "stock_consumer": "sglang.srt.layers.attention.triton_ops.extend_attention.extend_attention_fwd",
            "stock_store": "sglang.srt.mem_cache.memory_pool.MHATokenToKVPool.set_kv_buffer",
            "candidate_consumer": "m384_grouped_attention_sm90a.launch", "metadata": tensors["metadata"],
            "q_shape": list(tensors["q"].shape), "kv_shape": list(tensors["k"].shape),
            "stock_ms": stock_ms, "candidate_ms": candidate_ms,
            "stock_median_ms": statistics.median(stock_ms), "candidate_median_ms": statistics.median(candidate_ms),
            "output_max_abs": float(output_error.max()), "downstream_o_proj_max_abs": float(downstream_error.max()),
            "correct": bool(torch.isfinite(output_error).all() and torch.isfinite(downstream_error).all() and downstream_error.max() <= 0.25),
        }
        rows.append(row)
        atomic(output.with_name(f"COMPONENT_LEDGER_{family}.json"), {"expected_families": ["local", "global"], "completed_row": row})
    complete = len(rows) == 2 and {row["family"] for row in rows} == {"local", "global"} and all(row["correct"] for row in rows)
    atomic(output, {
        "classification": "interpretable_component_result" if complete else "candidate_correctness_failed",
        "science_consumed": True, "cuda_invocation_started": True, "producer_stage_completed": True,
        "manifest_sha256": sha256(manifest_bytes), "candidate_source_sha256": sha256(args.source.read_bytes()),
        "ledger_required_families": ["local", "global"], "ledger_complete": complete, "rows": rows,
        "science_started_marker": "science_started.json", "science_started": True,
    })
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
