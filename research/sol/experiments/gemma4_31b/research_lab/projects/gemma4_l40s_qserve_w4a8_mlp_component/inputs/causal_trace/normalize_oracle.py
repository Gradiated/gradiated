#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib


ROOT = pathlib.Path("/work/artifacts/qserve-causal-trace")


def main() -> int:
    oracle_path = ROOT / "ORACLE_TERMINAL.json"
    oracle = json.loads(oracle_path.read_text())
    trace = json.loads((ROOT / "TRACE_TERMINAL_NORMALIZED.json").read_text())
    capture = oracle["capture"]
    target = trace["first_divergent_target"]
    if (
        int(capture["depth"]) != int(target["depth"])
        or int(capture["layer"]) != int(target["layer"])
        or int(capture["decode_step"]) != int(target["decode_step"])
    ):
        raise RuntimeError("oracle tensor does not match normalized target")
    oracle["target"] = target
    oracle["normalization"] = {
        "schema_version": 1,
        "metrics_recomputed": False,
        "reason": "replace stale prefill-offset target metadata with the normalized target already matched by the captured tensor",
    }
    temporary = oracle_path.with_suffix(".json.part")
    temporary.write_text(json.dumps(oracle, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, oracle_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
