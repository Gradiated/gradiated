from __future__ import annotations

import math
from typing import Iterable

import torch

from dual_kv4_contract import (
    CanonicalTierDirectory,
    GLOBAL_LAYER_IDS,
    LOCAL_CAPACITY,
    OLD_CAPACITY,
    PHYSICAL_CAPACITY,
    RECENT_CAPACITY,
    WINDOW,
)
from sglang_global_tiered_kv4 import load_extension as load_global_extension
from sglang_local_kv4_outlier import (
    HEAD_DIM as LOCAL_HEAD_DIM,
    LocalKV4OutlierKVCacheMethod,
    fused_local_attention,
)
from sglang.srt.mem_cache.allocator.swa import SWATokenToKVPoolAllocator
from sglang.srt.mem_cache.memory_pool import (
    KVWriteLoc,
    MHATokenToKVPool,
    unwrap_write_loc,
)
from sglang.srt.mem_cache.swa_memory_pool import SWAKVPool
from sglang.srt.mem_cache.utils import maybe_init_custom_mem_pool


GLOBAL_HEAD_DIM = 512
GLOBAL_KV_HEADS = 4
GLOBAL_OLD_VECTOR_BYTES = 296
GLOBAL_LAYERS = len(GLOBAL_LAYER_IDS)
LOCAL_LAYERS = 50
GB = 1 << 30


def _as_int_list(values: torch.Tensor | Iterable[int]) -> list[int]:
    if isinstance(values, torch.Tensor):
        return [int(value) for value in values.detach().cpu().tolist()]
    return [int(value) for value in values]


class GlobalTieredKVPool:
    def __init__(self, device: str):
        self.device = device
        self.size = PHYSICAL_CAPACITY - 1
        self.page_size = 1
        self.layer_num = GLOBAL_LAYERS
        self.start_layer = 0
        self.directory = CanonicalTierDirectory()
        self.recent_k = [
            torch.empty(
                (RECENT_CAPACITY, GLOBAL_KV_HEADS, GLOBAL_HEAD_DIM),
                dtype=torch.uint8,
                device=device,
            )
            for _ in range(GLOBAL_LAYERS)
        ]
        self.recent_v = [
            torch.empty_like(value) for value in self.recent_k
        ]
        self.old_k = [
            torch.empty(
                (OLD_CAPACITY, GLOBAL_KV_HEADS, GLOBAL_OLD_VECTOR_BYTES),
                dtype=torch.uint8,
                device=device,
            )
            for _ in range(GLOBAL_LAYERS)
        ]
        self.old_v = [torch.empty_like(value) for value in self.old_k]
        self.recent_locations = torch.full(
            (PHYSICAL_CAPACITY,), -1, dtype=torch.int32, device=device
        )
        self.old_locations = torch.full_like(self.recent_locations, -1)
        self.recent_free_stack = torch.arange(
            RECENT_CAPACITY, dtype=torch.int32, device=device
        )
        self.old_free_stack = torch.arange(
            OLD_CAPACITY, dtype=torch.int32, device=device
        )
        self._epoch_signature: tuple | None = None

    def _sync_directory(self, physical_pages: Iterable[int]) -> None:
        pages = sorted(
            {
                int(page)
                for page in physical_pages
                if 0 <= int(page) < PHYSICAL_CAPACITY
            }
        )
        if not pages:
            return
        index = torch.tensor(pages, dtype=torch.int64, device=self.device)
        recent = torch.tensor(
            [self.directory.recent_locations[page] for page in pages],
            dtype=torch.int32,
            device=self.device,
        )
        old = torch.tensor(
            [self.directory.old_locations[page] for page in pages],
            dtype=torch.int32,
            device=self.device,
        )
        self.recent_locations[index] = recent
        self.old_locations[index] = old

    def begin_epoch(
        self,
        *,
        new_physical: torch.Tensor,
        positions: torch.Tensor,
        extend_start: torch.Tensor,
        extend_lens: torch.Tensor,
        prefix_lens: torch.Tensor,
        kv_indptr: torch.Tensor,
        kv_indices: torch.Tensor,
    ) -> dict:
        starts = _as_int_list(extend_start)
        lengths = _as_int_list(extend_lens)
        prefixes = _as_int_list(prefix_lens)
        physical = _as_int_list(new_physical)
        logical_positions = _as_int_list(positions)
        indptr = _as_int_list(kv_indptr)
        indices = _as_int_list(kv_indices)

        new_recent = []
        new_old = []
        retiring = []
        for request, (start, length, prefix) in enumerate(
            zip(starts, lengths, prefixes)
        ):
            final_length = prefix + length
            old_after = max(0, final_length - WINDOW)
            old_before = max(0, prefix - WINDOW)
            for row in range(start, start + length):
                if physical[row] < 0:
                    continue
                if logical_positions[row] < old_after:
                    new_old.append((row, physical[row]))
                else:
                    new_recent.append((row, physical[row]))
            request_start = indptr[request]
            for position in range(old_before, min(prefix, old_after)):
                retiring.append(indices[request_start + position])

        signature = (
            tuple(row[1] for row in new_recent),
            tuple(row[1] for row in new_old),
            tuple(retiring),
        )
        if self._epoch_signature is not None:
            if signature != self._epoch_signature:
                raise RuntimeError("global layer routing changed inside one forward")
        else:
            self.directory.route_new(signature[0], signature[1])
            self.directory.begin_transition(signature[2])
            self._sync_directory(signature[0] + signature[1] + signature[2])
            self._epoch_signature = signature
        return {
            "new_recent": tuple(new_recent),
            "new_old": tuple(new_old),
            "retiring": tuple(self.directory.pending_transition()),
            "signature": signature,
        }

    def write_layer(
        self,
        local_layer_id: int,
        cache_k: torch.Tensor,
        cache_v: torch.Tensor,
        routes: dict,
    ) -> None:
        extension = load_global_extension()
        for rows_name, producer_name in (
            ("new_recent", "store_recent"),
            ("new_old", "pack_old"),
        ):
            routed = routes[rows_name]
            if not routed:
                continue
            source_rows = torch.tensor(
                [row for row, _ in routed], dtype=torch.int64, device=cache_k.device
            )
            physical = torch.tensor(
                [page for _, page in routed], dtype=torch.int64, device=cache_k.device
            )
            producer = getattr(extension, producer_name)
            target_k = (
                self.recent_k[local_layer_id]
                if rows_name == "new_recent"
                else self.old_k[local_layer_id]
            )
            target_v = (
                self.recent_v[local_layer_id]
                if rows_name == "new_recent"
                else self.old_v[local_layer_id]
            )
            producer(
                cache_k.index_select(0, source_rows).contiguous(),
                physical,
                self.recent_locations
                if rows_name == "new_recent"
                else self.old_locations,
                target_k,
            )
            producer(
                cache_v.index_select(0, source_rows).contiguous(),
                physical,
                self.recent_locations
                if rows_name == "new_recent"
                else self.old_locations,
                target_v,
            )

    def retire_all_layers(self, routes: dict) -> None:
        transitions = routes["retiring"]
        if transitions:
            physical = torch.tensor(
                [row.physical for row in transitions],
                dtype=torch.int64,
                device=self.device,
            )
            extension = load_global_extension()
            for local_layer_id in range(GLOBAL_LAYERS):
                extension.retire_recent(
                    physical,
                    self.old_locations,
                    self.recent_locations,
                    self.recent_k[local_layer_id],
                    self.old_k[local_layer_id],
                )
                extension.retire_recent(
                    physical,
                    self.old_locations,
                    self.recent_locations,
                    self.recent_v[local_layer_id],
                    self.old_v[local_layer_id],
                )
            self.directory.finish_transition()
            self._sync_directory(_as_int_list(physical))

    def finish_forward(self) -> None:
        if self.directory.pending_transition():
            raise RuntimeError("global payload transition barrier did not finish")
        self._epoch_signature = None

    def release(self, physical_pages: torch.Tensor) -> None:
        pages = _as_int_list(physical_pages)
        self.directory.release(pages)
        self._sync_directory(pages)

    def clear(self) -> None:
        self.directory = CanonicalTierDirectory()
        self.recent_locations.fill_(-1)
        self.old_locations.fill_(-1)
        self._epoch_signature = None

    def move_kv_cache(self, target: torch.Tensor, source: torch.Tensor) -> None:
        targets = _as_int_list(target)
        sources = _as_int_list(source)
        if len(targets) != len(sources):
            raise ValueError("canonical move source/target lengths differ")
        for target_page, source_page in zip(targets, sources):
            self.directory.move(target_page, source_page)
        self._sync_directory(targets + sources)

    def get_kv_size_bytes(self):
        k_payload = sum(value.numel() for value in self.recent_k + self.old_k)
        v_payload = sum(value.numel() for value in self.recent_v + self.old_v)
        metadata = (
            self.recent_locations.numel() * self.recent_locations.element_size()
            + self.old_locations.numel() * self.old_locations.element_size()
            + self.recent_free_stack.numel() * self.recent_free_stack.element_size()
            + self.old_free_stack.numel() * self.old_free_stack.element_size()
        )
        return k_payload + metadata, v_payload

    def get_key_buffer(self, layer_id: int):
        raise RuntimeError("global mixed-tier buffers require the fused consumer")

    def get_value_buffer(self, layer_id: int):
        raise RuntimeError("global mixed-tier buffers require the fused consumer")

    def get_kv_buffer(self, layer_id: int):
        return self.get_key_buffer(layer_id), self.get_value_buffer(layer_id)

    def set_kv_buffer(self, *args, **kwargs):
        raise RuntimeError("global mixed-tier writes require position-aware routing")

    def register_layer_transfer_counter(self, _counter):
        return None


class DualKV4SWAKVPool(SWAKVPool):
    def __init__(
        self,
        size: int,
        size_swa: int,
        page_size: int,
        dtype: torch.dtype,
        head_num: int,
        head_dim: int,
        swa_attention_layer_ids: list[int],
        full_attention_layer_ids: list[int],
        device: str,
        token_to_kv_pool_class=MHATokenToKVPool,
        **kwargs,
    ):
        if page_size != 1:
            raise ValueError("dual KV4 requires page size one")
        if tuple(swa_attention_layer_ids) != tuple(
            layer for layer in range(60) if layer not in GLOBAL_LAYER_IDS
        ):
            raise ValueError("local layer schedule differs from five-local/one-global")
        if tuple(full_attention_layer_ids) != GLOBAL_LAYER_IDS:
            raise ValueError("global layer schedule differs from five-local/one-global")
        if size != PHYSICAL_CAPACITY - 1 or size_swa != LOCAL_CAPACITY:
            raise ValueError("fixed c32 allocator capacities changed")

        self.size = size
        self.size_swa = size_swa
        self.dtype = dtype
        self.head_num = head_num
        self.head_dim = head_dim
        self.device = device
        self.swa_layer_nums = LOCAL_LAYERS
        self.full_layer_nums = GLOBAL_LAYERS
        self.layer_num = 60
        self.start_layer = 0
        self.page_size = 1
        self.layer_transfer_counter = None
        self.enable_custom_mem_pool, self.custom_mem_pool, _ = (
            maybe_init_custom_mem_pool(device=device)
        )

        self.swa_kv_pool = token_to_kv_pool_class(
            size=LOCAL_CAPACITY,
            page_size=1,
            dtype=dtype,
            head_num=16,
            head_dim=LOCAL_HEAD_DIM,
            layer_num=LOCAL_LAYERS,
            device=device,
            enable_memory_saver=False,
            post_capture_active=False,
            quant_method=LocalKV4OutlierKVCacheMethod(),
        )
        self.full_kv_pool = GlobalTieredKVPool(device)
        self.layers_mapping = {}
        for local_id, global_id in enumerate(full_attention_layer_ids):
            self.layers_mapping[global_id] = (local_id, False)
        for local_id, global_id in enumerate(swa_attention_layer_ids):
            self.layers_mapping[global_id] = (local_id, True)
        self.full_to_swa_index_mapping = None
        k_size, v_size = self.get_kv_size_bytes()
        self.mem_usage = (k_size + v_size) / GB

    def get_kv_size_bytes(self):
        local_k, local_v = self.swa_kv_pool.get_kv_size_bytes()
        global_k, global_v = self.full_kv_pool.get_kv_size_bytes()
        return local_k + global_k, local_v + global_v

    def set_kv_buffer(self, layer, loc_info, cache_k, cache_v, k_scale=1.0, v_scale=1.0):
        loc, swa_loc, _ = unwrap_write_loc(loc_info)
        local_id, is_local = self.layers_mapping[layer.layer_id]
        if not is_local:
            raise RuntimeError("global write bypassed the position-aware router")
        if swa_loc is None:
            raise RuntimeError("local write requires canonical-to-SWA translation")
        self.swa_kv_pool.set_kv_buffer(
            None,
            swa_loc,
            cache_k,
            cache_v,
            k_scale,
            v_scale,
            layer_id_override=local_id,
        )

    def move_kv_cache(self, target: torch.Tensor, source: torch.Tensor):
        self.full_kv_pool.move_kv_cache(target, source)
        target_swa = self.translate_loc_from_full_to_swa(target)
        source_swa = self.translate_loc_from_full_to_swa(source)
        self.swa_kv_pool.move_kv_cache(target_swa, source_swa)


class DualKV4Allocator(SWATokenToKVPoolAllocator):
    def free(self, free_index: torch.Tensor):
        if free_index.numel() and self.is_not_in_free_group:
            self._kvcache.full_kv_pool.release(free_index)
        super().free(free_index)

    def clear(self):
        super().clear()
        self._kvcache.full_kv_pool.clear()


def _global_routes(backend, forward_batch):
    extend_lens = forward_batch.extend_seq_lens
    prefix_lens = forward_batch.extend_prefix_lens
    if extend_lens is None or prefix_lens is None:
        extend_lens = torch.ones_like(forward_batch.seq_lens)
        prefix_lens = forward_batch.seq_lens - 1
    extend_start = forward_batch.extend_start_loc
    if extend_start is None:
        extend_start = torch.cat(
            (
                torch.zeros(1, dtype=torch.int32, device=extend_lens.device),
                torch.cumsum(extend_lens[:-1], dim=0),
            )
        )
    return backend.token_to_kv_pool.full_kv_pool.begin_epoch(
        new_physical=forward_batch.out_cache_loc,
        positions=forward_batch.positions,
        extend_start=extend_start,
        extend_lens=extend_lens,
        prefix_lens=prefix_lens,
        kv_indptr=backend.forward_metadata.kv_indptr,
        kv_indices=backend.forward_metadata.kv_indices,
    )


def _global_attention(backend, q, layer, max_query_len: int):
    pool = backend.token_to_kv_pool
    local_layer_id, is_local = pool.layers_mapping[layer.layer_id]
    if is_local:
        raise ValueError("local layer entered the global consumer")
    global_pool = pool.full_kv_pool
    return load_global_extension().paged_attention(
        q.contiguous(),
        global_pool.recent_k[local_layer_id],
        global_pool.recent_v[local_layer_id],
        global_pool.old_k[local_layer_id],
        global_pool.old_v[local_layer_id],
        global_pool.recent_locations,
        global_pool.old_locations,
        backend.forward_metadata.qo_indptr,
        backend.forward_metadata.kv_indptr,
        backend.forward_metadata.kv_indices,
        max_query_len,
        1.0 / math.sqrt(GLOBAL_HEAD_DIM),
    )


def _forward_global(backend, q, k, v, layer, forward_batch, max_query_len: int):
    if k is None or v is None:
        raise ValueError("global mixed-tier producer requires current K and V")
    routes = _global_routes(backend, forward_batch)
    local_layer_id, is_local = backend.token_to_kv_pool.layers_mapping[layer.layer_id]
    if is_local:
        raise ValueError("local layer entered the global producer")
    backend.token_to_kv_pool.full_kv_pool.write_layer(
        local_layer_id, k, v, routes
    )
    if local_layer_id == 0:
        backend.token_to_kv_pool.full_kv_pool.retire_all_layers(routes)
    if layer.layer_id == GLOBAL_LAYER_IDS[-1]:
        backend.token_to_kv_pool.full_kv_pool.finish_forward()
    output = _global_attention(
        backend,
        q.view(-1, layer.tp_q_head_num, layer.qk_head_dim),
        layer,
        max_query_len,
    )
    return output.reshape(-1, layer.tp_q_head_num * layer.v_head_dim)


def _store_local(backend, k, v, layer, forward_batch):
    loc = KVWriteLoc(
        forward_batch.out_cache_loc,
        backend.forward_metadata.swa_out_cache_loc,
        full_loc=backend.forward_metadata.out_cache_loc_full_physical,
    )
    backend._set_kv_buffer(forward_batch, layer, loc, k, v)


def _forward_local(backend, q, k, v, layer, forward_batch, max_query_len: int):
    _store_local(backend, k, v, layer, forward_batch)
    q = q.view(-1, layer.tp_q_head_num, layer.qk_head_dim)
    return fused_local_attention(
        q,
        pool=backend.token_to_kv_pool,
        layer_id=layer.layer_id,
        qo_indptr=backend.forward_metadata.qo_indptr,
        window_kv_indptr=backend.forward_metadata.window_kv_indptr,
        window_kv_indices=backend.forward_metadata.window_kv_indices,
        max_query_len=max_query_len,
    ).reshape(-1, layer.tp_q_head_num * layer.v_head_dim)


def install_current_runtime() -> None:
    from sglang.srt.layers.attention import triton_backend
    from sglang.srt.mem_cache import kv_cache_configurator
    from sglang.srt.model_executor import pool_configurator

    backend_class = triton_backend.TritonAttnBackend
    if getattr(backend_class, "_dual_kv4_installed", False):
        return

    class FixedDualKV4PoolConfigurator(pool_configurator.MemoryPoolConfigurator):
        def __init__(self, kvc):
            if kvc.server_args.mem_fraction_static != 0.953:
                raise ValueError("dual KV4 admits only mem-fraction-static 0.953")

        def _fixed(self, available_bytes):
            required = 11_272_647_324
            if available_bytes < required:
                raise RuntimeError(
                    f"dual KV4 needs {required} KV bytes, got {available_bytes}"
                )
            return pool_configurator.MemoryPoolConfig(
                max_total_num_tokens=PHYSICAL_CAPACITY - 1,
                full_max_total_num_tokens=PHYSICAL_CAPACITY - 1,
                swa_max_total_num_tokens=LOCAL_CAPACITY,
            )

        def calculate_pool_sizes(self, available_bytes, page_size):
            if page_size != 1:
                raise ValueError("dual KV4 requires page size one")
            return self._fixed(available_bytes)

        def calculate_pool_sizes_from_max_tokens(self, max_total_num_tokens, page_size):
            if max_total_num_tokens < PHYSICAL_CAPACITY - 1:
                raise RuntimeError("fixed c32 canonical capacity was clamped")
            return self._fixed(11_272_647_324)

    original_factory = pool_configurator.create_memory_pool_configurator

    def configurator_factory(kvc):
        if (
            getattr(kvc.model_config.hf_config, "model_type", None) == "gemma4"
            and kvc.server_args.mem_fraction_static == 0.953
        ):
            return FixedDualKV4PoolConfigurator(kvc)
        return original_factory(kvc)

    def forward_extend(self, q, k, v, layer, forward_batch, **kwargs):
        if kwargs.get("sinks") is not None or kwargs.get("score_mod") is not None:
            raise NotImplementedError("dual KV4 admits no sinks or score modifier")
        max_query_len = int(backend_max_extend_len(self))
        if layer.layer_id in GLOBAL_LAYER_IDS:
            return _forward_global(
                self, q, k, v, layer, forward_batch, max_query_len
            )
        return _forward_local(self, q, k, v, layer, forward_batch, max_query_len)

    def forward_decode(self, q, k, v, layer, forward_batch, **kwargs):
        if kwargs.get("sinks") is not None or kwargs.get("score_mod") is not None:
            raise NotImplementedError("dual KV4 admits no sinks or score modifier")
        if layer.layer_id in GLOBAL_LAYER_IDS:
            return _forward_global(self, q, k, v, layer, forward_batch, 1)
        return _forward_local(self, q, k, v, layer, forward_batch, 1)

    pool_configurator.create_memory_pool_configurator = configurator_factory
    kv_cache_configurator.SWAKVPool = DualKV4SWAKVPool
    kv_cache_configurator.SWATokenToKVPoolAllocator = DualKV4Allocator
    backend_class.forward_extend = forward_extend
    backend_class.forward_decode = forward_decode
    backend_class._dual_kv4_installed = True


def backend_max_extend_len(backend) -> int:
    value = backend.forward_metadata.max_extend_len
    return int(value.item()) if isinstance(value, torch.Tensor) else int(value)
