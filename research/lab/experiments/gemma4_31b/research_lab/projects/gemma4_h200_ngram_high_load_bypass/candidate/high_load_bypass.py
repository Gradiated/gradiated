from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time

import torch


TREE_DEPTH = 12
HIGH_LOAD_MIN_REQUESTS = 8
OUT = Path(os.environ.get("HIGH_LOAD_BYPASS_OUT", "/work/out"))
EVENT_LOCK = threading.Lock()


def append_event(value: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    with EVENT_LOCK:
        descriptor = os.open(
            OUT / "HIGH_LOAD_BYPASS_EVENTS.jsonl",
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o644,
        )
        try:
            os.write(descriptor, raw)
        finally:
            os.close(descriptor)


def atomic_once(name: str, value: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    if path.exists():
        return
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def install() -> None:
    from sglang.srt.speculative.ngram_worker import NGRAMWorker
    from sglang.srt.speculative.spec_info import SpeculativeAlgorithm

    original_forward = NGRAMWorker.forward_batch_generation

    def clear_match_state(worker: NGRAMWorker, batch, reason: str) -> None:
        request_ids = [request.rid for request in batch.reqs]
        if request_ids:
            worker.ngram_corpus.erase_match_state(request_ids)
        append_event(
            {
                "schema_version": 1,
                "kind": "transition",
                "reason": reason,
                "batch_size": batch.batch_size(),
                "match_state_action": "erase_then_rebuild_from_authoritative_request_tokens_on_ngram_reentry",
                "request_ids": [str(value) for value in request_ids],
            }
        )

    def bypass_forward(self: NGRAMWorker, batch):
        if batch.forward_mode.is_extend():
            return original_forward(self, batch)

        batch_size = batch.batch_size()
        bypass = batch_size >= HIGH_LOAD_MIN_REQUESTS
        prior = getattr(self, "_high_load_bypass_active", False)
        entering_bypass = bypass and not prior
        if bypass != prior:
            clear_match_state(
                self,
                batch,
                "enter_high_load_bypass" if bypass else "reenter_depth_12_ngram",
            )
        self._high_load_bypass_active = bypass

        if not bypass:
            started = time.perf_counter()
            result = original_forward(self, batch)
            append_event(
                {
                    "schema_version": 1,
                    "kind": "decode_step",
                    "mode": "depth_12_ngram",
                    "batch_size": batch_size,
                    "target_rows": batch_size * TREE_DEPTH,
                    "target_forward_wall_ms": (
                        time.perf_counter() - started
                    )
                    * 1000,
                    "num_correct_drafts": (
                        result.num_correct_drafts_per_req_cpu or []
                    ),
                    "cache_owner": "ngram_verify_accept_slots",
                    "match_state": "authoritative_request_token_reentry",
                }
            )
            return result

        if batch.return_logprob or batch.has_grammar:
            raise RuntimeError("high_load_bypass_bound_workload_contract_violation")

        spec_algorithm_before = str(batch.spec_algorithm)
        spec_info_before = (
            type(batch.spec_info).__name__ if batch.spec_info is not None else None
        )
        input_ids_before = (
            int(batch.input_ids.numel()) if batch.input_ids is not None else None
        )
        authoritative_input_ids = torch.tensor(
            [
                (
                    request.output_ids[-1]
                    if request.output_ids
                    else request.origin_input_ids[-1]
                )
                for request in batch.reqs
            ],
            dtype=torch.int64,
            device=batch.device,
        )
        if entering_bypass:
            batch.spec_algorithm = SpeculativeAlgorithm.NONE
            batch.spec_info = None
            batch.input_ids = authoritative_input_ids
            batch.prepare_for_decode()
        else:
            if not batch.spec_algorithm.is_none() or batch.spec_info is not None:
                raise RuntimeError("high_load_bypass_persistent_non_spec_contract")
            if batch.input_ids is None or not torch.equal(
                batch.input_ids, authoritative_input_ids
            ):
                raise RuntimeError("high_load_bypass_authoritative_input_mismatch")

        allocated = batch.out_cache_loc
        if allocated.numel() != batch_size:
            raise RuntimeError(
                f"high_load_bypass_non_spec_cache_shape:{allocated.numel()}:{batch_size}"
            )
        if torch.unique(allocated).numel() != allocated.numel():
            raise RuntimeError("high_load_bypass_non_spec_cache_alias")
        mapped = batch.req_to_token_pool.req_to_token[
            batch.req_pool_indices, batch.seq_lens - 1
        ].to(allocated.dtype)
        if not torch.equal(mapped, allocated):
            raise RuntimeError("high_load_bypass_req_to_token_mismatch")
        if batch.input_ids.numel() != batch_size or not torch.equal(
            batch.input_ids, authoritative_input_ids
        ):
            raise RuntimeError("high_load_bypass_input_ids_shape_or_value")

        started = time.perf_counter()
        result = self.target_worker.forward_batch_generation(batch)
        target_forward_wall_ms = (time.perf_counter() - started) * 1000
        result.num_correct_drafts = 0
        result.num_correct_drafts_per_req_cpu = [0] * batch_size
        result.accept_lens = None
        self._update_ngram_corpus(batch)
        append_event(
            {
                "schema_version": 1,
                "kind": "decode_step",
                "mode": "ordinary_greedy_target_decode",
                "batch_size": batch_size,
                "target_rows": batch_size,
                "target_forward_wall_ms": target_forward_wall_ms,
                "num_correct_drafts": [0] * batch_size,
                "cache_owner": "one_unique_non_speculative_target_slot_per_request",
                "allocated_cache_slots": int(allocated.numel()),
                "unique_cache_slots": int(torch.unique(allocated).numel()),
                "req_to_token_matches_out_cache_loc": True,
                "spec_algorithm_before": spec_algorithm_before,
                "spec_algorithm_after": str(batch.spec_algorithm),
                "spec_info_before": spec_info_before,
                "spec_info_after": None,
                "input_ids_before": input_ids_before,
                "input_ids_after": int(batch.input_ids.numel()),
                "input_ids_match_authoritative_request_tokens": True,
                "out_cache_loc_shape": list(allocated.shape),
                "accept_lens": None,
                "match_state": "erased_while_bypassed",
            }
        )
        return result

    NGRAMWorker.forward_batch_generation = bypass_forward
    atomic_once(
        "HIGH_LOAD_BYPASS_PATCH_STATE.json",
        {
            "kind": "whole_step_load_adaptive_ngram_bypass",
            "threshold_running_requests": HIGH_LOAD_MIN_REQUESTS,
            "low_load": "unchanged_depth_12_ngram",
            "high_load": "ordinary_one_token_greedy_target_decode",
            "match_state": (
                "erase on both threshold transitions; rebuild from authoritative "
                "request tokens through stock NgramCorpus.batch_get on re-entry"
            ),
            "cache_ownership": (
                "high-load path calls stock non-speculative prepare_for_decode "
                "and requires one unique target cache slot per request"
            ),
        },
    )


install()
