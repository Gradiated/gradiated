#!/usr/bin/env python3
import argparse
import contextlib
import hashlib
import inspect
import json
import math
import time
import warnings
from pathlib import Path

import torch
import torch.nn.functional as F
import torch.nn.attention as attention_module
from torch.nn.attention import SDPBackend, sdpa_kernel


CASES = (("local_decode", 1024, 16, 256, 50), ("global_decode_peak", 4571, 4, 512, 10))
M = 12
QH = 32
OUTPUT_TOKENS = 512
BASELINE_ATTENTION_S = 2.6481594640016555
MAX_ATTENTION_S = 2.2842315983022874
MIXED_RESULT_SHA256 = "02b833cdaa6878816b350ca7cae6982e203fb91a98bdabde2e604d91f66d624a"
BACKENDS = (
    ("default", None),
    ("flash", SDPBackend.FLASH_ATTENTION),
    ("efficient", SDPBackend.EFFICIENT_ATTENTION),
    ("cudnn", SDPBackend.CUDNN_ATTENTION),
    ("math", SDPBackend.MATH),
)


def atomic(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def metrics(actual, reference):
    a, r = actual.float(), reference.float()
    diff = a - r
    return {
        "finite": bool(torch.isfinite(a).all()),
        "normalized_rmse": float(torch.sqrt(torch.mean(diff * diff)) / torch.sqrt(torch.mean(r * r))),
        "cosine_similarity": float(F.cosine_similarity(a.flatten(), r.flatten(), dim=0)),
    }


def profile_kernel(call):
    with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA]) as prof:
        call()
        torch.cuda.synchronize()
    return sorted({event.key for event in prof.key_averages() if "scaled_dot" in event.key or "attention" in event.key})


def run_route(query, key, value, backend, repeated):
    if repeated:
        repeats = QH // key.shape[1]
        key = key.repeat_interleave(repeats, dim=1)
        value = value.repeat_interleave(repeats, dim=1)
    call = lambda: F.scaled_dot_product_attention(query, key, value, enable_gqa=not repeated)
    manager = contextlib.nullcontext() if backend is None else sdpa_kernel(backend)
    caught = []
    try:
        with warnings.catch_warnings(record=True) as ws, manager:
            warnings.simplefilter("always")
            for _ in range(2):
                output = call()
            torch.cuda.synchronize()
            starts, ends = [], []
            for _ in range(7):
                start, end = torch.cuda.Event(True), torch.cuda.Event(True)
                start.record(); output = call(); end.record()
                starts.append(start); ends.append(end)
            torch.cuda.synchronize()
            samples = sorted(float(s.elapsed_time(e)) for s, e in zip(starts, ends))
            kernels = profile_kernel(call)
            caught = [str(w.message) for w in ws]
        return {"status": "supported", "p50_ms": samples[len(samples)//2], "raw_ms": samples,
                "warnings": caught, "selected_kernel_evidence": kernels, "output": output}
    except Exception as exc:
        return {"status": "unsupported", "error_type": type(exc).__name__, "error": str(exc)[:2000],
                "warnings": caught}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    source_file = attention_module.__file__
    source_bytes = Path(source_file).read_bytes()
    result = {
        "schema_version": 1,
        "type": "gemma4_h200_exact_shape_sdpa_backend_discriminator",
        "identity": {"torch": torch.__version__, "cuda": torch.version.cuda,
                     "gpu": torch.cuda.get_device_name(), "capability": list(torch.cuda.get_device_capability())},
        "frozen_shapes": {"m": M, "query_heads": QH, "cases": CASES},
        "source_evidence": {"sdpa_kernel_file": source_file, "sha256": hashlib.sha256(source_bytes).hexdigest(),
                            "sdpa_kernel_source": inspect.getsource(sdpa_kernel)},
        "layout_equivalence_basis": "repeat_interleave each KV head QH/KVH times is the explicit GQA definition used by the frozen numerical reference",
        "mixed_result_sha256": MIXED_RESULT_SHA256,
        "rows": [],
    }
    best = {}
    for case, context, kvh, dim, multiplicity in CASES:
        torch.manual_seed(20260718 + context + dim)
        q = torch.randn((M, QH, 1, dim), device="cuda", dtype=torch.bfloat16) / math.sqrt(dim)
        k = torch.randn((M, kvh, context, dim), device="cuda", dtype=torch.bfloat16) / math.sqrt(dim)
        v = torch.randn((M, kvh, context, dim), device="cuda", dtype=torch.bfloat16) / math.sqrt(dim)
        reference = F.scaled_dot_product_attention(q, k.repeat_interleave(QH // kvh, 1),
                                                   v.repeat_interleave(QH // kvh, 1), enable_gqa=False)
        passing = []
        for layout in ("native_gqa", "repeated_kv"):
            for name, backend in BACKENDS:
                route = run_route(q, k, v, backend, layout == "repeated_kv")
                row = {"case": case, "context": context, "kv_heads": kvh, "head_dim": dim,
                       "multiplicity": multiplicity, "layout": layout, "backend": name, **route}
                output = row.pop("output", None)
                if output is not None:
                    row["oracle"] = metrics(output, reference)
                    row["pass"] = bool(row["oracle"]["finite"] and row["oracle"]["normalized_rmse"] <= 0.02
                                       and row["oracle"]["cosine_similarity"] >= 0.999)
                    if row["pass"]:
                        passing.append(row)
                else:
                    row["pass"] = False
                result["rows"].append(row)
                atomic(args.output, result)
        best[case] = min(passing, key=lambda row: row["p50_ms"])
        del q, k, v, reference
        torch.cuda.empty_cache()
    weighted_ms = sum(best[case]["multiplicity"] * best[case]["p50_ms"] for case, *_ in CASES)
    attention_s = weighted_ms * (OUTPUT_TOKENS / M / 1000)
    old_non_attention_candidate_s = 3.1796844858846938 - BASELINE_ATTENTION_S
    old_control_s = 3.5196957752316567
    candidate_s = old_non_attention_candidate_s + attention_s
    margin = 1.0 - candidate_s / old_control_s
    result["best_passing_rows"] = best
    result["decision"] = {"weighted_attention_seconds_per_request": attention_s,
                          "maximum_weighted_attention_seconds_per_request": MAX_ATTENTION_S,
                          "attention_reduction": 1.0 - attention_s / BASELINE_ATTENTION_S,
                          "combined_component_seconds_per_request": candidate_s,
                          "combined_margin_vs_frozen_all_bf16": margin,
                          "target_margin": 0.20,
                          "target_met": bool(attention_s <= MAX_ATTENTION_S and margin >= 0.20),
                          "component_proxy_nominee": "H200 E4M3 compute/BF16 state + selected SDPA routes" if attention_s <= MAX_ATTENTION_S and margin >= 0.20 else None,
                          "endpoint_nominee": None}
    result["scientific_wall_seconds"] = time.perf_counter() - started
    result["pass"] = True
    atomic(args.output, result)


if __name__ == "__main__":
    main()
