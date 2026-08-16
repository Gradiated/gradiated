from __future__ import annotations

import importlib


def install_retained_stack() -> None:
    import os

    os.environ["RESIDUAL_ARM"] = "control"
    importlib.import_module("residual_sitecustomize")


def install_local_value_split() -> None:
    import os

    if os.environ.get("ATTENTION_RESIDENCY_ARM") != "candidate":
        return
    candidate = importlib.import_module("candidate_local_value_split")
    target = importlib.import_module(
        "sglang.srt.layers.attention.triton_ops.extend_attention"
    )
    original = target.extend_attention_fwd

    def wrapped(
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
        eligible = (
            q_extend.shape[-2:] == (32, 256)
            and k_extend.shape[-2:] == (16, 256)
            and v_extend.shape[-2:] == (16, 256)
            and sliding_window_size == 1024
        )
        implementation = candidate.extend_attention_fwd if eligible else original
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

    target.extend_attention_fwd = wrapped


install_retained_stack()
install_local_value_split()
