#!/usr/bin/env python3
"""Fail-closed patch for the exact vLLM 0.15.0 GLM model source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_SOURCE_SHA256 = "6a984f701d46dfa05389a45d7aedde6a10ef45a6f59e73d3bbfa1e82f556b4a9"
TARGET = "vllm/model_executor/models/glm4_moe_lite.py"
NEEDLE = "        for layer in islice(self.layers, self.start_layer, self.end_layer):\n            hidden_states, residual = layer(positions, hidden_states, residual)"
REPLACEMENT = """        stop_layer = self.end_layer
        exit_mode = os.environ.get(\"VLLM_EXIT35_MODE\", \"0\") == \"1\"
        if exit_mode:
            if input_ids is None:
                raise RuntimeError(\"exit35 requires input_ids for phase detection\")
            threshold = int(os.environ.get(\"VLLM_EXIT35_PREFILL_THRESHOLD\", \"64\"))
            is_decode = input_ids.numel() <= threshold
            if not is_decode and input_ids.numel() <= 0:
                raise RuntimeError(\"exit35 rejected empty phase metadata\")
            if is_decode:
                stop_layer = min(self.end_layer, self.start_layer + 35)
        for layer in islice(self.layers, self.start_layer, stop_layer):
            hidden_states, residual = layer(positions, hidden_states, residual)"""


def patch(source: Path, evidence: Path) -> None:
    before = source.read_bytes()
    before_hash = hashlib.sha256(before).hexdigest()
    if before_hash != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(f"unexpected vLLM source hash: {before_hash}")
    text = before.decode()
    if text.count(NEEDLE) != 1:
        raise RuntimeError("expected exactly one GLM layer loop")
    if "import os\n" not in text:
        text = text.replace("import typing\n", "import os\nimport typing\n", 1)
    output = text.replace(NEEDLE, REPLACEMENT, 1).encode()
    source.write_bytes(output)
    evidence.write_text(json.dumps({
        "target": TARGET,
        "source_sha256_before": before_hash,
        "source_sha256_after": hashlib.sha256(output).hexdigest(),
        "changed_occurrences": 1,
        "exit_depth": 35,
        "phase_rule": "VLLM_EXIT35_MODE=1 and input_ids.numel() <= VLLM_EXIT35_PREFILL_THRESHOLD",
        "prefill_rule": "full self.end_layer execution",
        "mixed_batch_policy": "not representable by one scalar input_ids count; caller must reject mixed phases",
    }, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    patch(args.source, args.evidence)


if __name__ == "__main__":
    main()
