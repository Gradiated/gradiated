#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import pathlib

import torch
import torch.nn.functional as functional

import qserve_sm89
from sglang.srt.layers.quantization import fp8_utils
from sglang.srt.layers.quantization.fp8_kernel import sglang_per_token_quant_fp8


ROOT = pathlib.Path("/work/artifacts/qserve-causal-trace")
CACHE = pathlib.Path(
    "/work/w4_cache/d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2"
)
GROUP_SIZE = 128
INTERMEDIATE = 21504


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def cache_file(layer: int, kind: str, shard: int) -> pathlib.Path:
    return CACHE / (
        f"model__language_model__layers__{layer}__mlp__{kind}"
        f"__shard{shard}.pt"
    )


def load_cache(layer: int, kind: str, shard: int) -> dict:
    value = torch.load(
        cache_file(layer, kind, shard),
        map_location="cpu",
        weights_only=True,
    )
    if int(value["shard_id"]) != shard:
        raise ValueError(f"cache shard identity mismatch: {kind} {shard}")
    return value


def unpack_codes(packed: torch.Tensor) -> torch.Tensor:
    output_features, packed_inputs = packed.shape
    input_features = packed_inputs * 2
    shaped = packed.view(torch.uint8).reshape(
        output_features // 32,
        input_features // 32,
        8,
        4,
        2,
        2,
        4,
    )
    low = (shaped & 15).to(torch.int8)
    high = (shaped >> 4).to(torch.int8)
    reordered = torch.stack((low, high), dim=-1)
    first_permutation = reordered.permute(0, 1, 2, 3, 7, 4, 5, 6)
    original = first_permutation.permute(0, 4, 6, 2, 1, 5, 3, 7)
    return original.contiguous().reshape(output_features, input_features)


def inverse_metadata(reordered: torch.Tensor) -> torch.Tensor:
    groups, output_features = reordered.shape
    return (
        reordered.reshape(groups, output_features // 32, 8, 4)
        .transpose(-2, -1)
        .contiguous()
        .reshape(groups, output_features)
        .transpose(0, 1)
        .contiguous()
    )


def combine(caches: list[dict]) -> dict[str, torch.Tensor]:
    packed = [value["packed"] for value in caches]
    return {
        "qweight": torch.cat([value["qweight"] for value in packed], dim=0),
        "scales_i8": torch.cat(
            [value["scales_i8"] for value in packed], dim=1
        ),
        "zeros": torch.cat([value["zeros"] for value in packed], dim=1),
        "weight_scales": torch.cat(
            [value["weight_scales"] for value in packed], dim=0
        ),
        "prefill_weight": torch.cat(
            [value["prefill_weight"] for value in caches], dim=1
        ),
        "prefill_scale": torch.cat(
            [value["prefill_scale"] for value in caches], dim=0
        ),
    }


def dequantized_mm(
    activation: torch.Tensor,
    packed: dict[str, torch.Tensor],
    chunk: int = 512,
) -> torch.Tensor:
    stage2 = inverse_metadata(packed["scales_i8"])
    zeros = inverse_metadata(packed["zeros"])
    if not torch.equal(zeros.to(torch.int16), -7 * stage2.to(torch.int16)):
        raise ValueError("W4 zero metadata does not match symmetric -7 offset")
    outputs = []
    output_features = packed["qweight"].shape[0]
    for start in range(0, output_features, chunk):
        stop = min(start + chunk, output_features)
        codes = unpack_codes(packed["qweight"][start:stop])
        effective = (
            stage2[start:stop].float()
            * packed["weight_scales"][start:stop].float().unsqueeze(1)
        )
        weight = (
            (codes.float().reshape(stop - start, -1, GROUP_SIZE) - 7.0)
            * effective.unsqueeze(2)
        ).reshape(stop - start, -1)
        outputs.append(
            torch.mm(
                activation.float(),
                weight.to(device=activation.device).t(),
            ).to(torch.bfloat16)
        )
    return torch.cat(outputs, dim=1)


def fused_linear(
    xq: torch.Tensor,
    xs: torch.Tensor,
    packed: dict[str, torch.Tensor],
) -> torch.Tensor:
    qweight = packed["qweight"].to("cuda")
    zeros = packed["zeros"].to("cuda")
    scales_i8 = packed["scales_i8"].to("cuda")
    weight_scales = packed["weight_scales"].to("cuda")
    output = torch.empty(
        (xq.shape[0], qweight.shape[0]),
        device="cuda",
        dtype=torch.bfloat16,
    )
    qserve_sm89.w4a8_gemm(
        xq,
        qweight,
        zeros,
        scales_i8,
        weight_scales,
        xs,
        output,
    )
    output.float().square().sum().item()
    return output


def fp8_linear(x: torch.Tensor, packed: dict[str, torch.Tensor]) -> torch.Tensor:
    weight = packed["prefill_weight"].to("cuda").t().contiguous().t()
    weight_scale = packed["prefill_scale"].to("cuda")
    xq, xs = sglang_per_token_quant_fp8(x)
    output = fp8_utils.fp8_scaled_mm(
        xq,
        weight,
        xs,
        weight_scale,
        out_dtype=torch.bfloat16,
        bias=None,
    )
    output.float().square().sum().item()
    return output


def activate(value: torch.Tensor) -> torch.Tensor:
    gate = value[:, :INTERMEDIATE].float()
    up = value[:, INTERMEDIATE:].float()
    return functional.gelu(gate, approximate="tanh") * up


def quantize_s8(value: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    absolute_max = value.abs().amax(dim=1)
    scales = torch.where(
        absolute_max > 0,
        absolute_max / 127.0,
        torch.ones_like(absolute_max),
    ).to(torch.float16)
    quantized = (
        torch.round(value / scales.float().unsqueeze(1))
        .clamp(-127, 127)
        .to(torch.int8)
    )
    return quantized, scales


def metrics(actual: torch.Tensor, reference: torch.Tensor) -> dict[str, object]:
    actual32 = actual.float()
    reference32 = reference.float()
    delta = actual32 - reference32
    denominator = max(float(torch.linalg.vector_norm(reference32)), 1e-12)
    return {
        "relative_l2": float(torch.linalg.vector_norm(delta)) / denominator,
        "cosine_similarity": float(
            functional.cosine_similarity(
                actual32.flatten(), reference32.flatten(), dim=0
            )
        ),
        "maximum_absolute": float(delta.abs().max()),
        "actual_sum_squares": float(actual32.square().sum()),
        "reference_sum_squares": float(reference32.square().sum()),
        "actual_nonfinite": int((~torch.isfinite(actual32)).sum()),
        "reference_nonfinite": int((~torch.isfinite(reference32)).sum()),
    }


def stage(
    fused: torch.Tensor,
    oracle: torch.Tensor,
    fp8: torch.Tensor,
) -> dict[str, object]:
    return {
        "fused_vs_dequantized_w4_oracle": metrics(fused, oracle),
        "fused_vs_fp8": metrics(fused, fp8),
        "dequantized_w4_oracle_vs_fp8": metrics(oracle, fp8),
    }


def main() -> int:
    capture = torch.load(ROOT / "captured-hidden.pt", map_location="cpu")
    trace_path = (
        ROOT / "TRACE_TERMINAL_NORMALIZED.json"
        if (ROOT / "TRACE_TERMINAL_NORMALIZED.json").is_file()
        else ROOT / "TRACE_TERMINAL.json"
    )
    target = json.loads(trace_path.read_text())["first_divergent_target"]
    if int(capture["layer"]) != int(target["layer"]):
        raise ValueError("captured layer does not match trace target")
    layer = int(target["layer"])
    x = capture["x"].to(device="cuda", dtype=torch.bfloat16)
    gate = combine(
        [
            load_cache(layer, "gate_up_proj", 0),
            load_cache(layer, "gate_up_proj", 1),
        ]
    )
    down = combine([load_cache(layer, "down_proj", 0)])

    gate_xq = torch.empty_like(x, dtype=torch.int8)
    gate_xs = torch.empty((x.shape[0],), device="cuda", dtype=torch.float16)
    qserve_sm89.quantize_bf16_s8(x, gate_xq, gate_xs)
    gate_fused = fused_linear(gate_xq, gate_xs, gate)
    gate_oracle = dequantized_mm(
        gate_xq.float() * gate_xs.float().unsqueeze(1), gate
    )
    gate_fp8 = fp8_linear(x, gate)

    activation_fused_q = torch.empty(
        (x.shape[0], INTERMEDIATE), device="cuda", dtype=torch.int8
    )
    activation_fused_s = torch.empty(
        (x.shape[0],), device="cuda", dtype=torch.float16
    )
    qserve_sm89.gelu_mul_quant_bf16_s8(
        gate_fused,
        activation_fused_q,
        activation_fused_s,
    )
    activation_fused = (
        activation_fused_q.float()
        * activation_fused_s.float().unsqueeze(1)
    ).to(torch.bfloat16)
    activation_oracle_q, activation_oracle_s = quantize_s8(
        activate(gate_oracle)
    )
    activation_oracle = (
        activation_oracle_q.float()
        * activation_oracle_s.float().unsqueeze(1)
    ).to(torch.bfloat16)
    activation_fp8 = activate(gate_fp8).to(torch.bfloat16)

    down_fused = fused_linear(
        activation_fused_q,
        activation_fused_s,
        down,
    )
    down_oracle = dequantized_mm(
        activation_oracle_q.float()
        * activation_oracle_s.float().unsqueeze(1),
        down,
    )
    down_fp8 = fp8_linear(activation_fp8, down)
    torch.cuda.synchronize()

    result = {
        "schema_version": 1,
        "classification": "first_divergent_layer_oracle_complete",
        "target": target,
        "capture": {
            "run_id": capture["run_id"],
            "depth": capture["depth"],
            "layer": capture["layer"],
            "decode_step": capture["decode_step"],
            "shape": capture["shape"],
            "dtype": capture["dtype"],
            "input_sum_squares": float(x.float().square().sum()),
            "input_nonfinite": int((~torch.isfinite(x)).sum()),
        },
        "cache_files": {
            "gate": [
                str(cache_file(layer, "gate_up_proj", 0)),
                str(cache_file(layer, "gate_up_proj", 1)),
            ],
            "down": [str(cache_file(layer, "down_proj", 0))],
        },
        "stages": {
            "gate_up": stage(gate_fused, gate_oracle, gate_fp8),
            "activation": stage(
                activation_fused,
                activation_oracle,
                activation_fp8,
            ),
            "down": stage(down_fused, down_oracle, down_fp8),
        },
        "identities": {
            "group_size": GROUP_SIZE,
            "output_dtype": "torch.bfloat16",
            "activation_quant_dtype": "torch.int8",
            "kernel": "qserve_sm89.w4a8_gemm",
        },
    }
    atomic(ROOT / "ORACLE_TERMINAL.json", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
