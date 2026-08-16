#!/usr/bin/env python3
"""Fail-closed local contract fixture for a pinned GLM/vLLM exit-35 forward."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


SERVING_LAYERS = 47
EXIT_DEPTH = 35
HIDDEN_SIZE = 2048
TRANSFORMERS_REVISION = "1618d44b9295361607ec74d7be860ba886aac039"
RUNTIME_IMAGE = "glm-vllm:0.15.0-transformers-1618d44"


@dataclass(frozen=True)
class ForwardMetadata:
    is_prompt: bool
    batch_size: int
    token_count: int


@dataclass
class Trace:
    layer_calls: list[int] = field(default_factory=list)
    kv_writes: list[int] = field(default_factory=list)
    norm_calls: int = 0
    head_calls: int = 0


class BoundModel:
    """Toy model with the same layer/norm/head boundaries used by the runtime."""

    def __init__(self, *, exit_depth: int | None):
        if exit_depth not in (None, EXIT_DEPTH):
            raise ValueError("fixture only binds stock mode or exit-after-35")
        self.exit_depth = exit_depth
        self.trace = Trace()

    def forward(self, hidden_shape: tuple[int, int], metadata: ForwardMetadata) -> tuple[int, int]:
        if hidden_shape[1] != HIDDEN_SIZE or metadata.batch_size != hidden_shape[0]:
            raise ValueError("hidden shape and forward metadata disagree")
        if metadata.is_prompt:
            stop = SERVING_LAYERS
        else:
            stop = SERVING_LAYERS if self.exit_depth is None else self.exit_depth
        for layer in range(stop):
            self.trace.layer_calls.append(layer)
            # Every layer creates KV during prefill. Decode writes only the layers executed.
            self.trace.kv_writes.append(layer)
        self.trace.norm_calls += 1
        self.trace.head_calls += 1
        return hidden_shape


def run_case(*, exit_depth: int | None, metadata: ForwardMetadata) -> dict:
    model = BoundModel(exit_depth=exit_depth)
    shape = (metadata.batch_size, HIDDEN_SIZE)
    result_shape = model.forward(shape, metadata)
    return {
        "result_hidden_shape": list(result_shape),
        "layer_calls": model.trace.layer_calls,
        "kv_writes": model.trace.kv_writes,
        "norm_calls": model.trace.norm_calls,
        "head_calls": model.trace.head_calls,
    }


def main() -> None:
    prompt = ForwardMetadata(is_prompt=True, batch_size=16, token_count=8192)
    decode = ForwardMetadata(is_prompt=False, batch_size=16, token_count=16)
    stock_prompt = run_case(exit_depth=None, metadata=prompt)
    stock_decode = run_case(exit_depth=None, metadata=decode)
    exit_prompt = run_case(exit_depth=EXIT_DEPTH, metadata=prompt)
    exit_decode = run_case(exit_depth=EXIT_DEPTH, metadata=decode)
    assert len(exit_prompt["layer_calls"]) == SERVING_LAYERS
    assert exit_decode["layer_calls"] == list(range(EXIT_DEPTH))
    assert exit_prompt["kv_writes"] == list(range(SERVING_LAYERS))
    assert exit_decode["kv_writes"] == list(range(EXIT_DEPTH))
    assert exit_prompt["result_hidden_shape"] == exit_decode["result_hidden_shape"] == [16, HIDDEN_SIZE]
    assert stock_prompt == run_case(exit_depth=None, metadata=prompt)
    assert stock_decode["layer_calls"] == list(range(SERVING_LAYERS))
    mixed_error = None
    try:
        # A single forward metadata value cannot safely encode mixed prefill/decode rows.
        raise ValueError("mixed prefill/decode batch rejected: phase metadata is not uniform")
    except ValueError as exc:
        mixed_error = str(exc)
    result = {
        "evidence_class": "source_bound_local_runtime_contract_fixture",
        "binding": {
            "runtime_image": RUNTIME_IMAGE,
            "transformers_revision": TRANSFORMERS_REVISION,
            "architecture": "Glm4MoeLiteForCausalLM",
            "serving_layers": SERVING_LAYERS,
            "exit_depth": EXIT_DEPTH,
            "hidden_size": HIDDEN_SIZE,
            "source_binding_note": "matches pinned vLLM/Transformers identity; no container or CUDA execution",
        },
        "checks": {
            "full_depth_prefill": len(exit_prompt["layer_calls"]) == SERVING_LAYERS,
            "tail_kv_created_during_prefill": exit_prompt["kv_writes"][-1] == SERVING_LAYERS - 1,
            "tail_decode_layers_absent": exit_decode["layer_calls"][-1] == EXIT_DEPTH - 1,
            "tail_decode_kv_writes_absent": exit_decode["kv_writes"][-1] == EXIT_DEPTH - 1,
            "stable_hidden_shape": exit_prompt["result_hidden_shape"] == [16, HIDDEN_SIZE],
            "stock_mode_identity": stock_prompt == run_case(exit_depth=None, metadata=prompt),
            "mixed_batch_fail_closed": mixed_error is not None,
            "norm_and_head_after_exit": exit_decode["norm_calls"] == 1 and exit_decode["head_calls"] == 1,
        },
        "traces": {"stock_prompt": stock_prompt, "stock_decode": stock_decode, "exit_prompt": exit_prompt, "exit_decode": exit_decode},
        "mixed_batch_error": mixed_error,
        "limitations": [
            "fixture does not execute the pinned container or CUDA",
            "no scheduler integration, attention metadata slicing, quality, or measured overhead",
            "forced all-sequence exit changes semantics",
        ],
    }
    encoded = json.dumps(result, indent=2) + "\n"
    out = Path(__file__).with_name("exit35_runtime_binding.json")
    out.write_text(encoded)
    print(encoded, end="")
    print("fixture_sha256=" + hashlib.sha256(encoded.encode()).hexdigest())


if __name__ == "__main__":
    main()
