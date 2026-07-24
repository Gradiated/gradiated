from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import torch


LOW_LOAD_DEPTH = 12
HIGH_LOAD_DEPTH = 6
HIGH_LOAD_MIN_REQUESTS = 8
OUT = Path(os.environ.get("ADAPTIVE_NGRAM_OUT", "/work/out"))


def atomic_once(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    if path.exists():
        return
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def install() -> None:
    from sglang.srt.speculative.ngram_worker import NGRAMWorker

    original_init = NGRAMWorker.__init__
    original_prepare_drafts = NGRAMWorker._prepare_draft_tokens
    original_prepare_verify = NGRAMWorker._prepare_for_speculative_decoding

    def buffers(worker: NGRAMWorker, depth: int) -> dict[str, object]:
        max_batch = worker.max_batch_size
        retrieve_indexes = torch.empty(
            (max_batch, depth), dtype=torch.int64, device=worker.device
        )
        retrieve_next_token = torch.empty_like(retrieve_indexes)
        retrieve_next_sibling = torch.empty_like(retrieve_indexes)
        positions = torch.empty(
            (max_batch * depth,), dtype=torch.int64, device=worker.device
        )
        draft_tokens = torch.empty_like(positions)
        tree_mask = torch.empty(
            (max_batch * depth * depth,),
            dtype=torch.bool,
            device=worker.device,
        )
        return {
            "retrieve_indexes": retrieve_indexes,
            "retrieve_next_token": retrieve_next_token,
            "retrieve_next_sibling": retrieve_next_sibling,
            "positions": positions,
            "draft_tokens": draft_tokens,
            "tree_mask": tree_mask,
            "retrieve_indexes_batch": [
                retrieve_indexes[:batch_size, :]
                for batch_size in range(max_batch + 1)
            ],
            "retrieve_next_token_batch": [
                retrieve_next_token[:batch_size, :]
                for batch_size in range(max_batch + 1)
            ],
            "retrieve_next_sibling_batch": [
                retrieve_next_sibling[:batch_size, :]
                for batch_size in range(max_batch + 1)
            ],
            "positions_batch": [
                positions[: batch_size * depth]
                for batch_size in range(max_batch + 1)
            ],
            "draft_tokens_batch": [
                draft_tokens[: batch_size * depth]
                for batch_size in range(max_batch + 1)
            ],
            "tree_mask_batch": [
                tree_mask[: batch_size * depth * depth]
                for batch_size in range(max_batch + 1)
            ],
        }

    def adaptive_init(self: NGRAMWorker, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        if self.draft_token_num != LOW_LOAD_DEPTH:
            raise RuntimeError(
                f"adaptive_depth_requires_bound_depth_12:{self.draft_token_num}"
            )
        self._adaptive_buffers = {
            LOW_LOAD_DEPTH: {
                name: getattr(self, name)
                for name in (
                    "retrieve_indexes",
                    "retrieve_next_token",
                    "retrieve_next_sibling",
                    "positions",
                    "draft_tokens",
                    "tree_mask",
                    "retrieve_indexes_batch",
                    "retrieve_next_token_batch",
                    "retrieve_next_sibling_batch",
                    "positions_batch",
                    "draft_tokens_batch",
                    "tree_mask_batch",
                )
            },
            HIGH_LOAD_DEPTH: buffers(self, HIGH_LOAD_DEPTH),
        }

    def select_depth(self: NGRAMWorker, depth: int) -> None:
        selected = self._adaptive_buffers[depth]
        self.draft_token_num = depth
        for name, value in selected.items():
            setattr(self, name, value)

    def adaptive_prepare_drafts(
        self: NGRAMWorker, batch
    ) -> tuple[np.ndarray, np.ndarray]:
        if self.draft_token_num == LOW_LOAD_DEPTH:
            return original_prepare_drafts(self, batch)
        batch_size = batch.batch_size()
        self.ngram_corpus.synchronize()
        request_ids = []
        batch_tokens = []
        total_lengths = []
        for request in batch.reqs:
            check_token = self._efficient_concat_last_n(
                request.origin_input_ids,
                request.output_ids,
                self.max_trie_depth,
            )
            request_ids.append(request.rid)
            batch_tokens.append(check_token)
            total_lengths.append(
                len(request.origin_input_ids) + len(request.output_ids)
            )
        full_drafts, full_mask = self.ngram_corpus.batch_get(
            request_ids, batch_tokens, total_lengths
        )
        expected_drafts = batch_size * LOW_LOAD_DEPTH
        expected_mask = batch_size * LOW_LOAD_DEPTH * LOW_LOAD_DEPTH
        if len(full_drafts) != expected_drafts or len(full_mask) != expected_mask:
            raise RuntimeError(
                "adaptive_depth_bound_producer_shape_mismatch:"
                f"{len(full_drafts)}:{len(full_mask)}"
            )
        depth = self.draft_token_num
        drafts = (
            np.asarray(full_drafts)
            .reshape(batch_size, LOW_LOAD_DEPTH)[:, :depth]
            .copy()
            .reshape(-1)
        )
        mask = (
            np.asarray(full_mask)
            .reshape(batch_size, LOW_LOAD_DEPTH, LOW_LOAD_DEPTH)[
                :, :depth, :depth
            ]
            .copy()
            .reshape(-1)
        )
        return drafts, mask

    def adaptive_prepare_verify(self: NGRAMWorker, batch):
        batch_size = batch.batch_size()
        depth = (
            HIGH_LOAD_DEPTH
            if batch_size >= HIGH_LOAD_MIN_REQUESTS
            else LOW_LOAD_DEPTH
        )
        select_depth(self, depth)
        return original_prepare_verify(self, batch)

    NGRAMWorker.__init__ = adaptive_init
    NGRAMWorker._prepare_draft_tokens = adaptive_prepare_drafts
    NGRAMWorker._prepare_for_speculative_decoding = adaptive_prepare_verify
    atomic_once(
        "ADAPTIVE_DEPTH_PATCH_STATE.json",
        {
            "kind": "running_request_count_to_ngram_draft_depth",
            "low_load": {
                "running_requests_min": 1,
                "running_requests_max": 7,
                "draft_depth": LOW_LOAD_DEPTH,
            },
            "high_load": {
                "running_requests_min": HIGH_LOAD_MIN_REQUESTS,
                "draft_depth": HIGH_LOAD_DEPTH,
            },
            "producer": "NgramCorpus.batch_get fixed-depth-12 BFS prefix",
            "consumer": "unchanged NgramVerifyInput greedy verifier",
        },
    )


install()
