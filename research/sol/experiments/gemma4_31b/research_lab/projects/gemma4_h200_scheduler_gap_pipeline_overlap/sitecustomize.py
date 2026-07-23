from __future__ import annotations

import hashlib
import importlib
import json
import os
import pathlib
import signal


def append(path: str, row: object) -> None:
    destination = pathlib.Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def install_qkv_baseline() -> None:
    from install_endpoint_patch import EXPECTED_SHA256, NEW, OLD

    path = pathlib.Path("/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual == EXPECTED_SHA256:
        if raw.decode().count(OLD) != 1:
            raise RuntimeError("bound QKV patch target is not unique")
        path.write_text(raw.decode().replace(OLD, NEW))
    elif "qkv_norm_rope_inplace" not in raw.decode():
        raise RuntimeError(f"bound QKV source mismatch:{actual}")


def install_profile_signals() -> None:
    marker = os.environ.get("PROFILE_SIGNAL_AUDIT")
    if not marker:
        return

    def toggle(action: str) -> None:
        import torch

        function = getattr(torch.cuda.cudart(), f"cudaProfiler{action}")
        result = function()
        append(marker, {"action": action.lower(), "pid": os.getpid(), "result": int(result)})

    signal.signal(signal.SIGUSR1, lambda *_: toggle("Start"))
    signal.signal(signal.SIGUSR2, lambda *_: toggle("Stop"))


def install_stacked_attention() -> None:
    target = pathlib.Path("/sgl-workspace/sglang/python/sglang/srt/layers/attention/triton_backend.py")
    if target.is_file() and "deferred_local_fp8_kv" in target.read_text():
        return
    module = importlib.import_module("attention_intervention")
    module.install()


def install_pinned_penalty_transfer() -> None:
    if audit := os.environ.get("RESIDUAL_CANDIDATE_AUDIT"):
        os.environ["SYNC_CANDIDATE_AUDIT"] = audit
    module = importlib.import_module("pinned_async_penalty_tokens")
    actual = hashlib.sha256(module.TARGET.read_bytes()).hexdigest()
    if actual == module.EXPECTED_SHA256:
        module.install()
        return
    if actual != "b6480f792867d7aba3dc39ef66048408c6c92ddad3ed81b23934493a351be459":
        raise RuntimeError(f"pinned schedule_batch source mismatch:{actual}")


def install_retained_dense_add() -> None:
    if audit := os.environ.get("RESIDUAL_CANDIDATE_AUDIT"):
        os.environ["SYNC_CANDIDATE_AUDIT"] = audit
    module = importlib.import_module("host_min_new_tokens_gate")
    module.install()


def install_metadata_candidate() -> None:
    if os.environ.get("RESIDUAL_ARM") != "candidate":
        return
    module = importlib.import_module("residual_intervention")
    module.install()


def install_scheduler_rebind_stack() -> None:
    if os.environ.get("SCHEDULER_REBIND_STACKED") != "1":
        return
    stacked = importlib.import_module("residual_intervention")
    stacked.install()
    if os.environ.get("RESIDUAL_ARM") == "candidate":
        candidate = importlib.import_module("scheduler_intervention")
        candidate.install()
        append(
            os.environ["RESIDUAL_CANDIDATE_AUDIT"],
            {
                "candidate_path": "Scheduler.run_batch.observed_source_schedule_stream_forward_penalty_snapshot",
                "implementation_sha256": "3b5aa497985a400c16189db8359a458d981adff66d8465c26a92ed54394414e6",
                "phase": "installation_complete",
                "predecessor": "pinned_async_penalty_tokens",
                "worker_pid": os.getpid(),
            },
        )


install_qkv_baseline()
install_profile_signals()
install_stacked_attention()
install_pinned_penalty_transfer()
install_retained_dense_add()
if os.environ.get("SCHEDULER_REBIND_STACKED") == "1":
    install_scheduler_rebind_stack()
else:
    install_metadata_candidate()
