"""Buffer verified NGRAM writes until exact request completion."""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import threading
import weakref
from pathlib import Path

from completed_request_buffer import CompletedRequestCommitBuffer


ROOT = Path(os.environ.get("COMPLETED_REQUEST_ROOT", "/work"))
OUT = Path(os.environ.get("COMPLETED_REQUEST_OUT", str(ROOT / "out")))
OUT.mkdir(parents=True, exist_ok=True)
TRACE = OUT / "completed-request-ngram.jsonl"
LOCK = threading.Lock()
WORKERS = weakref.WeakSet()
OWNER_SEQUENCE = itertools.count(1)


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


from sglang.srt.managers.schedule_batch import FINISH_ABORT
from sglang.srt.managers.scheduler import Scheduler
from sglang.srt.speculative.ngram_worker import NGRAMWorker


ORIGINAL_INIT = NGRAMWorker.__init__
ORIGINAL_CLEAR = NGRAMWorker.clear_cache_pool
ORIGINAL_FORWARD = NGRAMWorker.forward_batch_generation
ORIGINAL_ABORT_REQUEST = Scheduler.abort_request


def owner(req):
    value = getattr(req, "_completed_request_owner", None)
    if value is None:
        value = f"generation-{next(OWNER_SEQUENCE)}"
        req._completed_request_owner = value
    return value


def patched_init(self, *args, **kwargs):
    ORIGINAL_INIT(self, *args, **kwargs)
    self._completed_request_buffer = CompletedRequestCommitBuffer(
        self.max_batch_size
    )
    self._completed_request_update_calls = 0
    WORKERS.add(self)
    emit(
        {
            "event": "worker_initialized",
            "overlay_sha256": digest(__file__),
            "buffer_sha256": digest(
                Path(__file__).with_name("completed_request_buffer.py")
            ),
            "max_active_requests": self.max_batch_size,
            "max_trie_depth": self.max_trie_depth,
            "draft_token_num": self.draft_token_num,
        }
    )


def patched_clear(self):
    result = ORIGINAL_CLEAR(self)
    self._completed_request_buffer.clear()
    emit({"event": "cache_cleared", "active_requests": 0, "buffered_rows": 0})
    return result


def patched_update(self, batch):
    completed = []
    rare_rows = []
    for req in batch.reqs:
        request_id = str(req.rid)
        request_owner = owner(req)
        aborted = isinstance(req.finished_reason, FINISH_ABORT)
        if aborted:
            self._completed_request_buffer.finish(
                request_id, request_owner, aborted=True
            )
        else:
            tokens = self._efficient_concat_last_n(
                req.origin_input_ids, req.output_ids, self.max_trie_depth
            )
            self._completed_request_buffer.stage(
                request_id,
                request_owner,
                tokens,
                max_rows=max(1, int(req.sampling_params.max_new_tokens)),
            )
            if req.finished():
                committed = self._completed_request_buffer.finish(
                    request_id, request_owner, aborted=False
                )
                if committed:
                    self.ngram_corpus.batch_put(committed)
                if 200032 in req.origin_input_ids:
                    self._completed_request_rare_completion_seen = True
                completed.append(
                    {
                        "request_id": request_id,
                        "committed_rows": len(committed),
                    }
                )
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
                    "request_id": request_id,
                    "output_len": len(req.output_ids),
                    "finished": req.finished(),
                    "aborted": aborted,
                }
            )

    self._completed_request_update_calls += 1
    state = self._completed_request_buffer
    if completed or rare_rows or self._completed_request_update_calls % 128 == 0:
        emit(
            {
                "event": "corpus_update",
                "update_call": self._completed_request_update_calls,
                "requests": len(batch.reqs),
                "active_requests": state.active_requests,
                "buffered_rows": state.buffered_rows,
                "committed_requests": state.committed_requests,
                "committed_rows": state.committed_rows,
                "discarded_requests": state.discarded_requests,
                "discarded_rows": state.discarded_rows,
                "id_reuses": state.id_reuses,
                "completed": completed,
                "rare_rows": rare_rows,
            }
        )


def patched_forward(self, *args, **kwargs):
    batch = args[0]
    try:
        result = ORIGINAL_FORWARD(self, *args, **kwargs)
        accepted = result.num_correct_drafts_per_req_cpu
        if accepted is not None:
            rows = []
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
                rows.append(
                    {
                        "request_index": request_index,
                        "accepted_drafts": int(accepted_drafts),
                        "output_len": len(req.output_ids),
                    }
                )
            emit(
                {
                    "event": "target_verify",
                    "after_request_32_completion": getattr(
                        self, "_completed_request_rare_completion_seen", False
                    ),
                    "rows": rows,
                }
            )
        return result
    except BaseException:
        for req in batch.reqs:
            self._completed_request_buffer.discard(str(req.rid), owner(req))
        emit(
            {
                "event": "forward_exception_cleanup",
                "request_ids": [str(req.rid) for req in batch.reqs],
            }
        )
        raise


def patched_abort_request(self, recv_req):
    result = ORIGINAL_ABORT_REQUEST(self, recv_req)
    discarded = 0
    for worker in list(WORKERS):
        discarded += worker._completed_request_buffer.discard_matching(
            recv_req.rid, all_requests=bool(recv_req.abort_all)
        )
    if discarded:
        emit(
            {
                "event": "scheduler_abort_cleanup",
                "request_id_prefix": str(recv_req.rid),
                "abort_all": bool(recv_req.abort_all),
                "discarded_requests": discarded,
            }
        )
    return result


NGRAMWorker.__init__ = patched_init
NGRAMWorker.clear_cache_pool = patched_clear
NGRAMWorker._update_ngram_corpus = patched_update
NGRAMWorker.forward_batch_generation = patched_forward
Scheduler.abort_request = patched_abort_request

atomic(
    "OVERLAY_STATE.json",
    {
        "overlay": "completed_request_ngram_commit",
        "overlay_sha256": digest(__file__),
        "buffer_sha256": digest(
            Path(__file__).with_name("completed_request_buffer.py")
        ),
        "source_delta": (
            "_update_ngram_corpus write buffering plus exact abort/exception cleanup"
        ),
        "read_path": "unchanged",
        "global_commit_path": "NgramCorpus.batch_put",
        "memory_bound": (
            "max_running_requests active states and request max_new_tokens rows"
        ),
    },
)
