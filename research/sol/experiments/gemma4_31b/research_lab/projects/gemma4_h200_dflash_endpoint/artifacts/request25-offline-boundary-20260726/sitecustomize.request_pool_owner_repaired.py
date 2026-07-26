#!/usr/bin/env python3
"""One-shot request-25 pre-forward/KV/pre-post-logit observer."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import time
from typing import Any

from request25_boundary_probe import (
    input_ids_sha256,
    make_boundary_record,
    request_rows,
    row_major_slice,
    select_request_row,
)

OUTPUT = pathlib.Path(os.environ["REQUEST25_BOUNDARY_CAPTURE"])
SOURCE_BINDING_SHA256 = os.environ["REQUEST25_SOURCE_BINDING_SHA256"]
REQUEST_INDEX = 25
REQUEST_SEMANTIC_SHA256 = (
    "ee2edfa7a9ff571b0268966f506c4cb868868ab880ac87c2684b055d48a0e150"
)
REQUEST_INPUT_IDS_SHA256 = (
    "51a23cdfb44941cb799a80c7ca3fd7f859e8558405f70976d1f8508703f6b360"
)
WORKER_SHA256 = "8fbddb39f4b33b4ac55b1919bc58fa846acb60892886199251d3592a5223050f"
PRE_FORWARD_LINE = 528
RAW_LOGIT_LINE = 537
POST_LOGIT_LINE = 544

SLOT_TO_RID: dict[int, str] = {}
PENDING: dict[str, Any] | None = None
CAPTURED = False
SOURCE_CHECKED = False
TARGET_RID: str | None = None


def _tolist(value: Any) -> list:
    if value is None:
        return []
    if hasattr(value, "detach"):
        return value.detach().cpu().tolist()
    return list(value)


def _atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _fail(exc: BaseException, phase: str) -> None:
    global CAPTURED
    CAPTURED = True
    _atomic_json(
        OUTPUT.with_suffix(".error.json"),
        {
            "schema_version": 1,
            "phase": phase,
            "type": type(exc).__name__,
            "message": str(exc)[:4000],
        },
    )


def _verify_source(filename: str) -> None:
    global SOURCE_CHECKED
    if SOURCE_CHECKED:
        return
    observed = hashlib.sha256(pathlib.Path(filename).read_bytes()).hexdigest()
    if observed != WORKER_SHA256:
        raise RuntimeError(
            f"executed worker hash {observed} differs from {WORKER_SHA256}"
        )
    SOURCE_CHECKED = True


def _logical_ids(batch: Any) -> list[str] | None:
    direct = getattr(batch, "rids", None)
    if direct is not None:
        return [str(value) for value in direct]
    slots = [int(value) for value in _tolist(batch.req_pool_indices)]
    if not all(slot in SLOT_TO_RID for slot in slots):
        return None
    return [SLOT_TO_RID[slot] for slot in slots]


def _kv_digest(pool: Any, locations: list[int]) -> tuple[str, dict[str, Any]]:
    import torch

    started = time.perf_counter()
    valid = [int(location) for location in locations if int(location) >= 0]
    if not valid:
        return hashlib.sha256(b"").hexdigest(), {
            "scheme": "all_prefix_locations_one_coordinate_per_kv_layer_v1",
            "location_count": 0,
            "sampled_values": 0,
            "explicit_cuda_synchronizations": 0,
            "host_transfer_synchronizations": 0,
        }
    location_tensor = torch.tensor(valid, dtype=torch.int64, device=pool.device)
    layer_ids = (
        sorted(int(value) for value in pool.layers_mapping)
        if hasattr(pool, "layers_mapping")
        else list(range(int(pool.layer_num)))
    )
    samples = []
    for layer_id in layer_ids:
        layer_locations = location_tensor
        if (
            hasattr(pool, "layers_mapping")
            and bool(pool.layers_mapping[layer_id][1])
            and hasattr(pool, "translate_loc_from_full_to_swa")
        ):
            layer_locations = pool.translate_loc_from_full_to_swa(location_tensor)
        key = pool.get_key_buffer(layer_id)
        value = pool.get_value_buffer(layer_id)
        head = layer_id % int(key.shape[-2])
        key_dim = (layer_id * 131) % int(key.shape[-1])
        value_dim = (layer_id * 137) % int(value.shape[-1])
        samples.append(key[layer_locations, head, key_dim].view(-1))
        samples.append(value[layer_locations, head, value_dim].view(-1))
    packed = torch.stack(samples, dim=0).contiguous().view(torch.uint8).cpu()
    raw = packed.numpy().tobytes()
    return hashlib.sha256(raw).hexdigest(), {
        "scheme": "all_prefix_locations_one_coordinate_per_kv_layer_v1",
        "layer_count": len(layer_ids),
        "location_count": len(valid),
        "sampled_values": len(samples) * len(valid),
        "sampled_bytes": len(raw),
        "elapsed_ms": (time.perf_counter() - started) * 1000.0,
        "explicit_cuda_synchronizations": 0,
        "host_transfer_synchronizations": 1,
    }


def _capture_pre(locals_: dict[str, Any]) -> None:
    global PENDING
    batch = locals_["model_worker_batch"]
    forward = locals_["verify_forward_batch"]
    slots = [int(value) for value in _tolist(batch.req_pool_indices)]
    ids = _logical_ids(batch)
    if TARGET_RID is None:
        return
    selected = select_request_row(ids, slots, TARGET_RID)
    if selected is None:
        return
    row, slot = selected
    rows = int(locals_["bs"])
    width = int(locals_["self"].block_size)
    if row >= rows:
        raise ValueError("logical request row exceeds verify batch size")

    input_ids = row_major_slice(
        _tolist(forward.input_ids),
        row=row,
        rows=rows,
        width=width,
        field="input_ids",
    )
    positions = row_major_slice(
        _tolist(forward.positions),
        row=row,
        rows=rows,
        width=width,
        field="positions",
    )
    out_cache_loc = row_major_slice(
        _tolist(forward.out_cache_loc),
        row=row,
        rows=rows,
        width=width,
        field="out_cache_loc",
    )
    seq_lens = [int(value) for value in _tolist(forward.seq_lens)][:rows]
    seq_lens_cpu = [int(value) for value in _tolist(forward.seq_lens_cpu)][:rows]
    if len(seq_lens) != rows or len(seq_lens_cpu) != rows:
        raise ValueError("sequence-length vectors do not match verify rows")
    seq_len = seq_lens[row]
    seq_len_cpu = seq_lens_cpu[row]
    worker = locals_["self"]
    req_to_token = worker.target_worker.model_runner.req_to_token_pool.req_to_token
    prefix = [
        int(value)
        for value in _tolist(req_to_token[slot, :seq_len])
    ]
    kv_sha256, kv_stats = _kv_digest(
        worker.target_worker.model_runner.token_to_kv_pool,
        prefix,
    )
    PENDING = {
        "request_id": TARGET_RID,
        "request_row": row,
        "request_slot": slot,
        "input_ids": input_ids,
        "positions": positions,
        "seq_len": seq_len,
        "seq_len_cpu": seq_len_cpu,
        "out_cache_loc": out_cache_loc,
        "req_to_token_prefix": prefix,
        "pre_forward_kv_sha256": kv_sha256,
        "kv_digest_stats": kv_stats,
        "flat_logit_row": row * width,
    }


def _top1(logits: Any, flat_row: int) -> int:
    return int(logits[flat_row].argmax(dim=-1).detach().cpu().item())


def _capture_raw(locals_: dict[str, Any]) -> None:
    if PENDING is None:
        return
    logits = locals_["logits_output"].next_token_logits
    PENDING["raw_first_position_top1"] = _top1(
        logits, int(PENDING["flat_logit_row"])
    )


def _capture_post(locals_: dict[str, Any]) -> None:
    global CAPTURED
    if PENDING is None:
        return
    if "raw_first_position_top1" not in PENDING:
        raise RuntimeError("post-adjustment boundary reached before raw boundary")
    logits = locals_["logits_output"].next_token_logits
    post = _top1(logits, int(PENDING["flat_logit_row"]))
    fields = dict(PENDING)
    fields.pop("flat_logit_row")
    record = make_boundary_record(
        **fields,
        request_index=REQUEST_INDEX,
        request_semantic_sha256=REQUEST_SEMANTIC_SHA256,
        request_input_ids_sha256=REQUEST_INPUT_IDS_SHA256,
        post_adjustment_first_position_top1=post,
        source_binding_sha256=SOURCE_BINDING_SHA256,
    )
    _atomic_json(OUTPUT, record)
    CAPTURED = True


def _trace(frame, event, arg):
    global TARGET_RID
    if CAPTURED:
        return _trace
    try:
        if event == "return" and frame.f_code.co_name == "from_schedule_batch":
            schedule = frame.f_locals.get("batch")
            if schedule is not None and arg is not None:
                reqs = getattr(schedule, "reqs", None)
                raw_slots = getattr(schedule, "req_pool_indices", None)
                if reqs is not None and raw_slots is not None:
                    slots = [int(value) for value in _tolist(raw_slots)]
                    rids = [str(getattr(req, "rid")) for req in reqs]
                    request25_rids = [
                        str(getattr(req, "rid"))
                        for req in reqs
                        if input_ids_sha256(getattr(req, "origin_input_ids"))
                        == REQUEST_INPUT_IDS_SHA256
                    ]
                    if len(request25_rids) > 1:
                        raise ValueError("request-25 input identity appears twice")
                    if request25_rids:
                        observed_rid = request25_rids[0]
                        if TARGET_RID is not None and TARGET_RID != observed_rid:
                            raise ValueError("request-25 logical RID changed")
                        TARGET_RID = observed_rid
                    if len(slots) == len(rids) and all(rids):
                        SLOT_TO_RID.update(dict(zip(slots, rids, strict=True)))
                        if getattr(arg, "rids", None) is None:
                            arg.rids = list(rids)
            return _trace
        if (
            event != "line"
            or frame.f_code.co_name != "forward_batch_generation"
            or not frame.f_code.co_filename.endswith(
                "/speculative/dflash_worker_v2.py"
            )
        ):
            return _trace
        _verify_source(frame.f_code.co_filename)
        if frame.f_lineno == PRE_FORWARD_LINE:
            _capture_pre(frame.f_locals)
        elif frame.f_lineno == RAW_LOGIT_LINE:
            _capture_raw(frame.f_locals)
        elif frame.f_lineno == POST_LOGIT_LINE:
            _capture_post(frame.f_locals)
    except Exception as exc:
        _fail(exc, f"{pathlib.Path(frame.f_code.co_filename).name}:{frame.f_lineno}")
    return _trace


sys.settrace(_trace)
