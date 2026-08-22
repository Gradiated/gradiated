"""Fail-closed SGLang seam for the hash-bound U=8 streamed global-KV path."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import threading

import torch

import multiresolution_global_kv as activated
import streaming_global_kv_schedule as streamed


EXPECTED_CANDIDATE_SHA256 = "636cc6e683d04f8950ce288f567ed5411a8d3cbb667b92329827c9bc6d35a23a"
EXPECTED_ACTIVATED_SHA256 = "47c1dd902dd287cab2403cb06790095a3e041df434e48ffe22832dfdad4d4880"
_LOCK = threading.Lock()
_INSTALLED = False
_DIAGNOSTIC_WRITTEN = False


def _atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _diagnostic(kind: str, **fields: object) -> None:
    global _DIAGNOSTIC_WRITTEN
    with _LOCK:
        if _DIAGNOSTIC_WRITTEN:
            return
        _DIAGNOSTIC_WRITTEN = True
        _atomic(pathlib.Path(os.environ["GLOBAL_KV_DIAGNOSTIC"]), {"classification": kind, **fields})


def _telemetry(row: dict[str, object]) -> None:
    path = pathlib.Path(os.environ["GLOBAL_KV_TELEMETRY"])
    with _LOCK, path.open("a") as output:
        output.write(json.dumps(row, sort_keys=True) + "\n")


def _source_digest(module: object) -> str:
    return hashlib.sha256(pathlib.Path(module.__file__).read_bytes()).hexdigest()


class _State:
    def __init__(self) -> None:
        self.summary = activated.IncrementalGlobalSummaryState(range(8))
        self.k: list[torch.Tensor] = []
        self.v: list[torch.Tensor] = []

    def clone_prefix(self, count: int) -> "_State":
        result = _State()
        if count:
            exact_k = torch.cat(self.k, dim=0)[:count]
            exact_v = torch.cat(self.v, dim=0)[:count]
            result.summary.append_committed(exact_k, exact_v)
            result.k.append(exact_k.detach().clone())
            result.v.append(exact_v.detach().clone())
        return result

    def consume(self, q: torch.Tensor, k: torch.Tensor, v: torch.Tensor, phase: str) -> tuple[torch.Tensor, int]:
        start = self.summary.committed_tokens
        exact_k = torch.cat([*self.k, k], dim=0) if self.k else k
        exact_v = torch.cat([*self.v, v], dim=0) if self.v else v
        request = streamed.LayerRequest(
            phase=phase,
            q=q,
            exact_post_rope_k=exact_k,
            exact_v=exact_v,
            query_start=start,
            summary_state=self.summary,
            protected_positions=range(8),
        )
        proof = streamed.forward_layer_local_inplace([request])
        self.k.append(k.detach())
        self.v.append(v.detach())
        return q, proof["peak_compact_tokens"]


def install() -> None:
    global _INSTALLED
    if _INSTALLED or os.environ.get("GLOBAL_KV_HOOK") != "1":
        return
    if _source_digest(streamed) != EXPECTED_CANDIDATE_SHA256 or _source_digest(activated) != EXPECTED_ACTIVATED_SHA256:
        raise RuntimeError("global_kv_bound_source_digest_mismatch")
    from sglang.srt.layers.radix_attention import RadixAttention

    original = RadixAttention.forward

    def forward(self, q, k, v, forward_batch, save_kv_cache=True, **kwargs):
        is_global = self.sliding_window_size == -1 and self.layer_id % 6 == 5 and k is not None
        if not is_global:
            return original(self, q, k, v, forward_batch, save_kv_cache, **kwargs)
        if (self.tp_q_head_num, self.tp_k_head_num, self.head_dim) != (32, 4, 512):
            _diagnostic(
                "global_kv_runtime_geometry_incompatible",
                layer_id=self.layer_id,
                observed={
                    "q_heads": self.tp_q_head_num,
                    "kv_heads": self.tp_k_head_num,
                    "head_dim": self.head_dim,
                },
                required={"q_heads": 32, "kv_heads": 4, "head_dim": 512},
            )
            return original(self, q, k, v, forward_batch, save_kv_cache, **kwargs)
        try:
            states = getattr(self, "_streamed_global_kv_states", None)
            prefixes = getattr(self, "_streamed_global_kv_prefixes", None)
            if states is None:
                states, prefixes = {}, {}
                self._streamed_global_kv_states, self._streamed_global_kv_prefixes = states, prefixes
            rids = forward_batch.rids or [str(int(item)) for item in forward_batch.req_pool_indices.tolist()]
            if forward_batch.forward_mode.is_extend():
                lengths = [int(item) for item in forward_batch.extend_seq_lens_cpu]
                prefix_lengths = list(forward_batch.extend_prefix_lens_cpu)
                phase = "prefill"
            else:
                lengths, prefix_lengths, phase = [1] * len(rids), [None] * len(rids), "decode"
            q3, k3, v3 = q.view(-1, 32, 512), k.view(-1, 4, 512), v.view(-1, 4, 512)
            output, cursor = torch.empty_like(q3), 0
            for rid, length, prefix_length in zip(rids, lengths, prefix_lengths, strict=True):
                state = states.get(rid)
                if state is None:
                    if prefix_length:
                        source = prefixes.get(int(prefix_length))
                        if source is None:
                            raise RuntimeError(f"global_kv_prefix_state_missing:{prefix_length}")
                        state = source.clone_prefix(int(prefix_length))
                    else:
                        state = _State()
                    states[rid] = state
                if prefix_length is not None and state.summary.committed_tokens != int(prefix_length):
                    raise RuntimeError("global_kv_request_ownership_mismatch")
                result, compact = state.consume(q3[cursor:cursor + length], k3[cursor:cursor + length], v3[cursor:cursor + length], phase)
                output[cursor:cursor + length] = result
                if state.summary.committed_tokens >= 535 and 535 not in prefixes:
                    prefixes[535] = state.clone_prefix(535)
                _telemetry({"phase": phase, "layer_id": self.layer_id, "candidate_path": "u8_streamed", "query_count": length, "compact_entries": compact, "fallback": False})
                cursor += length
            if cursor != q3.shape[0]:
                raise RuntimeError("global_kv_flattened_batch_mismatch")
            return output.reshape_as(q)
        except Exception as exc:
            _diagnostic("global_kv_live_hook_exception", exception=f"{type(exc).__name__}: {exc}", layer_id=self.layer_id)
            raise

    RadixAttention.forward = forward
    _INSTALLED = True
    activation_path = pathlib.Path(os.environ["GLOBAL_KV_ACTIVATION_CAPTURE"])
    _atomic(activation_path, {"candidate_path": "u8_streamed", "candidate_sha256": EXPECTED_CANDIDATE_SHA256, "activated_sha256": EXPECTED_ACTIVATED_SHA256, "hook_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(), "target": "sglang.srt.layers.radix_attention.RadixAttention.forward"})
    _telemetry({"phase": "install", "candidate_path": "u8_streamed", "fallback": False})


install()
