from __future__ import annotations

import hashlib
import importlib
import os
import pathlib


def install_qkv() -> None:
    from install_endpoint_patch import EXPECTED_SHA256, NEW, OLD

    path = pathlib.Path(
        "/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py"
    )
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual == EXPECTED_SHA256:
        text = raw.decode()
        if text.count(OLD) != 1:
            raise RuntimeError("bound QKV patch target is not unique")
        path.write_text(text.replace(OLD, NEW))
    elif "qkv_norm_rope_inplace" not in raw.decode():
        raise RuntimeError(f"bound QKV source mismatch:{actual}")


def install_stacked_frontier() -> None:
    audit = os.environ.get("RESIDUAL_CANDIDATE_AUDIT")
    if audit:
        os.environ["SYNC_CANDIDATE_AUDIT"] = audit
    attention = importlib.import_module("attention_deferred_local_kv")
    if "deferred_local_fp8_kv" not in attention.TARGET.read_text():
        attention.install()
    pinned = importlib.import_module("pinned_async_penalty_tokens")
    actual = hashlib.sha256(pinned.TARGET.read_bytes()).hexdigest()
    if actual == pinned.EXPECTED_SHA256:
        pinned.install()
    elif (
        actual
        != "b6480f792867d7aba3dc39ef66048408c6c92ddad3ed81b23934493a351be459"
    ):
        raise RuntimeError(f"pinned schedule_batch source mismatch:{actual}")
    importlib.import_module("host_min_new_tokens_gate").install()
    importlib.import_module("producer_fused_swa_translation").install()


if os.environ.get("STACKED_FRONTIER_ARM") == "candidate":
    install_qkv()
    install_stacked_frontier()
    if os.environ.get("RING_CACHE_ARM") == "candidate":
        importlib.import_module("endpoint_ring_patch").install()
    if os.environ.get("FP8_TIED_HEAD_ARM") == "candidate":
        importlib.import_module("fp8_tied_head_patch").install()
