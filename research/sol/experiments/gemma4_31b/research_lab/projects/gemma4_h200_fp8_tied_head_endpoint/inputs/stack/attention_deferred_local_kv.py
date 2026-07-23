from __future__ import annotations

import hashlib
import pathlib


TARGET = pathlib.Path("/sgl-workspace/sglang/python/sglang/srt/layers/attention/triton_backend.py")
EXPECTED_SHA256 = "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d"

OLD_INIT = """    def forward_extend(
        self,
        q: torch.Tensor,
        k: torch.Tensor,
        v: torch.Tensor,
        layer: RadixAttention,
        forward_batch: ForwardBatch,
        save_kv_cache=True,
        sinks=None,
    ):
        # TODO: reuse the buffer across layers
        if layer.qk_head_dim != layer.v_head_dim:
"""
NEW_INIT = """    def forward_extend(
        self,
        q: torch.Tensor,
        k: torch.Tensor,
        v: torch.Tensor,
        layer: RadixAttention,
        forward_batch: ForwardBatch,
        save_kv_cache=True,
        sinks=None,
    ):
        # Candidate: local FP8 cache quantization is deferred until the
        # extend-attention kernel has consumed K/V, eliminating protective clones.
        deferred_local_fp8_kv = False
        if layer.qk_head_dim != layer.v_head_dim:
"""

OLD_LOCAL = """                    else:
                        self.token_to_kv_pool.set_kv_buffer(
                            layer,
                            forward_batch.out_cache_loc,
                            k.clone(),
                            v.clone(),
                            layer.k_scale,
                            layer.v_scale,
                            swa_loc=self.forward_metadata.swa_out_cache_loc,
                        )
"""
NEW_LOCAL = """                    else:
                        if (
                            not self.enable_deterministic
                            and layer.sliding_window_size is not None
                            and layer.sliding_window_size > -1
                        ):
                            deferred_local_fp8_kv = True
                        else:
                            self.token_to_kv_pool.set_kv_buffer(
                                layer,
                                forward_batch.out_cache_loc,
                                k.clone(),
                                v.clone(),
                                layer.k_scale,
                                layer.v_scale,
                                swa_loc=self.forward_metadata.swa_out_cache_loc,
                            )
"""

OLD_RETURN = """            xai_temperature_len=layer.xai_temperature_len,
        )
        return o
"""
NEW_RETURN = """            xai_temperature_len=layer.xai_temperature_len,
        )
        if deferred_local_fp8_kv:
            # Same CUDA stream: _fwd_kernel consumes the unscaled tensors before
            # set_kv_buffer's in-place descale and FP8 conversion are enqueued.
            self.token_to_kv_pool.set_kv_buffer(
                layer,
                forward_batch.out_cache_loc,
                k,
                v,
                layer.k_scale,
                layer.v_scale,
                swa_loc=self.forward_metadata.swa_out_cache_loc,
            )
            if not getattr(self, "_deferred_local_fp8_kv_audited", False):
                import json as _json
                import os as _os
                _audit = _os.environ.get("RESIDUAL_CANDIDATE_AUDIT")
                if _audit:
                    with open(_audit, "a") as _handle:
                        _handle.write(_json.dumps({
                            "candidate_path": "TritonAttnBackend.forward_extend.local_fp8_deferred_cache_commit",
                            "phase": "runtime_invocation",
                            "layer_id": layer.layer_id,
                            "qk_head_dim": layer.qk_head_dim,
                            "v_head_dim": layer.v_head_dim,
                            "sliding_window_size": layer.sliding_window_size,
                            "removed_operations": ["k.clone", "v.clone"],
                        }, sort_keys=True) + "\\n")
                self._deferred_local_fp8_kv_audited = True
        return o
"""


def install() -> None:
    raw = TARGET.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != EXPECTED_SHA256:
        raise RuntimeError(f"pinned Triton backend source mismatch:{actual}")
    text = raw.decode()
    for old in (OLD_INIT, OLD_LOCAL, OLD_RETURN):
        if text.count(old) != 1:
            raise RuntimeError("attention intervention patch target is not unique")
    text = text.replace(OLD_INIT, NEW_INIT).replace(OLD_LOCAL, NEW_LOCAL).replace(OLD_RETURN, NEW_RETURN)
    TARGET.write_text(text)
