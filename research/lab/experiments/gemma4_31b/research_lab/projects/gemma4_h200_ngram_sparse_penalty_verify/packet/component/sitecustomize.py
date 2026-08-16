from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import threading

import torch

from sglang.srt.sampling.penaltylib.min_new_tokens import (
    BatchedMinNewTokensPenalizer,
)
from sglang.srt.sampling.penaltylib.orchestrator import (
    BatchedPenalizerOrchestrator,
)


OUT = Path(os.environ.get("SPARSE_PENALTY_OUT", "/work/out"))
TARGET_ROWS = int(os.environ.get("SPARSE_PENALTY_TARGET_ROWS", "384"))
LOCK = threading.Lock()
MAX_ROWS = 0
ORIGINAL_APPLY = BatchedPenalizerOrchestrator.apply


def atomic(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def broadcast_apply(
    orchestrator: BatchedPenalizerOrchestrator,
    logits: torch.Tensor,
    repeat: int | None,
) -> None:
    if repeat is None:
        ORIGINAL_APPLY(orchestrator, logits, repeat)
        return
    batch = logits.shape[0] // repeat
    additive = torch.zeros(
        (batch, logits.shape[1]), dtype=torch.float32, device=logits.device
    )
    orchestrator.accumulate_additive_penalties(additive)
    logits.view(batch, repeat, logits.shape[1]).add_(additive[:, None, :])
    scaling = orchestrator.accumulate_scaling_penalties()
    if scaling is not None:
        from sglang.srt.sampling.penaltylib.repetition_penalty import (
            apply_scaling_penalties,
        )

        apply_scaling_penalties(
            logits, torch.repeat_interleave(scaling, repeat, dim=0)
        )


def sparse_coordinates(
    orchestrator: BatchedPenalizerOrchestrator,
) -> tuple[torch.Tensor, torch.Tensor] | None:
    prepared = [
        penalizer
        for penalizer in orchestrator.penalizers.values()
        if penalizer._is_prepared
    ]
    if len(prepared) != 1 or not isinstance(
        prepared[0], BatchedMinNewTokensPenalizer
    ):
        return None
    penalizer = prepared[0]
    rows, tokens = torch.where(torch.isneginf(penalizer.stop_token_penalties))
    active = (
        penalizer.len_output_tokens.flatten()
        < penalizer.min_new_tokens.flatten()
    )
    keep = active[rows]
    return rows[keep], tokens[keep]


def direct_sparse_apply(
    logits: torch.Tensor,
    repeat: int,
    coordinates: tuple[torch.Tensor, torch.Tensor],
) -> None:
    rows, tokens = coordinates
    if rows.numel() == 0:
        return
    view = logits.view(logits.shape[0] // repeat, repeat, logits.shape[1])
    drafts = torch.arange(repeat, device=logits.device)
    view[rows[:, None], drafts[None, :], tokens[:, None]] = float("-inf")


def timed(
    base: torch.Tensor,
    operation,
    warmups: int = 3,
    repetitions: int = 20,
) -> tuple[list[float], torch.Tensor, torch.Tensor]:
    work = base.clone()
    for _ in range(warmups):
        work.copy_(base)
        operation(work)
        torch.argmax(work, dim=-1)
    torch.cuda.synchronize()
    samples = []
    selected = None
    for _ in range(repetitions):
        work.copy_(base)
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        operation(work)
        selected = torch.argmax(work, dim=-1)
        end.record()
        end.synchronize()
        samples.append(float(start.elapsed_time(end)))
    assert selected is not None
    return samples, work.clone(), selected.clone()


def capture_component(
    orchestrator: BatchedPenalizerOrchestrator,
    logits: torch.Tensor,
    repeat: int,
) -> None:
    global MAX_ROWS
    rows = logits.shape[0]
    if rows < TARGET_ROWS:
        return
    with LOCK:
        if rows <= MAX_ROWS:
            return
        MAX_ROWS = rows
    coordinates = sparse_coordinates(orchestrator)
    prepared = [
        {
            "class": type(penalizer).__name__,
            "prepared": bool(penalizer._is_prepared),
            "multiplicative": bool(penalizer.is_multiplicative),
        }
        for penalizer in orchestrator.penalizers.values()
    ]
    value: dict[str, object] = {
        "real_call": True,
        "shape": list(logits.shape),
        "stride": list(logits.stride()),
        "dtype": str(logits.dtype),
        "repeat": repeat,
        "target_rows": TARGET_ROWS,
        "active_penalizers": [row for row in prepared if row["prepared"]],
        "all_penalizers": prepared,
        "dense_logits_bytes": logits.numel() * logits.element_size(),
    }
    if coordinates is None:
        value["exact"] = False
        value["reason"] = "active_penalty_set_not_min_new_tokens_only"
        atomic("COMPONENT_CANDIDATE.json", value)
        return
    coordinate_count = int(coordinates[0].numel())
    value["nonzero_additive_coordinates_per_request"] = coordinate_count
    value["nonzero_coordinates_after_repeat"] = coordinate_count * repeat
    value["dense_penalty_application_read_write_bytes"] = (
        2 * logits.numel() * logits.element_size()
    )
    base = logits.detach().clone()
    baseline_samples, baseline_logits, baseline_tokens = timed(
        base, lambda tensor: broadcast_apply(orchestrator, tensor, repeat)
    )
    candidate_samples, candidate_logits, candidate_tokens = timed(
        base, lambda tensor: direct_sparse_apply(tensor, repeat, coordinates)
    )
    value.update(
        {
            "exact_logits": bool(torch.equal(baseline_logits, candidate_logits)),
            "exact_selected_tokens": bool(
                torch.equal(baseline_tokens, candidate_tokens)
            ),
            "selected_token_count": int(baseline_tokens.numel()),
            "baseline_penalty_plus_argmax_ms": {
                "samples": baseline_samples,
                "median": statistics.median(baseline_samples),
                "min": min(baseline_samples),
                "max": max(baseline_samples),
            },
            "candidate_penalty_plus_argmax_ms": {
                "samples": candidate_samples,
                "median": statistics.median(candidate_samples),
                "min": min(candidate_samples),
                "max": max(candidate_samples),
            },
            "candidate_path": "direct_min_new_token_columns_then_unchanged_torch_argmax",
        }
    )
    baseline_median = statistics.median(baseline_samples)
    candidate_median = statistics.median(candidate_samples)
    value["speedup_fraction"] = (
        (baseline_median - candidate_median) / baseline_median
    )
    value["exact"] = bool(
        value["exact_logits"] and value["exact_selected_tokens"]
    )
    atomic("COMPONENT_CANDIDATE.json", value)


def instrumented_apply(
    self: BatchedPenalizerOrchestrator,
    logits: torch.Tensor,
    repeat: int | None = None,
):
    if repeat == 12 and logits.is_cuda:
        capture_component(self, logits, repeat)
    return broadcast_apply(self, logits, repeat)


BatchedPenalizerOrchestrator.apply = instrumented_apply
atomic(
    "COMPONENT_PATCH_STATE.json",
    {
        "baseline": "installed broadcast-reuse BatchedPenalizerOrchestrator.apply",
        "candidate": "direct sparse min-new-token columns",
        "consumer": "unchanged torch.argmax in NgramVerifyInput._greedy_verify",
    },
)
