"""Depth-interleaved BF16 LM head for the exact Gemma-4 NGRAM verifier."""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
import os
import pathlib
from typing import Callable

import torch


LOGITS_PROCESSOR_SHA256 = (
    "e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14"
)
DEPTHS = 12
BATCH = 32
HIDDEN = 5376
VOCAB = 262144
BLOCK_N = 256
BLOCK_K = 64


def _source_hash(module: object) -> str:
    return hashlib.sha256(pathlib.Path(module.__file__).read_bytes()).hexdigest()


def _append_audit(row: dict) -> None:
    value = os.environ.get("GROUPED_LM_HEAD_AUDIT")
    if not value:
        return
    path = pathlib.Path(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        payload = json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
        os.write(descriptor, payload.encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@functools.lru_cache(maxsize=1)
def _triton_symbols():
    import triton
    import triton.language as tl

    @triton.jit
    def depth_interleaved_grouped_lm_head(
        hidden_ptr,
        weight_ptr,
        output_ptr,
        hidden_row_stride: tl.constexpr,
        weight_vocab_stride: tl.constexpr,
        output_row_stride: tl.constexpr,
        depths: tl.constexpr,
        batch: tl.constexpr,
        hidden: tl.constexpr,
        vocab: tl.constexpr,
        block_n: tl.constexpr,
        block_k: tl.constexpr,
    ):
        program = tl.program_id(0)
        depth = program % depths
        vocab_block = program // depths
        rows = tl.arange(0, batch)
        columns = vocab_block * block_n + tl.arange(0, block_n)
        accumulator = tl.zeros((batch, block_n), dtype=tl.float32)
        for start_k in range(0, hidden, block_k):
            features = start_k + tl.arange(0, block_k)
            hidden_rows = rows * depths + depth
            activations = tl.load(
                hidden_ptr
                + hidden_rows[:, None] * hidden_row_stride
                + features[None, :]
            )
            weight_nk = tl.load(
                weight_ptr
                + columns[:, None] * weight_vocab_stride
                + features[None, :],
                mask=columns[:, None] < vocab,
                other=0.0,
            )
            accumulator += tl.dot(activations, tl.trans(weight_nk))
        output_rows = rows * depths + depth
        tl.store(
            output_ptr
            + output_rows[:, None] * output_row_stride
            + columns[None, :],
            accumulator.to(tl.bfloat16),
            mask=columns[None, :] < vocab,
        )

    return triton, depth_interleaved_grouped_lm_head


def grouped_lm_head(hidden_states: torch.Tensor, weight: torch.Tensor) -> torch.Tensor:
    output = torch.empty(
        (BATCH * DEPTHS, VOCAB),
        dtype=torch.bfloat16,
        device=hidden_states.device,
    )
    return grouped_lm_head_into(hidden_states, weight, output)


def grouped_lm_head_into(
    hidden_states: torch.Tensor,
    weight: torch.Tensor,
    output: torch.Tensor,
    *,
    kernel_launcher: Callable | None = None,
) -> torch.Tensor:
    if hidden_states.dtype != torch.bfloat16 or weight.dtype != torch.bfloat16:
        raise RuntimeError(
            f"grouped_lm_head_dtype:{hidden_states.dtype}:{weight.dtype}"
        )
    if tuple(hidden_states.shape) != (BATCH * DEPTHS, HIDDEN):
        raise RuntimeError(f"grouped_lm_head_hidden_shape:{tuple(hidden_states.shape)}")
    if tuple(weight.shape) != (VOCAB, HIDDEN):
        raise RuntimeError(f"grouped_lm_head_weight_shape:{tuple(weight.shape)}")
    if tuple(output.shape) != (BATCH * DEPTHS, VOCAB):
        raise RuntimeError(f"grouped_lm_head_output_shape:{tuple(output.shape)}")
    if output.dtype not in (torch.bfloat16, torch.float32):
        raise RuntimeError(f"grouped_lm_head_output_dtype:{output.dtype}")
    if not hidden_states.is_cuda or not weight.is_cuda or not output.is_cuda:
        raise RuntimeError("grouped_lm_head_requires_cuda")
    if (
        not hidden_states.is_contiguous()
        or not weight.is_contiguous()
        or not output.is_contiguous()
    ):
        raise RuntimeError("grouped_lm_head_requires_contiguous_tensors")
    if not (
        hidden_states.device == weight.device
        and hidden_states.device == output.device
    ):
        raise RuntimeError("grouped_lm_head_requires_single_device")
    if kernel_launcher is not None:
        kernel_launcher(hidden_states, weight, output)
        return output

    triton, kernel = _triton_symbols()
    grid = (triton.cdiv(VOCAB, BLOCK_N) * DEPTHS,)
    kernel[grid](
        hidden_states,
        weight,
        output,
        hidden_states.stride(0),
        weight.stride(0),
        output.stride(0),
        DEPTHS,
        BATCH,
        HIDDEN,
        VOCAB,
        BLOCK_N,
        BLOCK_K,
        num_warps=8,
        num_stages=3,
    )
    return output


def project_decode_shapes(
    original: Callable,
    processor: object,
    hidden_states: torch.Tensor,
    lm_head: object,
    logits_metadata: object,
    embedding_bias: torch.Tensor | None,
    draft_tokens: int,
) -> torch.Tensor:
    rows = hidden_states.shape[0]
    if rows % draft_tokens:
        raise RuntimeError(
            f"decode_equivalent_rows_not_divisible:{rows}:{draft_tokens}"
        )
    batch_size = rows // draft_tokens
    chunk_metadata = dataclasses.replace(
        logits_metadata, next_token_logits_buffer=None
    )
    request_major = hidden_states.reshape(
        batch_size, draft_tokens, hidden_states.shape[-1]
    )
    depth_logits = [
        original(
            processor,
            request_major[:, depth, :].contiguous(),
            lm_head,
            chunk_metadata,
            embedding_bias,
        )
        for depth in range(draft_tokens)
    ]
    logits = torch.stack(depth_logits, dim=1).reshape(
        rows, depth_logits[0].shape[-1]
    )
    if logits_metadata.next_token_logits_buffer is not None:
        buffer = logits_metadata.next_token_logits_buffer
        buffer.copy_(logits)
        logits = buffer
    return logits


def grouped_get_logits(
    processor: object,
    hidden_states: torch.Tensor,
    lm_head: object,
    logits_metadata: object,
) -> torch.Tensor:
    hidden_states, local_hidden_states = processor._gather_dp_attn_hidden_states(
        hidden_states, logits_metadata
    )
    logits = grouped_lm_head(
        hidden_states.to(lm_head.weight.dtype).contiguous(),
        lm_head.weight,
    )
    if processor.logit_scale is not None:
        logits.mul_(processor.logit_scale)
    if processor.do_tensor_parallel_all_gather:
        if processor.use_attn_tp_group:
            logits = processor._gather_attn_tp_logits(logits)
        else:
            raise RuntimeError("grouped_lm_head_exact_component_requires_tp1")
    logits = processor._scatter_dp_attn_logits(
        logits, local_hidden_states, logits_metadata
    )
    logits = processor._copy_logits_to_buffer(logits, logits_metadata)
    if processor.final_logit_softcapping:
        from sglang.srt.layers.logits_processor import fused_softcap

        fused_softcap(logits, processor.final_logit_softcapping)
    return logits


def grouped_get_logits_buffer_direct(
    processor: object,
    hidden_states: torch.Tensor,
    lm_head: object,
    logits_metadata: object,
    *,
    kernel_launcher: Callable | None = None,
    softcap_operator: Callable | None = None,
) -> torch.Tensor:
    logits = logits_metadata.next_token_logits_buffer
    grouped_lm_head_into(
        hidden_states,
        lm_head.weight,
        logits,
        kernel_launcher=kernel_launcher,
    )
    if processor.final_logit_softcapping:
        if softcap_operator is None:
            from sglang.srt.layers.logits_processor import fused_softcap

            softcap_operator = fused_softcap
        softcap_operator(logits, processor.final_logit_softcapping)
    return logits


def _common_grouped_activation_blocker(
    processor: object,
    hidden_states: torch.Tensor,
    lm_head: object,
    embedding_bias: torch.Tensor | None,
) -> str | None:
    if tuple(hidden_states.shape) != (BATCH * DEPTHS, HIDDEN):
        return "non_production_shape"
    if not hasattr(lm_head, "weight"):
        return "weight_unavailable"
    if tuple(lm_head.weight.shape) != (VOCAB, HIDDEN):
        return "non_production_weight_shape"
    if hidden_states.dtype != torch.bfloat16 or lm_head.weight.dtype != torch.bfloat16:
        return "non_bfloat16"
    if processor.use_fp32_lm_head:
        return "fp32_lm_head"
    if embedding_bias is not None:
        return "embedding_bias"
    if not hidden_states.is_cuda or not lm_head.weight.is_cuda:
        return "non_cuda_input"
    if not hidden_states.is_contiguous() or not lm_head.weight.is_contiguous():
        return "non_contiguous_input"
    if hidden_states.device != lm_head.weight.device:
        return "input_device_mismatch"
    return None


def grouped_buffer_direct_blocker(
    processor: object,
    hidden_states: torch.Tensor,
    lm_head: object,
    logits_metadata: object,
    embedding_bias: torch.Tensor | None,
) -> str | None:
    blocker = _common_grouped_activation_blocker(
        processor, hidden_states, lm_head, embedding_bias
    )
    if blocker is not None:
        return blocker
    if processor.logit_scale is not None:
        return "logit_scale"
    if processor.do_tensor_parallel_all_gather:
        return "tensor_parallel_all_gather"
    if processor.do_tensor_parallel_all_gather_dp_attn:
        return "dp_attention_all_gather"
    logits = logits_metadata.next_token_logits_buffer
    if logits is None:
        return "live_logits_buffer_required"
    if tuple(logits.shape) != (BATCH * DEPTHS, VOCAB):
        return "live_logits_buffer_shape"
    if logits.dtype != torch.float32:
        return "live_logits_buffer_dtype"
    if tuple(logits.stride()) != (VOCAB, 1):
        return "live_logits_buffer_stride"
    if not logits.is_cuda or not logits.is_contiguous():
        return "live_logits_buffer_layout"
    if logits.device != hidden_states.device:
        return "live_logits_buffer_device"
    if logits.data_ptr() in (hidden_states.data_ptr(), lm_head.weight.data_ptr()):
        return "live_logits_buffer_alias"
    return None


def grouped_activation_blocker(
    processor: object,
    hidden_states: torch.Tensor,
    lm_head: object,
    logits_metadata: object,
    embedding_bias: torch.Tensor | None,
    *,
    capture_active: bool | None = None,
) -> str | None:
    blocker = _common_grouped_activation_blocker(
        processor, hidden_states, lm_head, embedding_bias
    )
    if blocker is not None:
        return blocker
    if logits_metadata.next_token_logits_buffer is not None:
        return "live_logits_buffer"
    if capture_active is None:
        capture_active = bool(
            torch.cuda.is_available() and torch.cuda.is_current_stream_capturing()
        )
    if capture_active:
        return "cuda_graph_capture"
    return None


def dispatch_target_get_logits(
    original: Callable,
    processor: object,
    hidden_states: torch.Tensor,
    lm_head: object,
    logits_metadata: object,
    embedding_bias: torch.Tensor | None,
    *,
    capture_active: bool | None = None,
    grouped_projector: Callable = grouped_get_logits,
    buffer_projector: Callable = grouped_get_logits_buffer_direct,
) -> torch.Tensor:
    if not logits_metadata.forward_mode.is_target_verify():
        return original(
            processor, hidden_states, lm_head, logits_metadata, embedding_bias
        )
    buffer_blocker = grouped_buffer_direct_blocker(
        processor,
        hidden_states,
        lm_head,
        logits_metadata,
        embedding_bias,
    )
    if buffer_blocker is None:
        return buffer_projector(
            processor, hidden_states, lm_head, logits_metadata
        )
    eager_blocker = grouped_activation_blocker(
        processor,
        hidden_states,
        lm_head,
        logits_metadata,
        embedding_bias,
        capture_active=capture_active,
    )
    if eager_blocker is None:
        return grouped_projector(
            processor, hidden_states, lm_head, logits_metadata
        )
    return project_decode_shapes(
        original,
        processor,
        hidden_states,
        lm_head,
        logits_metadata,
        embedding_bias,
        DEPTHS,
    )


def install() -> None:
    from sglang.srt.layers import logits_processor

    observed = _source_hash(logits_processor)
    if observed != LOGITS_PROCESSOR_SHA256:
        raise RuntimeError(f"grouped_lm_head_logits_source_mismatch:{observed}")
    cls = logits_processor.LogitsProcessor
    if getattr(cls, "_grouped_lm_head_installed", False):
        return

    original = cls._get_logits

    def grouped_target_get_logits(
        self,
        hidden_states,
        lm_head,
        logits_metadata,
        embedding_bias=None,
    ):
        return dispatch_target_get_logits(
            original,
            self,
            hidden_states,
            lm_head,
            logits_metadata,
            embedding_bias,
        )

    cls._get_logits = grouped_target_get_logits
    cls._grouped_lm_head_installed = True
    _append_audit(
        {
            "candidate_symbol": (
                "depth_interleaved_grouped_lm_head"
                "[vocab_block_major,depth_minor]"
            ),
            "production_shape": [BATCH, DEPTHS, HIDDEN, VOCAB],
            "block_n": BLOCK_N,
            "block_k": BLOCK_K,
            "source_sha256": observed,
            "activation_contract": {
                "buffer_direct_symbol": "grouped_get_logits_buffer_direct",
                "buffer_dtype": "torch.float32",
                "buffer_shape": [BATCH * DEPTHS, VOCAB],
                "buffer_stride": [VOCAB, 1],
                "captured_live_calls": "buffer_direct_candidate",
                "unsupported_calls": "stock_ordered_fallback",
            },
        }
    )
