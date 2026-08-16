#!/usr/bin/env python3
"""Real NGRAM dual-KV ownership at SGLang's production boundaries.

The scheduler allocates stock slots in ``NgramVerifyInput.prepare_for_verify``.
This module allocates a second, proxy-local slot vector from that same
resident worker allocator only for ``TARGET_VERIFY``, routes converted Gemma
layers through it there, and makes the opposite bank receive an explicit
shadow KV write.  Stock EXTEND, prefill, and ordinary decode retain no proxy
reservation.  The pinned NGRAM v2 runtime owns accepted-index compaction in
the instance ``NgramVerifyInput.sample`` mixin call reached by
``NGRAMWorker.forward_batch_generation``; its wrapper applies the identical
accepted/rejected lifecycle to the TARGET_VERIFY proxy bank after the stock
implementation has made its decision.

It deliberately does not construct a model, allocator, or sidecar.  All
mutable state belongs to the one production ModelRunner process.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any, Callable

from full_model_memory_adapter import CONVERTED_LAYERS, adapter_binding

ARTIFACT = Path("/work/artifact/forward_batch_dual_cache.json")
TARGET_ROWS = 32 * 12


def _atomic(payload: dict[str, Any]) -> None:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    part = ARTIFACT.with_suffix(".part")
    part.write_text(json.dumps(payload, sort_keys=True) + "\n")
    part.replace(ARTIFACT)


def _forward_mode_name(batch: Any) -> str:
    mode = getattr(batch, "forward_mode", None)
    return getattr(mode, "name", str(mode))


def _slots(value: Any) -> list[int]:
    """Read CPU fixtures and CUDA tensors without causing a device copy here."""
    if value is None:
        return []
    if hasattr(value, "tolist"):
        return [int(slot) for slot in value.tolist()]
    return [int(slot) for slot in value]


def _slot_count(value: Any) -> int:
    return len(value) if value is not None else 0


def _logical_slot_prefix(value: Any, count: int) -> Any:
    return value[:count]


def _logical_slot_select(value: Any, indices: list[int]) -> Any:
    try:
        return value[indices]
    except (IndexError, TypeError):
        return [value[index] for index in indices]


def _logical_rows(batch: Any, cache_slots: int) -> int:
    """Use ForwardBatch's authoritative CPU geometry before optional GPU scalar."""
    cpu_value = getattr(batch, "num_token_non_padded_cpu", None)
    if cpu_value is not None:
        return int(cpu_value)
    gpu_value = getattr(batch, "num_token_non_padded", None)
    if gpu_value is not None:
        return int(gpu_value.item() if hasattr(gpu_value, "item") else gpu_value)
    input_ids = getattr(batch, "input_ids", None)
    if input_ids is not None:
        return len(input_ids)
    return cache_slots


def materialize_seq_lens_cpu(batch: Any) -> bool:
    """Satisfy the pinned NGRAM EXTEND CPU-length contract without mutation.

    The native worker indexes ``seq_lens_cpu`` before its own speculative
    preparation.  SGLang leaves that optional mirror unset for this launch
    path even though the same batch already owns ``seq_lens``.  Preserve an
    existing stock mirror verbatim; otherwise create the minimal host list
    required by the native indexed consumer.  ``ForwardBatch.init_new`` also
    reduces this mirror with ``.sum()``, so the representation must retain the
    native CPU tensor contract rather than merely being indexable.
    """
    if getattr(batch, "seq_lens_cpu", None) is not None:
        return False
    seq_lens = getattr(batch, "seq_lens", None)
    if seq_lens is None:
        raise RuntimeError("NGRAM EXTEND batch lacks both seq_lens_cpu and seq_lens")
    values = _slots(seq_lens)
    if not values:
        raise RuntimeError("NGRAM EXTEND batch has empty seq_lens")
    # Import lazily: this module is also exercised by lightweight offline
    # fixtures, while the pinned runtime always provides torch.  Detach avoids
    # retaining an accidental graph; CPU materialization makes host semantics
    # explicit and preserves the source integer dtype for native reductions.
    import torch

    if isinstance(seq_lens, torch.Tensor):
        mirror = seq_lens.detach().to(device="cpu").clone()
    else:
        mirror = torch.tensor(values, device="cpu", dtype=torch.int32)
    if mirror.ndim != 1 or mirror.numel() != len(values):
        raise RuntimeError("NGRAM EXTEND seq_lens CPU mirror has invalid shape")
    setattr(batch, "seq_lens_cpu", mirror)
    return True


def validate_forward_batch(batch: Any) -> dict[str, Any]:
    """Validate only TARGET_VERIFY; ordinary NGRAM setup may have None fields."""
    mode = _forward_mode_name(batch)
    cache_slots = len(_slots(getattr(batch, "out_cache_loc", None)))
    logical_rows = _logical_rows(batch, cache_slots)
    padded_static_len = int(getattr(batch, "padded_static_len", -1) or -1)
    captured_rows = padded_static_len if padded_static_len >= 0 else logical_rows
    if mode != "TARGET_VERIFY":
        return {
            "mode": mode,
            "target_verify": False,
            "logical_rows": logical_rows,
            "captured_rows": captured_rows,
            "cache_slots": cache_slots,
        }
    if logical_rows != TARGET_ROWS:
        raise RuntimeError(f"TARGET_VERIFY logical rows {logical_rows} != {TARGET_ROWS}")
    if cache_slots < logical_rows:
        raise RuntimeError(
            f"TARGET_VERIFY cache slots {cache_slots} below logical rows {logical_rows}"
        )
    if captured_rows < logical_rows:
        raise RuntimeError("captured rows below logical rows")
    return {
        "mode": mode,
        "target_verify": True,
        "logical_rows": logical_rows,
        "captured_rows": captured_rows,
        "padded_rows": captured_rows - logical_rows,
        "cache_slots": cache_slots,
        "padded_rows_cache_inert": True,
    }


@dataclass
class DualCacheRecord:
    stock_slots: Any
    proxy_slots: Any
    pool: Any
    logical_rows: int
    mode: str
    released_slots: list[int] = field(default_factory=list)
    accepted_slots: list[int] = field(default_factory=list)
    lifecycle_finalized: bool = False


class ProductionDualCache:
    """Own the proxy slot vector and mirror lifecycle through SGLang objects."""

    def __init__(self, allocator: Any, pool: Any):
        self.fallback_allocator = allocator
        self.fallback_pool = pool

    def _allocator_and_pool(self, batch: Any) -> tuple[Any, Any]:
        tree_cache = getattr(batch, "tree_cache", None)
        allocator = (
            tree_cache.token_to_kv_pool_allocator if tree_cache is not None else None
        )
        if allocator is None:
            return self.fallback_allocator, self.fallback_pool
        pool = allocator.get_kvcache() if hasattr(allocator, "get_kvcache") else self.fallback_pool
        return allocator, pool

    def allocate(self, batch: Any, geometry: dict[str, Any]) -> DualCacheRecord | None:
        # The proxy contains only quality-unsafe converted-layer KV for
        # speculative target verification.  Reserving it for stock EXTEND or
        # decode consumes the live tree bank before TARGET_VERIFY and is both
        # unnecessary and unsafe for the bounded 8,192-row prefill geometry.
        if not geometry.get("target_verify", False) or not geometry["logical_rows"]:
            return None
        existing = getattr(batch, "_phase_selective_dual_cache", None)
        if existing is not None:
            return existing
        stock_slots = _logical_slot_prefix(getattr(batch, "out_cache_loc", None), geometry["logical_rows"])
        if _slot_count(stock_slots) != geometry["logical_rows"]:
            raise RuntimeError("stock scheduler did not provide one logical slot per row")
        allocator, pool = self._allocator_and_pool(batch)
        # Both vectors must retain their native allocator-owned representation:
        # SGLang consumers index, write, compact, and free CUDA tensors directly.
        proxy_slots = allocator.alloc(_slot_count(stock_slots))
        if proxy_slots is None:
            raise RuntimeError("proxy allocator exhausted before logical-slot allocation")
        if _slot_count(proxy_slots) != _slot_count(stock_slots) or set(_slots(proxy_slots)) & set(_slots(stock_slots)):
            raise RuntimeError("proxy allocator did not return a distinct logical slot vector")
        record = DualCacheRecord(stock_slots, proxy_slots, pool, geometry["logical_rows"], geometry["mode"])
        setattr(batch, "_phase_selective_dual_cache", record)
        return record

    def release_rejected(self, batch: Any, accepted_indices: Any) -> DualCacheRecord | None:
        record = getattr(batch, "_phase_selective_dual_cache", None)
        if record is None:
            return None
        if record.lifecycle_finalized:
            return record
        accepted = [index for index in _slots(accepted_indices) if index >= 0]
        if any(index >= _slot_count(record.proxy_slots) for index in accepted):
            raise RuntimeError("NGRAM accepted index lies outside proxy allocation")
        keep = set(accepted)
        record.accepted_slots = _logical_slot_select(record.proxy_slots, accepted)
        rejected = [index for index in range(_slot_count(record.proxy_slots)) if index not in keep]
        record.released_slots = _logical_slot_select(record.proxy_slots, rejected)
        if _slot_count(record.released_slots):
            allocator, _ = self._allocator_and_pool(batch)
            allocator.free(record.released_slots)
        # The stock NGRAM implementation has already compacted its own vector.
        # Preserve the corresponding proxy vector for request reuse / next decode.
        setattr(batch, "_phase_selective_proxy_cache_loc", record.accepted_slots)
        record.lifecycle_finalized = True
        return record

    def shadow_write(self, record: DualCacheRecord, attention: Any, slots: Any, k: Any, v: Any) -> None:
        """Invoke the real pool writer for the non-primary cache bank."""
        if not slots:
            return
        record.pool.set_kv_buffer(attention, slots, k, v)


def _batch_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    if "forward_batch" in kwargs:
        return kwargs["forward_batch"]
    for value in args:
        if hasattr(value, "forward_mode") and hasattr(value, "out_cache_loc"):
            return value
    return None


def _install_attention_wrappers(model: Any, cache: ProductionDualCache) -> list[int]:
    """Route converted Gemma RadixAttention calls and write their shadow bank."""
    layers = None
    for path in (("language_model", "layers"), ("model", "layers"), ("layers",)):
        try:
            value = model
            for name in path:
                value = getattr(value, name)
            layers = value
            break
        except AttributeError:
            continue
    if layers is None:
        raise RuntimeError("pinned Gemma layers unavailable for dual-cache consumer")
    installed: list[int] = []
    for index in CONVERTED_LAYERS:
        radix = getattr(getattr(layers[index], "self_attn"), "attn", None)
        if radix is None:
            raise RuntimeError(f"converted layer {index} lacks RadixAttention")
        if getattr(radix, "_phase_selective_dual_cache_wrapped", False):
            installed.append(index)
            continue
        original = radix.forward

        def wrapped(q: Any, k: Any, v: Any, *args: Any, _original: Callable[..., Any] = original,
                    _radix: Any = radix, **kwargs: Any) -> Any:
            batch = _batch_from_call(args, kwargs)
            record = getattr(batch, "_phase_selective_dual_cache", None) if batch is not None else None
            if record is None or len(record.proxy_slots) != record.logical_rows:
                return _original(q, k, v, *args, **kwargs)
            stock_slots = getattr(batch, "out_cache_loc")
            if record.mode == "TARGET_VERIFY":
                # Proxy is primary only at converted target-verify layers.
                batch.out_cache_loc = record.proxy_slots
                try:
                    output = _original(q, k, v, *args, **kwargs)
                finally:
                    batch.out_cache_loc = stock_slots
                cache.shadow_write(record, _radix, record.stock_slots, k, v)
                return output
            output = _original(q, k, v, *args, **kwargs)
            cache.shadow_write(record, _radix, record.proxy_slots, k, v)
            return output

        radix.forward = wrapped
        setattr(radix, "_phase_selective_dual_cache_wrapped", True)
        installed.append(index)
    return installed


def install_production_ngram_dual_cache(
    model_runner: Any,
    *,
    ngram_info_cls: Any | None = None,
    ngram_worker_cls: Any | None = None,
) -> dict[str, Any]:
    """Patch allocator/write/accept ownership at the real pinned NGRAM symbols."""
    if getattr(model_runner, "_phase_selective_ngram_dual_cache", None) is not None:
        return getattr(model_runner, "_phase_selective_ngram_dual_cache")
    if ngram_info_cls is None or ngram_worker_cls is None:
        from sglang.srt.speculative.ngram_info import NgramVerifyInput
        from sglang.srt.speculative.ngram_worker import NGRAMWorker
        ngram_info_cls, ngram_worker_cls = NgramVerifyInput, NGRAMWorker
    backend = getattr(model_runner, "attn_backend", None)
    allocator = getattr(backend, "token_to_kv_pool_allocator", None)
    pool = getattr(backend, "token_to_kv_pool", None)
    if allocator is None or pool is None:
        raise RuntimeError("ModelRunner lacks the production token-to-KV allocator/pool")
    if not all(hasattr(allocator, name) for name in ("alloc", "free")) or not hasattr(pool, "set_kv_buffer"):
        raise RuntimeError("pinned production allocator/pool lacks alloc/free/set_kv_buffer")
    cache = ProductionDualCache(allocator, pool)
    # The pinned server uses the v2 verification entrypoint.  Its arguments
    # are scheduler-owned (req pool, ScheduleBatch, target worker), so retain
    # the native ABI rather than imposing the older ``(batch, page_size)``
    # helper signature.
    prepare_name = "prepare_for_v2_verify" if hasattr(ngram_info_cls, "prepare_for_v2_verify") else "prepare_for_verify"
    original_prepare = getattr(ngram_info_cls, prepare_name)
    # Source-proven pinned runtime: forward_batch_generation resolves
    # ``verify_input = batch.spec_info`` then invokes its inherited ``sample``
    # method as ``sample(batch, logits_output, vocab_mask)``.  In this image
    # NgramVerifyInput has no class-level ``verify`` method.
    original_sample = ngram_info_cls.sample
    original_worker = ngram_worker_cls.forward_batch_generation

    def prepare(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_prepare(self, *args, **kwargs)
        batch = kwargs.get("batch")
        if batch is None:
            # v2: (req_to_token_pool, ScheduleBatch, target_worker); legacy:
            # (batch, page_size).  The ScheduleBatch is the first positional
            # object carrying the real ForwardBatch/cache geometry.
            batch = next((value for value in args if hasattr(value, "forward_mode") or hasattr(value, "batches")), None)
        if batch is None:
            return result
        geometry = validate_forward_batch(batch)
        cache.allocate(batch, geometry)
        if geometry["target_verify"]:
            setattr(batch, "_phase_selective_first_target_consumer", "NGRAMWorker.forward_batch_generation")
        return result

    def sample(self: Any, batch: Any, logits_output: Any, vocab_mask: Any = None) -> Any:
        result = original_sample(self, batch, logits_output, vocab_mask)
        # The exact source returns (predict, accept_lens, accept_index).
        cache.release_rejected(batch, result[2])
        return result

    def forward_batch_generation(self: Any, batch: Any, *args: Any, **kwargs: Any) -> Any:
        # This is the first decision-bearing consumer: it calls target_worker
        # with TARGET_VERIFY, then consumes logits in NGRAM verification.  At
        # method entry NGRAM may still be in an ordinary mode; its internal
        # prepare_for_verify is the authoritative point at which stock slots
        # are allocated and the mode becomes TARGET_VERIFY.
        seq_lens_cpu_materialized = materialize_seq_lens_cpu(batch)
        geometry = validate_forward_batch(batch)
        if geometry["target_verify"]:
            cache.allocate(batch, geometry)
            setattr(batch, "_phase_selective_first_target_consumer", "NGRAMWorker.forward_batch_generation")
        if seq_lens_cpu_materialized:
            _atomic({
                "installed": True,
                "seq_lens_cpu_materialized": True,
                "seq_lens_cpu_count": len(getattr(batch, "seq_lens_cpu")),
                "mode": geometry["mode"],
                "science_started": geometry["target_verify"],
            })
        return original_worker(self, batch, *args, **kwargs)

    setattr(ngram_info_cls, prepare_name, prepare)
    ngram_info_cls.sample = sample
    ngram_worker_cls.forward_batch_generation = forward_batch_generation
    attention_layers = _install_attention_wrappers(model_runner.model, cache)
    binding = {
        "installed": True,
        "producer": f"NgramVerifyInput.{prepare_name}",
        "first_target_consumer": "NGRAMWorker.forward_batch_generation",
        "acceptance_consumer": "NgramVerifyInput.sample (EagleVerifyInputV2Mixin)",
        "attention_consumer": "RadixAttention.forward",
        "converted_layers": attention_layers,
        "lifecycle": ["TARGET_VERIFY alloc", "stock/proxy shadow write", "accepted reuse", "rejected free"],
        "seq_lens_cpu_repair": "NGRAMWorker.forward_batch_generation materializes batch.seq_lens_cpu from batch.seq_lens only when absent",
    }
    setattr(model_runner, "_phase_selective_ngram_dual_cache_state", cache)
    setattr(model_runner, "_phase_selective_ngram_dual_cache", binding)
    return binding


def install_forward_batch_dual_cache_driver(model_runner: Any) -> dict[str, Any]:
    """Wrap the real production ModelRunner ForwardBatch boundary exactly once.

    ``load_model`` precedes attention-backend construction in the pinned
    runtime, so production NGRAM/cache bindings are deferred to the first
    actual ``ForwardBatch`` call.  This keeps the hook attached at the real
    boundary without guessing an allocator during model loading.
    """
    if getattr(model_runner, "_phase_selective_forward_batch_driver", None) is not None:
        raise RuntimeError("ForwardBatch dual-cache driver already installed")
    model = getattr(model_runner, "model", None)
    if model is None or getattr(model, "_phase_selective_adapter", None) != adapter_binding():
        raise RuntimeError("adapter must be bound to the resident production model first")
    original = model_runner.forward

    def wrapped_forward(forward_batch: Any, *args: Any, **kwargs: Any) -> Any:
        ngram_binding = getattr(model_runner, "_phase_selective_ngram_dual_cache", None)
        if ngram_binding is None:
            ngram_binding = install_production_ngram_dual_cache(model_runner)
        observed = validate_forward_batch(forward_batch)
        # Ordinary prefill/decode remains entirely stock-only.  NGRAM
        # allocation may already have created the TARGET_VERIFY record;
        # allocate() is explicitly idempotent for that case and a no-op for
        # every other mode.
        model_runner._phase_selective_ngram_dual_cache_state.allocate(forward_batch, observed)
        observed.update({
            "observed_monotonic_s": monotonic(),
            "converted_layers": list(CONVERTED_LAYERS),
            "cache_policy": "production_dual_allocator_shadow_write_accept_move_reject_free",
            "first_target_consumer": ngram_binding["first_target_consumer"],
            "science_started": observed["target_verify"],
        })
        _atomic(observed)
        return original(forward_batch, *args, **kwargs)

    model_runner.forward = wrapped_forward
    binding = {
        "installed": True,
        "boundary": "ModelRunner.forward(ForwardBatch)",
        "converted_layers": list(CONVERTED_LAYERS),
        "one_resident_target_model": True,
        "ngram_dual_cache": "deferred_to_first_production_forward_batch",
    }
    setattr(model_runner, "_phase_selective_forward_batch_driver", binding)
    _atomic({"installed": True, "science_started": False, **binding})
    return binding


def probe() -> int:
    from sglang.srt.model_executor.forward_batch_info import ForwardBatch, ForwardMode
    _atomic({"probe": "pinned_forward_batch_import", "forward_batch": ForwardBatch.__name__,
             "target_verify_mode": ForwardMode.TARGET_VERIFY.name, "science_started": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(probe())
