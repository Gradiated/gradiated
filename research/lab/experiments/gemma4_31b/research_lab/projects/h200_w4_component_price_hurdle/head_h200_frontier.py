#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import statistics
import time
import types
from pathlib import Path

import torch
import vllm
from vllm.config import VllmConfig, set_current_vllm_config
from vllm.distributed.parallel_state import destroy_distributed_environment, destroy_model_parallel, ensure_model_parallel_initialized, init_distributed_environment
from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead


MS = (96, 128)
HIDDEN, VOCAB, STEPS = 5376, 262144, 358


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def timing(call):
    for _ in range(3):
        call()
    torch.cuda.synchronize()
    events, walls, output = [], [], None
    for _ in range(5):
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        start.record(); wall = time.perf_counter(); output = call(); end.record(); end.synchronize()
        events.append(start.elapsed_time(end)); walls.append((time.perf_counter() - wall) * 1000)
    return {"iterations": 5, "cuda_event": {"raw_ms": events, "p50_ms": statistics.median(events)}, "synchronized_wall": {"raw_ms": walls, "p50_ms": statistics.median(walls)}}, output


def main() -> int:
    target = argparse.ArgumentParser(); target.add_argument("--output", type=Path, required=True); output = target.parse_args().output
    result: dict[str, object] = {"schema_version": 1, "type": "actual_h200_bf16_parallel_lm_head_component_frontier", "stage": "conditional", "concurrency": list(MS), "rows": [], "pass": False}
    try:
        torch.manual_seed(20260718)
        config = VllmConfig(); config.model_config = types.SimpleNamespace(dtype=torch.bfloat16, head_dtype=None, is_moe=False)
        with set_current_vllm_config(config):
            init_distributed_environment(world_size=1, rank=0, distributed_init_method="tcp://127.0.0.1:29501", local_rank=0, backend="nccl")
            ensure_model_parallel_initialized(1, 1)
            with torch.device("cuda"):
                head = ParallelLMHead(VOCAB, HIDDEN, params_dtype=torch.bfloat16, prefix="model.lm_head")
            head.weight.data.normal_(0, 0.01)
            result["identity"] = {"vllm": vllm.__version__, "gpu": torch.cuda.get_device_name(), "capability": list(torch.cuda.get_device_capability()), "consumer": f"{type(head).__module__}.{type(head).__name__}", "consumer_sha256": hashlib.sha256(inspect.getsource(type(head)).encode()).hexdigest()}
            if "H200" not in str(result["identity"]["gpu"]):
                raise RuntimeError(f"expected H200, observed {result['identity']['gpu']}")
            for m in MS:
                x = torch.randn((m, HIDDEN), device="cuda", dtype=torch.bfloat16); torch.cuda.reset_peak_memory_stats()
                measured, output_value = timing(lambda: head.quant_method.apply(head, x, None)); reference = torch.mm(x, head.weight.t())
                delta = output_value.float() - reference.float(); rms = float(torch.sqrt(torch.mean(reference.float() ** 2))); nrmse = float(torch.sqrt(torch.mean(delta ** 2))) / max(rms, 1e-12); cosine = float(torch.nn.functional.cosine_similarity(output_value.float().flatten(), reference.float().flatten(), dim=0))
                passed = bool(torch.isfinite(output_value).all() and float(output_value.float().abs().max()) > 1e-6 and nrmse <= 0.01 and cosine >= 0.999)
                result["rows"].append({"m": m, "timing": measured, "per_request_head_seconds_at_358_steps": measured["cuda_event"]["p50_ms"] / 1000 * STEPS / m, "oracle": {"normalized_rmse": nrmse, "cosine_similarity": cosine, "pass": passed}, "allocator": {"peak_allocated_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_bytes": torch.cuda.max_memory_reserved()}, "pass": passed})
                del x, output_value, reference, delta
            destroy_model_parallel(); destroy_distributed_environment()
        result["pass"] = bool(len(result["rows"]) == len(MS) and all(bool(row["pass"]) for row in result["rows"]))
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:4000]}
    atomic(output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
