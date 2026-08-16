#!/usr/bin/env python3
import argparse
import hashlib
import inspect
import json
import math
import os
import statistics
import subprocess
import time
import traceback
from pathlib import Path

import torch
from sglang.srt.layers.attention.triton_ops.decode_attention import decode_attention_fwd

QH, KVH, CURRENT, CANDIDATE, LAYERS, BATCH, CONTEXT, TOKENS = 32, 4, 512, 256, 10, 32, 4571, 358
PAGE, SPLITS, SEED = 1, 8, 41
FROZEN_SAVING = 0.08169989766753512
MINIMUM = 0.04597286970625021
CANONICAL = 0.9194573941250042


def atomic(path, value):
    part = path.with_suffix(path.suffix + ".part")
    with part.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(part, path)


def timing(call, warmup=3, repeats=11):
    for _ in range(warmup):
        call()
    torch.cuda.synchronize()
    values = []
    for _ in range(repeats):
        start, end = torch.cuda.Event(True), torch.cuda.Event(True)
        start.record(); call(); end.record(); end.synchronize()
        values.append(float(start.elapsed_time(end)))
    return statistics.median(values), values


def output_state(tensor):
    view = tensor.float()
    return {"finite": bool(torch.isfinite(view).all()), "nonzero": bool(view.abs().max() > 1e-6), "checksum": float(view[:8].sum())}


def cache(dim):
    torch.manual_seed(SEED + dim)
    total = BATCH * CONTEXT
    key = (torch.randn((total, KVH, dim), device="cuda", dtype=torch.bfloat16) * .02).to(torch.float8_e5m2)
    value = (torch.randn((total, KVH, dim), device="cuda", dtype=torch.bfloat16) * .02).to(torch.float8_e5m2)
    indptr = torch.arange(BATCH + 1, device="cuda", dtype=torch.int32) * CONTEXT
    indices = torch.arange(total, device="cuda", dtype=torch.int64)
    return key, value, indptr, indices


def oracle(query, key, value, observed, dim):
    heads = torch.arange(QH, device="cuda") // (QH // KVH)
    key0, value0 = key[:CONTEXT].float(), value[:CONTEXT].float()
    scores = torch.einsum("hd,thd->ht", query[0].float(), key0[:, heads]) * dim ** -.5
    reference = torch.einsum("ht,thd->hd", torch.softmax(scores, -1), value0[:, heads])
    got = observed[0].float()
    cosine = float(torch.nn.functional.cosine_similarity(got.flatten(), reference.flatten(), dim=0))
    nrmse = float(torch.linalg.vector_norm(got - reference) / torch.linalg.vector_norm(reference).clamp_min(1e-12))
    return {"reference": "straightforward native-GQA softmax over dequantized E5M2 token-pool cache", "finite": bool(torch.isfinite(got).all()), "cosine_similarity": cosine, "normalized_rmse": nrmse, "pass": bool(cosine >= .99 and nrmse <= .05)}


def decode(dim, require_oracle=False):
    key, value, indptr, indices = cache(dim)
    torch.manual_seed(SEED + 1000 + dim)
    query = torch.randn((BATCH, QH, dim), device="cuda", dtype=torch.bfloat16) * .02
    out = torch.empty_like(query)
    logits = torch.empty((BATCH, QH, SPLITS, dim), device="cuda", dtype=torch.float32)
    lse = torch.empty((BATCH, QH, SPLITS), device="cuda", dtype=torch.float32)
    splits = torch.full((BATCH,), SPLITS, device="cuda", dtype=torch.int32)
    def call():
        decode_attention_fwd(query, key, value, out, indptr, indices, logits, lse, splits, SPLITS, dim ** -.5, 1., 1.)
    call(); torch.cuda.synchronize(); first = out.clone()
    call(); torch.cuda.synchronize()
    p50, raw = timing(call)
    row = {"component": "decode_attention_triton", "head_dim": dim, "query_shape": list(query.shape), "kv_shape": list(key.shape), "context": CONTEXT, "page_size": PAGE, "layout": "native_gqa_linear_token_pool", "kv_dtype": str(key.dtype), "kv_repeated": False, "num_kv_splits": SPLITS, "p50_ms": p50, "raw_ms": raw, "output": output_state(out), "deterministic_max_abs": float((out.float()-first.float()).abs().max())}
    if require_oracle:
        row["oracle"] = oracle(query, key, value, out, dim)
    return row


def writes(dim):
    rows = []
    for name, count in (("kv_write_prompt_chunk", 2048), ("kv_write_decode_step", BATCH)):
        torch.manual_seed(SEED + 2000 + dim + count)
        src_k = torch.randn((count, KVH, dim), device="cuda", dtype=torch.bfloat16) * .02
        src_v = torch.randn((count, KVH, dim), device="cuda", dtype=torch.bfloat16) * .02
        pages = math.ceil(count / PAGE)
        dst_k = torch.empty((pages, PAGE, KVH, dim), device="cuda", dtype=torch.float8_e5m2)
        dst_v = torch.empty_like(dst_k)
        flat_k, flat_v = dst_k.view(-1, KVH, dim)[:count], dst_v.view(-1, KVH, dim)[:count]
        def call(): flat_k.copy_(src_k); flat_v.copy_(src_v)
        p50, raw = timing(call)
        rows.append({"component": name, "head_dim": dim, "tokens": count, "page_size": PAGE, "kv_heads": KVH, "source_dtype": str(src_k.dtype), "cache_dtype": str(dst_k.dtype), "p50_ms": p50, "raw_ms": raw, "output": output_state(flat_k)})
    return rows


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True); started = time.time()
    result = {"schema_version": 1, "status": "running", "stage": "initializing", "pass": False, "rows": []}; atomic(args.output / "RESULT.json", result)
    try:
        if torch.cuda.get_device_capability() != (9, 0) or "H200" not in torch.cuda.get_device_name(): raise RuntimeError("exact NVIDIA H200 SM90 target is required")
        result["identity"] = {"gpu": torch.cuda.get_device_name(), "capability": list(torch.cuda.get_device_capability()), "torch": torch.__version__, "cuda": torch.version.cuda, "container_image": "docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a", "decode_symbol": {"symbol": "sglang.srt.layers.attention.triton_ops.decode_attention.decode_attention_fwd", "source_file": inspect.getsourcefile(decode_attention_fwd), "source_sha256": hashlib.sha256(inspect.getsource(decode_attention_fwd).encode()).hexdigest()}, "nvidia_smi": subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True).stdout.strip()}
        for stage, call in (("current_triton_decode", lambda: [decode(CURRENT)]), ("candidate_triton_decode_oracle", lambda: [decode(CANDIDATE, True)]), ("current_kv_writes", lambda: writes(CURRENT)), ("candidate_kv_writes", lambda: writes(CANDIDATE))):
            result["stage"] = stage; atomic(args.output / "RESULT.json", result); result["rows"].extend(call()); atomic(args.output / "RESULT.json", result)
        by = {(r["head_dim"], r["component"]): r for r in result["rows"]}
        weights = {"decode_attention_triton": LAYERS * TOKENS / BATCH, "kv_write_prompt_chunk": LAYERS * (BATCH * 4214 * (1-.127) / 2048) / BATCH, "kv_write_decode_step": LAYERS * TOKENS / BATCH}
        completion = []
        for name, weight in weights.items():
            current = by[(CURRENT, name)]["p50_ms"] / 1000 * weight; candidate = by[(CANDIDATE, name)]["p50_ms"] / 1000 * weight
            completion.append({"component": name, "weight": weight, "current_seconds_per_request": current, "candidate_seconds_per_request": candidate})
        current_completion, candidate_completion = sum(x["current_seconds_per_request"] for x in completion), sum(x["candidate_seconds_per_request"] for x in completion)
        candidate = by[(CANDIDATE, "decode_attention_triton")]
        gates = {"candidate_kernel_supported": True, "candidate_kernel_avoids_dense_kv_repetition": not candidate["kv_repeated"], "candidate_oracle_pass": candidate["oracle"]["pass"], "all_outputs_finite_nonzero": all(r["output"]["finite"] and r["output"]["nonzero"] for r in result["rows"])}
        saving = FROZEN_SAVING + current_completion - candidate_completion
        passed = bool(all(gates.values()) and candidate["deterministic_max_abs"] == 0 and saving >= MINIMUM)
        result.update({"status": "terminal", "pass": passed, "classification": "nominate_architecture_proxy" if passed else "close_architecture_proxy", "quality_claim": False, "geometry": {"query_heads": QH, "kv_heads": KVH, "current_global_head_dim": CURRENT, "candidate_global_head_dim": CANDIDATE, "global_layers": LAYERS, "concurrency": BATCH, "peak_global_context": CONTEXT, "output_tokens_per_request": TOKENS, "kv_dtype": "fp8_e5m2", "decode_backend": "triton", "triton_kv_splits": SPLITS, "page_size": PAGE}, "frozen_partial": {"saving_seconds_per_request": FROZEN_SAVING, "result_sha256": "5926b98497dd86636aefe3d7385b1ec7ea50e61278c4e33c8eb563b1b828ed85"}, "completion": {"components": completion, "current_seconds_per_request": current_completion, "candidate_seconds_per_request": candidate_completion}, "complete_saving_seconds_per_request": saving, "fraction_of_canonical_service_saved": saving / CANONICAL, "minimum_complete_saving_seconds_per_request": MINIMUM, "hard_gates": gates, "candidate_kernel": {"requested_backend": "triton", "symbol": result["identity"]["decode_symbol"]["symbol"], "dense_kv_repetition": False, "oracle": candidate["oracle"], "supported": True}, "stage": "complete", "elapsed_seconds": time.time() - started})
    except Exception as error:
        result.update({"status": "terminal", "classification": "execution_failure", "error": {"type": type(error).__name__, "message": str(error)}, "traceback": traceback.format_exc(), "elapsed_seconds": time.time()-started})
    atomic(args.output / "RESULT.json", result)
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
