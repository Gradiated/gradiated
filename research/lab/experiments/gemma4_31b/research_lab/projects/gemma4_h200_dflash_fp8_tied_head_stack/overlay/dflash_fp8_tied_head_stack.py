from __future__ import annotations

import hashlib
import pathlib
from collections.abc import Callable, Mapping
from typing import Any

import torch


VOCAB_SIZE = 262144
HIDDEN_SIZE = 5376
ADMITTED_WEIGHT_SCALE = 0.002162388525903225
FP8_MAX = float(torch.finfo(torch.float8_e4m3fn).max)
TARGET_WEIGHT_NAME = "_dflash_fp8_target_weight"
TARGET_SCALE_NAME = "_dflash_fp8_target_weight_scale"
TARGET_OWNER_NAME = "_dflash_fp8_projection_owner"

EXPECTED_SOURCE_SHA256 = {
    "models/gemma4_mm.py": "72d6d7ebe63dfa143b78f6e2fb50969ec59d5469c390a52ae2ca7bdb84c6622b",
    "speculative/dflash_worker.py": "2ad9f037efb19ba4d108daef1290aa7da6ada45ab5b186c33f3f2898376e7498",
    "speculative/dflash_info.py": "f17c37c1d0047e75f3214ec67cf2b02dd52cfcec35cf0daaaee0407f892a0e53",
    "speculative/dflash_utils.py": "f6935ff13d8b0c24ab2b443509ba8425918f8b4a6fafc520cd8a875f91891030",
    "speculative/triton_ops/dflash_accept_bonus.py": "422ffbd00b54913f3d9c14d2596ffd79e51800b6565dc0de78603a36dbd6fdce",
    "layers/logits_processor.py": "e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14",
    "layers/vocab_parallel_embedding.py": "014a8df6559d8af35f0b21f8416e5ab2997e715a0687dc4b7b70c461b3e2e28b",
    "layers/sampler.py": "85541951e1cf50d10c54978178e403ff9d4aa6f223e629ea91965735ba882a8f",
    "model_executor/runner/decode_cuda_graph_runner.py": "324ec71b9b78e12099199f5c015803e77e5fb1600c25b891c5ff32d24d16b41d",
    "model_executor/runner/base_cuda_graph_runner.py": "3c41ea490798de9df74d8779ed32d2faa4f93c4cbce5191424c763bb74d6160f",
    "model_executor/model_runner.py": "27700b47b4d9920f6d0c38bd30c11ed2503e143a42c54c4bb00fc9f21b02170c",
}


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source_hashes(observed: Mapping[str, str]) -> None:
    missing = sorted(set(EXPECTED_SOURCE_SHA256) - set(observed))
    unexpected = sorted(set(observed) - set(EXPECTED_SOURCE_SHA256))
    mismatched = {
        name: {
            "expected": EXPECTED_SOURCE_SHA256[name],
            "observed": observed[name],
        }
        for name in EXPECTED_SOURCE_SHA256.keys() & observed.keys()
        if observed[name] != EXPECTED_SOURCE_SHA256[name]
    }
    if missing or unexpected or mismatched:
        raise RuntimeError(
            "unsupported_sglang_source_topology:"
            f"missing={missing},unexpected={unexpected},mismatched={mismatched}"
        )


def source_hashes(
    srt_root: pathlib.Path,
    *,
    gemma4_override: pathlib.Path | None = None,
) -> dict[str, str]:
    values = {}
    for relative in EXPECTED_SOURCE_SHA256:
        path = (
            gemma4_override
            if relative == "models/gemma4_mm.py" and gemma4_override is not None
            else srt_root / relative
        )
        values[relative] = sha256_file(path)
    return values


def materialize_e4m3_target_projection(
    tied_head: torch.nn.Module,
    *,
    vocab_size: int = VOCAB_SIZE,
    hidden_size: int = HIDDEN_SIZE,
    weight_scale: float = ADMITTED_WEIGHT_SCALE,
    chunk_rows: int = 4096,
    require_cuda: bool = True,
) -> None:
    weight = getattr(tied_head, "weight", None)
    if not isinstance(weight, torch.Tensor):
        raise RuntimeError("target tied head has no tensor weight")
    if tuple(weight.shape) != (vocab_size, hidden_size):
        raise RuntimeError(
            "unsupported target tied-head shape:"
            f"{tuple(weight.shape)} != {(vocab_size, hidden_size)}"
        )
    if weight.dtype != torch.bfloat16:
        raise RuntimeError(
            f"target embedding must remain BF16, observed {weight.dtype}"
        )
    if require_cuda and weight.device.type != "cuda":
        raise RuntimeError(
            f"target E4M3 projection requires CUDA storage, observed {weight.device}"
        )
    if weight_scale <= 0:
        raise RuntimeError(f"invalid target weight scale {weight_scale}")

    if hasattr(tied_head, TARGET_WEIGHT_NAME):
        validate_projection_ownership(
            tied_head,
            tied_head,
            vocab_size=vocab_size,
            hidden_size=hidden_size,
        )
        return

    dequant_scale = torch.tensor(
        weight_scale,
        dtype=torch.float32,
        device=weight.device,
    )
    quant_scale = dequant_scale.reciprocal()
    storage = torch.empty(
        (vocab_size, hidden_size),
        dtype=torch.float8_e4m3fn,
        device=weight.device,
    )
    for start in range(0, vocab_size, chunk_rows):
        stop = min(start + chunk_rows, vocab_size)
        scaled = weight[start:stop].float().mul(quant_scale)
        if not bool(torch.isfinite(scaled).all().item()):
            raise RuntimeError("nonfinite target embedding value during E4M3 conversion")
        storage[start:stop] = scaled.clamp(
            min=-FP8_MAX,
            max=FP8_MAX,
        ).to(torch.float8_e4m3fn)

    tied_head.register_buffer(TARGET_WEIGHT_NAME, storage.T, persistent=False)
    tied_head.register_buffer(
        TARGET_SCALE_NAME,
        dequant_scale.reshape(1),
        persistent=False,
    )
    setattr(tied_head, TARGET_OWNER_NAME, "target_logits_only")
    validate_projection_ownership(
        tied_head,
        tied_head,
        vocab_size=vocab_size,
        hidden_size=hidden_size,
    )


def validate_projection_ownership(
    lm_head: torch.nn.Module,
    embed_tokens: torch.nn.Module,
    *,
    vocab_size: int = VOCAB_SIZE,
    hidden_size: int = HIDDEN_SIZE,
) -> dict[str, Any]:
    if lm_head is not embed_tokens:
        raise RuntimeError("DFLASH BF16 lm_head/embed_tokens tie was broken")
    embedding = getattr(embed_tokens, "weight", None)
    target_weight = getattr(lm_head, TARGET_WEIGHT_NAME, None)
    target_scale = getattr(lm_head, TARGET_SCALE_NAME, None)
    if not isinstance(embedding, torch.Tensor) or embedding.dtype != torch.bfloat16:
        raise RuntimeError("DFLASH embedding storage is not BF16")
    if tuple(embedding.shape) != (vocab_size, hidden_size):
        raise RuntimeError("DFLASH embedding storage has unsupported shape")
    if not isinstance(target_weight, torch.Tensor):
        raise RuntimeError("DFLASH target projection storage is missing")
    if tuple(target_weight.shape) != (hidden_size, vocab_size):
        raise RuntimeError("DFLASH target projection storage has unsupported shape")
    if target_weight.dtype != torch.float8_e4m3fn:
        raise RuntimeError("DFLASH target projection storage is not E4M3")
    if target_weight.data_ptr() == embedding.data_ptr():
        raise RuntimeError("DFLASH target and draft/embedding storage alias")
    if not isinstance(target_scale, torch.Tensor) or target_scale.numel() != 1:
        raise RuntimeError("DFLASH target projection scale is invalid")
    if getattr(lm_head, TARGET_OWNER_NAME, None) != "target_logits_only":
        raise RuntimeError("DFLASH target projection owner marker is invalid")
    if hasattr(lm_head, "_dflash_fp8_draft_weight"):
        raise RuntimeError("DFLASH draft projection must not own FP8 target storage")
    return {
        "embedding_dtype": str(embedding.dtype),
        "target_weight_dtype": str(target_weight.dtype),
        "separate_storage": True,
        "target_owner": "target_logits_only",
        "draft_owner": "tied_bf16_weight",
    }


def compute_target_logits(
    hidden_states: torch.Tensor,
    lm_head: torch.nn.Module,
    *,
    embedding_bias: torch.Tensor | None = None,
    apply_fp8_linear_fn: Callable[..., torch.Tensor] | None = None,
) -> torch.Tensor:
    if embedding_bias is not None:
        raise RuntimeError("DFLASH FP8 tied-head overlay does not support head bias")
    target_weight = getattr(lm_head, TARGET_WEIGHT_NAME, None)
    target_scale = getattr(lm_head, TARGET_SCALE_NAME, None)
    if not isinstance(target_weight, torch.Tensor) or not isinstance(
        target_scale, torch.Tensor
    ):
        raise RuntimeError("DFLASH FP8 target projection is not materialized")
    if apply_fp8_linear_fn is None:
        from sglang.srt.layers.quantization.fp8_utils import apply_fp8_linear

        apply_fp8_linear_fn = apply_fp8_linear
    output = apply_fp8_linear_fn(
        hidden_states,
        target_weight,
        target_scale,
        compressed_tensor_quant=True,
        use_per_token_if_dynamic=False,
    )
    if output.dtype != torch.bfloat16:
        raise RuntimeError(
            f"DFLASH target logits must remain BF16, observed {output.dtype}"
        )
    return output


def install() -> None:
    from sglang.srt.layers import logits_processor
    from sglang.srt.models import gemma4_mm
    from sglang.srt.speculative import dflash_worker

    if getattr(logits_processor.LogitsProcessor, "_dflash_fp8_stack_installed", False):
        return

    srt_root = pathlib.Path(dflash_worker.__file__).resolve().parents[1]
    verify_source_hashes(source_hashes(srt_root))

    original_compute = logits_processor.LogitsProcessor._compute_lm_head
    original_load_weights = gemma4_mm.Gemma4ForConditionalGeneration.load_weights
    original_capture_hook = (
        gemma4_mm.Gemma4ForConditionalGeneration.set_dflash_layers_to_capture
    )

    def compute(
        processor,
        hidden_states,
        lm_head,
        embedding_bias=None,
    ):
        if not hasattr(lm_head, TARGET_WEIGHT_NAME):
            return original_compute(
                processor,
                hidden_states,
                lm_head,
                embedding_bias,
            )
        return compute_target_logits(
            hidden_states,
            lm_head,
            embedding_bias=embedding_bias,
        )

    def load_weights(model, weights):
        loaded = original_load_weights(model, weights)
        materialize_e4m3_target_projection(model.language_model.embed_tokens)
        return loaded

    def set_dflash_layers_to_capture(model, layer_ids):
        result = original_capture_hook(model, layer_ids)
        validate_projection_ownership(
            model.lm_head,
            model.language_model.embed_tokens,
        )
        return result

    logits_processor.LogitsProcessor._compute_lm_head = compute
    gemma4_mm.Gemma4ForConditionalGeneration.load_weights = load_weights
    gemma4_mm.Gemma4ForConditionalGeneration.set_dflash_layers_to_capture = (
        set_dflash_layers_to_capture
    )
    logits_processor.LogitsProcessor._dflash_fp8_stack_installed = True
