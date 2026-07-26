from __future__ import annotations

import hashlib
import json
import os
import pathlib


EXTEND_ATTENTION_SHA256 = (
    "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"
)


def _source_hash(module: object) -> str:
    return hashlib.sha256(pathlib.Path(module.__file__).read_bytes()).hexdigest()


def _append(value: dict) -> None:
    path_value = os.environ.get("PACKED_M384_ROUTE_AUDIT")
    if not path_value:
        return
    path = pathlib.Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
        os.write(descriptor, payload.encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _install_packed_attention() -> None:
    if os.environ.get("PACKED_M384_ENDPOINT_ARM") != "candidate":
        return
    from sglang.srt.layers.attention.triton_ops import extend_attention as target

    observed = _source_hash(target)
    if observed != EXTEND_ATTENTION_SHA256:
        raise RuntimeError(f"packed_m384_extend_source_mismatch:{observed}")
    if getattr(target, "_packed_m384_endpoint_installed", False):
        return

    import packed_m384_endpoint as candidate

    original = target.extend_attention_fwd

    def routed(
        q_extend,
        k_extend,
        v_extend,
        o_extend,
        k_buffer,
        v_buffer,
        qo_indptr,
        kv_indptr,
        kv_indices,
        custom_mask,
        is_causal,
        mask_indptr,
        max_len_extend,
        k_scale,
        v_scale,
        sm_scale=None,
        logit_cap=0.0,
        skip_prefix_custom_mask=True,
        sliding_window_size=-1,
        sinks=None,
        window_kv_offsets=None,
        xai_temperature_len=-1,
    ):
        batch = qo_indptr.shape[0] - 1
        target_verify = custom_mask is not None and max_len_extend == 12
        local = (
            q_extend.shape[-2:] == (32, 256)
            and k_extend.shape[-2:] == (16, 256)
            and v_extend.shape[-2:] == (16, 256)
            and sliding_window_size == 1024
        )
        global_attention = (
            q_extend.shape[-2:] == (32, 512)
            and k_extend.shape[-2:] == (4, 512)
            and v_extend.shape[-2:] == (4, 512)
            and sliding_window_size <= 0
        )
        exact = (
            batch == 32
            and q_extend.shape[0] == 384
            and is_causal
            and logit_cap == 0.0
            and sinks is None
            and xai_temperature_len == -1
            and (local or global_attention)
        )
        if target_verify:
            _append(
                {
                    "batch": batch,
                    "candidate": "packed_m384_endpoint",
                    "global": global_attention,
                    "kv_indices": kv_indices.numel(),
                    "local": local,
                    "max_len_extend": max_len_extend,
                    "q_stride": list(q_extend.stride()),
                    "k_stride": list(k_extend.stride()),
                    "v_stride": list(v_extend.stride()),
                    "o_stride": list(o_extend.stride()),
                    "q_shape": list(q_extend.shape),
                    "route": "candidate" if exact else "rejected_no_fallback",
                }
            )
            if not exact:
                raise RuntimeError("packed_m384_target_verify_no_fallback")
            implementation = candidate.extend_attention_fwd
        else:
            implementation = original
        return implementation(
            q_extend,
            k_extend,
            v_extend,
            o_extend,
            k_buffer,
            v_buffer,
            qo_indptr,
            kv_indptr,
            kv_indices,
            custom_mask,
            is_causal,
            mask_indptr,
            max_len_extend,
            k_scale,
            v_scale,
            sm_scale,
            logit_cap,
            skip_prefix_custom_mask,
            sliding_window_size,
            sinks,
            window_kv_offsets,
            xai_temperature_len,
        )

    target.extend_attention_fwd = routed
    target._packed_m384_endpoint_installed = True
    _append(
        {
            "candidate": "packed_m384_endpoint",
            "event": "installed",
            "source_sha256": observed,
        }
    )


_install_packed_attention()

if os.environ.get("DECODE_EQ_LM_HEAD") == "1":
    from decode_equivalent_lm_head import install as _install_decode_equivalent

    _install_decode_equivalent()

if os.environ.get("TOKEN_TRACE_EVENTS"):
    from token_trace_hook import install as _install_token_trace

    _install_token_trace()
