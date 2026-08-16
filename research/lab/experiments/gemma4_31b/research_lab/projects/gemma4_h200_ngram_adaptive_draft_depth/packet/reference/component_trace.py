from __future__ import annotations

import hashlib
import inspect
import json
import os
from pathlib import Path
import threading

import torch


OUT = Path(os.environ.get("ADAPTIVE_NGRAM_OUT", "/work/out"))
TRACE_NAME = os.environ.get("ADAPTIVE_TRACE_NAME", "candidate")
LOCK = threading.Lock()
CAPTURED = False


def atomic(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def append_event(value: object) -> None:
    path = OUT / "ADAPTIVE_DEPTH_EVENTS.jsonl"
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(
            descriptor,
            (
                json.dumps(value, sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode(),
        )
    finally:
        os.close(descriptor)


def prompt_identity(request) -> str:
    raw = json.dumps(
        [int(token) for token in request.origin_input_ids],
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def install() -> None:
    from sglang.srt.speculative.ngram_info import NgramVerifyInput

    original = NgramVerifyInput._greedy_verify
    original_source_sha256 = hashlib.sha256(
        inspect.getsource(original).encode()
    ).hexdigest()

    def traced_greedy_verify(self, batch, logits_output) -> None:
        global CAPTURED
        target_predict = torch.argmax(
            logits_output.next_token_logits, dim=-1
        ).reshape(batch.batch_size(), self.draft_token_num)
        original(self, batch, logits_output)
        append_event(
            {
                "batch_size": batch.batch_size(),
                "draft_depth": self.draft_token_num,
                "target_rows": logits_output.next_token_logits.shape[0],
                "num_correct_drafts": self.num_correct_drafts.detach()
                .cpu()
                .tolist(),
            }
        )
        if batch.batch_size() < 8:
            return
        with LOCK:
            if CAPTURED:
                return
            CAPTURED = True
        try:
            accept_indices = self.accept_indices.detach().cpu().tolist()
            predict = self.predict.detach().flatten().cpu().tolist()
            accepted_bonus_tokens = [
                [
                    int(predict[int(index)])
                    for index in indices
                    if int(index) != -1
                ]
                for indices in accept_indices
            ]
            atomic(
                f"HIGH_LOAD_{TRACE_NAME.upper()}_TRACE.json",
                {
                    "real_cuda_call": bool(
                        logits_output.next_token_logits.is_cuda
                    ),
                    "batch_size": int(batch.batch_size()),
                    "draft_depth": int(self.draft_token_num),
                    "target_rows": int(
                        logits_output.next_token_logits.shape[0]
                    ),
                    "target_rows_per_request": int(
                        logits_output.next_token_logits.shape[0]
                        // batch.batch_size()
                    ),
                    "greedy_consumer_source_sha256": original_source_sha256,
                    "request_prompt_sha256": [
                        prompt_identity(request) for request in batch.reqs
                    ],
                    "draft_tokens": self.draft_token.detach()
                    .reshape(batch.batch_size(), self.draft_token_num)
                    .cpu()
                    .tolist(),
                    "target_predict": target_predict.cpu().tolist(),
                    "accept_indices": accept_indices,
                    "num_correct_drafts": self.num_correct_drafts.detach()
                    .cpu()
                    .tolist(),
                    "accepted_bonus_tokens": accepted_bonus_tokens,
                },
            )
        except Exception as error:
            atomic(
                f"HIGH_LOAD_{TRACE_NAME.upper()}_TRACE_ERROR.json",
                {
                    "error": repr(error),
                    "batch_size": int(batch.batch_size()),
                    "draft_depth": int(self.draft_token_num),
                },
            )

    NgramVerifyInput._greedy_verify = traced_greedy_verify


install()
