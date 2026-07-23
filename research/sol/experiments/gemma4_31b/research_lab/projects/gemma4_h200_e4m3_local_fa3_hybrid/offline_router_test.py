#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from gemma4_layer_hybrid_backend import Gemma4LayerHybridAttnBackend


class FakeBackend:
    def __init__(self, name: str):
        self.name = name
        self.calls: list[tuple[str, int | None]] = []

    def _record(self, name, layer=None):
        self.calls.append((name, None if layer is None else layer.layer_id))
        return self.name

    def init_forward_metadata(self, batch):
        return self._record("init_forward_metadata")

    def init_forward_metadata_out_graph(self, batch, in_capture=False):
        return self._record(f"init_forward_metadata_out_graph:{in_capture}")

    def init_forward_metadata_in_graph(self, batch):
        return self._record("init_forward_metadata_in_graph")

    def init_cuda_graph_state(self, max_bs, max_num_tokens):
        return self._record(f"init_cuda_graph_state:{max_bs}:{max_num_tokens}")

    def get_cuda_graph_seq_len_fill_value(self):
        return 1

    def on_after_cuda_graph_warmup(self):
        return self._record("on_after_cuda_graph_warmup")

    def forward(self, **kwargs):
        return self._record("forward", kwargs["layer"])

    def forward_decode(self, q, k, v, layer, forward_batch, **kwargs):
        return self._record("forward_decode", layer)

    def forward_extend(self, q, k, v, layer, forward_batch, **kwargs):
        return self._record("forward_extend", layer)

    def get_indexer_metadata(self, layer_id, forward_batch):
        self.calls.append(("get_indexer_metadata", layer_id))
        return self.name


def layer(layer_id: int, local: bool):
    return SimpleNamespace(
        layer_id=layer_id,
        tp_q_head_num=32,
        tp_k_head_num=16 if local else 4,
        qk_head_dim=256 if local else 512,
        v_head_dim=256 if local else 512,
        sliding_window_size=1023 if local else -1,
    )


def main() -> int:
    output = Path(os.environ["E4M3_FA3_HYBRID_AUDIT"])
    local = FakeBackend("fa3")
    global_backend = FakeBackend("triton")
    layer_types = [
        "full_attention" if (index + 1) % 6 == 0 else "sliding_attention"
        for index in range(60)
    ]
    runner = SimpleNamespace(
        kv_cache_dtype="torch.float8_e5m2",
        token_to_kv_pool=SimpleNamespace(
            swa_kv_pool=SimpleNamespace(dtype="torch.float8_e4m3fn"),
            full_kv_pool=SimpleNamespace(dtype="torch.float8_e5m2"),
        ),
        req_to_token_pool=object(),
        model_config=SimpleNamespace(
            hf_text_config=SimpleNamespace(layer_types=layer_types)
        ),
    )
    hybrid = Gemma4LayerHybridAttnBackend(runner, local, global_backend)
    batch = object()
    hybrid.init_forward_metadata(batch)
    hybrid.init_forward_metadata_out_graph(batch, in_capture=True)
    hybrid.init_forward_metadata_in_graph(batch)
    hybrid.init_cuda_graph_state(32, 32)
    hybrid.on_after_cuda_graph_warmup()
    local_layer = layer(0, True)
    global_layer = layer(5, False)
    assert hybrid.forward(
        q=None,
        k=None,
        v=None,
        layer=local_layer,
        forward_batch=batch,
    ) == "fa3"
    assert (
        hybrid.forward_decode(None, None, None, global_layer, batch) == "triton"
    )
    assert hybrid.forward_extend(None, None, None, local_layer, batch) == "fa3"
    assert hybrid.get_indexer_metadata(5, batch) == "triton"
    assert hybrid.get_cuda_graph_seq_len_fill_value() == 1
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    binding = next(row for row in rows if row["event"] == "router_bound")
    assert len(binding["local_layer_ids"]) == 50
    assert len(binding["global_layer_ids"]) == 10
    dispatch = {row["route"]: row for row in rows if row["event"] == "layer_dispatched"}
    assert dispatch["local_fa3"]["backend"] == "FakeBackend"
    assert dispatch["global_triton"]["backend"] == "FakeBackend"
    print(json.dumps({"pass": True, "audit_rows": len(rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
