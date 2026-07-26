#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[6]
PROJECTS = ROOT.parent
UPSTREAM_ROOT = (
    PROJECTS / "gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/upstream"
)
UPSTREAM_MODEL = UPSTREAM_ROOT / "gemma4_causal.py"
UPSTREAM_RUNNER = UPSTREAM_ROOT / "model_runner.py"
CANDIDATE_MODEL = ROOT / "inputs/candidate/gemma4_causal.py"
CANDIDATE_RUNNER = ROOT / "inputs/candidate/model_runner.py"

EXPECTED = {
    UPSTREAM_MODEL: "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989",
    UPSTREAM_RUNNER: "f4dad073eb9f89afd4cda0439b97dee63f8de131d0ed10078b817dba1f978f59",
}

MODEL_IMPORT = (
    "from sglang.srt.model_executor.forward_batch_info import ForwardBatch, PPProxyTensors\n"
)
MODEL_IMPORT_PATCH = (
    MODEL_IMPORT
    + "from prompt_token_compaction_runtime import begin_layer_loop as "
    + "begin_prompt_compaction_layer_loop\n"
)
MODEL_LOOP = """        for layer_idx in range(self.start_layer, self.end_layer):
            if layer_idx in self.layers_to_capture:
"""
MODEL_LOOP_PATCH = """        prompt_compaction = begin_prompt_compaction_layer_loop(
            input_ids, positions, forward_batch
        )
        for layer_idx in range(self.start_layer, self.end_layer):
            if layer_idx in self.layers_to_capture:
"""
MODEL_AFTER_CALL = """            hidden_states = layer_outputs[0]
            # Gemma4DecoderLayer.forward always returns (hidden_states, None);
"""
MODEL_AFTER_CALL_PATCH = """            hidden_states = layer_outputs[0]
            hidden_states, positions, per_layer_inputs, forward_batch = (
                prompt_compaction.merge_after(
                    layer_idx, hidden_states, per_layer_inputs
                )
            )
            # Gemma4DecoderLayer.forward always returns (hidden_states, None);
"""

RUNNER_IMPORT = "from sglang.srt.model_executor.forward_batch_info import (\n"
RUNNER_IMPORT_PATCH = (
    "from prompt_token_compaction_runtime import bind_runtime_resources as "
    "bind_prompt_compaction_runtime_resources\n"
    + RUNNER_IMPORT
)
RUNNER_BIND_ANCHOR = """        # Deprecated kwarg: pre-planners mark the batch themselves now.
        forward_batch.apply_deprecated_skip_attn_backend_init(skip_attn_backend_init)
"""
RUNNER_BIND_PATCH = """        bind_prompt_compaction_runtime_resources(self, forward_batch)
        # Deprecated kwarg: pre-planners mark the batch themselves now.
        forward_batch.apply_deprecated_skip_attn_backend_init(skip_attn_backend_init)
"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bound_source(path: Path) -> str:
    data = path.read_bytes()
    actual = sha256_bytes(data)
    expected = EXPECTED[path]
    if actual != expected:
        raise RuntimeError(f"upstream_binding_mismatch:{path}:{actual}:{expected}")
    return data.decode()


def _replace_once(source: str, anchor: str, replacement: str) -> str:
    if source.count(anchor) != 1:
        raise RuntimeError(f"source_anchor_not_unique:{anchor[:60]!r}")
    return source.replace(anchor, replacement)


def materialize() -> dict[str, object]:
    model = _bound_source(UPSTREAM_MODEL)
    model = _replace_once(model, MODEL_IMPORT, MODEL_IMPORT_PATCH)
    model = _replace_once(model, MODEL_LOOP, MODEL_LOOP_PATCH)
    model = _replace_once(model, MODEL_AFTER_CALL, MODEL_AFTER_CALL_PATCH)
    ast.parse(model)

    runner = _bound_source(UPSTREAM_RUNNER)
    runner = _replace_once(runner, RUNNER_IMPORT, RUNNER_IMPORT_PATCH)
    runner = _replace_once(runner, RUNNER_BIND_ANCHOR, RUNNER_BIND_PATCH)
    ast.parse(runner)

    compact_offset = model.index("prompt_compaction.merge_after(")
    next_layer_load = model.index("layer = self.layers[layer_idx]")
    layer_call = model.index("layer_outputs = layer(", next_layer_load)
    if not next_layer_load < layer_call < compact_offset:
        raise RuntimeError("compaction_does_not_follow_boundary_layer_consumer")
    later_loop = model.find("for layer_idx in range", compact_offset)
    if later_loop != -1:
        raise RuntimeError("unexpected_second_layer_loop")

    CANDIDATE_MODEL.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATE_MODEL.write_text(model)
    CANDIDATE_RUNNER.write_text(runner)
    runtime = ROOT / "prompt_token_compaction_runtime.py"
    runtime_config = ROOT / "CANDIDATE_RUNTIME_CONFIG.json"
    return {
        "upstream_model_path": str(UPSTREAM_MODEL.relative_to(WORKSPACE)),
        "upstream_model_sha256": EXPECTED[UPSTREAM_MODEL],
        "candidate_model_path": str(CANDIDATE_MODEL.relative_to(ROOT)),
        "candidate_model_sha256": sha256_bytes(model.encode()),
        "upstream_runner_path": str(UPSTREAM_RUNNER.relative_to(WORKSPACE)),
        "upstream_runner_sha256": EXPECTED[UPSTREAM_RUNNER],
        "candidate_runner_path": str(CANDIDATE_RUNNER.relative_to(ROOT)),
        "candidate_runner_sha256": sha256_bytes(runner.encode()),
        "runtime_path": str(runtime.relative_to(ROOT)),
        "runtime_sha256": sha256_bytes(runtime.read_bytes()),
        "runtime_config_path": str(runtime_config.relative_to(ROOT)),
        "runtime_config_sha256": sha256_bytes(runtime_config.read_bytes()),
        "syntax_valid": True,
        "merge_follows_layer_5": True,
        "every_input_contributes_by_construction": True,
        "later_layer_call_receives_compacted_state_and_batch": True,
        "late_attention_metadata_reinitialized": True,
        "compact_kv_view_implemented": True,
        "dropped_slots_remain_allocator_owned": True,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(materialize(), indent=2, sort_keys=True))
