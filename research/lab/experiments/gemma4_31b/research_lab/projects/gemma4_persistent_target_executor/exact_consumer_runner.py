from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import statistics
import time


M = 384
K = 21504
N = 5376
GATE_UP = 43008
SEED = 20260726


def atomic(path: pathlib.Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def samples(torch, function, repetitions: int) -> list[float]:
    for _ in range(10):
        function()
    torch.cuda.synchronize()
    values = []
    for _ in range(repetitions):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        output = function()
        end.record()
        end.synchronize()
        if isinstance(output, tuple):
            for tensor in output:
                tensor.view(-1)[-1].item()
        else:
            output.view(-1)[-1].item()
        values.append(start.elapsed_time(end))
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--repetitions", type=int, default=50)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    state_path = args.output / "INVOCATION_STATE.json"
    atomic(
        state_path,
        {
            "candidate_cuda_started": False,
            "candidate_science_started": False,
            "consumer_started": False,
            "schema_version": 1,
        },
    )

    import torch
    from safetensors import safe_open
    from sglang.srt.layers.activation import GeluAndMul
    from sglang.srt.layers.quantization.fp8_kernel import (
        sglang_per_token_quant_fp8,
    )
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm

    from fused_swiglu_quant import (
        fused_swiglu_quant,
        invocation_count,
        prepare,
    )

    device = torch.cuda.get_device_properties(0)
    if not torch.cuda.is_available() or "H200" not in device.name:
        raise RuntimeError("exact H200 required")
    shard = args.checkpoint / "model-00001-of-00002.safetensors"
    key = "model.language_model.layers.0.mlp.down_proj.weight"
    with safe_open(str(shard), framework="pt", device="cpu") as handle:
        raw = handle.get_tensor(key)
    if raw.dtype != torch.bfloat16 or tuple(raw.shape) != (N, K):
        raise RuntimeError(f"exact weight mismatch:{raw.dtype}:{tuple(raw.shape)}")
    weight_bf16 = raw.cuda().t()
    weight_scale = (
        weight_bf16.float().abs().amax(dim=0).div(448.0).clamp_min(1e-8)
    )
    weight = (weight_bf16 / weight_scale).to(torch.float8_e4m3fn)
    if tuple(weight.stride()) != (1, K):
        raise RuntimeError(f"consumer column-major mismatch:{weight.stride()}")
    prepare()

    torch.manual_seed(SEED)
    gate_up = torch.empty(
        (M, GATE_UP), device="cuda", dtype=torch.bfloat16
    ).normal_(0.0, 0.7)
    activation = GeluAndMul(approximate="tanh")

    def control_producer():
        return sglang_per_token_quant_fp8(activation(gate_up))

    def candidate_producer():
        return fused_swiglu_quant(gate_up)

    state = json.loads(state_path.read_text())
    state["candidate_cuda_started"] = True
    state["candidate_science_started"] = True
    atomic(state_path, state)
    candidate_q, candidate_scale = candidate_producer()
    torch.cuda.synchronize()
    producer_path = args.output / "PRODUCER.pt"
    torch.save(
        {"q": candidate_q.cpu(), "scale": candidate_scale.cpu()},
        producer_path,
    )
    producer = {
        "path": producer_path.name,
        "q_shape": list(candidate_q.shape),
        "q_stride": list(candidate_q.stride()),
        "scale_shape": list(candidate_scale.shape),
        "scale_stride": list(candidate_scale.stride()),
        "sha256": sha256(producer_path),
    }
    atomic(args.output / "PRODUCER.json", producer)

    control_q, control_scale = control_producer()
    state = json.loads(state_path.read_text())
    state["consumer_started"] = True
    atomic(state_path, state)

    def consume(q, scale):
        return fp8_scaled_mm(
            q,
            weight,
            scale,
            weight_scale,
            out_dtype=torch.bfloat16,
            bias=None,
        )

    control_output = consume(control_q, control_scale)
    candidate_output = consume(candidate_q, candidate_scale)
    difference = candidate_output.float() - control_output.float()
    relative_l2 = (
        torch.linalg.vector_norm(difference)
        / torch.linalg.vector_norm(control_output.float()).clamp_min(1e-12)
    ).item()
    quantized_exact_fraction = (
        candidate_q.float().eq(control_q.float()).float().mean().item()
    )
    scale_max_abs_error = (
        candidate_scale.float() - control_scale.float()
    ).abs().max().item()
    control_producer_ms = samples(
        torch, control_producer, args.repetitions
    )
    candidate_producer_ms = samples(
        torch, candidate_producer, args.repetitions
    )
    control_component_ms = samples(
        torch,
        lambda: consume(*control_producer()),
        args.repetitions,
    )
    candidate_component_ms = samples(
        torch,
        lambda: consume(*candidate_producer()),
        args.repetitions,
    )
    correctness = {
        "all_finite": bool(torch.isfinite(candidate_output).all().item()),
        "nonzero": int(torch.count_nonzero(candidate_output).item()),
        "output_max_abs_error": difference.abs().max().item(),
        "output_relative_l2_error": relative_l2,
        "quantized_exact_fraction": quantized_exact_fraction,
        "scale_max_abs_error": scale_max_abs_error,
    }
    timing = {
        "candidate_component_median_ms": statistics.median(
            candidate_component_ms
        ),
        "candidate_producer_median_ms": statistics.median(
            candidate_producer_ms
        ),
        "control_component_median_ms": statistics.median(control_component_ms),
        "control_producer_median_ms": statistics.median(control_producer_ms),
        "repetitions": args.repetitions,
    }
    passed = (
        correctness["all_finite"]
        and correctness["nonzero"] > 0
        and relative_l2 == 0.0
        and quantized_exact_fraction == 1.0
        and scale_max_abs_error == 0.0
    )
    terminal = {
        "candidate_invocations": invocation_count(),
        "candidate_symbol": "fused_swiglu_quant_kernel",
        "classification": "correct" if passed else "numerical_negative",
        "consumer_symbol": (
            "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm"
        ),
        "correctness": correctness,
        "device": {
            "major": device.major,
            "minor": device.minor,
            "name": device.name,
            "sm_count": device.multi_processor_count,
        },
        "geometry": {"gate_up": [M, GATE_UP], "weight": [K, N]},
        "kind": "exact_m384_swiglu_quant_down_real_consumer",
        "pass": passed,
        "producer": producer,
        "schema_version": 1,
        "seed": SEED,
        "timing": timing,
        "timestamp_unix_s": time.time(),
    }
    atomic(args.output / "TERMINAL.json", terminal)
    return 0 if passed else 20


if __name__ == "__main__":
    raise SystemExit(main())
