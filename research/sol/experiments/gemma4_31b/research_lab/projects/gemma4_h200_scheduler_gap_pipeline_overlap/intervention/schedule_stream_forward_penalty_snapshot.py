from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import inspect
import json
import os
import pathlib


def _emit(row: dict[str, object]) -> None:
    destination = os.environ.get("RESIDUAL_CANDIDATE_AUDIT")
    if not destination:
        return
    path = pathlib.Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def install() -> None:
    import torch
    from sglang.srt.managers.scheduler import Scheduler

    source = inspect.getsource(Scheduler._forward_isolation)
    required = (
        "sched_sampling_info.copy_for_forward()",
        "self.record_batch_in_overlap(batch)",
        "batch.sampling_info = sched_sampling_info",
    )
    if not all(token in source for token in required):
        raise RuntimeError("scheduler_snapshot_source_mismatch")
    original_run_batch = Scheduler.run_batch

    def run_batch(self, batch, *args, **kwargs):
        if (
            self.is_generation
            and self.enable_overlap
            and batch.sampling_info is not None
        ):
            with torch.cuda.stream(self.schedule_stream):
                batch._schedule_stream_forward_penalty_snapshot = (
                    batch.sampling_info.copy_for_forward()
                )
            _emit(
                {
                    "candidate_path": "Scheduler.run_batch.schedule_stream_forward_penalty_snapshot",
                    "phase": "runtime_invocation",
                    "ordering_edge": "forward_stream.wait_stream(schedule_stream)",
                    "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                }
            )
        return original_run_batch(self, batch, *args, **kwargs)

    @contextlib.contextmanager
    def forward_isolation(self, batch, *, overlap: bool):
        snapshot_v2_full = batch.is_spec_v2
        sched_snapshot = (
            {field.name: getattr(batch, field.name) for field in dataclasses.fields(batch)}
            if snapshot_v2_full
            else None
        )
        sched_sampling_info = batch.sampling_info
        prepared = getattr(batch, "_schedule_stream_forward_penalty_snapshot", None)
        if sched_sampling_info is not None:
            batch.sampling_info = prepared or sched_sampling_info.copy_for_forward()
        if overlap:
            self.record_batch_in_overlap(batch)
        try:
            yield
        finally:
            if hasattr(batch, "_schedule_stream_forward_penalty_snapshot"):
                delattr(batch, "_schedule_stream_forward_penalty_snapshot")
            if snapshot_v2_full:
                for name, value in sched_snapshot.items():
                    setattr(batch, name, value)
            else:
                batch.sampling_info = sched_sampling_info

    Scheduler.run_batch = run_batch
    Scheduler._forward_isolation = forward_isolation
