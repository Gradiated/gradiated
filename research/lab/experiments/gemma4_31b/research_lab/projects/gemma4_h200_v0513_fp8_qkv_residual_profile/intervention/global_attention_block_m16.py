from __future__ import annotations

import hashlib
import pathlib


TARGET = pathlib.Path(
    "/sgl-workspace/sglang/python/sglang/srt/layers/attention/triton_ops/extend_attention.py"
)
EXPECTED_SHA256 = "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"

OLD = """    BLOCK_DMODEL, BLOCK_DPE, BLOCK_DV, BLOCK_M, BLOCK_N, num_warps = (
        _get_block_sizes_for_extend_attention(Lq, Lv)
    )

    sm_scale = sm_scale or 1.0 / (Lq**0.5)
    batch_size, head_num = qo_indptr.shape[0] - 1, q_extend.shape[1]
"""

NEW = """    BLOCK_DMODEL, BLOCK_DPE, BLOCK_DV, BLOCK_M, BLOCK_N, num_warps = (
        _get_block_sizes_for_extend_attention(Lq, Lv)
    )

    # Exact H200 Gemma-4 global-attention specialization. NCU measures the
    # 32x64 kernel at 255 registers/thread and one CTA/SM, while HBM and L2 are
    # well below saturation. The 16-row tile reduces per-program live state;
    # all local-attention and other head shapes retain the pinned schedule.
    global_head512_block_m16 = (
        _is_cuda
        and CUDA_CAPABILITY[0] == 9
        and Lq == 512
        and Lv == 512
        and sliding_window_size <= -1
    )
    if global_head512_block_m16:
        BLOCK_M, BLOCK_N = 16, 64
        if not getattr(extend_attention_fwd, "_global_head512_block_m16_audited", False):
            import json as _json
            import os as _os

            _audit = _os.environ.get("RESIDUAL_CANDIDATE_AUDIT")
            if _audit:
                with open(_audit, "a") as _handle:
                    _handle.write(_json.dumps({
                        "candidate_path": "extend_attention_fwd.global_head512_block_m16",
                        "phase": "runtime_invocation",
                        "qk_head_dim": Lq,
                        "v_head_dim": Lv,
                        "q_heads": q_extend.shape[1],
                        "kv_heads": k_extend.shape[1],
                        "sliding_window_size": sliding_window_size,
                        "control_tile": [32, 64],
                        "candidate_tile": [BLOCK_M, BLOCK_N],
                        "max_len_extend": max_len_extend,
                        "causal_limiter": "register_live_state",
                    }, sort_keys=True) + "\\n")
            extend_attention_fwd._global_head512_block_m16_audited = True

    sm_scale = sm_scale or 1.0 / (Lq**0.5)
    batch_size, head_num = qo_indptr.shape[0] - 1, q_extend.shape[1]
"""


def install() -> None:
    raw = TARGET.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != EXPECTED_SHA256:
        raise RuntimeError(f"pinned Triton extend-attention source mismatch:{actual}")
    text = raw.decode()
    if text.count(OLD) != 1:
        raise RuntimeError("global attention intervention patch target is not unique")
    TARGET.write_text(text.replace(OLD, NEW))
