#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

FRONTIER = 0.6518282820


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--results", type=pathlib.Path, required=True); parser.add_argument("--output", type=pathlib.Path, required=True); args = parser.parse_args()
    terminals = {arm: json.loads((args.results / f"{arm}-c32" / "TERMINAL.json").read_text()) for arm in ("ar", "dflash")}
    rows = {arm: [json.loads(path.read_text()) for path in sorted((args.results / f"{arm}-c32").glob("request-*.json"))] for arm in terminals}
    token_equal = len(rows["ar"]) == len(rows["dflash"]) == 32 and all(a["token_ids"] == b["token_ids"] and len(a["token_ids"]) == 358 for a, b in zip(rows["ar"], rows["dflash"]))
    dflash = terminals["dflash"]
    value = {"schema_version": 1, "status": "terminal", "classification": "endpoint_positive" if dflash["pass"] and token_equal else "quality_or_integration_reject", "control": terminals["ar"], "candidate": dflash, "greedy_token_equality": token_equal, "candidate_beats_same_runtime_control": dflash["service_seconds_per_request"] < terminals["ar"]["service_seconds_per_request"], "candidate_beats_lab_frontier": dflash["service_seconds_per_request"] < FRONTIER, "frontier_seconds_per_request": FRONTIER}
    temporary = args.output.with_suffix(".part"); temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n"); temporary.replace(args.output)
    return 0 if value["classification"] == "endpoint_positive" else 72


if __name__ == "__main__": raise SystemExit(main())
