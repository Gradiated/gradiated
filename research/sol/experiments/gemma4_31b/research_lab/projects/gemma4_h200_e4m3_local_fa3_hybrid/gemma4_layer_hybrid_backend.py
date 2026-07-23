from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sglang.srt.layers.attention.base_attn_backend import AttentionBackend

if TYPE_CHECKING:
    from sglang.srt.layers.radix_attention import RadixAttention
    from sglang.srt.model_executor.forward_batch_info import ForwardBatch
    from sglang.srt.model_executor.model_runner import ModelRunner


class Gemma4LayerHybridAttnBackend(AttentionBackend):
    needs_cpu_seq_lens = True

    def __init__(
        self,
        model_runner: ModelRunner,
        local_backend: AttentionBackend,
        global_backend: AttentionBackend,
    ):
        self.model_runner = model_runner
        self.local_backend = local_backend
        self.global_backend = global_backend
        self.data_type = model_runner.kv_cache_dtype
        self.token_to_kv_pool = model_runner.token_to_kv_pool
        self.req_to_token_pool = model_runner.req_to_token_pool
        config = model_runner.model_config.hf_text_config
        self.local_layer_ids = frozenset(
            index
            for index, layer_type in enumerate(config.layer_types)
            if layer_type == "sliding_attention"
        )
        self.global_layer_ids = frozenset(
            index
            for index, layer_type in enumerate(config.layer_types)
            if layer_type == "full_attention"
        )
        if len(self.local_layer_ids) != 50 or len(self.global_layer_ids) != 10:
            raise RuntimeError(
                "gemma4_layer_pattern_mismatch:"
                f"{len(self.local_layer_ids)}:{len(self.global_layer_ids)}"
            )
        self._audited_layer_ids: set[int] = set()
        self._audit_path = os.environ.get("E4M3_FA3_HYBRID_AUDIT")
        self._write_binding_audit()

    def _write_audit(self, value: dict[str, Any]) -> None:
        if not self._audit_path:
            return
        path = Path(self._audit_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
        try:
            os.write(
                descriptor,
                (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(),
            )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _write_binding_audit(self) -> None:
        self._write_audit(
            {
                "event": "router_bound",
                "local_backend": type(self.local_backend).__name__,
                "global_backend": type(self.global_backend).__name__,
                "local_layer_ids": sorted(self.local_layer_ids),
                "global_layer_ids": sorted(self.global_layer_ids),
                "kv_cache_dtype": str(self.data_type),
            }
        )

    def _select_backend(self, layer: RadixAttention) -> AttentionBackend:
        layer_id = int(layer.layer_id)
        if layer_id in self.local_layer_ids:
            backend = self.local_backend
            expected = (32, 16, 256, 256)
            route = "local_fa3"
            if not (
                layer.sliding_window_size is not None
                and layer.sliding_window_size > -1
            ):
                raise RuntimeError(f"local_layer_without_window:{layer_id}")
        elif layer_id in self.global_layer_ids:
            backend = self.global_backend
            expected = (32, 4, 512, 512)
            route = "global_triton"
            if layer.sliding_window_size is not None and layer.sliding_window_size > -1:
                raise RuntimeError(f"global_layer_with_window:{layer_id}")
        else:
            raise RuntimeError(f"unbound_attention_layer:{layer_id}")
        observed = (
            int(layer.tp_q_head_num),
            int(layer.tp_k_head_num),
            int(layer.qk_head_dim),
            int(layer.v_head_dim),
        )
        if observed != expected:
            raise RuntimeError(
                f"gemma4_layer_geometry_mismatch:{layer_id}:{observed}:{expected}"
            )
        if layer_id not in self._audited_layer_ids:
            self._write_audit(
                {
                    "event": "layer_dispatched",
                    "layer_id": layer_id,
                    "route": route,
                    "backend": type(backend).__name__,
                    "q_heads": observed[0],
                    "kv_heads": observed[1],
                    "qk_head_dim": observed[2],
                    "v_head_dim": observed[3],
                    "sliding_window_size": layer.sliding_window_size,
                }
            )
            self._audited_layer_ids.add(layer_id)
        return backend

    def init_forward_metadata(self, forward_batch: ForwardBatch):
        self.global_backend.init_forward_metadata(forward_batch)
        self.local_backend.init_forward_metadata(forward_batch)

    def init_forward_metadata_out_graph(
        self, forward_batch: ForwardBatch, in_capture: bool = False
    ):
        self.global_backend.init_forward_metadata_out_graph(
            forward_batch, in_capture=in_capture
        )
        self.local_backend.init_forward_metadata_out_graph(
            forward_batch, in_capture=in_capture
        )

    def init_forward_metadata_in_graph(self, forward_batch: ForwardBatch):
        self.global_backend.init_forward_metadata_in_graph(forward_batch)
        self.local_backend.init_forward_metadata_in_graph(forward_batch)

    def init_cuda_graph_state(self, max_bs: int, max_num_tokens: int):
        self.global_backend.init_cuda_graph_state(max_bs, max_num_tokens)
        self.local_backend.init_cuda_graph_state(max_bs, max_num_tokens)

    def get_cuda_graph_seq_len_fill_value(self):
        local_value = self.local_backend.get_cuda_graph_seq_len_fill_value()
        global_value = self.global_backend.get_cuda_graph_seq_len_fill_value()
        if local_value != global_value:
            raise RuntimeError(
                f"hybrid_cuda_graph_fill_mismatch:{local_value}:{global_value}"
            )
        return local_value

    def on_after_cuda_graph_warmup(self):
        self.global_backend.on_after_cuda_graph_warmup()
        self.local_backend.on_after_cuda_graph_warmup()

    def forward(
        self,
        q=None,
        k=None,
        v=None,
        layer=None,
        forward_batch=None,
        save_kv_cache: bool = True,
        **kwargs,
    ):
        backend = self._select_backend(layer)
        return backend.forward(
            q=q,
            k=k,
            v=v,
            layer=layer,
            forward_batch=forward_batch,
            save_kv_cache=save_kv_cache,
            **kwargs,
        )

    def forward_decode(
        self,
        q,
        k,
        v,
        layer,
        forward_batch,
        save_kv_cache: bool = True,
        **kwargs,
    ):
        return self._select_backend(layer).forward_decode(
            q,
            k,
            v,
            layer,
            forward_batch,
            save_kv_cache=save_kv_cache,
            **kwargs,
        )

    def forward_extend(
        self,
        q,
        k,
        v,
        layer,
        forward_batch,
        save_kv_cache: bool = True,
        **kwargs,
    ):
        return self._select_backend(layer).forward_extend(
            q,
            k,
            v,
            layer,
            forward_batch,
            save_kv_cache=save_kv_cache,
            **kwargs,
        )

    def get_indexer_metadata(self, layer_id: int, forward_batch: ForwardBatch):
        if layer_id in self.local_layer_ids:
            backend = self.local_backend
        elif layer_id in self.global_layer_ids:
            backend = self.global_backend
        else:
            raise RuntimeError(f"unbound_attention_layer:{layer_id}")
        return backend.get_indexer_metadata(layer_id, forward_batch)

    def support_triton(self):
        return True
