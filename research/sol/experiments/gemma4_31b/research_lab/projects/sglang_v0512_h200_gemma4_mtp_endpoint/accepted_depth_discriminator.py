from __future__ import annotations

import hashlib
import json
import os
import pathlib
import time


EXPECTED_SOURCE = {
    "sglang.srt.speculative.frozen_kv_mtp_worker": "ffd537efe8c28cecdbef1f5984f5f90f81f655ec3c1a65dca68f25d2b9a24d99",
    "sglang.srt.speculative.eagle_info": "2948d3a52dd1915f7efc9f175c8b0d65f50b803fc4028647c91564cda597e82f",
    "sglang.srt.managers.scheduler": "3a26deea85f43d61c27b94013288ad95d6ee75111fe40134893541777c9c8cd4",
}


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _append(row: dict[str, object]) -> None:
    path = pathlib.Path(os.environ["ACCEPTED_DEPTH_AUDIT"])
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(
            descriptor,
            (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        )
    finally:
        os.close(descriptor)


def _timed(function, *args, **kwargs):
    import torch

    timing = os.environ.get("ACCEPTED_DEPTH_TIMING") == "1"
    if timing:
        torch.cuda.synchronize()
    started = time.perf_counter_ns()
    value = function(*args, **kwargs)
    if timing:
        torch.cuda.synchronize()
    return value, (time.perf_counter_ns() - started) / 1_000_000


def install() -> None:
    if "ACCEPTED_DEPTH_AUDIT" not in os.environ:
        return

    from sglang.srt.managers import scheduler
    from sglang.srt.speculative import eagle_info, frozen_kv_mtp_worker
    from sglang.srt.speculative.frozen_kv_mtp_worker import FrozenKVMTPWorker

    observed = {
        "sglang.srt.speculative.frozen_kv_mtp_worker": _sha256(
            pathlib.Path(frozen_kv_mtp_worker.__file__)
        ),
        "sglang.srt.speculative.eagle_info": _sha256(pathlib.Path(eagle_info.__file__)),
        "sglang.srt.managers.scheduler": _sha256(pathlib.Path(scheduler.__file__)),
    }
    if observed != EXPECTED_SOURCE:
        raise RuntimeError(
            "accepted-depth source mismatch:"
            + json.dumps({"expected": EXPECTED_SOURCE, "observed": observed}, sort_keys=True)
        )

    original_draft_forward = FrozenKVMTPWorker.draft_forward
    original_verify = FrozenKVMTPWorker.verify

    def draft_forward(self, forward_batch):
        result, elapsed_ms = _timed(original_draft_forward, self, forward_batch)
        parent_list, top_scores_index, draft_tokens = result
        _append(
            {
                "event": "assistant_forward",
                "worker_pid": os.getpid(),
                "batch_size": int(forward_batch.batch_size),
                "speculative_num_steps": int(self.speculative_num_steps),
                "speculative_num_draft_tokens": int(
                    self.speculative_num_draft_tokens
                ),
                "proposed_drafts_per_request": int(
                    self.speculative_num_draft_tokens - 1
                ),
                "draft_tokens_numel": int(draft_tokens.numel()),
                "parent_list_numel": int(parent_list.numel()),
                "top_scores_index_numel": int(top_scores_index.numel()),
                "elapsed_ms": elapsed_ms,
                "candidate_path": "FrozenKVMTPWorker.draft_forward.assistant_model_runner",
            }
        )
        return result

    def verify(self, batch):
        result, elapsed_ms = _timed(original_verify, self, batch)
        accepted_drafts = [int(value) for value in result.num_correct_drafts_per_req_cpu]
        _append(
            {
                "event": "target_verify",
                "worker_pid": os.getpid(),
                "batch_size": len(accepted_drafts),
                "accepted_drafts_per_request": accepted_drafts,
                "accepted_drafts_total": sum(accepted_drafts),
                "accepted_tokens_total": int(result.accept_tokens.numel()),
                "elapsed_ms": elapsed_ms,
                "candidate_path": "FrozenKVMTPWorker.verify.target_worker_and_accept",
            }
        )
        return result

    FrozenKVMTPWorker.draft_forward = draft_forward
    FrozenKVMTPWorker.verify = verify
    _append(
        {
            "event": "installation_complete",
            "worker_pid": os.getpid(),
            "source_sha256": observed,
            "candidate_path": "FrozenKVMTPWorker.native_accepted_depth_discriminator",
        }
    )

