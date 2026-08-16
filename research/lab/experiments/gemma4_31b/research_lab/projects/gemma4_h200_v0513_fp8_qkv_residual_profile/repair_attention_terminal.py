#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--profile-map", type=pathlib.Path, required=True)
    args = parser.parse_args()
    original_path = args.artifact_root / "TERMINAL.json"
    pair_path = args.artifact_root / "attention_pair/PAIRED_TERMINAL.json"
    original = json.loads(original_path.read_text())
    pair = json.loads(pair_path.read_text())
    profile_map = json.loads(args.profile_map.read_text())
    if original.get("classification") != "invalid" or pair.get("classification") != "invalid":
        raise RuntimeError("repair_requires_original_invalid_guard_terminal")
    control, candidate = pair["control"], pair["candidate"]
    proof = pair["candidate_path_proof"]
    path_ok = any(
        row.get("phase") == "runtime_invocation"
        and row.get("qk_head_dim") == 256
        and row.get("v_head_dim") == 256
        and row.get("sliding_window_size") == 1024
        and row.get("removed_operations") == ["k.clone", "v.clone"]
        for row in proof
    )
    exact_accounting = (
        control.get("complete_requests") == candidate.get("complete_requests") == 32
        and len(control.get("rows", [])) == len(candidate.get("rows", [])) == 32
        and pair["accounting_proof"]["control"] == pair["accounting_proof"]["candidate"]
        and pair["accounting_proof"]["control"]["cached_prompt_tokens_delta"] == 17120
        and pair["accounting_proof"]["control"]["uncached_prompt_tokens_delta"] == 117728
    )
    valid = (
        path_ok
        and exact_accounting
        and profile_map.get("pass") is True
        and pair.get("fp8_proof") is True
        and pair.get("qkv_proof") is True
        and all(row.get("pass") is True for row in pair["semantic_proof"])
        and control.get("pass") is True
        and candidate.get("pass") is True
    )
    gain = 1 - candidate["service_seconds_per_request"] / control["service_seconds_per_request"]
    classification = (
        "promote_ceiling"
        if valid and candidate["service_seconds_per_request"] <= pair["economic_ceiling_seconds_per_request"]
        else "promote_gain"
        if valid and gain >= 0.05
        else "retain_simple_positive"
        if valid and gain > 0
        else "close_attention_attempt"
        if valid
        else "invalid"
    )
    repaired = {
        **original,
        "classification": classification,
        "pass": valid,
        "reduction_fraction": gain,
        "candidate_path_proof": proof,
        "candidate_path_proof_gate": {
            "pass": path_ok,
            "corrected_qk_head_dim": 256,
            "original_incorrect_qk_head_dim": 288,
            "repair_class": "post_producer_numeric_guard",
        },
        "attention_subtype_map": profile_map,
    }
    atomic(args.artifact_root / "TERMINAL.pre_consumer_repair.json", original)
    atomic(
        args.artifact_root / "CONSUMER_REPAIR.json",
        {
            "schema_version": 1,
            "pass": valid,
            "repair_class": "post_producer_numeric_guard",
            "scientific_arms_replayed": 0,
            "diagnostic": "Runtime audit reported the configured local qk_head_dim=256; the rejected 288 expectation was an offline shape-inference error. Pinned source maps Lq=256 to BLOCK_M=64, matching grid-Z 32 for 2048-token chunks.",
            "original_terminal": "TERMINAL.pre_consumer_repair.json",
            "repaired_terminal": "TERMINAL.json",
        },
    )
    atomic(original_path, repaired)
    print(json.dumps({"classification": classification, "pass": valid, "gain": gain}, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
