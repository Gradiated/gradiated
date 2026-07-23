from __future__ import annotations

import hashlib
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TARGET_ROOT = Path("/sgl-workspace/sglang/python/sglang/srt")
TARGET_RUNNER = TARGET_ROOT / "model_executor/model_runner.py"
TARGET_BACKEND = TARGET_ROOT / "layers/attention/gemma4_layer_hybrid_backend.py"
BACKEND_SOURCE = ROOT / "gemma4_layer_hybrid_backend.py"
EXPECTED_RUNNER_SHA256 = "f4dad073eb9f89afd4cda0439b97dee63f8de131d0ed10078b817dba1f978f59"
OLD = """        else:
            attn_backend = self._get_attention_backend_from_str(
                self.server_args.attention_backend,
                init_new_workspace=init_new_workspace,
            )
"""
NEW = """        else:
            if __import__("os").environ.get("E4M3_FA3_LAYER_HYBRID") == "1":
                from sglang.srt.layers.attention.gemma4_layer_hybrid_backend import (
                    Gemma4LayerHybridAttnBackend,
                )

                attn_backend = Gemma4LayerHybridAttnBackend(
                    self,
                    local_backend=self._get_attention_backend_from_str(
                        "fa3", init_new_workspace=init_new_workspace
                    ),
                    global_backend=self._get_attention_backend_from_str(
                        "triton", init_new_workspace=init_new_workspace
                    ),
                )
            else:
                attn_backend = self._get_attention_backend_from_str(
                    self.server_args.attention_backend,
                    init_new_workspace=init_new_workspace,
                )
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install() -> None:
    raw = TARGET_RUNNER.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    text = raw.decode()
    if NEW not in text:
        if digest != EXPECTED_RUNNER_SHA256:
            raise RuntimeError(f"bound_model_runner_source_mismatch:{digest}")
        if text.count(OLD) != 1:
            raise RuntimeError("bound_model_runner_patch_target_not_unique")
        temporary = TARGET_RUNNER.with_suffix(".hybrid.part")
        temporary.write_text(text.replace(OLD, NEW))
        os.replace(temporary, TARGET_RUNNER)
    backend_bytes = BACKEND_SOURCE.read_bytes()
    if TARGET_BACKEND.exists() and TARGET_BACKEND.read_bytes() == backend_bytes:
        return
    temporary_backend = TARGET_BACKEND.with_suffix(".part")
    temporary_backend.write_bytes(backend_bytes)
    os.replace(temporary_backend, TARGET_BACKEND)
