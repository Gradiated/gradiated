from __future__ import annotations

import json
import os
from pathlib import Path

import torch

from sglang.srt.sampling.penaltylib.min_new_tokens import (
    BatchedMinNewTokensPenalizer,
)
from sglang.srt.sampling.penaltylib.orchestrator import (
    BatchedPenalizerOrchestrator,
)


OUT = Path(os.environ.get("SPARSE_PENALTY_OUT", "/work/out"))
ORIGINAL_ORCHESTRATOR_APPLY = BatchedPenalizerOrchestrator.apply


def atomic_once(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    if path.exists():
        return
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def sparse_prepare(self: BatchedMinNewTokensPenalizer) -> None:
    requests = self.orchestrator.reqs()
    self.min_new_tokens = torch.tensor(
        [req.sampling_params.min_new_tokens for req in requests],
        dtype=torch.int32,
        device=self.orchestrator.device,
    ).unsqueeze_(1)
    sequences = [
        torch.tensor(
            list(
                (req.sampling_params.stop_token_ids or set())
                | (req.tokenizer.additional_stop_token_ids or set())
                | {req.tokenizer.eos_token_id}
            ),
            dtype=torch.int64,
            device=self.orchestrator.device,
        )
        for req in requests
    ]
    self.sparse_stop_token_ids = torch.nn.utils.rnn.pad_sequence(
        sequences,
        batch_first=True,
        padding_value=self.orchestrator.vocab_size,
    )
    self.len_output_tokens = torch.zeros(
        (len(requests), 1), dtype=torch.int32, device=self.orchestrator.device
    )


def apply_sparse(
    self: BatchedMinNewTokensPenalizer,
    logits: torch.Tensor,
    repeat: int = 1,
) -> int:
    active = (
        self.len_output_tokens.flatten() < self.min_new_tokens.flatten()
    )
    request_rows, stop_columns = torch.where(
        active[:, None]
        & (self.sparse_stop_token_ids < self.orchestrator.vocab_size)
    )
    if request_rows.numel() == 0:
        return 0
    tokens = self.sparse_stop_token_ids[request_rows, stop_columns]
    if repeat == 1:
        logits[request_rows, tokens] = float("-inf")
    else:
        drafts = torch.arange(repeat, device=logits.device)
        logits.view(
            logits.shape[0] // repeat, repeat, logits.shape[1]
        )[request_rows[:, None], drafts[None, :], tokens[:, None]] = float("-inf")
    return int(request_rows.numel())


def sparse_apply(self: BatchedMinNewTokensPenalizer, logits: torch.Tensor) -> None:
    apply_sparse(self, logits)


def sparse_filter(
    self: BatchedMinNewTokensPenalizer, keep_indices: torch.Tensor
) -> None:
    self.min_new_tokens = self.min_new_tokens[keep_indices]
    self.sparse_stop_token_ids = self.sparse_stop_token_ids[keep_indices]
    self.len_output_tokens = self.len_output_tokens[keep_indices]


def padded(tensor: torch.Tensor, width: int, value: int) -> torch.Tensor:
    if tensor.shape[1] == width:
        return tensor
    return torch.nn.functional.pad(tensor, (0, width - tensor.shape[1]), value=value)


def sparse_merge(
    self: BatchedMinNewTokensPenalizer,
    other: BatchedMinNewTokensPenalizer,
) -> None:
    width = max(
        self.sparse_stop_token_ids.shape[1],
        other.sparse_stop_token_ids.shape[1],
    )
    sentinel = self.orchestrator.vocab_size
    self.min_new_tokens = torch.cat(
        [self.min_new_tokens, other.min_new_tokens], dim=0
    )
    self.sparse_stop_token_ids = torch.cat(
        [
            padded(self.sparse_stop_token_ids, width, sentinel),
            padded(other.sparse_stop_token_ids, width, sentinel),
        ],
        dim=0,
    )
    self.len_output_tokens = torch.cat(
        [self.len_output_tokens, other.len_output_tokens], dim=0
    )


def sparse_teardown(self: BatchedMinNewTokensPenalizer) -> None:
    for name in (
        "min_new_tokens",
        "sparse_stop_token_ids",
        "len_output_tokens",
    ):
        if hasattr(self, name):
            delattr(self, name)


def sparse_orchestrator_apply(
    self: BatchedPenalizerOrchestrator,
    logits: torch.Tensor,
    repeat: int | None = None,
) -> None:
    if repeat is None:
        for penalizer in self.penalizers.values():
            penalizer.apply(logits)
        return
    sparse_coordinates = 0
    for penalizer in self.penalizers.values():
        if not penalizer._is_prepared:
            continue
        if isinstance(penalizer, BatchedMinNewTokensPenalizer):
            sparse_coordinates += apply_sparse(penalizer, logits, repeat)
        elif penalizer.is_multiplicative:
            scaling = penalizer.get_scaling_penalties()
            from sglang.srt.sampling.penaltylib.repetition_penalty import (
                apply_scaling_penalties,
            )

            apply_scaling_penalties(
                logits, torch.repeat_interleave(scaling, repeat, dim=0)
            )
        else:
            batch = logits.shape[0] // repeat
            additive = torch.zeros(
                (batch, logits.shape[1]),
                dtype=torch.float32,
                device=logits.device,
            )
            penalizer.apply(additive)
            logits.view(batch, repeat, logits.shape[1]).add_(
                additive[:, None, :]
            )
    atomic_once(
        "CANDIDATE_PATH.json",
        {
            "candidate_cuda_executed": True,
            "repeat": repeat,
            "logits_shape": list(logits.shape),
            "sparse_coordinates_per_request_batch": sparse_coordinates,
            "consumer": "unchanged NgramVerifyInput._greedy_verify torch.argmax",
        },
    )


BatchedMinNewTokensPenalizer._prepare = sparse_prepare
BatchedMinNewTokensPenalizer._apply = sparse_apply
BatchedMinNewTokensPenalizer._filter = sparse_filter
BatchedMinNewTokensPenalizer._merge = sparse_merge
BatchedMinNewTokensPenalizer._teardown = sparse_teardown
BatchedPenalizerOrchestrator.apply = sparse_orchestrator_apply
atomic_once(
    "PATCH_STATE.json",
    {
        "kind": "direct_sparse_min_new_token_columns",
        "representation": "padded stop-token ids, no dense FP32 penalty matrix",
        "consumer": "unchanged greedy argmax and verify_tree_greedy",
        "semantics": "set active stop-token logits to negative infinity",
    },
)

import adaptive_depth
import component_trace
