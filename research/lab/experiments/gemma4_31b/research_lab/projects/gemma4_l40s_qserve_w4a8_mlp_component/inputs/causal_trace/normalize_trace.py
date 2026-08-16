#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib


ROOT = pathlib.Path("/work/artifacts/qserve-causal-trace")


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def first_divergence(reference: list[int], candidate: list[int]) -> int | None:
    for index, (left, right) in enumerate(zip(reference, candidate)):
        if left != right:
            return index
    return None if len(reference) == len(candidate) else min(len(reference), len(candidate))


def main() -> int:
    trace = json.loads((ROOT / "TRACE_TERMINAL.json").read_text())
    baseline = trace["rows"][0]["output_ids"]
    target = None
    for row in trace["rows"][1:]:
        divergence = first_divergence(baseline, row["output_ids"])
        if divergence is not None:
            target = {
                "depth": int(row["depth"]),
                "layer": int(row["depth"]) - 1,
                "output_token_index": divergence,
                # The fixed 21-token prompt is one M<=32 forward step (step 0);
                # each emitted token then advances the observed step by one.
                "decode_step": divergence,
            }
            break
    if target is None:
        raise RuntimeError("trace has no decision-bearing divergence")
    normalized = dict(trace)
    normalized["first_divergent_target"] = target
    normalized["normalization"] = {
        "schema_version": 1,
        "source": "TRACE_TERMINAL.json",
        "reason": "fixed prompt has 21 tokens and therefore uses the resident M<=32 decode-class MLP route during scheduler prefill",
        "route_semantics": "step 0 is prompt prefill; output token index n is produced by observed forward step n",
        "producer_rows_replayed": False,
    }
    atomic(ROOT / "TRACE_TERMINAL_NORMALIZED.json", normalized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
