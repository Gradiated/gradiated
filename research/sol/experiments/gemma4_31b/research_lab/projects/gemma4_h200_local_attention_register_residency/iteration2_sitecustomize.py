from __future__ import annotations

import importlib
import os


def install_retained_stack() -> None:
    os.environ["RESIDUAL_ARM"] = "control"
    importlib.import_module("residual_sitecustomize")


def install_two_stage_local_attention() -> None:
    if os.environ.get("ATTENTION_RESIDENCY_ARM") != "candidate":
        return
    candidate = importlib.import_module("two_stage_local_attention")
    target = importlib.import_module(
        "sglang.srt.layers.attention.triton_ops.extend_attention"
    )
    target.extend_attention_fwd = candidate.extend_attention_fwd


install_retained_stack()
install_two_stage_local_attention()
