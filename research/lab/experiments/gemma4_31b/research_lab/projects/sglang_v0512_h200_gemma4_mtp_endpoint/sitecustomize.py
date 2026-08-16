"""Project-local v0.5.13 QKV patch plus the admitted eager-buffer repair."""

import hashlib
import os
import pathlib


def _patch_qkv() -> None:
    if os.environ.get("QKV_STACK_ARM") != "candidate":
        return
    from install_endpoint_patch import EXPECTED_SHA256, NEW, OLD

    path = pathlib.Path("/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() == EXPECTED_SHA256:
        text = raw.decode()
        if text.count(OLD) != 1:
            raise RuntimeError("QKV stack patch target is not unique")
        path.write_text(text.replace(OLD, NEW))
    elif "qkv_norm_rope_inplace" not in raw.decode():
        raise RuntimeError("QKV stack source identity mismatch")


_patch_qkv()
