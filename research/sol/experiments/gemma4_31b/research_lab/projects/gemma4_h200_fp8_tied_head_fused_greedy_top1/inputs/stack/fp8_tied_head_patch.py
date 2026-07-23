from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import statistics
import threading
import time

import torch


VOCAB = 262144
HIDDEN = 5376
FP8_MAX = float(torch.finfo(torch.float8_e4m3fn).max)
AUDIT_ROOT = pathlib.Path(os.environ["FP8_TIED_HEAD_AUDIT"])
MODE = os.environ.get("FP8_TIED_HEAD_MODE", "endpoint")
_lock = threading.Lock()
_component_complete = False
_graph_capture_seen = False


def _atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata(tensor: torch.Tensor) -> dict[str, object]:
    return {
        "shape": list(tensor.shape),
        "dtype": str(tensor.dtype),
        "stride": list(tensor.stride()),
        "contiguous": tensor.is_contiguous(),
        "device": str(tensor.device),
    }


def _quantize_output_weight(layer: torch.nn.Module) -> None:
    weight = layer.weight
    if (
        tuple(weight.shape) != (VOCAB, HIDDEN)
        or weight.dtype != torch.bfloat16
        or weight.device.type != "cuda"
        or hasattr(layer, "_fp8_output_weight")
    ):
        return
    sample_indices = torch.tensor(
        [0, 1, 17, 4095, VOCAB - 1], device=weight.device, dtype=torch.long
    )
    before = weight.index_select(0, sample_indices).clone()
    amax = weight.abs().amax().float()
    dequant_scale = (amax / FP8_MAX).clamp(min=torch.finfo(torch.float32).tiny)
    quant_scale = dequant_scale.reciprocal()
    output_weight_storage = torch.empty(
        (VOCAB, HIDDEN), device=weight.device, dtype=torch.float8_e4m3fn
    )
    saturated = 0
    nonfinite = 0
    chunk_rows = 4096
    for start in range(0, VOCAB, chunk_rows):
        stop = min(start + chunk_rows, VOCAB)
        chunk = weight[start:stop]
        finite = torch.isfinite(chunk)
        nonfinite += int((~finite).sum().item())
        scaled = chunk.float().mul_(quant_scale)
        saturated += int((scaled.abs() >= FP8_MAX).sum().item())
        output_weight_storage[start:stop] = (
            scaled.clamp_(min=-FP8_MAX, max=FP8_MAX)
            .to(torch.float8_e4m3fn)
            .contiguous()
        )
        del scaled
    output_weight = output_weight_storage.T
    after = weight.index_select(0, sample_indices)
    if not torch.equal(before, after):
        raise RuntimeError("BF16 embedding changed while building FP8 output weight")
    layer.register_buffer("_fp8_output_weight", output_weight, persistent=False)
    layer.register_buffer(
        "_fp8_output_weight_scale", dequant_scale.reshape(1), persistent=False
    )
    _atomic(
        AUDIT_ROOT / "representation.json",
        {
            "schema_version": 1,
            "candidate": "per_tensor_e4m3_tied_output_weight",
            "embedding": _metadata(weight),
            "embedding_preserved": True,
            "embedding_data_ptr": weight.data_ptr(),
            "output_weight": _metadata(output_weight),
            "output_weight_data_ptr": output_weight.data_ptr(),
            "separate_storage": weight.data_ptr() != output_weight.data_ptr(),
            "weight_scale": float(dequant_scale.item()),
            "weight_scale_granularity": "per_tensor",
            "weight_saturation_count": saturated,
            "weight_saturation_fraction": saturated / weight.numel(),
            "weight_nonfinite_count": nonfinite,
            "materialized_dequantized_weight": False,
        },
    )


def _candidate(hidden_states: torch.Tensor, lm_head: torch.nn.Module) -> torch.Tensor:
    from sglang.srt.layers.quantization.fp8_utils import apply_fp8_linear

    return apply_fp8_linear(
        hidden_states,
        lm_head._fp8_output_weight,
        lm_head._fp8_output_weight_scale,
        compressed_tensor_quant=True,
        use_per_token_if_dynamic=False,
    )


def _timings(function, repeats: int = 60) -> dict[str, float]:
    for _ in range(8):
        function()
    torch.cuda.synchronize()
    values = []
    for _ in range(repeats):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        output = function()
        end.record()
        end.synchronize()
        values.append(float(start.elapsed_time(end)))
        if not torch.isfinite(output).all():
            raise RuntimeError("nonfinite timed logits")
    ordered = sorted(values)
    return {
        "repeats": repeats,
        "minimum_ms": ordered[0],
        "p10_ms": ordered[max(0, math.floor(0.10 * (repeats - 1)))],
        "median_ms": statistics.median(values),
        "p90_ms": ordered[math.floor(0.90 * (repeats - 1))],
        "maximum_ms": ordered[-1],
        "mean_ms": statistics.fmean(values),
    }


def _numerical(
    baseline: torch.Tensor,
    candidate: torch.Tensor,
    softcap: float | None,
) -> dict[str, object]:
    baseline_f = baseline.float()
    candidate_f = candidate.float()
    delta = candidate_f - baseline_f
    relative_l2 = float(
        torch.linalg.vector_norm(delta)
        / torch.linalg.vector_norm(baseline_f).clamp(min=1e-12)
    )
    cosine = float(
        torch.nn.functional.cosine_similarity(
            baseline_f.reshape(1, -1), candidate_f.reshape(1, -1)
        ).item()
    )
    baseline_top = torch.topk(baseline_f, k=10, dim=-1).indices
    candidate_top = torch.topk(candidate_f, k=10, dim=-1).indices
    top10_overlap = float(
        torch.stack(
            [
                torch.isin(candidate_top[row], baseline_top[row]).float().mean()
                for row in range(baseline.shape[0])
            ]
        )
        .mean()
        .item()
    )
    result: dict[str, object] = {
        "relative_l2": relative_l2,
        "cosine": cosine,
        "max_absolute_error": float(delta.abs().max().item()),
        "baseline_nonfinite_count": int((~torch.isfinite(baseline)).sum().item()),
        "candidate_nonfinite_count": int((~torch.isfinite(candidate)).sum().item()),
        "argmax_agreement": float(
            (baseline_f.argmax(-1) == candidate_f.argmax(-1)).float().mean().item()
        ),
        "top10_overlap": top10_overlap,
    }
    if softcap is not None:
        baseline_soft = softcap * torch.tanh(baseline_f / softcap)
        candidate_soft = softcap * torch.tanh(candidate_f / softcap)
        result["softcap"] = {
            "value": softcap,
            "relative_l2": float(
                torch.linalg.vector_norm(candidate_soft - baseline_soft)
                / torch.linalg.vector_norm(baseline_soft).clamp(min=1e-12)
            ),
            "argmax_agreement": float(
                (baseline_soft.argmax(-1) == candidate_soft.argmax(-1))
                .float()
                .mean()
                .item()
            ),
            "candidate_nonfinite_count": int(
                (~torch.isfinite(candidate_soft)).sum().item()
            ),
        }
    return result


def _run_component(
    processor,
    hidden_states: torch.Tensor,
    lm_head: torch.nn.Module,
    original_compute,
    embedding_bias,
) -> None:
    global _component_complete
    if MODE != "component" or hidden_states.shape[0] < 32 or _component_complete:
        return
    if not _lock.acquire(blocking=False):
        return
    try:
        if _component_complete:
            return
        rows = hidden_states[:32].detach().contiguous()
        torch.save(rows.cpu(), AUDIT_ROOT / "real_hidden_rows.pt")
        results = []
        for m in (1, 12, 32):
            sample = rows[:m]
            baseline = original_compute(processor, sample, lm_head, embedding_bias)
            candidate = _candidate(sample, lm_head)
            amax = sample.abs().amax().float()
            activation_scale = (
                amax / FP8_MAX
            ).clamp(min=torch.finfo(torch.float32).tiny)
            results.append(
                {
                    "m": m,
                    "hidden_states": _metadata(sample),
                    "activation_scale": float(activation_scale.item()),
                    "activation_scale_granularity": "per_tensor",
                    "activation_saturation_count": int(
                        ((sample.float() / activation_scale).abs() >= FP8_MAX)
                        .sum()
                        .item()
                    ),
                    "activation_nonfinite_count": int(
                        (~torch.isfinite(sample)).sum().item()
                    ),
                    "baseline_timing": _timings(
                        lambda sample=sample: original_compute(
                            processor, sample, lm_head, embedding_bias
                        )
                    ),
                    "candidate_timing": _timings(
                        lambda sample=sample: _candidate(sample, lm_head)
                    ),
                    "numerical": _numerical(
                        baseline,
                        candidate,
                        processor.final_logit_softcapping,
                    ),
                }
            )
        representation = json.loads((AUDIT_ROOT / "representation.json").read_text())
        _atomic(
            AUDIT_ROOT / "COMPONENT_RESULT.json",
            {
                "schema_version": 1,
                "status": "complete",
                "consumer": "sglang.srt.layers.logits_processor.LogitsProcessor._compute_lm_head",
                "downstream": "LogitsProcessor._get_logits softcap then sampling",
                "source": {
                    "patch_sha256": _sha256(pathlib.Path(__file__)),
                    "torch": torch.__version__,
                    "cuda": torch.version.cuda,
                    "gpu": torch.cuda.get_device_name(),
                },
                "real_hidden_state_rows": 32,
                "graph_capture_seen": _graph_capture_seen,
                "candidate_path_calls": 1,
                "candidate_output_dtype": "torch.bfloat16",
                "embedding_preserved": representation["embedding_preserved"],
                "separate_storage": representation["separate_storage"],
                "weight_saturation_count": representation[
                    "weight_saturation_count"
                ],
                "weight_saturation_fraction": representation[
                    "weight_saturation_fraction"
                ],
                "weight_nonfinite_count": representation["weight_nonfinite_count"],
                "rows": results,
                "completed_unix_s": time.time(),
            },
        )
        _component_complete = True
    finally:
        _lock.release()


def install() -> None:
    from sglang.srt.layers.logits_processor import LogitsProcessor
    from sglang.srt.layers.vocab_parallel_embedding import VocabParallelEmbedding
    from sglang.srt.models.gemma4_causal import Gemma4ForCausalLM
    from sglang.srt.models.gemma4_mm import Gemma4ForConditionalGeneration

    original_loader = VocabParallelEmbedding.weight_loader
    original_compute = LogitsProcessor._compute_lm_head
    original_load_weights = Gemma4ForCausalLM.load_weights
    original_conditional_load_weights = Gemma4ForConditionalGeneration.load_weights

    def weight_loader(self, param, loaded_weight):
        original_loader(self, param, loaded_weight)
        if param is getattr(self, "weight", None):
            _quantize_output_weight(self)

    def compute(processor, hidden_states, lm_head, embedding_bias=None):
        global _graph_capture_seen
        if not hasattr(lm_head, "_fp8_output_weight"):
            return original_compute(
                processor, hidden_states, lm_head, embedding_bias
            )
        capturing = torch.cuda.is_current_stream_capturing()
        if capturing:
            _graph_capture_seen = True
        output = _candidate(hidden_states, lm_head)
        if not capturing:
            _run_component(
                processor,
                hidden_states,
                lm_head,
                original_compute,
                embedding_bias,
            )
            path = AUDIT_ROOT / "path.json"
            if not path.exists():
                _atomic(
                    path,
                    {
                        "consumer": "LogitsProcessor._compute_lm_head",
                        "candidate_symbol": "sglang.srt.layers.quantization.fp8_utils.apply_fp8_linear",
                        "candidate_output": _metadata(output),
                        "embedding_dtype": str(lm_head.weight.dtype),
                        "candidate_weight_dtype": str(
                            lm_head._fp8_output_weight.dtype
                        ),
                        "graph_capture_seen": _graph_capture_seen,
                    },
                )
        return output

    def load_weights(model, weights):
        result = original_load_weights(model, weights)
        matches = []
        for module in model.modules():
            weight = getattr(module, "weight", None)
            if (
                isinstance(weight, torch.Tensor)
                and tuple(weight.shape) == (VOCAB, HIDDEN)
            ):
                matches.append(module)
        if len(matches) != 1:
            raise RuntimeError(
                f"expected one exact tied embedding, observed {len(matches)}"
            )
        _quantize_output_weight(matches[0])
        return result

    def conditional_load_weights(model, weights):
        result = original_conditional_load_weights(model, weights)
        _quantize_output_weight(model.language_model.embed_tokens)
        return result

    VocabParallelEmbedding.weight_loader = weight_loader
    LogitsProcessor._compute_lm_head = compute
    Gemma4ForCausalLM.load_weights = load_weights
    Gemma4ForConditionalGeneration.load_weights = conditional_load_weights
