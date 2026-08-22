from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import statistics
from pathlib import Path
from types import SimpleNamespace


STOCK_GEMMA4_SHA256 = "e16b28577c7cdca4876d26636564ed411fc7ce4a25b724456ee906d8129eed20"
MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_checkpoint_tensors(checkpoint: Path, suffixes: list[str]) -> dict[str, object]:
    from safetensors import safe_open

    index_path = checkpoint / "model.safetensors.index.json"
    if index_path.exists():
        with index_path.open() as handle:
            weight_map = json.load(handle)["weight_map"]
        matches = {}
        for suffix in suffixes:
            names = [name for name in weight_map if name == "model.language_model." + suffix]
            if len(names) != 1:
                raise ValueError(f"{suffix}: expected one tensor, found {names}")
            matches[suffix] = (names[0], checkpoint / weight_map[names[0]])
    else:
        matches = {}
        for shard in sorted(checkpoint.glob("*.safetensors")):
            with safe_open(shard, framework="pt", device="cpu") as handle:
                keys = list(handle.keys())
            for suffix in suffixes:
                names = [name for name in keys if name == "model.language_model." + suffix]
                if names:
                    if suffix in matches or len(names) != 1:
                        raise ValueError(f"{suffix}: checkpoint tensor is ambiguous")
                    matches[suffix] = (names[0], shard)
        missing = set(suffixes) - set(matches)
        if missing:
            raise ValueError(f"missing checkpoint tensors: {sorted(missing)}")

    tensors = {}
    by_shard: dict[Path, list[tuple[str, str]]] = {}
    for suffix, (name, shard) in matches.items():
        by_shard.setdefault(shard, []).append((suffix, name))
    for shard, requested in by_shard.items():
        with safe_open(shard, framework="pt", device="cpu") as handle:
            for suffix, name in requested:
                tensors[suffix] = handle.get_tensor(name)
    return tensors


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def tensor_metrics(reference, candidate) -> dict:
    import torch

    ref = reference.float()
    cand = candidate.float()
    diff = cand - ref
    denom = torch.linalg.vector_norm(ref).clamp_min(1e-12)
    return {
        "finite": bool(torch.isfinite(cand).all().item()),
        "max_abs": float(diff.abs().max().item()),
        "relative_l2": float((torch.linalg.vector_norm(diff) / denom).item()),
        "cosine": float(
            torch.nn.functional.cosine_similarity(
                ref.flatten(), cand.flatten(), dim=0, eps=1e-12
            ).item()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--hidden", type=Path, required=True)
    parser.add_argument("--hidden-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--layer", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=8)
    parser.add_argument("--repetitions", type=int, default=40)
    args = parser.parse_args()

    import torch
    from vllm import _custom_ops as ops
    from transformers import AutoConfig
    from transformers.models.gemma4.modeling_gemma4 import (
        Gemma4TextRotaryEmbedding,
        apply_rotary_pos_emb,
    )
    from vllm.model_executor.models.gemma4 import Gemma4Attention
    from flashinfer import BatchDecodeWithPagedKVCacheWrapper

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    device_name = torch.cuda.get_device_name(0)
    capability = torch.cuda.get_device_capability(0)
    if "B200" not in device_name.upper() or capability[0] != 10:
        raise RuntimeError(f"expected B200 SM100, observed {device_name} {capability}")
    if sha256(args.hidden) != args.hidden_sha256:
        raise ValueError("hidden input digest mismatch")
    installed_source = Path(inspect.getsourcefile(Gemma4Attention) or "")
    if sha256(installed_source) != STOCK_GEMMA4_SHA256:
        raise ValueError("installed Gemma4 source does not match the pinned runtime")
    if args.layer not in range(5, 60, 6):
        raise ValueError("component layer must be one of the ten global layers")

    hidden_payload = torch.load(args.hidden, map_location="cpu", weights_only=True)
    hidden = hidden_payload["hidden"] if isinstance(hidden_payload, dict) else hidden_payload
    if tuple(hidden.shape) != (32, 5376) or hidden.dtype != torch.bfloat16:
        raise ValueError(f"expected BF16 [32,5376] hidden input, got {hidden.shape} {hidden.dtype}")
    hidden = hidden.contiguous().cuda()

    prefix = f"layers.{args.layer}.self_attn."
    suffixes = [
        prefix + "q_proj.weight",
        prefix + "k_proj.weight",
        prefix + "q_norm.weight",
        prefix + "k_norm.weight",
    ]
    tensors = load_checkpoint_tensors(args.checkpoint, suffixes)
    q_weight = tensors[suffixes[0]].to(device="cuda", dtype=torch.bfloat16)
    k_weight = tensors[suffixes[1]].to(device="cuda", dtype=torch.bfloat16)
    q_norm_weight = tensors[suffixes[2]].to(device="cuda", dtype=torch.bfloat16)
    k_norm_weight = tensors[suffixes[3]].to(device="cuda", dtype=torch.bfloat16)
    if tuple(q_weight.shape) != (16384, 5376):
        raise ValueError(f"unexpected q_proj shape {q_weight.shape}")
    if tuple(k_weight.shape) != (2048, 5376):
        raise ValueError(f"unexpected k_proj shape {k_weight.shape}")

    stock_weight = torch.cat((q_weight, k_weight, k_weight), dim=0)
    candidate_weight = torch.cat((q_weight, k_weight), dim=0)
    stock_weight_q, stock_weight_scale = ops.scaled_fp8_quant(stock_weight, scale=None)
    candidate_weight_q, candidate_weight_scale = ops.scaled_fp8_quant(
        candidate_weight, scale=None
    )
    if not torch.equal(stock_weight_q[:18432], candidate_weight_q):
        raise ValueError("retained candidate FP8 weight bytes differ from stock")
    if not torch.equal(stock_weight_scale, candidate_weight_scale):
        raise ValueError("stock and candidate FP8 weight scales differ")
    stock_weight_q = stock_weight_q.t()
    candidate_weight_q = candidate_weight_q.t()
    hidden_q, hidden_scale = ops.scaled_fp8_quant(hidden, scale=None)

    def stock_projection():
        return ops.cutlass_scaled_mm(
            hidden_q,
            stock_weight_q,
            scale_a=hidden_scale,
            scale_b=stock_weight_scale,
            out_dtype=torch.bfloat16,
        )

    def candidate_projection():
        return ops.cutlass_scaled_mm(
            hidden_q,
            candidate_weight_q,
            scale_a=hidden_scale,
            scale_b=candidate_weight_scale,
            out_dtype=torch.bfloat16,
        )

    stock_first = stock_projection()
    torch.cuda.synchronize()
    candidate_first = candidate_projection()
    torch.cuda.synchronize()

    stock_q, stock_k, stock_v = stock_first.split((16384, 2048, 2048), dim=-1)
    candidate_q, candidate_k = candidate_first.split((16384, 2048), dim=-1)
    candidate_v = candidate_k
    raw_metrics = {
        "q": tensor_metrics(stock_q, candidate_q),
        "k": tensor_metrics(stock_k, candidate_k),
        "stock_k_equals_stock_v_bitwise": bool(torch.equal(stock_k, stock_v)),
        "candidate_k_aliases_v": candidate_k.data_ptr() == candidate_v.data_ptr(),
    }

    def normalize_and_rotate(q, k, v):
        q = q.view(32, 32, 512)
        k = k.view(32, 4, 512)
        v = v.view(32, 4, 512)
        q = torch.nn.functional.rms_norm(q, (512,), q_norm_weight, 1e-6)
        k = torch.nn.functional.rms_norm(k, (512,), k_norm_weight, 1e-6)
        v = torch.nn.functional.rms_norm(v, (512,), None, 1e-6)
        positions = torch.full((1, 32), 4213, dtype=torch.int64, device="cuda")
        config = AutoConfig.from_pretrained(args.checkpoint, local_files_only=True).text_config
        rope = Gemma4TextRotaryEmbedding(config, device="cuda", layer_type="full_attention")
        q = q.transpose(0, 1).unsqueeze(0)
        k = k.transpose(0, 1).unsqueeze(0)
        cos, sin = rope(q, positions, layer_type="full_attention")
        q = apply_rotary_pos_emb(q, cos, sin, unsqueeze_dim=1).squeeze(0).transpose(0, 1)
        k = apply_rotary_pos_emb(k, cos, sin, unsqueeze_dim=1).squeeze(0).transpose(0, 1)
        return q, k, v.view(32, 4, 512)

    stock_qn, stock_kn, stock_vn = normalize_and_rotate(stock_q, stock_k, stock_v)
    candidate_qn, candidate_kn, candidate_vn = normalize_and_rotate(
        candidate_q, candidate_k, candidate_v
    )
    normalized_metrics = {
        "q": tensor_metrics(stock_qn, candidate_qn),
        "k": tensor_metrics(stock_kn, candidate_kn),
        "v": tensor_metrics(stock_vn, candidate_vn),
    }

    block_size = 32
    seq_len = 4214
    blocks_per_request = math.ceil(seq_len / block_size)
    num_blocks = 32 * blocks_per_request
    block_table = torch.arange(
        num_blocks, dtype=torch.int32, device="cuda"
    ).view(32, blocks_per_request)
    slot_mapping = (
        block_table[:, -1].to(torch.int64) * block_size + (seq_len - 1) % block_size
    )
    indptr = torch.arange(0, num_blocks + 1, blocks_per_request, dtype=torch.int32)
    last_page_len = torch.full((32,), block_size, dtype=torch.int32)
    workspace = torch.empty(128 * 1024 * 1024, dtype=torch.uint8, device="cuda")
    wrapper = BatchDecodeWithPagedKVCacheWrapper(workspace, "NHD")
    wrapper.plan(indptr, block_table.flatten(), last_page_len, 32, 4, 512, block_size,
                 q_data_type=torch.bfloat16, kv_data_type=torch.bfloat16, sm_scale=1.0)
    def first_consumer(q, k, v):
        cache = torch.zeros((num_blocks, 2, block_size, 4, 512), dtype=torch.bfloat16, device="cuda")
        cache[block_table[:, -1], 0, block_size - 1] = k
        cache[block_table[:, -1], 1, block_size - 1] = v
        result = wrapper.run(q, cache)
        torch.cuda.synchronize()
        return result
    stock_attn = first_consumer(stock_qn, stock_kn, stock_vn)
    candidate_attn = first_consumer(candidate_qn, candidate_kn, candidate_vn)
    attention_metrics = tensor_metrics(stock_attn, candidate_attn)

    def time_paired() -> tuple[list[float], list[float]]:
        for _ in range(args.warmups):
            stock_projection()
            candidate_projection()
        torch.cuda.synchronize()
        timings = {"stock": [], "candidate": []}
        arms = {"stock": stock_projection, "candidate": candidate_projection}
        for repetition in range(args.repetitions):
            order = ("stock", "candidate") if repetition % 2 == 0 else (
                "candidate",
                "stock",
            )
            for name in order:
                start = torch.cuda.Event(enable_timing=True)
                end = torch.cuda.Event(enable_timing=True)
                start.record()
                output = arms[name]()
                end.record()
                end.synchronize()
                timings[name].append(start.elapsed_time(end) * 1000.0)
                if not torch.isfinite(output).all():
                    raise ValueError("nonfinite timed output")
        return timings["stock"], timings["candidate"]

    stock_us, candidate_us = time_paired()
    final_stock = stock_projection()
    final_candidate = candidate_projection()
    torch.cuda.synchronize()
    final_metrics = {
        "qk": tensor_metrics(final_stock[:, :18432], final_candidate),
        "stock_checksum": float(final_stock.float().sum().item()),
        "candidate_checksum": float(final_candidate.float().sum().item()),
    }

    payload = {
        "schema_version": 1,
        "classification": "b200_exact_global_k_eq_v_component",
        "identity": {
            "model_revision": MODEL_REVISION,
            "installed_gemma4_sha256": sha256(installed_source),
            "checkpoint": str(args.checkpoint),
            "hidden_path": str(args.hidden),
            "hidden_sha256": args.hidden_sha256,
            "device_name": device_name,
            "capability": list(capability),
            "layer": args.layer,
        },
        "science_started": True,
        "geometry": {
            "m": 32,
            "k": 5376,
            "stock_n": 20480,
            "candidate_n": 18432,
            "q_heads": 32,
            "kv_heads": 4,
            "head_dim": 512,
            "sequence_length": seq_len,
            "block_size": block_size,
            "kv_cache_layout": "HND backing exposed through logical [2,B,N,H,D] view",
        },
        "correctness": {
            "raw_projection": raw_metrics,
            "normalized_and_rotary": normalized_metrics,
            "flash_attention_first_consumer": attention_metrics,
            "final_projection": final_metrics,
        },
        "timing_us": {
            "stock": {
                "samples": stock_us,
                "p50": statistics.median(stock_us),
                "p90": percentile(stock_us, 0.9),
            },
            "candidate": {
                "samples": candidate_us,
                "p50": statistics.median(candidate_us),
                "p90": percentile(candidate_us, 0.9),
            },
            "p50_delta": statistics.median(stock_us)
            - statistics.median(candidate_us),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with temporary.open() as handle:
        json.load(handle)
    temporary.replace(args.output)
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output)}))


if __name__ == "__main__":
    main()
