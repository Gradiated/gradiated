#!/usr/bin/env python3
"""CPU oracle for the fixed D256 local KV4 plus four E5M2 residual format."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np


HEAD_DIM = 256
GROUP_SIZE = 64
GROUPS = 4
OUTLIERS = 4
PACKED_BYTES = 128
SCALE_OFFSET = 128
INDEX_OFFSET = 136
RESIDUAL_OFFSET = 140
VECTOR_BYTES = 144
QMIN = -7
QMAX = 7


def _as_f32(values) -> np.ndarray:
    return np.asarray(values, dtype=np.float32)


def bf16_bits(values) -> np.ndarray:
    x = _as_f32(values)
    u = x.view(np.uint32)
    rounded = u + np.uint32(0x7FFF) + ((u >> 16) & np.uint32(1))
    return (rounded >> 16).astype(np.uint16)


def bf16_from_bits(bits) -> np.ndarray:
    u = np.asarray(bits, dtype=np.uint16).astype(np.uint32) << np.uint32(16)
    return u.view(np.float32)


def bf16_round(values) -> np.ndarray:
    return bf16_from_bits(bf16_bits(values))


def _e5m2_codebook() -> tuple[np.ndarray, np.ndarray]:
    codes = []
    values = []
    for code in range(256):
        sign = -1.0 if code & 0x80 else 1.0
        exponent = (code >> 2) & 0x1F
        mantissa = code & 0x3
        if exponent == 0:
            value = sign * math.ldexp(float(mantissa), -16)
        elif exponent == 0x1F:
            continue
        else:
            value = sign * math.ldexp(1.0 + mantissa / 4.0, exponent - 15)
        codes.append(code)
        values.append(value)
    return np.asarray(codes, dtype=np.uint8), np.asarray(values, dtype=np.float32)


E5M2_CODES, E5M2_VALUES = _e5m2_codebook()


def e5m2_encode(values) -> np.ndarray:
    x = _as_f32(values)
    if not np.all(np.isfinite(x)):
        raise ValueError("the local KV producer accepts finite BF16 K/V only")
    flat = np.clip(x.reshape(-1), -57344.0, 57344.0)
    distances = np.abs(flat[:, None] - E5M2_VALUES[None, :])
    minimum = distances.min(axis=1, keepdims=True)
    tied = distances == minimum
    even = (E5M2_CODES & np.uint8(1)) == 0
    preferred = tied & even[None, :]
    use_preferred = preferred.any(axis=1)
    indices = np.where(
        use_preferred,
        preferred.argmax(axis=1),
        tied.argmax(axis=1),
    )
    return E5M2_CODES[indices].reshape(x.shape)


def e5m2_decode(codes) -> np.ndarray:
    c = np.asarray(codes, dtype=np.uint8)
    sign = np.where((c & np.uint8(0x80)) != 0, -1.0, 1.0).astype(np.float32)
    exponent = ((c >> np.uint8(2)) & np.uint8(0x1F)).astype(np.int32)
    mantissa = (c & np.uint8(0x3)).astype(np.float32)
    if np.any(exponent == 0x1F):
        raise ValueError("nonfinite E5M2 code in residual sidecar")
    subnormal = sign * np.ldexp(mantissa, -16)
    normal = sign * np.ldexp(1.0 + mantissa / 4.0, exponent - 15)
    return np.where(exponent == 0, subnormal, normal).astype(np.float32)


@dataclass(frozen=True)
class EncodedVector:
    bytes: np.ndarray
    saturation_count: int
    outlier_channels: tuple[int, ...]


def encode_vector(vector) -> EncodedVector:
    x = bf16_round(_as_f32(vector).reshape(-1))
    if x.shape != (HEAD_DIM,):
        raise ValueError(f"expected D{HEAD_DIM}, got {x.shape}")
    if not np.all(np.isfinite(x)):
        raise ValueError("the local KV producer accepts finite BF16 K/V only")

    scales = np.zeros(GROUPS, dtype=np.float32)
    q = np.zeros(HEAD_DIM, dtype=np.int8)
    saturation_count = 0
    for group in range(GROUPS):
        start = group * GROUP_SIZE
        stop = start + GROUP_SIZE
        magnitudes = np.abs(x[start:stop])
        robust_maximum = float(np.partition(magnitudes, -2)[-2])
        if robust_maximum == 0.0:
            continue
        scale = float(bf16_round(np.asarray([robust_maximum / QMAX]))[0])
        if scale == 0.0:
            continue
        scales[group] = scale
        unbounded = np.rint(x[start:stop] / scale)
        saturation_count += int(np.count_nonzero((unbounded < QMIN) | (unbounded > QMAX)))
        q[start:stop] = np.clip(unbounded, QMIN, QMAX).astype(np.int8)

    base = q.astype(np.float32) * np.repeat(scales, GROUP_SIZE)
    residual = x - base
    channel = np.arange(HEAD_DIM)
    ranked = np.lexsort((channel, -np.abs(residual)))[:OUTLIERS]
    residual_codes = e5m2_encode(residual[ranked])

    packed = np.zeros(VECTOR_BYTES, dtype=np.uint8)
    low = q[0::2].astype(np.int16) & 0xF
    high = q[1::2].astype(np.int16) & 0xF
    packed[:PACKED_BYTES] = (low | (high << 4)).astype(np.uint8)
    packed[SCALE_OFFSET:INDEX_OFFSET] = bf16_bits(scales).view(np.uint8)
    packed[INDEX_OFFSET:RESIDUAL_OFFSET] = ranked.astype(np.uint8)
    packed[RESIDUAL_OFFSET:VECTOR_BYTES] = residual_codes
    return EncodedVector(
        bytes=packed,
        saturation_count=saturation_count,
        outlier_channels=tuple(int(i) for i in ranked),
    )


def decode_vector(encoded, *, corrected: bool = True) -> np.ndarray:
    row = np.asarray(encoded, dtype=np.uint8).reshape(-1)
    if row.shape != (VECTOR_BYTES,):
        raise ValueError(f"expected {VECTOR_BYTES} bytes, got {row.shape}")
    nibbles = np.empty(HEAD_DIM, dtype=np.uint8)
    nibbles[0::2] = row[:PACKED_BYTES] & np.uint8(0xF)
    nibbles[1::2] = row[:PACKED_BYTES] >> np.uint8(4)
    q = nibbles.astype(np.int16)
    q[q >= 8] -= 16
    scales = bf16_from_bits(row[SCALE_OFFSET:INDEX_OFFSET].view(np.uint16))
    result = q.astype(np.float32) * np.repeat(scales, GROUP_SIZE)
    if corrected:
        indices = row[INDEX_OFFSET:RESIDUAL_OFFSET].astype(np.int64)
        residuals = e5m2_decode(row[RESIDUAL_OFFSET:VECTOR_BYTES])
        result[indices] += residuals
    return result


def error_metrics(reference, candidate) -> dict:
    ref = np.asarray(reference, dtype=np.float64)
    got = np.asarray(candidate, dtype=np.float64)
    delta = got - ref
    ref_norm = float(np.linalg.norm(ref.reshape(-1)))
    got_norm = float(np.linalg.norm(got.reshape(-1)))
    dot = float(np.dot(ref.reshape(-1), got.reshape(-1)))
    return {
        "max_absolute": float(np.max(np.abs(delta))) if delta.size else 0.0,
        "relative_l2": float(np.linalg.norm(delta.reshape(-1)) / max(ref_norm, 1e-30)),
        "cosine": float(dot / max(ref_norm * got_norm, 1e-30)),
        "reference_nonfinite": int(np.count_nonzero(~np.isfinite(ref))),
        "candidate_nonfinite": int(np.count_nonzero(~np.isfinite(got))),
    }


def pack_cache(
    values,
    slots: Iterable[int],
    *,
    capacity: int,
) -> tuple[np.ndarray, dict]:
    source = _as_f32(values)
    if source.ndim != 3 or source.shape[2] != HEAD_DIM:
        raise ValueError("values must have shape [tokens, kv_heads, 256]")
    locations = np.asarray(list(slots), dtype=np.int64)
    if locations.shape != (source.shape[0],):
        raise ValueError("one slot is required per source token")
    cache = np.zeros((capacity, source.shape[1], VECTOR_BYTES), dtype=np.uint8)
    written = 0
    negative_noops = 0
    saturations = 0
    for token, location in enumerate(locations):
        if location < 0:
            negative_noops += 1
            continue
        if location >= capacity:
            raise IndexError(f"slot {location} outside cache capacity {capacity}")
        for head in range(source.shape[1]):
            encoded = encode_vector(source[token, head])
            cache[location, head] = encoded.bytes
            saturations += encoded.saturation_count
        written += 1
    return cache, {
        "written_tokens": written,
        "negative_slot_noops": negative_noops,
        "saturation_count": saturations,
    }


def paged_attention(
    q,
    *,
    q_request,
    q_position,
    cache_k,
    cache_v,
    request_slots,
    key_positions,
    window: int = 1024,
    corrected: bool = True,
) -> np.ndarray:
    query = _as_f32(q)
    if query.ndim != 3 or query.shape[2] != HEAD_DIM:
        raise ValueError("q must have shape [queries, query_heads, 256]")
    q_request = np.asarray(q_request, dtype=np.int64)
    q_position = np.asarray(q_position, dtype=np.int64)
    if q_request.shape != (query.shape[0],) or q_position.shape != (query.shape[0],):
        raise ValueError("query ownership and position must cover every query")
    kv_heads = cache_k.shape[1]
    if query.shape[1] % kv_heads:
        raise ValueError("query heads must be divisible by KV heads")
    gqa_group = query.shape[1] // kv_heads
    output = np.zeros_like(query, dtype=np.float32)
    scale = 1.0 / math.sqrt(HEAD_DIM)

    for query_index in range(query.shape[0]):
        request = int(q_request[query_index])
        slots = np.asarray(request_slots[request], dtype=np.int64)
        positions = np.asarray(key_positions[request], dtype=np.int64)
        if slots.shape != positions.shape:
            raise ValueError("each paged slot must have one logical key position")
        selected = (
            (slots >= 0)
            & (positions <= q_position[query_index])
            & (positions > q_position[query_index] - window)
        )
        for query_head in range(query.shape[1]):
            kv_head = query_head // gqa_group
            running_max = -math.inf
            running_sum = 0.0
            accumulator = np.zeros(HEAD_DIM, dtype=np.float64)
            for slot in slots[selected]:
                key = decode_vector(cache_k[slot, kv_head], corrected=corrected)
                score = float(np.dot(query[query_index, query_head], key) * scale)
                new_max = max(running_max, score)
                old_factor = 0.0 if running_max == -math.inf else math.exp(running_max - new_max)
                probability = math.exp(score - new_max)
                value = decode_vector(cache_v[slot, kv_head], corrected=corrected)
                accumulator = accumulator * old_factor + probability * value
                running_sum = running_sum * old_factor + probability
                running_max = new_max
            if running_sum:
                output[query_index, query_head] = (accumulator / running_sum).astype(
                    np.float32
                )
    return output


def dense_attention_oracle(
    q,
    *,
    q_request,
    q_position,
    dense_k,
    dense_v,
    request_slots,
    key_positions,
    window: int = 1024,
) -> np.ndarray:
    query = _as_f32(q)
    kv_heads = dense_k.shape[1]
    gqa_group = query.shape[1] // kv_heads
    output = np.zeros_like(query, dtype=np.float32)
    scale = 1.0 / math.sqrt(HEAD_DIM)
    for query_index in range(query.shape[0]):
        request = int(q_request[query_index])
        slots = np.asarray(request_slots[request], dtype=np.int64)
        positions = np.asarray(key_positions[request], dtype=np.int64)
        selected = (
            (slots >= 0)
            & (positions <= q_position[query_index])
            & (positions > q_position[query_index] - window)
        )
        for query_head in range(query.shape[1]):
            kv_head = query_head // gqa_group
            keys = dense_k[slots[selected], kv_head].astype(np.float64)
            values = dense_v[slots[selected], kv_head].astype(np.float64)
            scores = keys @ query[query_index, query_head].astype(np.float64) * scale
            scores -= np.max(scores)
            probabilities = np.exp(scores)
            probabilities /= np.sum(probabilities)
            output[query_index, query_head] = probabilities @ values
    return output
