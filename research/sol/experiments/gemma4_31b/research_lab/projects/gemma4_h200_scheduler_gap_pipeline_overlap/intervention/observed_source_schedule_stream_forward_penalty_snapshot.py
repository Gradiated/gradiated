from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import importlib
import inspect
import json
import os
import pathlib


EXPECTED_SOURCE_SHA256 = {
    "sglang.srt.managers.schedule_batch": "b6480f792867d7aba3dc39ef66048408c6c92ddad3ed81b23934493a351be459",
    "sglang.srt.managers.scheduler": "3a26deea85f43d61c27b94013288ad95d6ee75111fe40134893541777c9c8cd4",
    "sglang.srt.sampling.sampling_batch_info": "e7903417a4cab05294975d069555987e2720557dd9fd0b8d79a6f934f3fbb0db",
    "sglang.srt.sampling.penaltylib.orchestrator": "88d9a4c04866a8b2dad0efe6f010f28f7e7dfa0e65708920f7845d760e833192",
}


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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

    identities = {}
    for module_name, expected in EXPECTED_SOURCE_SHA256.items():
        module = importlib.import_module(module_name)
        actual = _sha256(pathlib.Path(module.__file__))
        identities[module_name] = actual
        if actual != expected:
            raise RuntimeError(
                f"observed scheduler source mismatch:{module_name}:{actual}"
            )

    source = inspect.getsource(Scheduler._forward_isolation)
    required = (
        "sched_sampling_info.copy_for_forward()",
        "self.record_batch_in_overlap(batch)",
        "batch.sampling_info = sched_sampling_info",
    )
    if not all(token in source for token in required):
        raise RuntimeError("observed scheduler snapshot source mismatch")
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
                    "candidate_path": "Scheduler.run_batch.observed_source_schedule_stream_forward_penalty_snapshot",
                    "phase": "runtime_invocation",
                    "ordering_edge": "forward_stream.wait_stream(schedule_stream)",
                    "lifetime": "record_batch_in_overlap_two_iteration_ring",
                    "source_sha256": identities,
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
            if overlap and prepared is None:
                raise RuntimeError("observed scheduler snapshot was not prepared")
            batch.sampling_info = (
                prepared if prepared is not None else sched_sampling_info.copy_for_forward()
            )
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
