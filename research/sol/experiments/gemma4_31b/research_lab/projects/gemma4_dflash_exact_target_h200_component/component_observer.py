#!/usr/bin/env python3
"""Fail-isolated exact DFlash/AR/NGRAM component observer for SGLang f63458b5."""

from __future__ import annotations

import functools
import hashlib
import json
import os
import pathlib
import threading
import time
import traceback
from typing import Any, Callable

BLOCK_SIZE = 16
_INSTALLED = False
_LOCK = threading.Lock()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def tensor_list(value: Any) -> list[Any]:
    return value.detach().to("cpu").tolist()


def tensor_digest(value: Any) -> str:
    tensor = value.detach().contiguous().to("cpu")
    payload = tensor.numpy().tobytes()
    identity = {
        "dtype": str(tensor.dtype),
        "shape": list(tensor.shape),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
    return hashlib.sha256(canonical(identity)).hexdigest()


def interval_union_ms(intervals: list[dict[str, Any]]) -> float:
    ordered = sorted(
        (float(row["start_ms"]), float(row["end_ms"])) for row in intervals
    )
    total = 0.0
    current_start = None
    current_end = None
    for start, end in ordered:
        if end < start:
            raise ValueError("negative CUDA interval")
        if current_start is None:
            current_start, current_end = start, end
        elif start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    if current_start is not None:
        total += current_end - current_start
    return total


class Recorder:
    def __init__(self) -> None:
        self.root = pathlib.Path(os.environ["DFLASH_COMPONENT_OBSERVER_ROOT"])
        self.arm = os.environ["DFLASH_COMPONENT_ARM"]
        self.generation = os.environ["DFLASH_COMPONENT_GENERATION"]
        self.root.mkdir(parents=True, exist_ok=True)
        self.rows_path = self.root / f"observer-{os.getpid()}.jsonl"
        self.diagnostic = self.root / "OBSERVER_DIAGNOSTIC.json"
        self.disabled = False
        self.round_index = 0
        self.pending: dict[str, dict[str, Any]] = {}

    def append(self, row: dict[str, Any]) -> None:
        payload = canonical(row) + b"\n"
        with _LOCK:
            descriptor = os.open(
                self.rows_path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o644,
            )
            try:
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def fail(self, where: str, error: BaseException) -> None:
        self.disabled = True
        if self.diagnostic.exists():
            return
        atomic(
            self.diagnostic,
            {
                "schema_version": 1,
                "classification": "observer_integration_defect",
                "arm": self.arm,
                "generation": self.generation,
                "where": where,
                "error": f"{type(error).__name__}: {error}",
                "traceback": traceback.format_exc()[-12000:],
                "pid": os.getpid(),
                "created_unix_s": time.time(),
            },
        )


class CudaIntervals:
    def __init__(self, torch_module: Any) -> None:
        self.torch = torch_module
        self.origin = torch_module.cuda.Event(enable_timing=True)
        self.origin.record()
        self.events: list[tuple[str, Any, Any]] = []

    def wrap(self, phase: str, function: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(function)
        def measured(*args: Any, **kwargs: Any) -> Any:
            start = self.torch.cuda.Event(enable_timing=True)
            end = self.torch.cuda.Event(enable_timing=True)
            start.record()
            try:
                return function(*args, **kwargs)
            finally:
                end.record()
                self.events.append((phase, start, end))

        return measured

    def materialize(self) -> tuple[list[dict[str, Any]], float]:
        self.torch.cuda.synchronize()
        rows = [
            {
                "phase": phase,
                "start_ms": self.origin.elapsed_time(start),
                "end_ms": self.origin.elapsed_time(end),
                "duration_ms": start.elapsed_time(end),
            }
            for phase, start, end in self.events
        ]
        return rows, interval_union_ms(rows)


def rid_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def install_dflash(recorder: Recorder, torch: Any) -> None:
    import sglang.srt.speculative.dflash_worker_v2 as module

    original = module.DFlashWorkerV2.forward_batch_generation

    @functools.wraps(original)
    def observed(self: Any, batch: Any, on_publish: Any = None) -> Any:
        if (
            recorder.disabled
            or batch.forward_mode.is_extend()
            or batch.forward_mode.is_idle()
            or batch.is_extend_in_batch
        ):
            return original(self, batch, on_publish=on_publish)
        recorder.round_index += 1
        round_index = recorder.round_index
        intervals = CudaIntervals(torch)
        host_start = time.monotonic_ns()
        captured: dict[str, Any] = {}
        prefix_lens = batch.seq_lens.detach().clone()

        draft_forward = self.draft_model_runner.forward
        draft_sample = self._greedy_sample_from_vocab_parallel_head
        target_forward = self.target_worker.forward_batch_generation
        append_kv = self._append_target_hidden_to_draft_kv_by_loc
        eager_accept = module.compute_dflash_correct_drafts_and_bonus
        triton_accept = module._compute_dflash_accept_bonus_triton_unchecked
        prepare_block = module._prepare_dflash_draft_block_unchecked
        embed_module = (
            self.target_worker.model_runner.model.get_input_embeddings()
        )
        embed_forward = embed_module.forward

        def target_measured(*args: Any, **kwargs: Any) -> Any:
            forward_batch = kwargs.get("forward_batch")
            result = intervals.wrap("target_verify", target_forward)(*args, **kwargs)
            if kwargs.get("is_verify") and forward_batch is not None:
                captured["forward_batch"] = forward_batch
            return result

        def accept_eager(*args: Any, **kwargs: Any) -> Any:
            target = kwargs.get("target_predict")
            if target is not None:
                captured["target_top1"] = target.detach().clone()
            return intervals.wrap("acceptance", eager_accept)(*args, **kwargs)

        def accept_triton(*args: Any, **kwargs: Any) -> Any:
            target = kwargs.get("target_top1")
            if target is not None:
                captured["target_top1"] = target.detach().clone()
            return intervals.wrap("acceptance", triton_accept)(*args, **kwargs)

        self.draft_model_runner.forward = intervals.wrap("draft", draft_forward)
        self._greedy_sample_from_vocab_parallel_head = intervals.wrap(
            "draft", draft_sample
        )
        embed_module.forward = intervals.wrap("draft", embed_forward)
        self.target_worker.forward_batch_generation = target_measured
        self._append_target_hidden_to_draft_kv_by_loc = intervals.wrap(
            "kv_commit", append_kv
        )
        module.compute_dflash_correct_drafts_and_bonus = accept_eager
        module._compute_dflash_accept_bonus_triton_unchecked = accept_triton
        module._prepare_dflash_draft_block_unchecked = intervals.wrap(
            "draft", prepare_block
        )
        try:
            result = original(self, batch, on_publish=on_publish)
            host_end = time.monotonic_ns()
            phase_rows, union_ms = intervals.materialize()
            forward_batch = captured["forward_batch"]
            rids = list(forward_batch.rids)
            physical = tensor_list(forward_batch.req_pool_indices.view(-1))
            candidates = forward_batch.spec_info.draft_token.view(-1, BLOCK_SIZE)
            target_top1 = captured["target_top1"].view(-1, BLOCK_SIZE)
            commit_lens = result.accept_lens.view(-1).to(torch.int64)
            new_seq_lens = result.new_seq_lens.view(-1).to(torch.int64)
            out_tokens = result.next_token_ids.view(-1, BLOCK_SIZE)
            req_to_token = (
                self.target_worker.model_runner.req_to_token_pool.req_to_token
            )
            for row_index, rid_value in enumerate(rids):
                rid = rid_text(rid_value)
                slot = int(physical[row_index])
                prefix_len = int(prefix_lens[row_index].item())
                commit_len = int(commit_lens[row_index].item())
                accepted = commit_len - 1
                new_len = int(new_seq_lens[row_index].item())
                candidate_row = candidates[row_index]
                target_row = target_top1[row_index]
                bonus = int(target_row[accepted].item())
                first_mismatch = None if accepted == BLOCK_SIZE - 1 else accepted
                committed_slots = req_to_token[slot, :new_len]
                previous = recorder.pending.get(rid)
                next_round = None
                if previous is not None:
                    next_round = {
                        "prior_bonus_token": previous["bonus_token"],
                        "prior_acceptance_category": previous[
                            "acceptance_category"
                        ],
                        "current_token": int(candidate_row[0].item()),
                        "pending_bonus_is_current": (
                            previous["bonus_token"] == int(candidate_row[0].item())
                        ),
                        "prior_new_seq_len": previous["new_seq_len"],
                        "current_prefix_len": prefix_len,
                        "committed_length_continuity": (
                            previous["new_seq_len"] == prefix_len
                        ),
                        "prior_committed_kv_digest": previous["committed_kv_digest"],
                        "current_prefix_kv_digest": tensor_digest(
                            req_to_token[slot, :prefix_len]
                        ),
                        "kv_prefix_stable": (
                            previous["committed_kv_digest"]
                            == tensor_digest(req_to_token[slot, :prefix_len])
                        ),
                        "first_next_round_target_top1": int(target_row[0].item()),
                    }
                committed_digest = tensor_digest(committed_slots)
                recorder.pending[rid] = {
                    "bonus_token": bonus,
                    "new_seq_len": new_len,
                    "committed_kv_digest": committed_digest,
                    "acceptance_category": (
                        "zero"
                        if accepted == 0
                        else "full"
                        if accepted == BLOCK_SIZE - 1
                        else "partial"
                    ),
                }
                recorder.append(
                    {
                        "schema_version": 1,
                        "arm": "dflash",
                        "generation": recorder.generation,
                        "round_index": round_index,
                        "row_index": row_index,
                        "logical_request_id_source": "ForwardBatch.rids[row]",
                        "logical_request_id": rid,
                        "physical_request_pool_index_source": (
                            "ForwardBatch.req_pool_indices[row]"
                        ),
                        "physical_request_pool_index": slot,
                        "kv_table_source": (
                            "target_worker.model_runner.req_to_token_pool.req_to_token"
                        ),
                        "block_size_including_current": BLOCK_SIZE,
                        "proposed_drafts": BLOCK_SIZE - 1,
                        "accepted_drafts": accepted,
                        "commit_len": commit_len,
                        "first_mismatch": first_mismatch,
                        "candidate_tokens": tensor_list(candidate_row),
                        "target_top1": tensor_list(target_row),
                        "emitted_tokens": tensor_list(out_tokens[row_index, :commit_len]),
                        "bonus_token": bonus,
                        "prefix_seq_len": prefix_len,
                        "new_seq_len": new_len,
                        "committed_kv_slots": tensor_list(
                            req_to_token[slot, prefix_len:new_len]
                        ),
                        "committed_kv_digest": committed_digest,
                        "next_round_audit": next_round,
                        "cuda_intervals_ms": phase_rows,
                        "cuda_interval_union_ms": union_ms,
                        "host_outer_seconds": (host_end - host_start) / 1e9,
                    }
                )
            return result
        except Exception as error:
            recorder.fail("DFlashWorkerV2.forward_batch_generation", error)
            raise
        finally:
            self.draft_model_runner.forward = draft_forward
            self._greedy_sample_from_vocab_parallel_head = draft_sample
            embed_module.forward = embed_forward
            self.target_worker.forward_batch_generation = target_forward
            self._append_target_hidden_to_draft_kv_by_loc = append_kv
            module.compute_dflash_correct_drafts_and_bonus = eager_accept
            module._compute_dflash_accept_bonus_triton_unchecked = triton_accept
            module._prepare_dflash_draft_block_unchecked = prepare_block

    module.DFlashWorkerV2.forward_batch_generation = observed


def install_ngram(recorder: Recorder, torch: Any) -> None:
    import sglang.srt.speculative.ngram_worker as module

    original = module.NGRAMWorker.forward_batch_generation

    @functools.wraps(original)
    def observed(self: Any, batch: Any, on_publish: Any = None) -> Any:
        if recorder.disabled or not batch.forward_mode.is_decode():
            return original(self, batch, on_publish=on_publish)
        recorder.round_index += 1
        intervals = CudaIntervals(torch)
        host_start = time.monotonic_ns()
        target_forward = self.target_worker.forward_batch_generation
        prepare = self._prepare_for_speculative_decoding
        move = module.move_accept_tokens_to_target_kvcache
        accept = module.eagle_sample
        self.target_worker.forward_batch_generation = intervals.wrap(
            "target_verify", target_forward
        )
        self._prepare_for_speculative_decoding = intervals.wrap(
            "ngram_proposal", prepare
        )
        module.move_accept_tokens_to_target_kvcache = intervals.wrap("kv_commit", move)
        module.eagle_sample = intervals.wrap("acceptance", accept)
        try:
            result = original(self, batch, on_publish=on_publish)
            host_end = time.monotonic_ns()
            phase_rows, union_ms = intervals.materialize()
            commit_lens = tensor_list(result.accept_lens.view(-1))
            for row_index, req in enumerate(batch.reqs):
                recorder.append(
                    {
                        "schema_version": 1,
                        "arm": "ngram",
                        "generation": recorder.generation,
                        "round_index": recorder.round_index,
                        "row_index": row_index,
                        "logical_request_id": rid_text(req.rid),
                        "block_size_including_current": BLOCK_SIZE,
                        "proposed_drafts": BLOCK_SIZE - 1,
                        "accepted_drafts": int(commit_lens[row_index]) - 1,
                        "commit_len": int(commit_lens[row_index]),
                        "cuda_intervals_ms": phase_rows,
                        "cuda_interval_union_ms": union_ms,
                        "host_outer_seconds": (host_end - host_start) / 1e9,
                    }
                )
            return result
        except Exception as error:
            recorder.fail("NGRAMWorker.forward_batch_generation", error)
            raise
        finally:
            self.target_worker.forward_batch_generation = target_forward
            self._prepare_for_speculative_decoding = prepare
            module.move_accept_tokens_to_target_kvcache = move
            module.eagle_sample = accept

    module.NGRAMWorker.forward_batch_generation = observed


def install_ar(recorder: Recorder, torch: Any) -> None:
    import sglang.srt.managers.tp_worker as module

    original = module.TpModelWorker.forward_batch_generation

    @functools.wraps(original)
    def observed(self: Any, batch: Any = None, *args: Any, **kwargs: Any) -> Any:
        if recorder.disabled or batch is None or not batch.forward_mode.is_decode():
            return original(self, batch, *args, **kwargs)
        recorder.round_index += 1
        intervals = CudaIntervals(torch)
        host_start = time.monotonic_ns()
        try:
            result = intervals.wrap("target_decode", original)(
                self, batch, *args, **kwargs
            )
            host_end = time.monotonic_ns()
            phase_rows, union_ms = intervals.materialize()
            for row_index, req in enumerate(batch.reqs):
                recorder.append(
                    {
                        "schema_version": 1,
                        "arm": "ar",
                        "generation": recorder.generation,
                        "round_index": recorder.round_index,
                        "row_index": row_index,
                        "logical_request_id": rid_text(req.rid),
                        "proposed_drafts": 0,
                        "accepted_drafts": 0,
                        "commit_len": 1,
                        "cuda_intervals_ms": phase_rows,
                        "cuda_interval_union_ms": union_ms,
                        "host_outer_seconds": (host_end - host_start) / 1e9,
                    }
                )
            return result
        except Exception as error:
            recorder.fail("TpModelWorker.forward_batch_generation", error)
            raise

    module.TpModelWorker.forward_batch_generation = observed


def install() -> None:
    global _INSTALLED
    if _INSTALLED or "DFLASH_COMPONENT_OBSERVER_ROOT" not in os.environ:
        return
    _INSTALLED = True
    try:
        import torch

        recorder = Recorder()
        if recorder.arm == "dflash":
            install_dflash(recorder, torch)
        elif recorder.arm == "ngram":
            install_ngram(recorder, torch)
        elif recorder.arm == "ar":
            install_ar(recorder, torch)
        else:
            raise ValueError(f"unknown observer arm: {recorder.arm}")
    except Exception as error:
        root = pathlib.Path(
            os.environ.get("DFLASH_COMPONENT_OBSERVER_ROOT", "/tmp")
        )
        root.mkdir(parents=True, exist_ok=True)
        atomic(
            root / "OBSERVER_DIAGNOSTIC.json",
            {
                "schema_version": 1,
                "classification": "observer_install_defect",
                "error": f"{type(error).__name__}: {error}",
                "traceback": traceback.format_exc()[-12000:],
                "pid": os.getpid(),
            },
        )
