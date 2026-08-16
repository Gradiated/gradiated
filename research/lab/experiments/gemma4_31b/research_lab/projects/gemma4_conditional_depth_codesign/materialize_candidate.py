#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT / "inputs/upstream/gemma4_causal.py"
CANDIDATE = ROOT / "inputs/candidate/gemma4_causal.py"
EXPECTED_UPSTREAM_SHA256 = (
    "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989"
)

IMPORT_ANCHOR = (
    "from sglang.srt.model_executor.forward_batch_info import ForwardBatch, PPProxyTensors\n"
)
IMPORT_REPLACEMENT = (
    IMPORT_ANCHOR
    + "from conditional_depth_policy import active_layer_indices as "
    + "conditional_depth_active_layer_indices\n"
)
LOOP_ANCHOR = """        for layer_idx in range(self.start_layer, self.end_layer):
            if layer_idx in self.layers_to_capture:
                aux_hidden_states.append(hidden_states)

            if per_layer_inputs is not None:
"""
LOOP_REPLACEMENT = """        active_layer_indices = conditional_depth_active_layer_indices(forward_batch)
        for layer_idx in range(self.start_layer, self.end_layer):
            if layer_idx in self.layers_to_capture:
                aux_hidden_states.append(hidden_states)

            if layer_idx not in active_layer_indices:
                continue

            if per_layer_inputs is not None:
"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def materialize() -> dict[str, object]:
    upstream_bytes = UPSTREAM.read_bytes()
    upstream_sha256 = sha256_bytes(upstream_bytes)
    if upstream_sha256 != EXPECTED_UPSTREAM_SHA256:
        raise RuntimeError(
            f"upstream_binding_mismatch:{upstream_sha256}:{EXPECTED_UPSTREAM_SHA256}"
        )
    source = upstream_bytes.decode()
    if source.count(IMPORT_ANCHOR) != 1:
        raise RuntimeError("forward_batch_import_anchor_not_unique")
    if source.count(LOOP_ANCHOR) != 1:
        raise RuntimeError("gemma4_layer_loop_anchor_not_unique")
    candidate = source.replace(IMPORT_ANCHOR, IMPORT_REPLACEMENT).replace(
        LOOP_ANCHOR, LOOP_REPLACEMENT
    )
    ast.parse(candidate)
    skip_offset = candidate.index("if layer_idx not in active_layer_indices:")
    layer_load_offset = candidate.index("layer = self.layers[layer_idx]", skip_offset)
    layer_call_offset = candidate.index("layer_outputs = layer(", layer_load_offset)
    if not skip_offset < layer_load_offset < layer_call_offset:
        raise RuntimeError("conditional_depth_skip_does_not_dominate_layer_call")
    CANDIDATE.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(candidate)
    policy = ROOT / "conditional_depth_policy.py"
    return {
        "upstream_path": str(UPSTREAM.relative_to(ROOT)),
        "upstream_sha256": upstream_sha256,
        "candidate_path": str(CANDIDATE.relative_to(ROOT)),
        "candidate_sha256": sha256_bytes(candidate.encode()),
        "policy_path": str(policy.relative_to(ROOT)),
        "policy_sha256": sha256_bytes(policy.read_bytes()),
        "syntax_valid": True,
        "skip_dominates_layer_load_and_call": True,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(materialize(), indent=2, sort_keys=True))
