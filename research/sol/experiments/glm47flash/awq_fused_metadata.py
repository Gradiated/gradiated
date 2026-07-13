from collections.abc import Sequence


def dequantize_symmetric_int4_groupwise(
    quantized: Sequence[Sequence[int]],
    scales: Sequence[Sequence[float]],
    group_size: int,
) -> list[list[float]]:
    """CPU fixture for the checkpoint's symmetric W4A16 group mapping."""
    if group_size <= 0:
        raise ValueError("group_size must be positive")
    result = []
    for row, row_scales in zip(quantized, scales, strict=True):
        if len(row) % group_size or len(row_scales) != len(row) // group_size:
            raise ValueError("scale count does not match quantized groups")
        if any(value < -8 or value > 7 for value in row):
            raise ValueError("value outside signed int4 range")
        result.append(
            [value * row_scales[index // group_size] for index, value in enumerate(row)]
        )
    return result


def fuse_projection_tensor(name: str, q_tensor: Sequence, kv_tensor: Sequence):
    if name.endswith(".weight_shape"):
        if len(q_tensor) != 2 or len(kv_tensor) != 2:
            raise ValueError("weight_shape must be a two-element descriptor")
        if q_tensor[1] != kv_tensor[1]:
            raise ValueError("fused projections must have equal input features")
        return [q_tensor[0] + kv_tensor[0], q_tensor[1]]
    return list(q_tensor) + list(kv_tensor)


def fused_projection_is_packed(has_weight_packed: bool, quantization_name: str) -> bool:
    return has_weight_packed or quantization_name in {
        "awq",
        "awq_marlin",
        "moe_wna16",
    }


def should_ignore_fused_projection(
    fused_name: str,
    ignore: Sequence[str],
    packed_modules_mapping: dict[str, list[str]],
) -> bool:
    for fused_component, source_components in packed_modules_mapping.items():
        if fused_component not in fused_name:
            continue
        source_names = [fused_name.replace(fused_component, source) for source in source_components]
        return all(source_name in ignore for source_name in source_names)
    return fused_name in ignore
