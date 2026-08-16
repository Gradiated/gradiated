"""Support-two write-promotion gate for the bound native NGRAM worker."""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

from distinct_request_gate import DistinctRequestPromotionGate


ROOT = Path(os.environ.get("DISTINCT_REQUEST_ROOT", "/work"))
OUT = Path(os.environ.get("DISTINCT_REQUEST_OUT", str(ROOT / "out")))
OUT.mkdir(parents=True, exist_ok=True)
TRACE = OUT / "distinct-request-ngram.jsonl"
LOCK = threading.Lock()
MAX_PROBATION_ENTRIES = 16384


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(name, row):
    path = OUT / name
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(row, indent=2, sort_keys=True) + "\n")
    part.replace(path)


def emit(row):
    with LOCK:
        with TRACE.open("a") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


from sglang.srt.speculative.ngram_worker import NGRAMWorker


ORIGINAL_INIT = NGRAMWorker.__init__
ORIGINAL_CLEAR = NGRAMWorker.clear_cache_pool
ORIGINAL_UPDATE = NGRAMWorker._update_ngram_corpus
ORIGINAL_FORWARD = NGRAMWorker.forward_batch_generation


def patched_init(self, *args, **kwargs):
    ORIGINAL_INIT(self, *args, **kwargs)
    self._distinct_request_gate = DistinctRequestPromotionGate(
        MAX_PROBATION_ENTRIES
    )
    self._distinct_request_update_calls = 0
    emit(
        {
            "event": "worker_initialized",
            "overlay_sha256": digest(__file__),
            "gate_sha256": digest(Path(__file__).with_name("distinct_request_gate.py")),
            "max_probation_entries": MAX_PROBATION_ENTRIES,
            "support": 2,
            "draft_token_num": self.draft_token_num,
            "max_trie_depth": self.max_trie_depth,
        }
    )


def patched_clear(self):
    result = ORIGINAL_CLEAR(self)
    self._distinct_request_gate.clear()
    emit({"event": "cache_cleared", "probation_entries": 0})
    return result


def patched_update(self, batch):
    admitted_tokens = []
    rare_rows = []
    for req in batch.reqs:
        tokens = self._efficient_concat_last_n(
            req.origin_input_ids, req.output_ids, self.max_trie_depth
        )
        admitted = self._distinct_request_gate.admit(req.rid, tokens)
        if admitted:
            admitted_tokens.append(tokens)
        marker = next(
            (
                token
                for token in (200032, 200790)
                if token in req.origin_input_ids
            ),
            None,
        )
        if marker is not None:
            rare_rows.append(
                {
                    "request_index": marker - 200000,
                    "request_id": str(req.rid),
                    "output_len": len(req.output_ids),
                    "suffix": list(tokens),
                    "admitted": admitted,
                }
            )
    if admitted_tokens:
        self.ngram_corpus.batch_put(admitted_tokens)
    self._distinct_request_update_calls += 1
    gate = self._distinct_request_gate
    if rare_rows or self._distinct_request_update_calls % 128 == 0:
        emit(
            {
                "event": "corpus_update",
                "update_call": self._distinct_request_update_calls,
                "requests": len(batch.reqs),
                "admitted_suffixes": len(admitted_tokens),
                "probation_entries": gate.probation_entries,
                "cumulative_admitted": gate.admitted,
                "same_request_repeats": gate.same_request_repeats,
                "evicted": gate.evicted,
                "rare_rows": rare_rows,
            }
        )


def patched_forward(self, *args, **kwargs):
    batch = args[0]
    result = ORIGINAL_FORWARD(self, *args, **kwargs)
    accepted = result.num_correct_drafts_per_req_cpu
    if accepted is not None:
        rows = []
        rare_branch_seen = getattr(self, "_distinct_request_rare_branch_seen", False)
        for req, accepted_drafts in zip(batch.reqs, accepted):
            marker = (
                req.origin_input_ids[535]
                if len(req.origin_input_ids) > 535
                else None
            )
            request_index = (
                marker - 200000
                if marker is not None and 200000 <= marker <= 201035
                else None
            )
            if request_index == 790 and any(
                token != 51935 for token in req.output_ids
            ):
                rare_branch_seen = True
            rows.append(
                {
                    "request_index": request_index,
                    "accepted_drafts": int(accepted_drafts),
                    "output_len": len(req.output_ids),
                }
            )
        self._distinct_request_rare_branch_seen = rare_branch_seen
        emit(
            {
                "event": "target_verify",
                "after_request_790_rare_branch": rare_branch_seen,
                "rows": rows,
            }
        )
    return result


NGRAMWorker.__init__ = patched_init
NGRAMWorker.clear_cache_pool = patched_clear
NGRAMWorker._update_ngram_corpus = patched_update
NGRAMWorker.forward_batch_generation = patched_forward

atomic(
    "OVERLAY_STATE.json",
    {
        "overlay": "distinct_request_support_two_write_promotion",
        "overlay_sha256": digest(__file__),
        "gate_sha256": digest(Path(__file__).with_name("distinct_request_gate.py")),
        "source_delta": "_update_ngram_corpus_write_admission_only",
        "support": 2,
        "max_probation_entries": MAX_PROBATION_ENTRIES,
        "eviction": "deterministic_fifo",
        "read_path": "unchanged",
        "depth": 12,
    },
)
