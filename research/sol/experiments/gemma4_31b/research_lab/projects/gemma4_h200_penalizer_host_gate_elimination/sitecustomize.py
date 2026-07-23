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
    module.install()


def install_residual_candidate() -> None:
    if os.environ.get("RESIDUAL_ARM") != "candidate":
        return
    if audit := os.environ.get("RESIDUAL_CANDIDATE_AUDIT"):
        os.environ["SYNC_CANDIDATE_AUDIT"] = audit
    module = importlib.import_module("residual_intervention")
    module.install()


install_qkv_baseline()
install_profile_signals()
install_stacked_attention()
install_pinned_penalty_transfer()
install_residual_candidate()
