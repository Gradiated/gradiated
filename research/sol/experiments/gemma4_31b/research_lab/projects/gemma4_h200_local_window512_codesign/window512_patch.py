from __future__ import annotations

import hashlib
import pathlib


TARGET = pathlib.Path(
    "/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py"
)
BASE_SHA256 = "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989"
CONTROL = """        self.sliding_window = (
            config.sliding_window if layer_type == "sliding_attention" else None
        )
"""
CANDIDATE = """        self.sliding_window = (
            512 if layer_type == "sliding_attention" else None
        )
        if _window_audit := __import__("os").environ.get("WINDOW512_LAYER_AUDIT"):
            _window_path = __import__("pathlib").Path(_window_audit)
            _window_path.parent.mkdir(parents=True, exist_ok=True)
            with _window_path.open("a") as _window_handle:
                _window_handle.write(
                    __import__("json").dumps(
                        {
                            "candidate_path": "Gemma4Attention.__init__.local_window512",
                            "layer_id": layer_id,
                            "layer_type": layer_type,
                            "sliding_window_size": self.sliding_window,
                            "q_heads": config.num_attention_heads,
                            "kv_heads": (
                                getattr(
                                    config,
                                    "swa_num_key_value_heads",
                                    config.num_key_value_heads,
                                )
                                if layer_type == "sliding_attention"
                                else config.num_key_value_heads
                            ),
                            "qk_head_dim": head_dim,
                            "v_head_dim": head_dim,
                        },
                        sort_keys=True,
                    )
                    + "\\n"
                )
"""


def install() -> None:
    text = TARGET.read_text()
    if CANDIDATE in text:
        return
    if CONTROL not in text or text.count(CONTROL) != 1:
        raise RuntimeError(
            "bound Gemma4 local-window assignment is absent or non-unique:"
            + hashlib.sha256(text.encode()).hexdigest()
        )
    TARGET.write_text(text.replace(CONTROL, CANDIDATE))
