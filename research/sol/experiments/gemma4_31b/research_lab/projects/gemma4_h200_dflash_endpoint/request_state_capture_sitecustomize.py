#!/usr/bin/env python3
"""Read-only exact-c32 target/DFlash state capture installed as sitecustomize."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import time
from typing import Any

from request_state_observer import make_event, request_rows, split_by_lengths

OUTPUT = pathlib.Path(os.environ["REQUEST_STATE_CAPTURE"])
ARM = os.environ["REQUEST_STATE_ARM"]
PREFILL_CAPTURED: set[str] = set()
FIRST_STEP_CAPTURED: set[str] = set()


def _tolist(value: Any) -> list:
    if value is None:
        return []
    if hasattr(value, "detach"):
        return value.detach().cpu().tolist()
    return list(value)


def _append(value: dict[str, Any]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("a") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def _observer_error(exc: BaseException, phase: str) -> None:
    path = OUTPUT.with_suffix(".observer-error")
    with path.open("a") as handle:
        handle.write(
            json.dumps(
                {
                    "phase": phase,
                    "type": type(exc).__name__,
                    "message": str(exc)[:4000],
                },
                sort_keys=True,
            )
            + "\n"
        )


def _request_rows(batch: Any) -> list[tuple[int, int, str]]:
    slots = [int(value) for value in _tolist(batch.req_pool_indices)]
    return request_rows(getattr(batch, "rids", None), slots)


def _extend_lengths(batch: Any) -> list[int]:
    lengths = getattr(batch, "extend_seq_lens_cpu", None)
    if lengths is None:
        lengths = getattr(batch, "extend_lens", None)
    if lengths is None:
        raise ValueError("extend lengths are unavailable")
    return [int(value) for value in _tolist(lengths)][: len(batch.rids)]


def _hash_plane_segments(
    raw: bytes,
    *,
    layer_planes: int,
    flat_count: int,
    sample_itemsize: int,
    offsets: list[tuple[int, int]],
) -> list[str]:
    row_width_bytes = flat_count * sample_itemsize
    plane = memoryview(raw)
    digests = []
    for start, end in offsets:
        digest = hashlib.sha256()
        for layer_plane in range(layer_planes):
            base = layer_plane * row_width_bytes
            digest.update(
                plane[
                    base + start * sample_itemsize :
                    base + end * sample_itemsize
                ]
            )
        digests.append(digest.hexdigest())
    return digests


def _kv_digests(
    pool: Any,
    location_rows: list[list[int]],
) -> tuple[list[str], dict[str, Any]]:
    import torch

    started = time.perf_counter()
    valid_rows = [[int(loc) for loc in row if int(loc) >= 0] for row in location_rows]
    flat = [loc for row in valid_rows for loc in row]
    if not flat:
        empty = hashlib.sha256(b"").hexdigest()
        return [empty for _ in valid_rows], {
            "scheme": "all_locations_one_coordinate_per_kv_layer_v1",
            "sampled_values": 0,
            "elapsed_ms": 0.0,
            "explicit_cuda_synchronizations": 0,
        }
    locations = torch.tensor(flat, dtype=torch.int64, device=pool.device)
    layer_ids = (
        sorted(int(value) for value in pool.layers_mapping)
        if hasattr(pool, "layers_mapping")
        else list(range(int(pool.layer_num)))
    )
    samples = []
    for layer_id in layer_ids:
        layer_locations = locations
        if (
            hasattr(pool, "layers_mapping")
            and bool(pool.layers_mapping[layer_id][1])
            and hasattr(pool, "translate_loc_from_full_to_swa")
        ):
            layer_locations = pool.translate_loc_from_full_to_swa(locations)
        key = pool.get_key_buffer(layer_id)
        value = pool.get_value_buffer(layer_id)
        head = layer_id % int(key.shape[-2])
        key_dim = (layer_id * 131) % int(key.shape[-1])
        value_dim = (layer_id * 137) % int(value.shape[-1])
        samples.append(key[layer_locations, head, key_dim].view(-1))
        samples.append(value[layer_locations, head, value_dim].view(-1))
    sample_itemsize = samples[0].element_size()
    packed = torch.stack(samples, dim=0).contiguous().view(torch.uint8).cpu()
    raw = packed.numpy().tobytes()
    layer_planes = len(samples)
    offsets = []
    cursor = 0
    for row in valid_rows:
        offsets.append((cursor, cursor + len(row)))
        cursor += len(row)
    digests = _hash_plane_segments(
        raw,
        layer_planes=layer_planes,
        flat_count=len(flat),
        sample_itemsize=sample_itemsize,
        offsets=offsets,
    )
    return digests, {
        "scheme": "all_locations_one_coordinate_per_kv_layer_v1",
        "layer_count": len(layer_ids),
        "location_count": len(flat),
        "sampled_values": len(samples) * len(flat),
        "sampled_bytes": len(raw),
        "elapsed_ms": (time.perf_counter() - started) * 1000.0,
        "explicit_cuda_synchronizations": 0,
        "host_transfer_synchronizations": 1,
    }


def _split_locations(values: list[int], lengths: list[int]) -> list[list[int]]:
    # ForwardBatch pads out_cache_loc to the graph token count, while the host
    # extend lengths remain the exact actual-request token counts.
    actual_count = sum(lengths)
    return split_by_lengths(
        [int(value) for value in values[:actual_count]],
        lengths,
    )


def _capture_prefill(batch: Any, result: Any, worker: Any) -> None:
    rows = _request_rows(batch)
    if not rows:
        return
    next_ids = [int(value) for value in _tolist(result.next_token_ids)]
    logits = result.logits_output.next_token_logits
    top1 = [int(value) for value in _tolist(logits.argmax(dim=-1))]
    seq_after = [int(value) for value in _tolist(batch.seq_lens)]
    prefix = getattr(batch, "prefix_lens", None)
    seq_before = (
        [int(value) for value in _tolist(prefix)]
        if prefix is not None
        else [0 for _ in seq_after]
    )
    lengths = _extend_lengths(batch)
    locations = _split_locations(_tolist(batch.out_cache_loc), lengths)
    selected_locations = [locations[row] for row, _, _ in rows]
    digests, digest_stats = _kv_digests(
        worker.model_runner.token_to_kv_pool, selected_locations
    )
    for selected, ((row, slot, request_id), digest) in enumerate(
        zip(rows, digests, strict=True)
    ):
        if request_id in PREFILL_CAPTURED:
            continue
        event = make_event(
            arm=ARM,
            phase="target_prefill",
            request_id=request_id,
            request_slot=slot,
            sequence_length_before=seq_before[row],
            sequence_length_after=seq_after[row],
            kv_locations=selected_locations[selected],
            kv_content_sha256=digest,
            payload={
                "target_prefill_output": next_ids[row],
                "target_top1": top1[row],
                "target_output_matches_top1": next_ids[row] == top1[row],
                "prompt_cache_accounting": {
                    "prefix_tokens": seq_before[row],
                    "fresh_tokens": lengths[row],
                    "total_tokens": seq_after[row],
                },
                "kv_digest_stats": digest_stats,
            },
        )
        _append(event)
        PREFILL_CAPTURED.add(request_id)


def _capture_ar_first_step(batch: Any, result: Any, worker: Any) -> None:
    rows = [
        item
        for item in _request_rows(batch)
        if item[2] not in FIRST_STEP_CAPTURED
    ]
    if not rows:
        return
    next_ids = [int(value) for value in _tolist(result.next_token_ids)]
    top1 = [
        int(value)
        for value in _tolist(result.logits_output.next_token_logits.argmax(dim=-1))
    ]
    seq_after = [int(value) for value in _tolist(batch.seq_lens)]
    all_locations = [int(value) for value in _tolist(batch.out_cache_loc)]
    location_rows = [[all_locations[row]] for row, _, _ in rows]
    digests, digest_stats = _kv_digests(
        worker.model_runner.token_to_kv_pool, location_rows
    )
    input_ids = [int(value) for value in _tolist(batch.input_ids)]
    for selected, ((row, slot, request_id), digest) in enumerate(
        zip(rows, digests, strict=True)
    ):
        event = make_event(
            arm=ARM,
            phase="first_target_step",
            request_id=request_id,
            request_slot=slot,
            sequence_length_before=seq_after[row] - 1,
            sequence_length_after=seq_after[row],
            kv_locations=location_rows[selected],
            kv_content_sha256=digest,
            payload={
                "verified_id": input_ids[row],
                "target_top1": top1[row],
                "bonus_token": next_ids[row],
                "accepted_prefix": [],
                "emitted_stream_tokens": [next_ids[row]],
                "target_output_matches_top1": next_ids[row] == top1[row],
                "kv_digest_stats": digest_stats,
            },
        )
        _append(event)
        FIRST_STEP_CAPTURED.add(request_id)


def _capture_dflash_first_step(locals_: dict[str, Any]) -> None:
    batch = locals_["model_worker_batch"]
    rows = [
        item
        for item in _request_rows(batch)
        if item[2] not in FIRST_STEP_CAPTURED
    ]
    if not rows or "target_predict" not in locals_:
        return
    target = _tolist(locals_["target_predict"])
    candidates = _tolist(locals_["candidates"])
    accept = [int(value) for value in _tolist(locals_["accept_len"])]
    commit = [int(value) for value in _tolist(locals_["commit_lens"])]
    bonus = [int(value) for value in _tolist(locals_["bonus"])]
    emitted = _tolist(locals_["out_tokens"])
    prefix = [int(value) for value in _tolist(locals_["prefix_lens"])]
    new_seq = [int(value) for value in _tolist(locals_["new_seq_lens"])]
    locations_2d = _tolist(locals_["verify_out_cache_loc_2d"])
    location_rows = [
        [int(value) for value in locations_2d[row][: commit[row]]]
        for row, _, _ in rows
    ]
    worker = locals_["self"]
    digests, digest_stats = _kv_digests(
        worker.target_worker.model_runner.token_to_kv_pool, location_rows
    )
    for selected, ((row, slot, request_id), digest) in enumerate(
        zip(rows, digests, strict=True)
    ):
        accepted = accept[row]
        event = make_event(
            arm=ARM,
            phase="first_target_step",
            request_id=request_id,
            request_slot=slot,
            sequence_length_before=prefix[row],
            sequence_length_after=new_seq[row],
            kv_locations=location_rows[selected],
            kv_content_sha256=digest,
            payload={
                "verified_id": int(candidates[row][0]),
                "target_top1": [int(value) for value in target[row]],
                "draft_tokens": [int(value) for value in candidates[row]],
                "accepted_prefix": [
                    int(value) for value in candidates[row][1 : 1 + accepted]
                ],
                "accepted_draft_count": accepted,
                "bonus_token": bonus[row],
                "emitted_stream_tokens": [
                    int(value) for value in emitted[row][: commit[row]]
                ],
                "commit_length": commit[row],
                "kv_digest_stats": digest_stats,
            },
        )
        _append(event)
        FIRST_STEP_CAPTURED.add(request_id)


def _trace(frame, event, arg):
    if event != "return" or frame.f_code.co_name != "forward_batch_generation":
        return _trace
    filename = frame.f_code.co_filename
    try:
        if filename.endswith("/managers/tp_worker.py"):
            batch = frame.f_locals.get("batch")
            if batch is None or arg is None:
                return _trace
            forward_mode = getattr(batch, "forward_mode", None)
            if forward_mode is not None and forward_mode.is_extend():
                _capture_prefill(batch, arg, frame.f_locals["self"])
            elif ARM == "ar-c32" and forward_mode is not None and forward_mode.is_decode():
                _capture_ar_first_step(batch, arg, frame.f_locals["self"])
        elif (
            ARM == "dflash-depth4-c32"
            and filename.endswith("/speculative/dflash_worker_v2.py")
            and "target_predict" in frame.f_locals
        ):
            _capture_dflash_first_step(frame.f_locals)
    except Exception as exc:
        _observer_error(exc, pathlib.Path(filename).name)
    return _trace


sys.settrace(_trace)
