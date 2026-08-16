from __future__ import annotations

import hashlib
import json
import os
import pathlib
import threading
import time
from typing import Any

import torch


AUDIT_ROOT = pathlib.Path(os.environ["FP8_GRAPH_BOUNDARY_AUDIT"])
EXPECTED_SOURCE = {
    "sglang.srt.model_executor.cuda_graph_runner": "7d1898247e80ff6a446eb42e4968d2eea0df30b109ee2d089a9ad78791bc079e",
    "sglang.srt.model_executor.model_runner": "f4dad073eb9f89afd4cda0439b97dee63f8de131d0ed10078b817dba1f978f59",
    "sglang.srt.layers.sampler": "85541951e1cf50d10c54978178e403ff9d4aa6f223e629ea91965735ba882a8f",
}
_lock = threading.Lock()
_last_replay: dict[str, Any] | None = None
_capture_bs: set[int] = set()
_replay_raw_bs: set[int] = set()
_head_m: set[int] = set()
_replay_count = 0
_head_count = 0


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _append(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(
            descriptor,
            (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        )
    finally:
        os.close(descriptor)


def _metadata(value: object) -> object:
    if not isinstance(value, torch.Tensor):
        return None
    return {
        "shape": list(value.shape),
        "dtype": str(value.dtype),
        "stride": list(value.stride()),
        "data_ptr": value.data_ptr(),
    }


def _state() -> dict[str, object]:
    return {
        "schema_version": 1,
        "successful_capture_batch_sizes": sorted(_capture_bs),
        "observed_replay_raw_batch_sizes": sorted(_replay_raw_bs),
        "observed_head_m": sorted(_head_m),
        "replay_count_lower_bound": _replay_count,
        "candidate_head_count_lower_bound": _head_count,
        "bf16_head_fallback_count": 0,
        "last_replay": _last_replay,
    }


def record_head(
    *,
    hidden_states: torch.Tensor,
    output: torch.Tensor,
    embedding: torch.Tensor,
    candidate_weight: torch.Tensor,
    final_logit_softcapping: float | None,
    stream_capturing: bool,
) -> None:
    global _head_count
    m = int(hidden_states.reshape(-1, hidden_states.shape[-1]).shape[0])
    with _lock:
        _head_count += 1
        first = m not in _head_m
        _head_m.add(m)
        replay = dict(_last_replay) if _last_replay is not None else None
        if first:
            _append(
                AUDIT_ROOT / "head.jsonl",
                {
                    "event": "e4m3_head",
                    "sequence": _head_count,
                    "m": m,
                    "hidden_states": _metadata(hidden_states),
                    "candidate_output": _metadata(output),
                    "embedding": _metadata(embedding),
                    "candidate_weight": _metadata(candidate_weight),
                    "stream_capturing": stream_capturing,
                    "latest_completed_graph_replay": replay,
                    "post_graph_replay": replay is not None and not stream_capturing,
                    "candidate_symbol": "sglang.srt.layers.quantization.fp8_utils.apply_fp8_linear",
                    "final_logit_softcapping": final_logit_softcapping,
                    "bf16_head_fallback": False,
                    "timestamp_monotonic_ns": time.monotonic_ns(),
                },
            )
            _atomic(AUDIT_ROOT / "STATE.json", _state())


def install() -> None:
    global _last_replay, _replay_count
    from sglang.srt.layers import logits_processor, sampler
    from sglang.srt.model_executor import cuda_graph_runner, model_runner
    from sglang.srt.model_executor.cuda_graph_runner import CudaGraphRunner
    from sglang.srt.models import gemma4_causal, gemma4_mm

    modules = {
        "sglang.srt.model_executor.cuda_graph_runner": cuda_graph_runner,
        "sglang.srt.model_executor.model_runner": model_runner,
        "sglang.srt.layers.logits_processor": logits_processor,
        "sglang.srt.layers.sampler": sampler,
        "sglang.srt.models.gemma4_causal": gemma4_causal,
        "sglang.srt.models.gemma4_mm": gemma4_mm,
    }
    observed = {
        name: {
            "path": str(pathlib.Path(module.__file__)),
            "sha256": _sha256(pathlib.Path(module.__file__)),
        }
        for name, module in modules.items()
    }
    mismatches = {
        name: {"expected": expected, "observed": observed[name]["sha256"]}
        for name, expected in EXPECTED_SOURCE.items()
        if observed[name]["sha256"] != expected
    }
    if mismatches:
        raise RuntimeError(f"graph source binding mismatch:{mismatches}")
    cuda_source = pathlib.Path(cuda_graph_runner.__file__).read_text()
    model_source = pathlib.Path(model_runner.__file__).read_text()
    anchors = {
        "capture_calls_forward": "logits_output_or_pp_proxy_tensors = forward(" in cuda_source,
        "capture_forward_is_model_forward": "yield model.forward" in cuda_source,
        "replay_calls_cuda_graph": "self.graphs[graph_key].replay()" in cuda_source,
        "model_runner_selects_graph_replay": "ret = self.graph_runner.replay(" in model_source,
    }
    if not all(anchors.values()):
        raise RuntimeError(f"graph source anchors missing:{anchors}")
    _atomic(
        AUDIT_ROOT / "SOURCE_BINDING.json",
        {
            "schema_version": 1,
            "runtime_source": observed,
            "expected_source": EXPECTED_SOURCE,
            "source_anchors": anchors,
            "pinned_contract": "CudaGraphRunner captures model.forward; replay returns its buffers; the unchanged model path invokes LogitsProcessor after graph output becomes available.",
        },
    )

    original_capture = CudaGraphRunner.capture_one_batch_size
    original_replay = CudaGraphRunner.replay

    def capture(self, bs, forward, stream_idx=None):
        result = original_capture(self, bs, forward, stream_idx)
        with _lock:
            if int(bs) not in _capture_bs:
                _capture_bs.add(int(bs))
                _append(
                    AUDIT_ROOT / "capture.jsonl",
                    {
                        "event": "model_forward_graph_capture_complete",
                        "batch_size": int(bs),
                        "forward_name": getattr(forward, "__qualname__", repr(forward)),
                        "forward_module": getattr(forward, "__module__", None),
                        "stream_idx": stream_idx,
                        "timestamp_monotonic_ns": time.monotonic_ns(),
                    },
                )
                _atomic(AUDIT_ROOT / "STATE.json", _state())
        return result

    def replay(self, forward_batch, pp_proxy_tensors=None):
        global _last_replay, _replay_count
        result = original_replay(self, forward_batch, pp_proxy_tensors)
        raw_bs = int(getattr(self, "raw_bs", forward_batch.batch_size))
        graph_bs = int(getattr(self, "bs", raw_bs))
        with _lock:
            _replay_count += 1
            _last_replay = {
                "sequence": _replay_count,
                "raw_batch_size": raw_bs,
                "graph_batch_size": graph_bs,
                "output_type": type(result).__name__,
                "timestamp_monotonic_ns": time.monotonic_ns(),
            }
            if raw_bs not in _replay_raw_bs:
                _replay_raw_bs.add(raw_bs)
                _append(
                    AUDIT_ROOT / "replay.jsonl",
                    {
                        "event": "model_forward_graph_replay_complete",
                        **_last_replay,
                    },
                )
                _atomic(AUDIT_ROOT / "STATE.json", _state())
        return result

    CudaGraphRunner.capture_one_batch_size = capture
    CudaGraphRunner.replay = replay
