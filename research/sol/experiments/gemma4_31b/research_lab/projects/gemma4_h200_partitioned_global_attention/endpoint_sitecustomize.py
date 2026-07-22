from __future__ import annotations

import hashlib
import importlib
import os
import pathlib


PINNED_EXTEND_SHA256 = "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"
TARGET = pathlib.Path(
    "/sgl-workspace/sglang/python/sglang/srt/layers/attention/triton_ops/extend_attention.py"
)


def install_retained_stack() -> None:
    os.environ["RESIDUAL_ARM"] = "control"
    importlib.import_module("residual_sitecustomize")


def install_forced_residency() -> None:
    if os.environ.get("ATTENTION_RESIDENCY_ARM") != "candidate":
        return
    transformer = importlib.import_module("forced_residency_attention")
    raw = TARGET.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != PINNED_EXTEND_SHA256:
        if "global_head512_maxnreg128" in raw.decode():
            return
        raise RuntimeError(f"pinned_extend_attention_source_mismatch:{actual}")
    transformed = transformer.transform_source(raw)
    TARGET.write_bytes(transformed)


install_retained_stack()
install_forced_residency()
