from __future__ import annotations

import importlib
import json
import os
import pathlib


def install_retained_stack() -> None:
    os.environ["RESIDUAL_ARM"] = "control"
    importlib.import_module("residual_sitecustomize")


def install_multistage_attention() -> None:
    if os.environ.get("ATTENTION_RESIDENCY_ARM") != "candidate":
        return
    implementation = importlib.import_module("multistage_attention")
    target = importlib.import_module(
        "sglang.srt.layers.attention.triton_ops.extend_attention"
    )
    original = target.extend_attention_fwd

    def wrapped(
        q_extend, k_extend, v_extend, o_extend, k_buffer, v_buffer,
        qo_indptr, kv_indptr, kv_indices, custom_mask, is_causal, mask_indptr,
        max_len_extend, k_scale, v_scale, sm_scale=None, logit_cap=0.0,
        skip_prefix_custom_mask=True, sliding_window_size=-1, sinks=None,
        window_kv_offsets=None, xai_temperature_len=-1,
    ):
        eligible = (
            q_extend.shape[-2:] == (32, 512)
            and k_extend.shape[-2:] == (4, 512)
            and v_extend.shape[-2:] == (4, 512)
            and custom_mask is None and is_causal and sliding_window_size <= -1
            and sinks is None and logit_cap == 0.0 and xai_temperature_len <= 0
        )
        if not eligible:
            return original(
                q_extend, k_extend, v_extend, o_extend, k_buffer, v_buffer,
                qo_indptr, kv_indptr, kv_indices, custom_mask, is_causal,
                mask_indptr, max_len_extend, k_scale, v_scale, sm_scale,
                logit_cap, skip_prefix_custom_mask, sliding_window_size, sinks,
                window_kv_offsets, xai_temperature_len,
            )
        implementation.run_paged(
            q_extend, k_extend, v_extend, o_extend, k_buffer, v_buffer,
            qo_indptr, kv_indptr, kv_indices, k_scale, v_scale,
            sm_scale or 1.0 / (q_extend.shape[-1] ** 0.5),
        )
        audit = os.environ.get("PARTITIONED_ATTENTION_AUDIT")
        if audit and not getattr(wrapped, "_audited", False):
            path = pathlib.Path(audit); path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as handle:
                handle.write(json.dumps({"candidate_path":"multistage.grouped_qk_softmax.sliced_v_4x128","phase":"runtime_invocation","qk_head_dim":512,"v_head_dim":512,"q_heads":32,"kv_heads":4,"value_slices":4,"value_slice_width":128,"kernel_boundary_ends_value_accumulator_live_range":True}, sort_keys=True) + "\n")
            wrapped._audited = True

    target.extend_attention_fwd = wrapped


install_retained_stack()
install_multistage_attention()
