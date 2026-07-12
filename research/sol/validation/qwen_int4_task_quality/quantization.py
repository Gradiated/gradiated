from __future__ import annotations

import fnmatch
from dataclasses import asdict, dataclass

import torch


FROZEN_INCLUDED_PATTERNS = (
    "model.layers.*.self_attn.o_proj",
    "model.layers.*.mlp.gate_proj",
    "model.layers.*.mlp.up_proj",
)


@dataclass(frozen=True)
class FrozenMaskSummary:
    scheme: str
    group_size: int
    qmin: int
    qmax: int
    code_derivation_scale: str
    scale_storage: str
    dequantization_scale: str
    module_count: int
    parameter_count: int
    scale_count: int
    modified_modules: tuple[str, ...]
    included_module_patterns: tuple[str, ...]
    runtime_storage_compressed: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def symmetric_group8_int4_bf16_scale_qdq(
    weights: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    if weights.ndim != 2:
        raise ValueError("weights must be a two-dimensional tensor")
    if weights.shape[1] == 0 or weights.shape[1] % 8 != 0:
        raise ValueError("weight columns must be a positive multiple of group size 8")
    grouped = weights.to(torch.float32).reshape(weights.shape[0], -1, 8)
    maximum = grouped.abs().amax(dim=-1, keepdim=True)
    floating_scales = torch.where(
        maximum == 0.0, torch.ones_like(maximum), maximum / 7.0
    )
    stored_scales = floating_scales.to(torch.bfloat16).to(torch.float32)
    grouped_codes = torch.round(grouped / floating_scales).clamp(-7.0, 7.0)
    restored = (grouped_codes * stored_scales).reshape_as(weights).to(weights.dtype)
    return restored, stored_scales, grouped_codes.reshape_as(weights)


def quantize_frozen_selective_mask(
    model: torch.nn.Module,
    *,
    expected_module_count: int,
    expected_parameter_count: int,
) -> FrozenMaskSummary:
    modified_modules: list[str] = []
    parameter_count = 0
    scale_count = 0
    with torch.no_grad():
        for name, module in model.named_modules():
            if not isinstance(module, torch.nn.Linear):
                continue
            if not any(
                fnmatch.fnmatchcase(name, pattern)
                for pattern in FROZEN_INCLUDED_PATTERNS
            ):
                continue
            restored, scales, _ = symmetric_group8_int4_bf16_scale_qdq(module.weight)
            module.weight.copy_(restored)
            modified_modules.append(name)
            parameter_count += module.weight.numel()
            scale_count += scales.numel()
    if len(modified_modules) != expected_module_count:
        raise ValueError(
            f"frozen mask module count mismatch: expected {expected_module_count}, "
            f"measured {len(modified_modules)}"
        )
    if parameter_count != expected_parameter_count:
        raise ValueError(
            f"frozen mask parameter count mismatch: expected {expected_parameter_count}, "
            f"measured {parameter_count}"
        )
    return FrozenMaskSummary(
        scheme="symmetric_signed_int4",
        group_size=8,
        qmin=-7,
        qmax=7,
        code_derivation_scale="float32_max_abs_div_7",
        scale_storage="bfloat16",
        dequantization_scale="stored_bfloat16_promoted_to_float32",
        module_count=len(modified_modules),
        parameter_count=parameter_count,
        scale_count=scale_count,
        modified_modules=tuple(modified_modules),
        included_module_patterns=FROZEN_INCLUDED_PATTERNS,
        runtime_storage_compressed=False,
    )
