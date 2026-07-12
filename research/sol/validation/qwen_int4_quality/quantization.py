from __future__ import annotations

import fnmatch
from dataclasses import asdict, dataclass
from typing import Iterable, Literal

import torch
import torch.nn.functional as functional

Granularity = Literal["per_channel", "groupwise"]
PACKED_CODE_BITS_PER_PARAMETER = 4
SCALE_BITS_PER_VALUE = 16


@dataclass(frozen=True)
class MixedPrecisionStorageEstimate:
    kind: str
    unique_parameter_count: int
    baseline_checkpoint_bits_per_parameter: int
    baseline_checkpoint_weight_bytes: int
    quantized_parameter_count: int
    retained_full_precision_parameter_count: int
    retained_full_precision_bits_per_parameter: int
    packed_code_bits_per_parameter: int
    scale_bits_per_value: int
    estimated_packed_code_bytes: int
    estimated_scale_bytes: int
    estimated_retained_full_precision_bytes: int
    estimated_deployed_weight_bytes: int
    estimated_whole_model_bits_per_parameter: float
    estimated_weight_storage_reduction_percent: float


@dataclass(frozen=True)
class QuantizationSummary:
    scheme: str
    granularity: Granularity
    group_size: int | None
    qmin: int
    qmax: int
    module_count: int
    parameter_count: int
    scale_count: int
    estimated_packed_weight_bytes: int
    estimated_scale_bytes: int
    storage_estimate: MixedPrecisionStorageEstimate
    modified_modules: tuple[str, ...]
    excluded_patterns: tuple[str, ...]
    runtime_storage_compressed: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def symmetric_int4_qdq(
    weights: torch.Tensor,
    *,
    granularity: Granularity,
    group_size: int | None = None,
) -> tuple[torch.Tensor, torch.Tensor]:
    if weights.ndim != 2:
        raise ValueError("weights must be a two-dimensional tensor")
    if granularity == "per_channel":
        grouped = weights.to(torch.float32)
        original_input_features = weights.shape[1]
    elif granularity == "groupwise":
        if group_size is None or group_size <= 0:
            raise ValueError("group_size must be positive for groupwise quantization")
        original_input_features = weights.shape[1]
        padded_features = (
            (original_input_features + group_size - 1) // group_size
        ) * group_size
        grouped = functional.pad(
            weights.to(torch.float32), (0, padded_features - original_input_features)
        )
        grouped = grouped.reshape(
            weights.shape[0], padded_features // group_size, group_size
        )
    else:
        raise ValueError(f"unsupported granularity: {granularity}")

    maximum = grouped.abs().amax(dim=-1, keepdim=True)
    scales = torch.where(maximum == 0.0, torch.ones_like(maximum), maximum / 7.0)
    codes = torch.round(grouped / scales).clamp(-7.0, 7.0)
    restored = (codes * scales).reshape(weights.shape[0], -1)[
        :, :original_input_features
    ]
    return restored.to(weights.dtype), scales


def quantize_linear_weights(
    model: torch.nn.Module,
    *,
    granularity: Granularity,
    group_size: int | None,
    excluded_patterns: Iterable[str] = (),
    baseline_checkpoint_bits_per_parameter: int,
) -> QuantizationSummary:
    if (
        baseline_checkpoint_bits_per_parameter <= 0
        or baseline_checkpoint_bits_per_parameter % 8 != 0
    ):
        raise ValueError(
            "baseline checkpoint precision must be a positive whole number of bytes"
        )
    patterns = tuple(excluded_patterns)
    modified_modules: list[str] = []
    unique_parameter_count = sum(parameter.numel() for parameter in model.parameters())
    parameter_count = 0
    scale_count = 0
    estimated_packed_weight_bytes = 0
    seen_weights: set[int] = set()

    with torch.no_grad():
        for name, module in model.named_modules():
            if not isinstance(module, torch.nn.Linear):
                continue
            if any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns):
                continue
            parameter_identity = id(module.weight)
            if parameter_identity in seen_weights:
                continue
            seen_weights.add(parameter_identity)
            restored, scales = symmetric_int4_qdq(
                module.weight,
                granularity=granularity,
                group_size=group_size,
            )
            module.weight.copy_(restored)
            modified_modules.append(name)
            parameter_count += module.weight.numel()
            scale_count += scales.numel()
            estimated_packed_weight_bytes += (
                module.weight.numel() * PACKED_CODE_BITS_PER_PARAMETER + 7
            ) // 8

    retained_parameter_count = unique_parameter_count - parameter_count
    if retained_parameter_count < 0:
        raise RuntimeError(
            "quantized parameter count exceeds unique model parameter count"
        )
    baseline_checkpoint_weight_bytes = (
        unique_parameter_count * baseline_checkpoint_bits_per_parameter // 8
    )
    estimated_scale_bytes = scale_count * SCALE_BITS_PER_VALUE // 8
    estimated_retained_full_precision_bytes = (
        retained_parameter_count * baseline_checkpoint_bits_per_parameter // 8
    )
    estimated_deployed_weight_bytes = (
        estimated_packed_weight_bytes
        + estimated_scale_bytes
        + estimated_retained_full_precision_bytes
    )
    estimated_whole_model_bits_per_parameter = (
        estimated_deployed_weight_bytes * 8.0 / unique_parameter_count
        if unique_parameter_count
        else 0.0
    )
    estimated_weight_storage_reduction_percent = (
        100.0
        * (baseline_checkpoint_weight_bytes - estimated_deployed_weight_bytes)
        / baseline_checkpoint_weight_bytes
        if baseline_checkpoint_weight_bytes
        else 0.0
    )
    storage_estimate = MixedPrecisionStorageEstimate(
        kind="estimated_packed_mixed_precision_weights",
        unique_parameter_count=unique_parameter_count,
        baseline_checkpoint_bits_per_parameter=baseline_checkpoint_bits_per_parameter,
        baseline_checkpoint_weight_bytes=baseline_checkpoint_weight_bytes,
        quantized_parameter_count=parameter_count,
        retained_full_precision_parameter_count=retained_parameter_count,
        retained_full_precision_bits_per_parameter=baseline_checkpoint_bits_per_parameter,
        packed_code_bits_per_parameter=PACKED_CODE_BITS_PER_PARAMETER,
        scale_bits_per_value=SCALE_BITS_PER_VALUE,
        estimated_packed_code_bytes=estimated_packed_weight_bytes,
        estimated_scale_bytes=estimated_scale_bytes,
        estimated_retained_full_precision_bytes=estimated_retained_full_precision_bytes,
        estimated_deployed_weight_bytes=estimated_deployed_weight_bytes,
        estimated_whole_model_bits_per_parameter=estimated_whole_model_bits_per_parameter,
        estimated_weight_storage_reduction_percent=estimated_weight_storage_reduction_percent,
    )

    return QuantizationSummary(
        scheme="symmetric_signed_int4_quantize_dequantize",
        granularity=granularity,
        group_size=group_size if granularity == "groupwise" else None,
        qmin=-7,
        qmax=7,
        module_count=len(modified_modules),
        parameter_count=parameter_count,
        scale_count=scale_count,
        estimated_packed_weight_bytes=estimated_packed_weight_bytes,
        estimated_scale_bytes=estimated_scale_bytes,
        storage_estimate=storage_estimate,
        modified_modules=tuple(modified_modules),
        excluded_patterns=patterns,
        runtime_storage_compressed=False,
    )
