from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
from typing import Any

import torch


LOCAL_LAYER_IDS = tuple(i for i in range(60) if (i + 1) % 6)
GLOBAL_LAYER_IDS = tuple(range(5, 60, 6))
EXPECTED_SOURCE_SHA256 = {
    "sglang.srt.mem_cache.swa_memory_pool": "36830cdb84cc344ffb7bac9ff30ba9a41b488d67893a5015ecbba584e95a9858",
    "sglang.srt.mem_cache.memory_pool": "37f9915a2945c7bb389212eed65eb770cb9e3fa6976d0778b6831d2ac29d7bdd",
    "sglang.srt.model_executor.model_runner_kv_cache_mixin": "f8202315fb4052bcf2b6aea5d489c38f06e53ed6b2c76b9ff704bd328447100f",
    "sglang.srt.layers.attention.triton_backend": "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d",
    "sglang.srt.layers.attention.triton_ops.extend_attention": "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1",
    "sglang.srt.layers.attention.triton_ops.decode_attention": "1040f43a9ea579b944aa037b585997f8d7b585d85f459a1b1f420002b4bd092a",
}


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append(path: pathlib.Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(
            descriptor,
            (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _scalar(value: Any) -> float | None:
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    result = float(value)
    if not math.isfinite(result):
        raise RuntimeError(f"nonfinite KV scale: {result}")
    return result


def _tensor_meta(value: torch.Tensor) -> dict[str, Any]:
    return {
        "dtype": str(value.dtype),
        "shape": list(value.shape),
        "stride": list(value.stride()),
        "data_ptr": value.data_ptr(),
    }


def install_mixed_kv() -> None:
    from sglang.srt.layers.attention import triton_backend
    from sglang.srt.layers.attention.triton_ops import (
        decode_attention,
        extend_attention,
    )
    from sglang.srt.mem_cache import memory_pool, swa_memory_pool
    from sglang.srt.model_executor import model_runner_kv_cache_mixin

    modules = {
        "sglang.srt.mem_cache.swa_memory_pool": swa_memory_pool,
        "sglang.srt.mem_cache.memory_pool": memory_pool,
        "sglang.srt.model_executor.model_runner_kv_cache_mixin": model_runner_kv_cache_mixin,
        "sglang.srt.layers.attention.triton_backend": triton_backend,
        "sglang.srt.layers.attention.triton_ops.extend_attention": extend_attention,
        "sglang.srt.layers.attention.triton_ops.decode_attention": decode_attention,
    }
    observed = {name: _sha256(module.__file__) for name, module in modules.items()}
    if observed != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(
            "mixed KV pinned source mismatch: "
            + json.dumps(
                {"expected": EXPECTED_SOURCE_SHA256, "observed": observed},
                sort_keys=True,
            )
        )

    audit_root = pathlib.Path(os.environ["MIXED_KV_AUDIT_ROOT"])
    gate_path = pathlib.Path(os.environ["MIXED_KV_AUDIT_GATE"])
    init_path = audit_root / "init.json"
    producer_path = audit_root / "producer.jsonl"
    consumer_path = audit_root / "consumer.jsonl"
    original_pool_init = swa_memory_pool.SWAKVPool.__init__
    original_set = swa_memory_pool.SWAKVPool.set_kv_buffer
    original_extend = triton_backend.TritonAttnBackend.forward_extend
    original_decode = triton_backend.TritonAttnBackend.forward_decode
    armed = False
    producer_seen: set[tuple[str, int]] = set()
    consumer_seen: set[tuple[str, int]] = set()

    def audit_armed() -> bool:
        nonlocal armed
        if not armed and gate_path.exists():
            armed = True
        return armed

    def mixed_pool_init(self, *args, **kwargs):
        if args:
            raise RuntimeError("mixed KV binding requires the pinned keyword constructor")
        requested_dtype = kwargs.get("dtype")
        local_ids = tuple(kwargs.get("swa_attention_layer_ids", ()))
        global_ids = tuple(kwargs.get("full_attention_layer_ids", ()))
        if requested_dtype is not torch.float8_e5m2:
            raise RuntimeError(f"mixed KV wrapper must retain E5M2 convention, got {requested_dtype}")
        if local_ids != LOCAL_LAYER_IDS or global_ids != GLOBAL_LAYER_IDS:
            raise RuntimeError(
                f"unexpected Gemma 4 layer partition: local={local_ids}, global={global_ids}"
            )
        original_pool_class = kwargs.pop(
            "token_to_kv_pool_class", memory_pool.MHATokenToKVPool
        )
        allocations: list[dict[str, Any]] = []

        def layer_pool_factory(**pool_kwargs):
            pool_kind = "local" if not allocations else "global"
            if len(allocations) > 1:
                raise RuntimeError("SWAKVPool requested more than two layer pools")
            pool_kwargs["dtype"] = (
                torch.float8_e4m3fn
                if pool_kind == "local"
                else torch.float8_e5m2
            )
            pool = original_pool_class(**pool_kwargs)
            allocations.append(
                {
                    "pool": pool_kind,
                    "dtype": str(pool.dtype),
                    "size": pool.size,
                    "page_size": pool.page_size,
                    "layer_num": pool.layer_num,
                    "head_num": pool.head_num,
                    "head_dim": pool.head_dim,
                    "v_head_dim": pool.v_head_dim,
                }
            )
            return pool

        kwargs["token_to_kv_pool_class"] = layer_pool_factory
        original_pool_init(self, **kwargs)
        if len(allocations) != 2:
            raise RuntimeError(f"expected two layer pools, got {len(allocations)}")

        layer_rows = []
        ranges = []
        for layer_id in range(60):
            pool_index, is_local = self.layers_mapping[layer_id]
            pool = self.swa_kv_pool if is_local else self.full_kv_pool
            expected_dtype = (
                torch.float8_e4m3fn if is_local else torch.float8_e5m2
            )
            if pool.dtype is not expected_dtype:
                raise RuntimeError(
                    f"layer {layer_id} pool dtype {pool.dtype} != {expected_dtype}"
                )
            key = pool.get_key_buffer(pool_index)
            value = pool.get_value_buffer(pool_index)
            layer_rows.append(
                {
                    "layer_id": layer_id,
                    "pool": "local" if is_local else "global",
                    "pool_index": pool_index,
                    "key": _tensor_meta(key),
                    "value": _tensor_meta(value),
                }
            )
            for kind, tensor in (("key", key), ("value", value)):
                storage = tensor.untyped_storage()
                start = storage.data_ptr()
                ranges.append(
                    {
                        "layer_id": layer_id,
                        "pool": "local" if is_local else "global",
                        "kind": kind,
                        "start": start,
                        "end": start + storage.nbytes(),
                    }
                )
        sorted_ranges = sorted(ranges, key=lambda row: row["start"])
        alias_free = all(
            left["end"] <= right["start"]
            for left, right in zip(sorted_ranges, sorted_ranges[1:])
        )
        if not alias_free:
            raise RuntimeError("mixed KV layer buffers overlap")
        _atomic(
            init_path,
            {
                "schema_version": 1,
                "pass": True,
                "source_sha256": observed,
                "wrapper_dtype": str(self.dtype),
                "page_size": self.page_size,
                "allocations": allocations,
                "alias_free": alias_free,
                "layers": layer_rows,
                "consumer_symbols": {
                    "extend": "sglang.srt.layers.attention.triton_ops.extend_attention.extend_attention_fwd_unified",
                    "decode": "sglang.srt.layers.attention.triton_ops.decode_attention.decode_attention_fwd",
                },
            },
        )

    def audited_set(
        self,
        layer,
        loc,
        cache_k,
        cache_v,
        k_scale=1.0,
        v_scale=1.0,
        swa_loc=None,
    ):
        layer_id = layer.layer_id
        pool_index, is_local = self.layers_mapping[layer_id]
        selected_loc = swa_loc if is_local else loc
        phase = "decode" if selected_loc.numel() == 1 else "extend"
        should_audit = audit_armed() and (phase, layer_id) not in producer_seen
        input_k = _tensor_meta(cache_k) if should_audit else None
        input_v = _tensor_meta(cache_v) if should_audit else None
        original_set(
            self,
            layer,
            loc,
            cache_k,
            cache_v,
            k_scale,
            v_scale,
            swa_loc,
        )
        if should_audit:
            pool = self.swa_kv_pool if is_local else self.full_kv_pool
            key = pool.get_key_buffer(pool_index)
            value = pool.get_value_buffer(pool_index)
            valid_loc = selected_loc[selected_loc >= 0]
            if not valid_loc.numel():
                raise RuntimeError(f"layer {layer_id} has no valid {phase} slot")
            sample_loc = int(valid_loc[0].item())
            finite = bool(
                torch.isfinite(key[sample_loc].float().reshape(-1)[:16]).all().item()
                and torch.isfinite(value[sample_loc].float().reshape(-1)[:16]).all().item()
            )
            if not finite:
                raise RuntimeError(f"layer {layer_id} stored nonfinite KV")
            producer_seen.add((phase, layer_id))
            _append(
                producer_path,
                {
                    "event": "set_kv_buffer",
                    "phase": phase,
                    "layer_id": layer_id,
                    "pool": "local" if is_local else "global",
                    "pool_index": pool_index,
                    "input_key": input_k,
                    "input_value": input_v,
                    "storage_key": _tensor_meta(key),
                    "storage_value": _tensor_meta(value),
                    "k_scale": _scalar(k_scale),
                    "v_scale": _scalar(v_scale),
                    "loc_count": int(selected_loc.numel()),
                    "loc_min": int(valid_loc.min().item()),
                    "loc_max": int(valid_loc.max().item()),
                    "sample_loc": sample_loc,
                    "sample_finite": finite,
                    "used_swa_loc": bool(is_local),
                },
            )

    def audited_attention(original, phase, self, q, k, v, layer, forward_batch, **kwargs):
        output = original(self, q, k, v, layer, forward_batch, **kwargs)
        layer_id = layer.layer_id
        if audit_armed() and (phase, layer_id) not in consumer_seen:
            pool_index, is_local = self.token_to_kv_pool.layers_mapping[layer_id]
            key = self.token_to_kv_pool.get_key_buffer(layer_id)
            value = self.token_to_kv_pool.get_value_buffer(layer_id)
            finite = bool(torch.isfinite(output.float()).all().item())
            if not finite:
                raise RuntimeError(f"layer {layer_id} {phase} output is nonfinite")
            consumer_seen.add((phase, layer_id))
            _append(
                consumer_path,
                {
                    "event": "triton_attention",
                    "phase": phase,
                    "layer_id": layer_id,
                    "pool": "local" if is_local else "global",
                    "pool_index": pool_index,
                    "key": _tensor_meta(key),
                    "value": _tensor_meta(value),
                    "q": _tensor_meta(q),
                    "output": _tensor_meta(output),
                    "output_finite": finite,
                    "k_scale_float": _scalar(getattr(layer, "k_scale_float", 1.0)),
                    "v_scale_float": _scalar(getattr(layer, "v_scale_float", 1.0)),
                    "consumer_symbol": (
                        "sglang.srt.layers.attention.triton_ops.extend_attention.extend_attention_fwd_unified"
                        if phase == "extend"
                        else "sglang.srt.layers.attention.triton_ops.decode_attention.decode_attention_fwd"
                    ),
                },
            )
        return output

    def audited_extend(
        self,
        q,
        k,
        v,
        layer,
        forward_batch,
        save_kv_cache=True,
        sinks=None,
    ):
        return audited_attention(
            original_extend,
            "extend",
            self,
            q,
            k,
            v,
            layer,
            forward_batch,
            save_kv_cache=save_kv_cache,
            sinks=sinks,
        )

    def audited_decode(
        self,
        q,
        k,
        v,
        layer,
        forward_batch,
        save_kv_cache=True,
        sinks=None,
    ):
        return audited_attention(
            original_decode,
            "decode",
            self,
            q,
            k,
            v,
            layer,
            forward_batch,
            save_kv_cache=save_kv_cache,
            sinks=sinks,
        )

    swa_memory_pool.SWAKVPool.__init__ = mixed_pool_init
    swa_memory_pool.SWAKVPool.set_kv_buffer = audited_set
    triton_backend.TritonAttnBackend.forward_extend = audited_extend
    triton_backend.TritonAttnBackend.forward_decode = audited_decode
