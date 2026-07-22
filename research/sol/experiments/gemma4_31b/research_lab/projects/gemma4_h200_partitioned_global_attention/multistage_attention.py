from __future__ import annotations

import torch


VALUE_SLICE = 128
Q_HEADS = 32
KV_HEADS = 4
HEAD_DIM = 512
GROUP_SIZE = Q_HEADS // KV_HEADS

_causal_masks: dict[tuple[torch.device, int], torch.Tensor] = {}


def causal_mask(device: torch.device, tokens: int) -> torch.Tensor:
    key = (device, tokens)
    mask = _causal_masks.get(key)
    if mask is None:
        mask = torch.ones((tokens, tokens), device=device, dtype=torch.bool).tril_()
        _causal_masks[key] = mask
    return mask


def grouped_inputs(
    q: torch.Tensor, k: torch.Tensor, v: torch.Tensor
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    tokens = q.shape[0]
    if q.shape != (tokens, Q_HEADS, HEAD_DIM):
        raise ValueError(f"unexpected_q_shape:{tuple(q.shape)}")
    if k.shape != (tokens, KV_HEADS, HEAD_DIM):
        raise ValueError(f"unexpected_k_shape:{tuple(k.shape)}")
    if v.shape != (tokens, KV_HEADS, HEAD_DIM):
        raise ValueError(f"unexpected_v_shape:{tuple(v.shape)}")
    q_grouped = q.reshape(tokens, KV_HEADS, GROUP_SIZE, HEAD_DIM).permute(1, 2, 0, 3)
    k_grouped = k.permute(1, 0, 2).unsqueeze(1)
    v_grouped = v.permute(1, 0, 2).unsqueeze(1)
    return q_grouped, k_grouped, v_grouped


def probabilities(q: torch.Tensor, k: torch.Tensor) -> torch.Tensor:
    q_grouped, k_grouped, _ = grouped_inputs(q, k, k)
    scores = torch.matmul(q_grouped.float(), k_grouped.float().transpose(-1, -2))
    scores.masked_fill_(~causal_mask(q.device, q.shape[0]), float("-inf"))
    return torch.softmax(scores, dim=-1)


def probabilities_for_keys(
    q: torch.Tensor, key: torch.Tensor, prefix_tokens: int, sm_scale: float
) -> torch.Tensor:
    query_tokens = q.shape[0]
    q_grouped = q.reshape(query_tokens, KV_HEADS, GROUP_SIZE, HEAD_DIM).permute(1, 2, 0, 3)
    key_grouped = key.permute(1, 0, 2).unsqueeze(1)
    scores = torch.matmul(q_grouped.float(), key_grouped.float().transpose(-1, -2))
    scores.mul_(sm_scale)
    query_positions = prefix_tokens + torch.arange(query_tokens, device=q.device)
    key_positions = torch.arange(key.shape[0], device=q.device)
    scores.masked_fill_(key_positions[None, :] > query_positions[:, None], float("-inf"))
    return torch.softmax(scores, dim=-1)


def sliced_value_from_grouped(
    probs: torch.Tensor,
    v_grouped_float: torch.Tensor,
    output: torch.Tensor,
) -> None:
    parts = [
        torch.matmul(
            probs,
            v_grouped_float[..., start : start + VALUE_SLICE],
        )
        for start in range(0, HEAD_DIM, VALUE_SLICE)
    ]
    joined = torch.cat(parts, dim=-1).permute(2, 0, 1, 3).reshape_as(output)
    output.copy_(joined)


def run(q: torch.Tensor, k: torch.Tensor, v: torch.Tensor, output: torch.Tensor) -> None:
    probs = probabilities(q, k)
    _, _, v_grouped = grouped_inputs(q, k, v)
    sliced_value_from_grouped(probs, v_grouped.float(), output)


def profile_inputs(
    q: torch.Tensor, k: torch.Tensor, v: torch.Tensor
) -> tuple[torch.Tensor, torch.Tensor]:
    probs = probabilities(q, k)
    _, _, v_grouped = grouped_inputs(q, k, v)
    return probs, v_grouped.float()


def run_paged(
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
    output: torch.Tensor,
    k_buffer: torch.Tensor,
    v_buffer: torch.Tensor,
    qo_indptr: torch.Tensor,
    kv_indptr: torch.Tensor,
    kv_indices: torch.Tensor,
    k_scale: float,
    v_scale: float,
    sm_scale: float,
) -> None:
    q_offsets = qo_indptr.detach().cpu().tolist()
    kv_offsets = kv_indptr.detach().cpu().tolist()
    for sequence in range(len(q_offsets) - 1):
        q_start, q_end = q_offsets[sequence : sequence + 2]
        prefix_start, prefix_end = kv_offsets[sequence : sequence + 2]
        prefix_indices = kv_indices[prefix_start:prefix_end].long()
        prefix_k = k_buffer[prefix_indices].to(q.dtype) * k_scale
        prefix_v = v_buffer[prefix_indices].to(v.dtype) * v_scale
        key = torch.cat((prefix_k, k[q_start:q_end]), dim=0)
        value = torch.cat((prefix_v, v[q_start:q_end]), dim=0)
        probs = probabilities_for_keys(
            q[q_start:q_end], key, prefix_end - prefix_start, sm_scale
        )
        value_grouped = value.permute(1, 0, 2).unsqueeze(1).float()
        sliced_value_from_grouped(probs, value_grouped, output[q_start:q_end])


def temporary_bytes(tokens: int) -> dict[str, int]:
    score_or_probability = KV_HEADS * GROUP_SIZE * tokens * tokens * 4
    grouped_fp32_inputs = (Q_HEADS + 2 * KV_HEADS) * tokens * HEAD_DIM * 4
    sliced_outputs = Q_HEADS * tokens * HEAD_DIM * 4
    return {
        "score_bytes_fp32": score_or_probability,
        "probability_bytes_fp32": score_or_probability,
        "grouped_input_bytes_fp32": grouped_fp32_inputs,
        "sliced_output_bytes_fp32": sliced_outputs,
        "materialized_bytes_sum": 2 * score_or_probability
        + grouped_fp32_inputs
        + sliced_outputs,
    }
