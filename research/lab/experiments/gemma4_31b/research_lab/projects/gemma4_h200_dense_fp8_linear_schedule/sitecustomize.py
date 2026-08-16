from __future__ import annotations

import hashlib
import importlib
import os
import pathlib


def install_qkv_baseline() -> None:
    from install_endpoint_patch import EXPECTED_SHA256, NEW, OLD

    path = pathlib.Path("/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py")
    raw = path.read_bytes()
    observed = hashlib.sha256(raw).hexdigest()
    if observed == EXPECTED_SHA256:
        text = raw.decode()
        if text.count(OLD) != 1:
            raise RuntimeError("bound QKV patch target is not unique")
        path.write_text(text.replace(OLD, NEW))
    elif "qkv_norm_rope_inplace" not in raw.decode():
        raise RuntimeError(f"bound QKV source mismatch:{observed}")


def install_stacked_attention() -> None:
    target = pathlib.Path("/sgl-workspace/sglang/python/sglang/srt/layers/attention/triton_backend.py")
    if target.is_file() and "deferred_local_fp8_kv" in target.read_text():
        return
    importlib.import_module("attention_intervention").install()


def install_streamk() -> None:
    if os.environ.get("DOWN_STREAMK_ARM") not in {"component", "candidate"}:
        return
    importlib.import_module("down_streamk_probe").install()


def install_gate_up() -> None:
    if os.environ.get("GATE_UP_ARM") not in {"component", "candidate"}:
        return
    importlib.import_module("gate_up_probe").install()


install_qkv_baseline()
install_stacked_attention()
install_streamk()
install_gate_up()
