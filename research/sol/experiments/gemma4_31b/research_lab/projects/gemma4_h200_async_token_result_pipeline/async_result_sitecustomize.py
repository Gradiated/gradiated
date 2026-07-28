from __future__ import annotations

import functools
import importlib
import json
import os
import pathlib
import threading
import time


AUDIT = pathlib.Path(
    os.environ.get("ASYNC_RESULT_AUDIT", "/work/artifacts/async-result-audit.jsonl")
)
ARM_FILE = pathlib.Path(
    os.environ.get("ASYNC_RESULT_ARM_FILE", "/work/artifacts/ASYNC_RESULT_ARM")
)
MAX_BATCH = 32
_lock = threading.Lock()
_generation = 0
_last_returned_generation: int | None = None


def arm() -> str:
    try:
        value = ARM_FILE.read_text().strip()
    except FileNotFoundError:
        return "control"
    return value if value in {"control", "candidate"} else "control"


def append(event: str, **fields: object) -> None:
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "event": event,
        "arm": arm(),
        "monotonic_s": time.monotonic(),
        "pid": os.getpid(),
        **fields,
    }
    with _lock, AUDIT.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()


def install_retained_stack() -> None:
    importlib.import_module("bound_stack_sitecustomize")
    try:
        importlib.import_module("attention_intervention").install()
    except RuntimeError as error:
        if str(error) != (
            "pinned Triton backend source mismatch:"
            "1e322448fb8033511574ac7555bc3d22d11f2f55f324018403ab1203f7d61ceb"
        ):
            raise
    try:
        importlib.import_module("pinned_async_penalty_tokens").install()
    except RuntimeError as error:
        if str(error) != (
            "pinned schedule_batch source mismatch:"
            "b6480f792867d7aba3dc39ef66048408c6c92ddad3ed81b23934493a351be459"
        ):
            raise
    importlib.import_module("host_min_new_tokens_gate").install()
    importlib.import_module("residual_intervention").install()


class TimedEvent:
    def __init__(self, event, generation: int) -> None:
        self.event = event
        self.generation = generation

    def synchronize(self) -> None:
        started = time.perf_counter_ns()
        self.event.synchronize()
        elapsed_us = (time.perf_counter_ns() - started) / 1000
        append(
            "copy_event_synchronize",
            generation=self.generation,
            elapsed_us=elapsed_us,
        )

    def __getattr__(self, name: str):
        return getattr(self.event, name)


class TwoSlotPinnedRing:
    def __init__(self) -> None:
        self.slots = None
        self.events = [None, None]
        self.next_slot = 0
        self.dtype = None

    def copy(self, tensor, event):
        import torch

        if self.slots is None:
            self.dtype = tensor.dtype
            self.slots = [
                torch.empty(MAX_BATCH, dtype=tensor.dtype, device="cpu", pin_memory=True),
                torch.empty(MAX_BATCH, dtype=tensor.dtype, device="cpu", pin_memory=True),
            ]
            append(
                "ring_allocated",
                slots=2,
                elements_per_slot=MAX_BATCH,
                dtype=str(tensor.dtype),
                pinned=all(slot.is_pinned() for slot in self.slots),
            )
        if tensor.dtype != self.dtype or tensor.ndim != 1 or tensor.numel() > MAX_BATCH:
            raise RuntimeError(
                f"two-slot result contract mismatch: dtype={tensor.dtype}, "
                f"shape={tuple(tensor.shape)}"
            )
        index = self.next_slot
        previous = self.events[index]
        safe = previous is None or previous.query()
        append("slot_reuse_check", slot=index, safe=safe)
        if not safe:
            raise RuntimeError(f"two-slot overwrite hazard on slot {index}")
        target = self.slots[index][: tensor.numel()]
        target.copy_(tensor, non_blocking=True)
        event.record()
        self.events[index] = event
        self.next_slot = 1 - index
        return target, index


_ring = TwoSlotPinnedRing()


def install_pipeline() -> None:
    from sglang.srt.managers.scheduler import Scheduler
    from sglang.srt.managers.scheduler_components.batch_result_processor import (
        SchedulerBatchResultProcessor,
    )
    from sglang.srt.managers.utils import GenerationBatchResult

    original_copy = GenerationBatchResult.copy_to_cpu

    @functools.wraps(original_copy)
    def copy_to_cpu(self, return_logprob: bool, return_hidden_states: bool = True):
        global _generation
        _generation += 1
        generation = _generation
        self._async_result_generation = generation
        active_arm = arm()
        started = time.perf_counter_ns()
        candidate_supported = (
            active_arm == "candidate"
            and not return_logprob
            and not return_hidden_states
            and getattr(self, "accept_lens", None) is None
            and getattr(self, "routed_experts_output", None) is None
            and getattr(self, "indexer_topk_output", None) is None
            and getattr(self, "expert_distribution_metrics", None) is None
            and hasattr(getattr(self, "next_token_ids", None), "is_cuda")
            and self.next_token_ids.is_cuda
        )
        if active_arm == "candidate" and not candidate_supported:
            append(
                "candidate_fallback",
                generation=generation,
                return_logprob=return_logprob,
                return_hidden_states=return_hidden_states,
            )
        if candidate_supported:
            target, slot = _ring.copy(self.next_token_ids, self.copy_done)
            self.next_token_ids = target
            path = "two_slot_pinned"
        else:
            original_copy(self, return_logprob, return_hidden_states)
            slot = None
            path = "stock_to_cpu"
        elapsed_us = (time.perf_counter_ns() - started) / 1000
        append(
            "copy_to_cpu",
            generation=generation,
            path=path,
            slot=slot,
            elements=int(self.next_token_ids.numel()),
            pinned=bool(self.next_token_ids.is_pinned()),
            elapsed_us=elapsed_us,
        )

    GenerationBatchResult.copy_to_cpu = copy_to_cpu

    original_run = Scheduler.run_batch

    @functools.wraps(original_run)
    def run_batch(self, batch, *args, **kwargs):
        global _last_returned_generation
        append(
            "run_batch_entry",
            after_generation=_last_returned_generation,
            forward_mode=str(batch.forward_mode),
            batch_size=int(batch.batch_size()),
        )
        result = original_run(self, batch, *args, **kwargs)
        generation = getattr(result, "_async_result_generation", None)
        _last_returned_generation = generation
        append(
            "run_batch_return",
            generation=generation,
            forward_mode=str(batch.forward_mode),
            batch_size=int(batch.batch_size()),
        )
        return result

    Scheduler.run_batch = run_batch

    original_process = SchedulerBatchResultProcessor.process_batch_result_decode

    @functools.wraps(original_process)
    def process_decode(self, batch, result):
        generation = getattr(result, "_async_result_generation", None)
        event = getattr(result, "copy_done", None)
        if event is not None and not isinstance(event, TimedEvent):
            result.copy_done = TimedEvent(event, generation)
        append(
            "process_decode_entry",
            generation=generation,
            batch_size=int(batch.batch_size()),
        )
        started = time.perf_counter_ns()
        value = original_process(self, batch, result)
        elapsed_us = (time.perf_counter_ns() - started) / 1000
        append(
            "process_decode_return",
            generation=generation,
            batch_size=int(batch.batch_size()),
            elapsed_us=elapsed_us,
        )
        return value

    SchedulerBatchResultProcessor.process_batch_result_decode = process_decode

    original_normalize = SchedulerBatchResultProcessor._normalize_decode_outputs

    @functools.wraps(original_normalize)
    def normalize(self, *args, **kwargs):
        result = kwargs.get("result")
        if result is None and len(args) > 1:
            result = args[1]
        generation = getattr(result, "_async_result_generation", None)
        started = time.perf_counter_ns()
        value = original_normalize(self, *args, **kwargs)
        elapsed_us = (time.perf_counter_ns() - started) / 1000
        append(
            "normalize_decode_outputs",
            generation=generation,
            elapsed_us=elapsed_us,
        )
        return value

    SchedulerBatchResultProcessor._normalize_decode_outputs = normalize
    append("async_result_pipeline_installed")


install_retained_stack()
install_pipeline()
