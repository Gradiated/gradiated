"""Reuse the additive penalty workspace without an expanded NGRAM temporary."""

from __future__ import annotations

import json
import os
from pathlib import Path

import torch

from sglang.srt.sampling.penaltylib.orchestrator import (
    BatchedPenalizerOrchestrator,
)


OUT = Path(os.environ.get("TORCH_STAIRCASE_OUT", "/work/out"))
_original_apply = BatchedPenalizerOrchestrator.apply


def _broadcast_reuse_apply(self, logits: torch.Tensor, repeat: int | None = None):
    if repeat is None:
        return _original_apply(self, logits, repeat)
    bs = logits.shape[0] // repeat
    additive = torch.zeros(
        (bs, logits.shape[1]), dtype=torch.float32, device=logits.device
    )
    self.accumulate_additive_penalties(additive)
    logits.view(bs, repeat, logits.shape[1]).add_(additive[:, None, :])
    accumulated = self.accumulate_scaling_penalties()
    if accumulated is not None:
        from sglang.srt.sampling.penaltylib.repetition_penalty import (
            apply_scaling_penalties,
        )

        expanded = torch.repeat_interleave(accumulated, repeat, dim=0)
        apply_scaling_penalties(logits, expanded)


BatchedPenalizerOrchestrator.apply = _broadcast_reuse_apply
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "PATCH_STATE.json").write_text(
    json.dumps(
        {
            "kind": "target_verify_additive_broadcast_workspace_reuse",
            "owner": "BatchedPenalizerOrchestrator.apply",
            "removed_temporary": "repeat_interleave(additive, repeat, dim=0)",
            "semantics": "broadcast the same per-request additive values over repeat",
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
