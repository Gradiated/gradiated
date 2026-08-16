#!/usr/bin/env python3
"""Shared causal parallel-offset draft head for Gemma 4 31B."""

from __future__ import annotations

import dataclasses
import math
from typing import Iterable, Sequence


@dataclasses.dataclass(frozen=True)
class HeadConfig:
    hidden_size: int = 5376
    rank: int = 256
    depth: int = 16
    tap_layers: tuple[int, ...] = (45, 54, 60)
    attention_heads: int = 8
    mlp_ratio: int = 4
    vocab_size: int = 262144
    softcap: float = 30.0

    def validate(self) -> None:
        if self.hidden_size <= 0 or self.rank <= 0 or self.depth <= 0:
            raise ValueError("dimensions_must_be_positive")
        if self.rank % self.attention_heads:
            raise ValueError("rank_must_be_divisible_by_attention_heads")
        if not self.tap_layers:
            raise ValueError("at_least_one_tap_required")
        if tuple(sorted(set(self.tap_layers))) != self.tap_layers:
            raise ValueError("tap_layers_must_be_sorted_and_unique")


def parameter_count(config: HeadConfig) -> int:
    config.validate()
    tap_down = len(config.tap_layers) * config.hidden_size * config.rank
    offset = config.depth * config.rank
    attention = 4 * config.rank * config.rank
    mlp = 2 * config.rank * config.rank * config.mlp_ratio
    up = config.rank * config.hidden_size
    norms = config.hidden_size + 2 * config.rank
    return tap_down + offset + attention + mlp + up + norms


def service_flops(config: HeadConfig, batch: int) -> dict[str, int]:
    config.validate()
    b, d, h, r, v = (
        batch,
        config.depth,
        config.hidden_size,
        config.rank,
        config.vocab_size,
    )
    tap_projection = 2 * b * len(config.tap_layers) * h * r
    qkvo = 2 * b * d * 4 * r * r
    causal_attention = 4 * b * d * d * r
    mlp = 4 * b * d * r * r * config.mlp_ratio
    up_projection = 2 * b * d * r * h
    tied_projection = 2 * b * d * h * v
    return {
        "tap_projection": tap_projection,
        "qkvo": qkvo,
        "causal_attention": causal_attention,
        "mlp": mlp,
        "up_projection": up_projection,
        "tied_projection": tied_projection,
        "total": (
            tap_projection
            + qkvo
            + causal_attention
            + mlp
            + up_projection
            + tied_projection
        ),
    }


def service_bytes(config: HeadConfig, batch: int) -> dict[str, int]:
    config.validate()
    b, d, h, v = batch, config.depth, config.hidden_size, config.vocab_size
    return {
        "tap_inputs_bf16": b * len(config.tap_layers) * h * 2,
        "offset_hidden_bf16": b * d * h * 2,
        "head_parameters_bf16": parameter_count(config) * 2,
        "tied_weight_bf16_compulsory": v * h * 2,
        "full_logits_fp32_materialization": b * d * v * 4,
        "draft_token_ids_int64": b * d * 8,
    }


def build_torch_module(config: HeadConfig | None = None):
    import torch
    import torch.nn as nn
    import torch.nn.functional as functional

    config = config or HeadConfig()
    config.validate()

    class SharedCausalOffsetHead(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.config = config
            self.tap_down = nn.ModuleList(
                [
                    nn.Linear(config.hidden_size, config.rank, bias=False)
                    for _ in config.tap_layers
                ]
            )
            self.tap_norm = nn.RMSNorm(config.hidden_size)
            self.offset_embedding = nn.Parameter(
                torch.empty(config.depth, config.rank)
            )
            self.block_norm = nn.RMSNorm(config.rank)
            self.qkv = nn.Linear(config.rank, 3 * config.rank, bias=False)
            self.attention_out = nn.Linear(config.rank, config.rank, bias=False)
            self.mlp_norm = nn.RMSNorm(config.rank)
            self.mlp_up = nn.Linear(
                config.rank, config.rank * config.mlp_ratio, bias=False
            )
            self.mlp_down = nn.Linear(
                config.rank * config.mlp_ratio, config.rank, bias=False
            )
            self.hidden_up = nn.Linear(config.rank, config.hidden_size, bias=False)
            self.reset_parameters()

        def reset_parameters(self) -> None:
            nn.init.normal_(self.offset_embedding, mean=0.0, std=0.02)
            for module in self.modules():
                if isinstance(module, nn.Linear):
                    nn.init.normal_(module.weight, mean=0.0, std=0.02)

        def forward(self, taps: Sequence):
            if len(taps) != len(config.tap_layers):
                raise ValueError(
                    f"tap_count:{len(taps)}:expected:{len(config.tap_layers)}"
                )
            first_shape = tuple(taps[0].shape)
            if len(first_shape) != 2 or first_shape[1] != config.hidden_size:
                raise ValueError(f"tap_shape:{first_shape}")
            for tap in taps:
                if tuple(tap.shape) != first_shape:
                    raise ValueError("tap_shapes_differ")
                if tap.dtype != taps[0].dtype or tap.device != taps[0].device:
                    raise ValueError("tap_dtype_or_device_mismatch")
            seed = sum(
                projection(self.tap_norm(tap))
                for projection, tap in zip(self.tap_down, taps, strict=True)
            ) / math.sqrt(len(taps))
            states = seed[:, None, :] + self.offset_embedding[None, :, :]
            residual = states
            normalized = self.block_norm(states)
            qkv = self.qkv(normalized)
            query, key, value = qkv.chunk(3, dim=-1)
            batch = first_shape[0]
            head_dim = config.rank // config.attention_heads

            def heads(tensor):
                return tensor.view(
                    batch, config.depth, config.attention_heads, head_dim
                ).transpose(1, 2)

            attended = functional.scaled_dot_product_attention(
                heads(query),
                heads(key),
                heads(value),
                is_causal=True,
                dropout_p=0.0,
            )
            attended = attended.transpose(1, 2).reshape(
                batch, config.depth, config.rank
            )
            states = residual + self.attention_out(attended)
            states = states + self.mlp_down(
                functional.gelu(self.mlp_up(self.mlp_norm(states)), approximate="tanh")
            )
            output = taps[-1][:, None, :] + self.hidden_up(states)
            expected = (batch, config.depth, config.hidden_size)
            if tuple(output.shape) != expected:
                raise RuntimeError(f"offset_output_shape:{tuple(output.shape)}")
            return output.contiguous()

    return SharedCausalOffsetHead()


def batched_tied_logits(offset_hidden, tied_weight, softcap: float = 30.0):
    import torch

    if offset_hidden.ndim != 3 or tied_weight.ndim != 2:
        raise ValueError("tied_projection_rank")
    if offset_hidden.shape[-1] != tied_weight.shape[-1]:
        raise ValueError("tied_projection_hidden_mismatch")
    batch, depth, hidden = offset_hidden.shape
    flat = offset_hidden.reshape(batch * depth, hidden)
    logits = torch.matmul(flat.to(tied_weight.dtype), tied_weight.T).float()
    if softcap:
        logits = torch.tanh(logits / softcap) * softcap
    return logits.reshape(batch, depth, tied_weight.shape[0])


def batched_tied_top1(
    offset_hidden, tied_weight, softcap: float = 30.0, vocab_chunk: int = 8192
):
    import torch

    if vocab_chunk <= 0:
        raise ValueError("vocab_chunk_must_be_positive")
    batch, depth, hidden = offset_hidden.shape
    flat = offset_hidden.reshape(batch * depth, hidden)
    best_values = torch.full(
        (flat.shape[0],),
        -torch.inf,
        dtype=torch.float32,
        device=flat.device,
    )
    best_ids = torch.zeros(flat.shape[0], dtype=torch.int64, device=flat.device)
    for start in range(0, tied_weight.shape[0], vocab_chunk):
        end = min(start + vocab_chunk, tied_weight.shape[0])
        values = torch.matmul(flat.to(tied_weight.dtype), tied_weight[start:end].T)
        values = values.float()
        if softcap:
            values = torch.tanh(values / softcap) * softcap
        chunk_values, chunk_ids = torch.max(values, dim=-1)
        replace = chunk_values > best_values
        best_values = torch.where(replace, chunk_values, best_values)
        best_ids = torch.where(replace, chunk_ids + start, best_ids)
    return best_values.reshape(batch, depth), best_ids.reshape(batch, depth)


def prefix_weighted_loss(logits, target_ids, offset_weights):
    import torch.nn.functional as functional

    if logits.shape[:-1] != target_ids.shape:
        raise ValueError("target_shape_mismatch")
    if logits.shape[1] != offset_weights.shape[0]:
        raise ValueError("offset_weight_shape_mismatch")
    token_loss = functional.cross_entropy(
        logits.flatten(0, 1), target_ids.flatten(), reduction="none"
    ).reshape_as(target_ids)
    normalized = offset_weights / offset_weights.sum()
    return (token_loss * normalized[None, :]).sum(dim=1).mean()


def prefix_lengths(
    predicted: Iterable[Sequence[int]], targets: Iterable[Sequence[int]]
) -> list[int]:
    result: list[int] = []
    for prediction, target in zip(predicted, targets, strict=True):
        if len(prediction) != len(target):
            raise ValueError("prediction_target_depth_mismatch")
        accepted = 0
        for predicted_id, target_id in zip(prediction, target, strict=True):
            if predicted_id != target_id:
                break
            accepted += 1
        result.append(accepted)
    return result


def acceptance_curve(
    predicted: Iterable[Sequence[int]],
    targets: Iterable[Sequence[int]],
    depths: Sequence[int] = (4, 8, 12, 16),
) -> dict[int, dict[str, float]]:
    predictions = [list(row) for row in predicted]
    target_rows = [list(row) for row in targets]
    curve: dict[int, dict[str, float]] = {}
    for depth in depths:
        lengths = prefix_lengths(
            [row[:depth] for row in predictions],
            [row[:depth] for row in target_rows],
        )
        exact_by_offset = [
            sum(
                int(
                    all(
                        prediction[index] == target[index]
                        for index in range(offset + 1)
                    )
                )
                for prediction, target in zip(
                    predictions, target_rows, strict=True
                )
            )
            / len(predictions)
            for offset in range(depth)
        ]
        mean_prefix = sum(lengths) / len(lengths)
        curve[depth] = {
            "mean_accepted_draft_tokens": mean_prefix,
            "mean_accepted_target_tokens": mean_prefix + 1.0,
            "full_prefix_fraction": sum(length == depth for length in lengths)
            / len(lengths),
            "per_offset_prefix_recall_min": min(exact_by_offset),
        }
    return curve
