from __future__ import annotations

from dataclasses import asdict, dataclass

import torch


@dataclass(frozen=True)
class KvHeadDedupSummary:
    scheme: str
    layer_count: int
    original_kv_heads: int
    unique_kv_heads: int
    head_dim: int
    transformed_module_count: int
    transformed_parameter_count: int
    changed_value_count: int
    total_unique_parameter_count: int
    baseline_checkpoint_bits_per_parameter: int
    baseline_checkpoint_weight_bytes: int
    estimated_deduplicated_weight_bytes: int
    estimated_weight_storage_reduction_percent: float
    baseline_kv_cache_bytes_per_token: int
    deduplicated_kv_cache_bytes_per_token: int
    kv_cache_reduction_percent: float
    total_pairing_distance_squared: float
    layer_pairings: tuple[tuple[tuple[int, int], ...], ...]
    transformed_layer_indices: tuple[int, ...]
    all_layer_relative_pairing_distances: tuple[float, ...]
    runtime_weight_storage_deduplicated: bool
    runtime_kv_cache_deduplicated: bool
    requires_custom_attention_alias_kernel: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def minimum_weight_distance_pairing(
    k_weight: torch.Tensor,
    v_weight: torch.Tensor,
    *,
    num_heads: int,
    head_dim: int,
) -> tuple[tuple[tuple[int, int], ...], float]:
    _validate_projection(k_weight, num_heads, head_dim, "K")
    _validate_projection(v_weight, num_heads, head_dim, "V")
    if k_weight.shape[1] != v_weight.shape[1]:
        raise ValueError("K and V projection input dimensions must match")
    if num_heads % 2 != 0:
        raise ValueError("KV head count must be even")

    k_heads = k_weight.detach().to(torch.float32).reshape(num_heads, head_dim, -1)
    v_heads = v_weight.detach().to(torch.float32).reshape(num_heads, head_dim, -1)
    distances: dict[tuple[int, int], float] = {}
    for left in range(num_heads):
        for right in range(left + 1, num_heads):
            k_difference = k_heads[left] - k_heads[right]
            v_difference = v_heads[left] - v_heads[right]
            distances[(left, right)] = float(
                torch.sum(k_difference * k_difference).item()
                + torch.sum(v_difference * v_difference).item()
            )

    candidates = _perfect_pairings(tuple(range(num_heads)))
    return min(
        ((pairing, sum(distances[pair] for pair in pairing)) for pairing in candidates),
        key=lambda candidate: (candidate[1], candidate[0]),
    )


def apply_kv_head_deduplication(
    model: torch.nn.Module,
    *,
    baseline_checkpoint_bits_per_parameter: int,
    maximum_transformed_layers: int | None = None,
    maximum_pairs_per_transformed_layer: int | None = None,
) -> KvHeadDedupSummary:
    if baseline_checkpoint_bits_per_parameter <= 0:
        raise ValueError("baseline checkpoint precision must be positive")
    config = model.config
    layer_count = int(config.num_hidden_layers)
    num_heads = int(config.num_key_value_heads)
    head_dim = int(config.head_dim)
    if num_heads % 2 != 0:
        raise ValueError("KV head count must be even")

    layers = tuple(model.model.layers)
    if len(layers) != layer_count:
        raise ValueError("model layer count does not match config")
    transformed_layer_limit = maximum_transformed_layers or layer_count
    if transformed_layer_limit <= 0 or transformed_layer_limit > layer_count:
        raise ValueError(
            "maximum transformed layers must be between one and the model layer count"
        )
    pair_limit = maximum_pairs_per_transformed_layer or num_heads // 2
    if pair_limit <= 0 or pair_limit > num_heads // 2:
        raise ValueError(
            "maximum pairs per transformed layer is outside the KV geometry"
        )
    total_parameters = sum(parameter.numel() for parameter in model.parameters())
    transformed_parameters = 0
    changed_values = 0
    total_distance = 0.0
    layer_pairings: list[tuple[tuple[int, int], ...]] = []
    analyzed_layers: list[
        tuple[int, torch.nn.Module, tuple[tuple[int, int], ...], float, float]
    ] = []

    for index, layer in enumerate(layers):
        attention = layer.self_attn
        if attention.k_proj.bias is not None or attention.v_proj.bias is not None:
            raise ValueError("KV projection bias is not supported")
        pairing, distance = minimum_weight_distance_pairing(
            attention.k_proj.weight,
            attention.v_proj.weight,
            num_heads=num_heads,
            head_dim=head_dim,
        )
        energy = float(
            torch.sum(attention.k_proj.weight.detach().to(torch.float32) ** 2).item()
            + torch.sum(attention.v_proj.weight.detach().to(torch.float32) ** 2).item()
        )
        relative_distance = distance / energy if energy else 0.0
        analyzed_layers.append((index, layer, pairing, distance, relative_distance))

    selected_layers = sorted(
        sorted(analyzed_layers, key=lambda value: (value[4], value[0]))[
            :transformed_layer_limit
        ],
        key=lambda value: value[0],
    )
    selected_layers = [
        (
            index,
            layer,
            tuple(
                sorted(
                    sorted(
                        pairing,
                        key=lambda pair: (
                            _relative_pair_distance(layer.self_attn, pair, head_dim),
                            pair,
                        ),
                    )[:pair_limit]
                )
            ),
            distance,
            relative_distance,
        )
        for index, layer, pairing, distance, relative_distance in selected_layers
    ]

    with torch.no_grad():
        for _, layer, pairing, distance, _ in selected_layers:
            attention = layer.self_attn
            for projection in (attention.k_proj, attention.v_proj):
                heads = projection.weight.reshape(num_heads, head_dim, -1)
                for left, right in pairing:
                    left_before = heads[left].clone()
                    right_before = heads[right].clone()
                    mean = (
                        (left_before.to(torch.float32) + right_before.to(torch.float32))
                        / 2.0
                    ).to(projection.weight.dtype)
                    changed_values += int(
                        torch.count_nonzero(left_before != mean).item()
                    )
                    changed_values += int(
                        torch.count_nonzero(right_before != mean).item()
                    )
                    heads[left].copy_(mean)
                    heads[right].copy_(mean)
                transformed_parameters += (
                    len(pairing) * 2 * head_dim * projection.weight.shape[1]
                )
            layer_pairings.append(pairing)
            total_distance += distance

    bytes_per_parameter = baseline_checkpoint_bits_per_parameter / 8.0
    baseline_weight_bytes = round(total_parameters * bytes_per_parameter)
    deduplicated_projection_parameters = transformed_parameters // 2
    deduplicated_weight_bytes = round(
        (total_parameters - deduplicated_projection_parameters) * bytes_per_parameter
    )
    baseline_cache_bytes = round(
        layer_count * 2 * num_heads * head_dim * bytes_per_parameter
    )
    cache_bytes_saved = round(
        len(selected_layers) * 2 * pair_limit * head_dim * bytes_per_parameter
    )
    deduplicated_cache_bytes = baseline_cache_bytes - cache_bytes_saved

    return KvHeadDedupSummary(
        scheme="minimum_joint_kv_weight_distance_pair_mean",
        layer_count=layer_count,
        original_kv_heads=num_heads,
        unique_kv_heads=num_heads - pair_limit,
        head_dim=head_dim,
        transformed_module_count=len(selected_layers) * 2,
        transformed_parameter_count=transformed_parameters,
        changed_value_count=changed_values,
        total_unique_parameter_count=total_parameters,
        baseline_checkpoint_bits_per_parameter=baseline_checkpoint_bits_per_parameter,
        baseline_checkpoint_weight_bytes=baseline_weight_bytes,
        estimated_deduplicated_weight_bytes=deduplicated_weight_bytes,
        estimated_weight_storage_reduction_percent=_reduction_percent(
            baseline_weight_bytes,
            deduplicated_weight_bytes,
        ),
        baseline_kv_cache_bytes_per_token=baseline_cache_bytes,
        deduplicated_kv_cache_bytes_per_token=deduplicated_cache_bytes,
        kv_cache_reduction_percent=_reduction_percent(
            baseline_cache_bytes,
            deduplicated_cache_bytes,
        ),
        total_pairing_distance_squared=total_distance,
        layer_pairings=tuple(layer_pairings),
        transformed_layer_indices=tuple(value[0] for value in selected_layers),
        all_layer_relative_pairing_distances=tuple(
            value[4] for value in analyzed_layers
        ),
        runtime_weight_storage_deduplicated=False,
        runtime_kv_cache_deduplicated=False,
        requires_custom_attention_alias_kernel=True,
    )


def _perfect_pairings(
    remaining: tuple[int, ...],
) -> tuple[tuple[tuple[int, int], ...], ...]:
    if not remaining:
        return ((),)
    left = remaining[0]
    pairings: list[tuple[tuple[int, int], ...]] = []
    for index in range(1, len(remaining)):
        right = remaining[index]
        rest = remaining[1:index] + remaining[index + 1 :]
        for suffix in _perfect_pairings(rest):
            pairings.append(((left, right),) + suffix)
    return tuple(pairings)


def _validate_projection(
    weight: torch.Tensor,
    num_heads: int,
    head_dim: int,
    name: str,
) -> None:
    if weight.ndim != 2:
        raise ValueError(f"{name} projection weight must be two-dimensional")
    if num_heads <= 0 or head_dim <= 0:
        raise ValueError("KV head count and head dimension must be positive")
    if weight.shape[0] != num_heads * head_dim:
        raise ValueError(f"{name} projection rows do not match KV geometry")


def _relative_pair_distance(
    attention: torch.nn.Module,
    pair: tuple[int, int],
    head_dim: int,
) -> float:
    left, right = pair
    distance = 0.0
    energy = 0.0
    for projection in (attention.k_proj, attention.v_proj):
        heads = (
            projection.weight.detach()
            .to(torch.float32)
            .reshape(-1, head_dim, projection.weight.shape[1])
        )
        difference = heads[left] - heads[right]
        distance += float(torch.sum(difference * difference).item())
        energy += float(torch.sum(heads[left] * heads[left]).item())
        energy += float(torch.sum(heads[right] * heads[right]).item())
    return distance / energy if energy else 0.0


def _reduction_percent(baseline: int, candidate: int) -> float:
    return 100.0 * (baseline - candidate) / baseline if baseline else 0.0
