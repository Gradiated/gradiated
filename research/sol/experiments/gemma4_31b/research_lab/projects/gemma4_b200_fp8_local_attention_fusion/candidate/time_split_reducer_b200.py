#!/usr/bin/env python3
import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import torch

from check_split_reducer_correctness_b200 import (
    BATCH, SM_SCALE, WINDOW_LEFT, atomic_json, build_geometry, compare, verify_identity,
)
from local_paged_gqa_split_reducer_fused import make_wrapper, plan_exact, run_exact

WARMUPS = 8
SAMPLES = 40
CALLS_PER_REQUEST = 17900

def percentiles(xs):
    return {k: float(np.percentile(xs, q)) for k, q in (("p10_ms", 10), ("p50_ms", 50), ("p90_ms", 90))}

def bootstrap_lower(deltas):
    rng = np.random.default_rng(20260728)
    values = np.asarray(deltas, dtype=np.float64)
    medians = np.median(rng.choice(values, size=(4096, len(values)), replace=True), axis=1)
    return float(np.percentile(medians, 2.5))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    started = time.time()
    marker = args.artifact_root / "timing_science_started"
    try:
        if not torch.cuda.is_available() or torch.cuda.get_device_properties(0).major != 10:
            raise RuntimeError("typed_external_blocker: expected CUDA SM100")
        identity = verify_identity(args.project_root)
        geometry = build_geometry(torch.device("cuda:0"), 20260728)
        workspace = torch.zeros(128 * 1024 * 1024, dtype=torch.uint8, device="cuda")
        wrapper = make_wrapper(args.project_root, workspace)
        plan = plan_exact(wrapper, geometry["window_indptr"], geometry["window_indices"], geometry["last_page_len"])
        if not (plan["split_kv"] and plan["padded_batch_size"] == 64):
            raise RuntimeError("exact split plan guard failed")
        import vllm._custom_ops
        from flashinfer.decode import trtllm_batch_decode_with_kv_cache
        q, key, value = geometry["q"], geometry["append_key"], geometry["append_value"]
        initial = geometry["initial_cache"]
        stock_cache, candidate_cache = initial.clone(), initial.clone()
        stock_workspace = torch.zeros(128 * 1024 * 1024, dtype=torch.uint8, device="cuda")
        scale = torch.ones(1, dtype=torch.float32, device="cuda")
        def reset():
            stock_cache.copy_(initial); candidate_cache.copy_(initial)
        def stock():
            k = stock_cache[:, 0].transpose(1, 2); v = stock_cache[:, 1].transpose(1, 2)
            torch.ops._C_cache_ops.reshape_and_cache_flash(key, value, k, v, geometry["slot_mapping"], "auto", scale, scale)
            return trtllm_batch_decode_with_kv_cache(query=q, kv_cache=stock_cache, workspace_buffer=stock_workspace, block_tables=geometry["block_tables"], seq_lens=geometry["seq_lens"], max_seq_len=max(geometry["seq_lens_list"]), bmm1_scale=SM_SCALE, bmm2_scale=1.0, window_left=WINDOW_LEFT, kv_layout="HND", enable_pdl=False, backend="trtllm-gen", q_len_per_req=1)
        def candidate():
            return run_exact(wrapper, q, candidate_cache, key, value, geometry["slot_mapping"])
        for _ in range(WARMUPS):
            reset(); stock(); torch.cuda.synchronize(); reset(); candidate(); torch.cuda.synchronize()
        marker.parent.mkdir(parents=True, exist_ok=True); marker.write_text("timing_science_started=true\n")
        stock_ms, candidate_ms, deltas = [], [], []
        last_stock = last_candidate = None
        for i in range(SAMPLES):
            order = (stock, candidate) if i % 2 == 0 else (candidate, stock)
            pair = []
            for arm in order:
                reset(); begin, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                begin.record(); out = arm(); end.record(); torch.cuda.synchronize()
                pair.append((arm.__name__, float(begin.elapsed_time(end)), out, stock_cache.clone() if arm is stock else candidate_cache.clone()))
            by_name = {name: (ms, out, cache) for name, ms, out, cache in pair}
            stock_ms.append(by_name["stock"][0]); candidate_ms.append(by_name["candidate"][0]); deltas.append(by_name["stock"][0] - by_name["candidate"][0])
            last_stock, stock_final = by_name["stock"][1], by_name["stock"][2]
            last_candidate, candidate_final = by_name["candidate"][1], by_name["candidate"][2]
        metrics = compare(last_stock, last_candidate)
        cache_equal = bool(torch.equal(stock_final, candidate_final))
        lower = bootstrap_lower(deltas)
        positive = bool(metrics["pass"] and cache_equal and lower > 0.0)
        terminal = {"schema_version":1,"terminal":"positive" if positive else "negative","interpretable_result":True,"scientific_sample_consumed":True,"warmups_per_arm":WARMUPS,"samples_per_arm":SAMPLES,"sample_order":"20 stock-first and 20 candidate-first","identity":identity,"split_plan":plan,"correctness":{"output":metrics,"cache_bitwise_equal":cache_equal,"owners_per_request":16,"fresh_merges_per_q_head":1},"timing":{"stock":percentiles(stock_ms),"candidate":percentiles(candidate_ms),"paired_delta_ms":percentiles(deltas),"paired_delta_samples_ms":deltas,"bootstrap_95_lower_ms":lower,"projected_seconds_saved_per_request":float(np.median(deltas)*CALLS_PER_REQUEST/1000)},"elapsed_seconds":time.time()-started}
        atomic_json(args.artifact_root / "TIMING_TERMINAL.json", terminal)
        return 0
    except Exception as e:
        atomic_json(args.artifact_root / "TIMING_TERMINAL.json", {"schema_version":1,"terminal":"invalid_attempt","interpretable_result":False,"scientific_sample_consumed":False,"error_type":type(e).__name__,"error":str(e),"elapsed_seconds":time.time()-started})
        return 1
if __name__ == "__main__":
    raise SystemExit(main())
