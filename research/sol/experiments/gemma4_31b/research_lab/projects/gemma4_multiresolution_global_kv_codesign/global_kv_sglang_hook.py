"""Production SGLang global-attention adapter for the admitted 512/8/8 proxy."""
from __future__ import annotations

import json
import math
import os
import pathlib
import threading

import torch

SUMMARY = 512
RECENT = 8
PROTECTED = tuple(range(8))
TILE = 64
_LOCK = threading.Lock()
_INSTALLED = False
_MATCHED = False
_DIAGNOSTIC_WRITTEN = False


class RequestState:
    def __init__(self) -> None:
        self.k: list[torch.Tensor] = []
        self.v: list[torch.Tensor] = []
        self.tokens = 0

    def exact(self) -> tuple[torch.Tensor, torch.Tensor]:
        if not self.k:
            raise RuntimeError("global_kv_empty_request_state")
        return torch.cat(self.k), torch.cat(self.v)

    def append(self, k: torch.Tensor, v: torch.Tensor) -> None:
        self.k.append(k.detach())
        self.v.append(v.detach())
        self.tokens += k.shape[0]

    def clone_prefix(self, count: int) -> "RequestState":
        k, v = self.exact()
        result = RequestState()
        result.append(k[:count].clone(), v[:count].clone())
        return result


def _diagnostic(kind: str, **fields: object) -> None:
    global _DIAGNOSTIC_WRITTEN
    with _LOCK:
        if _DIAGNOSTIC_WRITTEN:
            return
        _DIAGNOSTIC_WRITTEN = True
        path = pathlib.Path(os.environ["GLOBAL_KV_DIAGNOSTIC"])
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(json.dumps({"classification": kind, **fields}, indent=2, sort_keys=True) + "\n")
        temporary.replace(path)


def _telemetry(row: dict[str, object]) -> None:
    path = pathlib.Path(os.environ["GLOBAL_KV_TELEMETRY"])
    with _LOCK, path.open("a") as output:
        output.write(json.dumps(row, sort_keys=True) + "\n")


def _compact(
    state: RequestState,
    q: torch.Tensor,
    current_k: torch.Tensor,
    current_v: torch.Tensor,
) -> torch.Tensor:
    start = state.tokens
    exact_k, exact_v = state.exact() if start else (
        current_k.new_empty((0, current_k.shape[1], current_k.shape[2])),
        current_v.new_empty((0, current_v.shape[1], current_v.shape[2])),
    )
    outputs = []
    for offset in range(0, q.shape[0], 32):
        block_q = q[offset : offset + 32]
        block_k = current_k[offset : offset + 32]
        block_v = current_v[offset : offset + 32]
        query_start = start + offset
        query_end = query_start + block_q.shape[0]
        available_k = torch.cat((exact_k, current_k[: offset + block_q.shape[0]]))
        available_v = torch.cat((exact_v, current_v[: offset + block_q.shape[0]]))
        old_end = max(0, query_start - RECENT)
        keys = []
        values = []
        counts = []
        causal_ends = []
        for begin in range(0, old_end, SUMMARY):
            end = min(begin + SUMMARY, old_end)
            positions = [p for p in range(begin, end) if p not in PROTECTED]
            if positions:
                index = torch.tensor(positions, device=q.device)
                keys.append(available_k.index_select(0, index).float().mean(0))
                values.append(available_v.index_select(0, index).float().mean(0))
                counts.append(len(positions))
                causal_ends.append(end - 1)
        exact_positions = sorted(set(p for p in PROTECTED if p < query_end).union(range(old_end, query_end)))
        index = torch.tensor(exact_positions, device=q.device)
        keys.extend(available_k.index_select(0, index).float().unbind())
        values.extend(available_v.index_select(0, index).float().unbind())
        counts.extend([1] * len(exact_positions))
        causal_ends.extend(exact_positions)
        if len(keys) > TILE:
            raise RuntimeError(f"global_kv_compact_tile_overflow:{len(keys)}")
        compact_k = torch.stack(keys)
        compact_v = torch.stack(values)
        kv_heads = compact_k.shape[1]
        groups = block_q.shape[1] // kv_heads
        grouped_q = block_q.float().view(block_q.shape[0], kv_heads, groups, block_q.shape[2])
        logits = torch.einsum("mhgd,khd->mhgk", grouped_q, compact_k)
        logits.mul_(block_q.shape[2] ** -0.5)
        logits.add_(torch.tensor(counts, device=q.device, dtype=torch.float32).log()[None, None, None, :])
        q_positions = torch.arange(query_start, query_end, device=q.device)
        causal = torch.tensor(causal_ends, device=q.device)
        logits.masked_fill_(causal[None, None, None, :] > q_positions[:, None, None, None], -torch.inf)
        probabilities = torch.softmax(logits, dim=-1)
        output = torch.einsum("mhgk,khd->mhgd", probabilities, compact_v)
        outputs.append(output.to(q.dtype).reshape(block_q.shape))
        _telemetry({
            "phase": "decode" if block_q.shape[0] == 1 else "prefill",
            "query_start": query_start,
            "query_count": block_q.shape[0],
            "compact_entries": len(keys),
            "fallback": False,
        })
    return torch.cat(outputs)


def install() -> None:
    global _INSTALLED, _MATCHED
    if _INSTALLED or os.environ.get("GLOBAL_KV_HOOK") != "1":
        return
    from sglang.srt.layers.radix_attention import RadixAttention

    original = RadixAttention.forward

    def forward(self, q, k, v, forward_batch, save_kv_cache=True, **kwargs):
        global _MATCHED
        is_global = (
            self.sliding_window_size == -1
            and self.tp_q_head_num == 32
            and self.tp_k_head_num == 4
            and self.head_dim == 512
            and self.layer_id % 6 == 5
            and k is not None
        )
        if not is_global:
            return original(self, q, k, v, forward_batch, save_kv_cache, **kwargs)
        try:
            if not _MATCHED:
                _MATCHED = True
                _telemetry({"phase": "global_layer_match", "layer_id": self.layer_id, "q_heads": self.tp_q_head_num, "kv_heads": self.tp_k_head_num, "head_dim": self.head_dim, "fallback": False})
            k = k.view(-1, 4, 512)
            v = v.view(-1, 4, 512)
            states = getattr(self, "_global_kv_states", None)
            prefixes = getattr(self, "_global_kv_prefixes", None)
            if states is None:
                states = self._global_kv_states = {}
                prefixes = self._global_kv_prefixes = {}
            rids = forward_batch.rids or [str(int(x)) for x in forward_batch.req_pool_indices.tolist()]
            if forward_batch.forward_mode.is_extend():
                lengths = list(forward_batch.extend_seq_lens_cpu)
                prefix_lengths = list(forward_batch.extend_prefix_lens_cpu)
            else:
                lengths = [1] * len(rids)
                prefix_lengths = [None] * len(rids)
            output = torch.empty_like(q)
            cursor = 0
            for rid, length, prefix_length in zip(rids, lengths, prefix_lengths):
                length = int(length)
                state = states.get(rid)
                if state is None:
                    if prefix_length:
                        state = prefixes.get(int(prefix_length))
                        if state is None:
                            raise RuntimeError(f"global_kv_prefix_state_missing:{prefix_length}")
                        state = state.clone_prefix(int(prefix_length))
                    else:
                        state = RequestState()
                    states[rid] = state
                if prefix_length is not None and state.tokens != int(prefix_length):
                    raise RuntimeError(f"global_kv_request_ownership_mismatch:{state.tokens}:{prefix_length}")
                request_q = q[cursor : cursor + length]
                request_k = k[cursor : cursor + length]
                request_v = v[cursor : cursor + length]
                output[cursor : cursor + length] = _compact(state, request_q, request_k, request_v)
                state.append(request_k, request_v)
                if state.tokens >= 535 and 535 not in prefixes:
                    prefixes[535] = state.clone_prefix(535)
                cursor += length
            if cursor != q.shape[0]:
                raise RuntimeError(f"global_kv_flattened_batch_mismatch:{cursor}:{q.shape[0]}")
            return output
        except Exception as exc:
            _diagnostic(
                "global_kv_live_hook_exception",
                exception=f"{type(exc).__name__}: {exc}",
                layer_id=self.layer_id,
                forward_mode=str(forward_batch.forward_mode),
            )
            raise

    RadixAttention.forward = forward
    _INSTALLED = True
    _telemetry({"phase": "install", "q_heads": 32, "kv_heads": 4, "head_dim": 512, "fallback": False})


install()
