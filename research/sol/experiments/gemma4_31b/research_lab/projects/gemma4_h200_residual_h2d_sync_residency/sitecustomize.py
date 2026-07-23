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


def install_stacked_frontier() -> None:
    target = pathlib.Path(
        "/sgl-workspace/sglang/python/sglang/srt/layers/attention/triton_backend.py"
    )
    if not (target.is_file() and "deferred_local_fp8_kv" in target.read_text()):
        importlib.import_module("attention_intervention").install()

    audit = os.environ.get("RESIDUAL_CANDIDATE_AUDIT")
    if audit:
        os.environ["SYNC_CANDIDATE_AUDIT"] = audit

    pinned = importlib.import_module("pinned_async_penalty_tokens")
    actual = hashlib.sha256(pinned.TARGET.read_bytes()).hexdigest()
    if actual == pinned.EXPECTED_SHA256:
        pinned.install()
    elif actual != "b6480f792867d7aba3dc39ef66048408c6c92ddad3ed81b23934493a351be459":
        raise RuntimeError(f"pinned schedule_batch source mismatch:{actual}")

    importlib.import_module("host_min_new_tokens_gate").install()
    importlib.import_module("residual_intervention").install()
    if os.environ.get("RESIDUAL_ARM") == "candidate":
        importlib.import_module("pinned_prefix_pointer_h2d").install()


install_qkv_baseline()
install_profile_signals()
install_stacked_frontier()
