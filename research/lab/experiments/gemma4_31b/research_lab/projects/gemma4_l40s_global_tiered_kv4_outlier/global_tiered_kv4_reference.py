#!/usr/bin/env python3
"""High-precision oracle for the fixed D512 global mixed-tier KV cache."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


HEAD_DIM = 512
GROUP_SIZE = 64
GROUPS = 8
OUTLIERS = 8
PACKED_BYTES = 256
SCALE_OFFSET = 256
INDEX_OFFSET = 272
RESIDUAL_OFFSET = 288
OLD_VECTOR_BYTES = 296
RECENT_TOKENS = 1024
QMIN = -7
QMAX = 7


def _as_f32(values) -> np.ndarray:
    return np.asarray(values, dtype=np.float32)


def bf16_bits(values) -> np.ndarray:
    x = _as_f32(values)
    bits = x.view(np.uint32)
    rounded = bits + np.uint32(0x7FFF) + ((bits >> 16) & np.uint32(1))
    return (rounded >> 16).astype(np.uint16)


def bf16_from_bits(bits) -> np.ndarray:
    widened = np.asarray(bits, dtype=np.uint16).astype(np.uint32) << np.uint32(16)
    return widened.view(np.float32)


def bf16_round(values) -> np.ndarray:
    return bf16_from_bits(bf16_bits(values))


def _e5m2_codebook() -> tuple[np.ndarray, np.ndarray]:
    codes: list[int] = []
    values: list[float] = []
    for code in range(256):
        exponent = (code >> 2) & 0x1F
        if exponent == 0x1F:
            continue
        sign = -1.0 if code & 0x80 else 1.0
        mantissa = code & 0x3
        value = (
            sign * math.ldexp(float(mantissa), -16)
            if exponent == 0
            else sign * math.ldexp(1.0 + mantissa / 4.0, exponent - 15)
        )
        codes.append(code)
        values.append(value)
    return np.asarray(codes, np.uint8), np.asarray(values, np.float32)


E5M2_CODES, E5M2_VALUES = _e5m2_codebook()


def e5m2_encode(values) -> np.ndarray:
    source = _as_f32(values)
    if not np.all(np.isfinite(source)):
        raise ValueError("the producer accepts finite K/V only")
    flat = np.clip(source.reshape(-1), -57344.0, 57344.0)
    distances = np.abs(flat[:, None] - E5M2_VALUES[None, :])
    minimum = distances.min(axis=1, keepdims=True)
    tied = distances == minimum
    preferred = tied & ((E5M2_CODES & np.uint8(1)) == 0)[None, :]
    indices = np.where(
        preferred.any(axis=1), preferred.argmax(axis=1), tied.argmax(axis=1)
    )
    return E5M2_CODES[indices].reshape(source.shape)


def e5m2_decode(codes) -> np.ndarray:
    source = np.asarray(codes, dtype=np.uint8)
    exponent = ((source >> np.uint8(2)) & np.uint8(0x1F)).astype(np.int32)
    if np.any(exponent == 0x1F):
        raise ValueError("nonfinite E5M2 code")
    sign = np.where(source & np.uint8(0x80), -1.0, 1.0).astype(np.float32)
    mantissa = (source & np.uint8(0x3)).astype(np.float32)
    subnormal = sign * np.ldexp(mantissa, -16)
    normal = sign * np.ldexp(1.0 + mantissa / 4.0, exponent - 15)
    return np.where(exponent == 0, subnormal, normal).astype(np.float32)


@dataclass(frozen=True)
class EncodedOldVector:
    bytes: np.ndarray
    saturation_count: int
    outlier_channels: tuple[int, ...]


def encode_old_vector(vector) -> EncodedOldVector:
    source = bf16_round(_as_f32(vector).reshape(-1))
    if source.shape != (HEAD_DIM,):
        raise ValueError(f"expected D{HEAD_DIM}, got {source.shape}")
    if not np.all(np.isfinite(source)):
        raise ValueError("the producer accepts finite K/V only")

    scales = np.zeros(GROUPS, np.float32)
    quantized = np.zeros(HEAD_DIM, np.int8)
    saturations = 0
    for group in range(GROUPS):
        start = group * GROUP_SIZE
        stop = start + GROUP_SIZE
        magnitudes = np.abs(source[start:stop])
        robust_maximum = float(np.partition(magnitudes, -2)[-2])
        if robust_maximum == 0.0:
            continue
        scale = float(bf16_round(np.asarray([robust_maximum / QMAX]))[0])
        if scale == 0.0:
            continue
        scales[group] = scale
        unbounded = np.rint(source[start:stop] / scale)
        saturations += int(
            np.count_nonzero((unbounded < QMIN) | (unbounded > QMAX))
        )
        quantized[start:stop] = np.clip(unbounded, QMIN, QMAX).astype(np.int8)

    base = quantized.astype(np.float32) * np.repeat(scales, GROUP_SIZE)
    residual = source - base
    channels = np.arange(HEAD_DIM)
    ranked = np.lexsort((channels, -np.abs(residual)))[:OUTLIERS]
    row = np.zeros(OLD_VECTOR_BYTES, np.uint8)
    low = quantized[0::2].astype(np.int16) & 0xF
    high = quantized[1::2].astype(np.int16) & 0xF
    row[:PACKED_BYTES] = (low | (high << 4)).astype(np.uint8)
    row[SCALE_OFFSET:INDEX_OFFSET] = bf16_bits(scales).view(np.uint8)
    row[INDEX_OFFSET:RESIDUAL_OFFSET] = ranked.astype(np.uint16).view(np.uint8)
    row[RESIDUAL_OFFSET:OLD_VECTOR_BYTES] = e5m2_encode(residual[ranked])
    return EncodedOldVector(
        bytes=row,
        saturation_count=saturations,
        outlier_channels=tuple(int(channel) for channel in ranked),
    )


def decode_old_vector(encoded, *, corrected: bool = True) -> np.ndarray:
    row = np.asarray(encoded, np.uint8).reshape(-1)
    if row.shape != (OLD_VECTOR_BYTES,):
        raise ValueError(f"expected {OLD_VECTOR_BYTES} bytes, got {row.shape}")
    nibbles = np.empty(HEAD_DIM, np.uint8)
    nibbles[0::2] = row[:PACKED_BYTES] & np.uint8(0xF)
    nibbles[1::2] = row[:PACKED_BYTES] >> np.uint8(4)
    signed = nibbles.astype(np.int16)
    signed[signed >= 8] -= 16
    scales = bf16_from_bits(row[SCALE_OFFSET:INDEX_OFFSET].view(np.uint16))
    result = signed.astype(np.float32) * np.repeat(scales, GROUP_SIZE)
    if corrected:
        indices = row[INDEX_OFFSET:RESIDUAL_OFFSET].view(np.uint16).astype(np.int64)
        if np.unique(indices).size != OUTLIERS or np.any(indices >= HEAD_DIM):
            raise ValueError("old-tier outlier indices must be unique D512 channels")
        result[indices] += e5m2_decode(row[RESIDUAL_OFFSET:OLD_VECTOR_BYTES])
    return result


def error_metrics(reference, candidate) -> dict:
    expected = np.asarray(reference, np.float64)
    actual = np.asarray(candidate, np.float64)
    delta = actual - expected
    expected_norm = float(np.linalg.norm(expected.reshape(-1)))
    actual_norm = float(np.linalg.norm(actual.reshape(-1)))
    dot = float(np.dot(expected.reshape(-1), actual.reshape(-1)))
    return {
        "max_absolute": float(np.max(np.abs(delta))) if delta.size else 0.0,
        "relative_l2": float(
            np.linalg.norm(delta.reshape(-1)) / max(expected_norm, 1e-30)
        ),
        "cosine": float(dot / max(expected_norm * actual_norm, 1e-30)),
        "reference_nonfinite": int(np.count_nonzero(~np.isfinite(expected))),
        "candidate_nonfinite": int(np.count_nonzero(~np.isfinite(actual))),
    }


@dataclass
class TieredCache:
    recent_k: np.ndarray
    recent_v: np.ndarray
    old_k: np.ndarray
    old_v: np.ndarray
    owners: np.ndarray
    positions: np.ndarray
    k_saturations: int
    v_saturations: int


def produce_cache(
    keys,
    values,
    *,
    owners,
    positions,
    transition_from_e5m2_at_or_after: int | None = None,
) -> TieredCache:
    key_source = bf16_round(keys)
    value_source = bf16_round(values)
    if key_source.shape != value_source.shape or key_source.ndim != 3:
        raise ValueError("K/V must have matching [physical_slots, kv_heads, D512]")
    if key_source.shape[2] != HEAD_DIM:
        raise ValueError("global K/V must use D512")
    owner_array = np.asarray(owners, np.int32)
    position_array = np.asarray(positions, np.int64)
    if owner_array.shape != (key_source.shape[0],) or position_array.shape != (
        key_source.shape[0],
    ):
        raise ValueError("each physical slot needs one owner and logical position")

    slots, heads, _ = key_source.shape
    recent_k = e5m2_encode(key_source)
    recent_v = e5m2_encode(value_source)
    old_k = np.empty((slots, heads, OLD_VECTOR_BYTES), np.uint8)
    old_v = np.empty_like(old_k)
    k_saturations = 0
    v_saturations = 0
    for slot in range(slots):
        for head in range(heads):
            transition = (
                transition_from_e5m2_at_or_after is not None
                and position_array[slot] >= transition_from_e5m2_at_or_after
            )
            old_source_k = (
                e5m2_decode(recent_k[slot, head])
                if transition
                else key_source[slot, head]
            )
            old_source_v = (
                e5m2_decode(recent_v[slot, head])
                if transition
                else value_source[slot, head]
            )
            encoded_k = encode_old_vector(old_source_k)
            encoded_v = encode_old_vector(old_source_v)
            old_k[slot, head] = encoded_k.bytes
            old_v[slot, head] = encoded_v.bytes
            k_saturations += encoded_k.saturation_count
            v_saturations += encoded_v.saturation_count
    return TieredCache(
        recent_k=recent_k,
        recent_v=recent_v,
        old_k=old_k,
        old_v=old_v,
        owners=owner_array,
        positions=position_array,
        k_saturations=k_saturations,
        v_saturations=v_saturations,
    )


def _validate_query_inputs(
    query: np.ndarray,
    q_request,
    q_position,
    request_slots,
) -> tuple[np.ndarray, np.ndarray]:
    requests = np.asarray(q_request, np.int32)
    positions = np.asarray(q_position, np.int64)
    if query.ndim != 3 or query.shape[2] != HEAD_DIM:
        raise ValueError("Q must have [queries, query_heads, D512]")
    if requests.shape != (query.shape[0],) or positions.shape != (query.shape[0],):
        raise ValueError("query request/position must cover every query")
    for slots in request_slots:
        if np.asarray(slots).ndim != 1:
            raise ValueError("each request page table must be one-dimensional")
    return requests, positions


def mixed_tier_paged_attention(
    q,
    *,
    q_request,
    q_position,
    cache: TieredCache,
    request_slots,
    corrected: bool = True,
) -> np.ndarray:
    query = bf16_round(q)
    requests, positions = _validate_query_inputs(
        query, q_request, q_position, request_slots
    )
    kv_heads = cache.recent_k.shape[1]
    if query.shape[1] % kv_heads:
        raise ValueError("query heads must divide evenly over KV heads")
    gqa_group = query.shape[1] // kv_heads
    output = np.zeros_like(query, np.float32)
    softmax_scale = 1.0 / math.sqrt(HEAD_DIM)

    for query_index, (request, query_position) in enumerate(zip(requests, positions)):
        slots = np.asarray(request_slots[int(request)], np.int64)
        for query_head in range(query.shape[1]):
            kv_head = query_head // gqa_group
            running_max = -math.inf
            running_sum = 0.0
            accumulator = np.zeros(HEAD_DIM, np.float64)
            for slot in slots:
                if slot < 0:
                    continue
                if slot >= cache.owners.size:
                    raise IndexError("physical page outside cache")
                if cache.owners[slot] != request:
                    raise ValueError("request/page ownership mismatch")
                key_position = int(cache.positions[slot])
                if key_position > query_position:
                    continue
                recent = key_position > query_position - RECENT_TOKENS
                key = (
                    e5m2_decode(cache.recent_k[slot, kv_head])
                    if recent
                    else decode_old_vector(cache.old_k[slot, kv_head], corrected=corrected)
                )
                score = float(np.dot(query[query_index, query_head], key) * softmax_scale)
                next_max = max(running_max, score)
                old_factor = (
                    0.0 if running_max == -math.inf else math.exp(running_max - next_max)
                )
                probability = math.exp(score - next_max)
                value = (
                    e5m2_decode(cache.recent_v[slot, kv_head])
                    if recent
                    else decode_old_vector(
                        cache.old_v[slot, kv_head], corrected=corrected
                    )
                )
                accumulator = accumulator * old_factor + probability * value
                running_sum = running_sum * old_factor + probability
                running_max = next_max
            if running_sum:
                output[query_index, query_head] = accumulator / running_sum
    return output


def dense_attention_reference(
    q,
    *,
    q_request,
    q_position,
    keys,
    values,
    owners,
    positions,
    request_slots,
    e5m2_baseline: bool = False,
) -> np.ndarray:
    query = bf16_round(q)
    requests, query_positions = _validate_query_inputs(
        query, q_request, q_position, request_slots
    )
    dense_k = bf16_round(keys)
    dense_v = bf16_round(values)
    if e5m2_baseline:
        dense_k = e5m2_decode(e5m2_encode(dense_k))
        dense_v = e5m2_decode(e5m2_encode(dense_v))
    owner_array = np.asarray(owners, np.int32)
    key_positions = np.asarray(positions, np.int64)
    kv_heads = dense_k.shape[1]
    group = query.shape[1] // kv_heads
    output = np.zeros_like(query, np.float32)
    scale = 1.0 / math.sqrt(HEAD_DIM)
    for query_index, (request, query_position) in enumerate(
        zip(requests, query_positions)
    ):
        slots = np.asarray(request_slots[int(request)], np.int64)
        selected = slots[
            (slots >= 0)
            & (owner_array[np.maximum(slots, 0)] == request)
            & (key_positions[np.maximum(slots, 0)] <= query_position)
        ]
        for query_head in range(query.shape[1]):
            kv_head = query_head // group
            key_matrix = dense_k[selected, kv_head].astype(np.float64)
            value_matrix = dense_v[selected, kv_head].astype(np.float64)
            scores = key_matrix @ query[query_index, query_head].astype(np.float64)
            scores *= scale
            scores -= scores.max()
            probabilities = np.exp(scores)
            probabilities /= probabilities.sum()
            output[query_index, query_head] = probabilities @ value_matrix
    return output
