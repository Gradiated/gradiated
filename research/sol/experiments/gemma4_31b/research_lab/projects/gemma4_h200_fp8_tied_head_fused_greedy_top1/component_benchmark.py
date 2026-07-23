from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import statistics
import time

import torch
from safetensors import safe_open

from fused_top1 import HIDDEN, VOCAB, fp8_greedy_top1


FP8_MAX = float(torch.finfo(torch.float8_e4m3fn).max)
M_SHAPES = (1, 2, 4, 8, 12, 16, 24, 32)
WEIGHT_KEY = "model.language_model.embed_tokens.weight"


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def distribution(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {
        "repeats": len(values),
        "minimum_ms": ordered[0],
        "p10_ms": ordered[math.floor(0.10 * (len(values) - 1))],
        "median_ms": statistics.median(values),
        "p90_ms": ordered[math.floor(0.90 * (len(values) - 1))],
        "maximum_ms": ordered[-1],
        "mean_ms": statistics.fmean(values),
    }


def timings(function, repeats: int) -> tuple[dict[str, float | int], torch.Tensor]:
    output = None
    for _ in range(8):
        output = function()
    torch.cuda.synchronize()
    values = []
    for _ in range(repeats):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        output = function()
        end.record()
        end.synchronize()
        values.append(float(start.elapsed_time(end)))
    assert output is not None
    return distribution(values), output


def load_weight(checkpoint: pathlib.Path) -> tuple[torch.Tensor, dict[str, object]]:
    index = json.loads((checkpoint / "model.safetensors.index.json").read_text())
    shard = checkpoint / index["weight_map"][WEIGHT_KEY]
    with safe_open(shard, framework="pt", device="cpu") as handle:
        weight_cpu = handle.get_tensor(WEIGHT_KEY)
    if tuple(weight_cpu.shape) != (VOCAB, HIDDEN):
        raise RuntimeError(f"unexpected embedding shape {tuple(weight_cpu.shape)}")
    if weight_cpu.dtype != torch.bfloat16:
        raise RuntimeError(f"unexpected embedding dtype {weight_cpu.dtype}")
    sample_indices = torch.tensor([0, 1, 17, 4095, VOCAB - 1])
    sample_before = weight_cpu.index_select(0, sample_indices).clone()
    weight = weight_cpu.cuda()
    amax = weight.abs().amax().float()
    dequant_scale = (amax / FP8_MAX).clamp(min=torch.finfo(torch.float32).tiny)
    quant_scale = dequant_scale.reciprocal()
    storage = torch.empty(
        (VOCAB, HIDDEN), device="cuda", dtype=torch.float8_e4m3fn
    )
    saturation_count = 0
    nonfinite_count = 0
    for start in range(0, VOCAB, 4096):
        stop = min(start + 4096, VOCAB)
        chunk = weight[start:stop]
        finite = torch.isfinite(chunk)
        nonfinite_count += int((~finite).sum().item())
        scaled = chunk.float().mul_(quant_scale)
        saturation_count += int((scaled.abs() >= FP8_MAX).sum().item())
        storage[start:stop] = (
            scaled.clamp_(min=-FP8_MAX, max=FP8_MAX)
            .to(torch.float8_e4m3fn)
            .contiguous()
        )
    sample_after = weight_cpu.index_select(0, sample_indices)
    if not torch.equal(sample_before, sample_after):
        raise RuntimeError("BF16 embedding changed during E4M3 materialization")
    return storage.T, {
        "checkpoint_shard": shard.name,
        "checkpoint_shard_size": shard.stat().st_size,
        "embedding_dtype": str(weight.dtype),
        "embedding_shape": list(weight.shape),
        "embedding_preserved": True,
        "weight_dtype": str(storage.dtype),
        "weight_shape": list(storage.T.shape),
        "weight_stride": list(storage.T.stride()),
        "weight_scale": float(dequant_scale.item()),
        "weight_scale_granularity": "per_tensor",
        "weight_nonfinite_count": nonfinite_count,
        "weight_saturation_count": saturation_count,
        "weight_saturation_fraction": saturation_count / weight.numel(),
        "weight_scale_tensor": dequant_scale,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=pathlib.Path, required=True)
    parser.add_argument("--hidden", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--repeats", type=int, default=40)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    state_path = args.output / "INVOCATION_STATE.json"
    atomic_json(
        state_path,
        {
            "schema_version": 1,
            "candidate_cuda_started": False,
            "component_science_started": False,
        },
    )

    from sglang.srt.layers.quantization.fp8_utils import (
        apply_fp8_linear,
        scaled_fp8_quant,
    )

    rows = torch.load(args.hidden, map_location="cpu", weights_only=True).cuda()
    if tuple(rows.shape) != (32, HIDDEN) or rows.dtype != torch.bfloat16:
        raise RuntimeError(f"unexpected hidden rows {rows.shape} {rows.dtype}")
    fp8_weight, representation = load_weight(args.checkpoint)
    weight_scale = representation.pop("weight_scale_tensor")
    assert isinstance(weight_scale, torch.Tensor)

    def quantize(sample: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return scaled_fp8_quant(
            sample,
            None,
            num_token_padding=None,
            use_per_token_if_dynamic=False,
        )

    def baseline(sample: torch.Tensor) -> torch.Tensor:
        logits = apply_fp8_linear(
            sample,
            fp8_weight,
            weight_scale,
            compressed_tensor_quant=True,
            use_per_token_if_dynamic=False,
        )
        logits = 30.0 * torch.tanh(logits / 30.0)
        return torch.argmax(logits, dim=-1)

    def candidate(
        sample: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        q_hidden, activation_scale = quantize(sample)
        return fp8_greedy_top1(
            q_hidden[: sample.shape[0]],
            fp8_weight,
            activation_scale,
            weight_scale,
        )

    atomic_json(
        state_path,
        {
            "schema_version": 1,
            "candidate_cuda_started": True,
            "component_science_started": False,
        },
    )
    smoke_tokens, smoke_values, smoke_partials, smoke_indices = candidate(rows[:1])
    torch.cuda.synchronize()
    if (
        smoke_tokens.numel() != 1
        or not torch.isfinite(smoke_values).all()
        or not torch.isfinite(smoke_partials).all()
        or smoke_indices.min() < 0
        or smoke_indices.max() >= VOCAB
    ):
        raise RuntimeError("candidate discovery smoke failed")

    atomic_json(
        state_path,
        {
            "schema_version": 1,
            "candidate_cuda_started": True,
            "component_science_started": True,
        },
    )
    results = []
    for m in M_SHAPES:
        sample = rows[:m].contiguous()
        baseline_tokens = baseline(sample)
        (
            candidate_tokens,
            candidate_values,
            partial_values,
            partial_indices,
        ) = candidate(sample)
        torch.cuda.synchronize()
        repeat_tokens = [candidate(sample)[0] for _ in range(3)]
        torch.cuda.synchronize()
        deterministic = all(
            torch.equal(candidate_tokens, repeated) for repeated in repeat_tokens
        )
        graph_input = sample.clone()
        graph = torch.cuda.CUDAGraph()
        candidate(graph_input)
        torch.cuda.synchronize()
        with torch.cuda.graph(graph):
            graph_output = candidate(graph_input)
        graph.replay()
        torch.cuda.synchronize()
        graph_tokens = graph_output[0].clone()

        baseline_timing, timed_baseline_tokens = timings(
            lambda sample=sample: baseline(sample), args.repeats
        )
        candidate_timing, timed_candidate_output = timings(
            lambda sample=sample: candidate(sample)[0], args.repeats
        )
        row = {
            "m": m,
            "baseline_tokens": baseline_tokens.cpu().tolist(),
            "candidate_tokens": candidate_tokens.cpu().tolist(),
            "tokens_exact": torch.equal(baseline_tokens, candidate_tokens),
            "timed_tokens_exact": torch.equal(
                timed_baseline_tokens, timed_candidate_output
            ),
            "deterministic_repeats": deterministic,
            "partial_nonfinite_count": int(
                (~torch.isfinite(partial_values)).sum().item()
            ),
            "final_nonfinite_count": int(
                (~torch.isfinite(candidate_values)).sum().item()
            ),
            "partial_index_min": int(partial_indices.min().item()),
            "partial_index_max": int(partial_indices.max().item()),
            "graph_replay_exact": torch.equal(baseline_tokens, graph_tokens),
            "baseline_timing": baseline_timing,
            "candidate_timing": candidate_timing,
            "consumer_speedup": float(
                baseline_timing["median_ms"] / candidate_timing["median_ms"]
            ),
        }
        atomic_json(args.output / f"M{m}_RESULT.json", row)
        results.append(row)

    zeros = torch.zeros((1, HIDDEN), device="cuda", dtype=torch.bfloat16)
    tie_baseline = baseline(zeros)
    tie_candidate = candidate(zeros)[0]
    torch.cuda.synchronize()
    tie_pass = (
        int(tie_baseline.item()) == 0 and int(tie_candidate.item()) == 0
    )

    fallback_calls = {"candidate": 0, "full_logits": 0}

    def dispatched(
        sample: torch.Tensor, *, is_all_greedy: bool, return_logprob: bool
    ) -> torch.Tensor:
        if is_all_greedy and not return_logprob:
            fallback_calls["candidate"] += 1
            return candidate(sample)[0]
        fallback_calls["full_logits"] += 1
        return apply_fp8_linear(
            sample,
            fp8_weight,
            weight_scale,
            compressed_tensor_quant=True,
            use_per_token_if_dynamic=False,
        )

    non_greedy = dispatched(rows[:2], is_all_greedy=False, return_logprob=False)
    logprob = dispatched(rows[:2], is_all_greedy=True, return_logprob=True)
    fallback_pass = (
        tuple(non_greedy.shape) == (2, VOCAB)
        and tuple(logprob.shape) == (2, VOCAB)
        and non_greedy.dtype == torch.bfloat16
        and logprob.dtype == torch.bfloat16
        and fallback_calls == {"candidate": 0, "full_logits": 2}
    )
    all_exact = all(
        row["tokens_exact"]
        and row["timed_tokens_exact"]
        and row["deterministic_repeats"]
        and row["partial_nonfinite_count"] == 0
        and row["final_nonfinite_count"] == 0
        and row["graph_replay_exact"]
        for row in results
    )
    all_positive = all(
        row["candidate_timing"]["median_ms"]
        < row["baseline_timing"]["median_ms"]
        for row in results
    )
    component = {
        "schema_version": 1,
        "status": "complete",
        "classification": (
            "component_positive"
            if all_exact and all_positive and tie_pass and fallback_pass
            else "component_reject"
        ),
        "source": {
            "gpu": torch.cuda.get_device_name(),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "triton": __import__("triton").__version__,
            "kernel_sha256": sha256(pathlib.Path(__file__).with_name("fused_top1.py")),
            "benchmark_sha256": sha256(pathlib.Path(__file__)),
        },
        "geometry": {
            "m_shapes": list(M_SHAPES),
            "k": HIDDEN,
            "n": VOCAB,
            "block_m": 16,
            "block_n": 64,
            "block_k": 64,
            "partial_pairs_per_row": VOCAB // 64,
            "device_reductions": 1,
        },
        "representation": representation,
        "hidden_rows_sha256": sha256(args.hidden),
        "rows": results,
        "tie": {
            "baseline_token": int(tie_baseline.item()),
            "candidate_token": int(tie_candidate.item()),
            "lowest_index_pass": tie_pass,
        },
        "fallback": {
            "calls": fallback_calls,
            "non_greedy_output": {
                "shape": list(non_greedy.shape),
                "dtype": str(non_greedy.dtype),
            },
            "logprob_output": {
                "shape": list(logprob.shape),
                "dtype": str(logprob.dtype),
            },
            "pass": fallback_pass,
        },
        "all_shapes_exact_finite_deterministic_graph_replay": all_exact,
        "all_shapes_positive": all_positive,
        "completed_unix_s": time.time(),
    }
    atomic_json(args.output / "COMPONENT_RESULT.json", component)
    atomic_json(
        args.output / "WORKER_TERMINAL.json",
        {
            "schema_version": 1,
            "status": "terminal",
            "classification": component["classification"],
            "component_result": str(args.output / "COMPONENT_RESULT.json"),
            "timestamp_unix_s": time.time(),
        },
    )
    print(json.dumps(component, sort_keys=True))
    return 0 if component["classification"] == "component_positive" else 2


if __name__ == "__main__":
    raise SystemExit(main())
