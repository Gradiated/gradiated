from __future__ import annotations

from dataclasses import asdict, dataclass

import torch
import torch.nn.functional as functional

from validation.qwen_kv_dedup_quality.transform import minimum_weight_distance_pairing


class LowRankAdapterLinear(torch.nn.Module):
    def __init__(self, base: torch.nn.Linear, *, rank: int, alpha: float) -> None:
        super().__init__()
        if rank <= 0 or alpha <= 0.0:
            raise ValueError("adapter rank and alpha must be positive")
        self.base = base
        self.rank = rank
        self.scaling = alpha / rank
        self.adapter_a = torch.nn.Parameter(
            torch.empty(rank, base.in_features, dtype=torch.float32)
        )
        self.adapter_b = torch.nn.Parameter(
            torch.zeros(base.out_features, rank, dtype=torch.float32)
        )
        torch.nn.init.kaiming_uniform_(self.adapter_a, a=5**0.5)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        base_output = self.base(inputs)
        adapter_hidden = functional.linear(inputs.to(torch.float32), self.adapter_a)
        adapter_output = functional.linear(adapter_hidden, self.adapter_b)
        return base_output + (adapter_output * self.scaling).to(base_output.dtype)


@dataclass(frozen=True)
class RecoveryStructureSummary:
    scheme: str
    layer_count: int
    original_kv_heads: int
    unique_kv_heads: int
    head_dim: int
    layer_pairings: tuple[tuple[tuple[int, int], ...], ...]
    paired_kv_parameter_count: int
    deduplicated_projection_parameter_count: int
    adapter_rank: int
    adapter_alpha: float
    adapter_target_module_count: int
    trainable_parameter_count: int
    total_parameter_count_after_adapters: int
    trainable_parameter_fraction: float
    exact_pair_sharing_at_initialization: bool
    adapter_b_zero_at_initialization: bool
    runtime_weight_storage_deduplicated: bool
    runtime_kv_cache_deduplicated: bool
    requires_custom_attention_alias_kernel: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def apply_recovery_structure(
    model: torch.nn.Module,
    *,
    original_kv_heads: int,
    unique_kv_heads: int,
    adapter_rank: int,
    adapter_alpha: float,
) -> RecoveryStructureSummary:
    if unique_kv_heads * 2 != original_kv_heads:
        raise ValueError(
            "recovery structure requires an exact two-to-one KV-head pairing"
        )
    config = model.config
    layer_count = int(config.num_hidden_layers)
    head_dim = int(config.head_dim)
    if int(config.num_key_value_heads) != original_kv_heads:
        raise ValueError(
            "runtime model KV-head count differs from the recovery contract"
        )
    layers = tuple(model.model.layers)
    if len(layers) != layer_count:
        raise ValueError("runtime model layer count differs from its config")
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    pairings: list[tuple[tuple[int, int], ...]] = []
    paired_parameters = 0
    for layer in layers:
        attention = layer.self_attn
        pairing, _ = minimum_weight_distance_pairing(
            attention.k_proj.weight,
            attention.v_proj.weight,
            num_heads=original_kv_heads,
            head_dim=head_dim,
        )
        with torch.no_grad():
            for projection in (attention.k_proj, attention.v_proj):
                heads = projection.weight.reshape(original_kv_heads, head_dim, -1)
                for left, right in pairing:
                    mean = (
                        heads[left].to(torch.float32) + heads[right].to(torch.float32)
                    ) / 2.0
                    heads[left].copy_(mean.to(projection.weight.dtype))
                    heads[right].copy_(mean.to(projection.weight.dtype))
                    paired_parameters += 2 * head_dim * projection.in_features
        attention.q_proj = LowRankAdapterLinear(
            attention.q_proj,
            rank=adapter_rank,
            alpha=adapter_alpha,
        )
        attention.o_proj = LowRankAdapterLinear(
            attention.o_proj,
            rank=adapter_rank,
            alpha=adapter_alpha,
        )
        pairings.append(pairing)
    trainable_parameters = sum(
        value.numel() for value in model.parameters() if value.requires_grad
    )
    total_parameters = sum(value.numel() for value in model.parameters())
    exact = assert_exact_kv_sharing(model, tuple(pairings))
    adapter_b_zero = all(
        int(torch.count_nonzero(value.detach()).item()) == 0
        for name, value in model.named_parameters()
        if name.endswith("adapter_b")
    )
    return RecoveryStructureSummary(
        scheme="minimum_joint_kv_weight_distance_pair_mean_plus_qo_rank_adapter",
        layer_count=layer_count,
        original_kv_heads=original_kv_heads,
        unique_kv_heads=unique_kv_heads,
        head_dim=head_dim,
        layer_pairings=tuple(pairings),
        paired_kv_parameter_count=paired_parameters,
        deduplicated_projection_parameter_count=paired_parameters // 2,
        adapter_rank=adapter_rank,
        adapter_alpha=adapter_alpha,
        adapter_target_module_count=layer_count * 2,
        trainable_parameter_count=trainable_parameters,
        total_parameter_count_after_adapters=total_parameters,
        trainable_parameter_fraction=trainable_parameters / total_parameters,
        exact_pair_sharing_at_initialization=exact,
        adapter_b_zero_at_initialization=adapter_b_zero,
        runtime_weight_storage_deduplicated=False,
        runtime_kv_cache_deduplicated=False,
        requires_custom_attention_alias_kernel=True,
    )


def assert_exact_kv_sharing(
    model: torch.nn.Module,
    layer_pairings: tuple[tuple[tuple[int, int], ...], ...],
) -> bool:
    layers = tuple(model.model.layers)
    if len(layers) != len(layer_pairings):
        return False
    head_dim = int(model.config.head_dim)
    heads = int(model.config.num_key_value_heads)
    for layer, pairing in zip(layers, layer_pairings, strict=True):
        for projection in (layer.self_attn.k_proj, layer.self_attn.v_proj):
            weights = projection.weight.detach().reshape(heads, head_dim, -1)
            if any(
                not torch.equal(weights[left], weights[right])
                for left, right in pairing
            ):
                return False
    return True


def adapter_state_dict(model: torch.nn.Module) -> dict[str, torch.Tensor]:
    return {
        name: value.detach().to(torch.float32).cpu().contiguous()
        for name, value in model.named_parameters()
        if value.requires_grad
    }
