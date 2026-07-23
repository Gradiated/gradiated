from __future__ import annotations

import functools
import importlib
import json
import os
import pathlib
import time


AUDIT = os.environ.get("DEVICE_GRAPH_PATH_AUDIT")


def append(row: dict[str, object]) -> None:
    if not AUDIT:
        return
    path = pathlib.Path(AUDIT)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "pid": os.getpid(),
        "monotonic_s": time.monotonic(),
        **row,
    }
    with path.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def install_retained_stack() -> None:
    importlib.import_module("bound_stack_sitecustomize")
    try:
        importlib.import_module("attention_intervention").install()
    except RuntimeError as error:
        # The tokenizer process installs the source-level retained stack before
        # SGLang forks/spawns its scheduler workers.  Those workers must accept
        # only the exact, already-installed attention bytes and continue on to
        # install their process-local audit wrappers.
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


def batch_size(value) -> int | None:
    if value is None:
        return None
    size = getattr(value, "batch_size", None)
    if callable(size):
        return int(size())
    if size is not None:
        return int(size)
    reqs = getattr(value, "reqs", None)
    return len(reqs) if reqs is not None else None


def wrap(cls, name: str, batch_position: int | None = None) -> None:
    original = getattr(cls, name)

    @functools.wraps(original)
    def wrapped(*args, **kwargs):
        batch = None
        if batch_position is not None and len(args) > batch_position:
            batch = args[batch_position]
        elif batch_position is not None:
            batch = kwargs.get("batch") or kwargs.get("forward_batch")
        row = {
            "event": f"{cls.__name__}.{name}",
            "batch_size": batch_size(batch),
            "phase": "host_entry",
        }
        if cls.__name__ == "CudaGraphRunner":
            row["phase"] = "cuda_graph_replay"
        append(row)
        result = original(*args, **kwargs)
        if cls.__name__ == "CudaGraphRunner":
            append(
                {
                    "event": "CudaGraphRunner.replay_complete",
                    "phase": "cuda_graph_replay",
                    "raw_batch_size": getattr(args[0], "raw_bs", None),
                    "captured_batch_size": getattr(args[0], "bs", None),
                }
            )
        return result

    setattr(cls, name, wrapped)


def install_audit() -> None:
    from sglang.srt.managers.schedule_batch import ScheduleBatch
    from sglang.srt.managers.scheduler import Scheduler
    from sglang.srt.managers.scheduler_components.batch_result_processor import (
        SchedulerBatchResultProcessor,
    )
    from sglang.srt.managers.tp_worker import TpModelWorker
    from sglang.srt.model_executor.cuda_graph_runner import CudaGraphRunner
    from sglang.srt.model_executor.model_runner import ModelRunner

    wrap(Scheduler, "run_batch", 1)
    wrap(Scheduler, "process_batch_result", 1)
    wrap(Scheduler, "update_running_batch", 1)
    wrap(ScheduleBatch, "prepare_for_decode", None)
    wrap(TpModelWorker, "forward_batch_generation", 1)
    wrap(ModelRunner, "sample", 2)
    wrap(CudaGraphRunner, "replay", 1)
    wrap(SchedulerBatchResultProcessor, "process_batch_result_decode", 1)
    append({"event": "device_graph_audit_installed", "phase": "installation"})


install_retained_stack()
install_audit()
