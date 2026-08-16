#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path


here = Path(__file__).resolve().parent
binding = json.loads((here / "DIRECT_MODEL_SUPERGRAPH_BINDING.json").read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


for key in (
    "cuda_graph_runner",
    "model_runner",
    "triton_backend",
):
    path = here / binding["source_binding"][f"{key}_path"]
    expected = binding["source_binding"][f"{key}_sha256"]
    actual = sha256(path)
    if actual != expected:
        raise SystemExit(f"direct-model source mismatch:{path}:{actual}")

for arm in binding["closed_arms"].values():
    path = here / arm["path"]
    actual = sha256(path)
    if actual != arm["sha256"]:
        raise SystemExit(f"closed-arm mismatch:{path}:{actual}")

source = (here / "static_c32_direct_model_sitecustomize.py").read_text()
tree = ast.parse(source)
if "runner.graphs" in source or ".graphs[EXPECTED_CONCURRENCY]" in source:
    raise SystemExit("forbidden child CUDAGraph access in direct-model source")
calls = [
    node
    for node in ast.walk(tree)
    if isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and node.func.attr == "forward"
]
if not any(
    isinstance(call.func.value, ast.Attribute)
    and call.func.value.attr == "model"
    for call in calls
):
    raise SystemExit("raw model.forward call missing")
if binding["candidate"]["block_geometry"] != [7, 8, 6]:
    raise SystemExit("direct-model geometry mismatch")
print(
    json.dumps(
        {
            "binding": "valid",
            "topology": "direct_raw_model_forward_parent_graph",
            "block_geometry": [7, 8, 6],
            "child_graph_access": False,
        }
    )
)
