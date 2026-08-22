#!/usr/bin/env python3
"""Validate the complete AR/DFLASH/NGRAM ledger and publish one typed terminal."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import statistics
from collections import Counter
from typing import Any

RATE_USD_PER_HOUR = 2.45
EXPECTED_REQUESTS = 32
EXPECTED_PROMPT_TOKENS = 4214
EXPECTED_OUTPUT_TOKENS = 358
BLOCK_SIZE = 16


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a JSON object")
    return value


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def observer_rows(root: pathlib.Path, arm: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((root / arm / "observer").glob("observer-*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("arm") == arm:
                    rows.append(row)
    return rows


def arm_terminal(root: pathlib.Path, arm: str) -> dict[str, Any]:
    return load(root / arm / "results" / "TERMINAL.json")


def validate_runner_terminal(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if value.get("complete_requests") != EXPECTED_REQUESTS:
        errors.append("complete_request_count")
    rows = value.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_REQUESTS:
        return [*errors, "request_row_ledger"]
    for row in rows:
        if row.get("error") is not None:
            errors.append(f"request_{row.get('index')}_error")
        if row.get("prompt_tokens") != EXPECTED_PROMPT_TOKENS:
            errors.append(f"request_{row.get('index')}_prompt_tokens")
        if row.get("completion_tokens") != EXPECTED_OUTPUT_TOKENS:
            errors.append(f"request_{row.get('index')}_completion_tokens")
        if len(row.get("output_token_ids") or []) != EXPECTED_OUTPUT_TOKENS:
            errors.append(f"request_{row.get('index')}_output_token_ids")
    return errors


def unique_rounds(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_round: dict[int, dict[str, Any]] = {}
    for row in rows:
        key = int(row["round_index"])
        if key in by_round:
            if (
                by_round[key]["cuda_intervals_ms"] != row["cuda_intervals_ms"]
                or by_round[key]["cuda_interval_union_ms"]
                != row["cuda_interval_union_ms"]
            ):
                raise ValueError(f"round {key} timing differs across request rows")
        else:
            by_round[key] = row
    return [by_round[key] for key in sorted(by_round)]


def summarize_arm(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rounds = unique_rounds(rows)
    accepted = [int(row["accepted_drafts"]) for row in rows]
    commit_tokens = sum(int(row["commit_len"]) for row in rows)
    cuda_seconds = sum(float(row["cuda_interval_union_ms"]) for row in rounds) / 1000
    host_seconds = sum(float(row["host_outer_seconds"]) for row in rounds)
    phases = Counter(
        interval["phase"]
        for row in rounds
        for interval in row["cuda_intervals_ms"]
    )
    return {
        "row_count": len(rows),
        "round_count": len(rounds),
        "accepted_draft_histogram": dict(sorted(Counter(accepted).items())),
        "mean_accepted_drafts": statistics.mean(accepted) if accepted else None,
        "committed_target_tokens": commit_tokens,
        "cuda_interval_union_seconds": cuda_seconds,
        "host_component_seconds": host_seconds,
        "accepted_target_tokens_per_cuda_union_second": (
            commit_tokens / cuda_seconds if cuda_seconds > 0 else None
        ),
        "accepted_target_tokens_per_host_component_second": (
            commit_tokens / host_seconds if host_seconds > 0 else None
        ),
        "component_cost_usd_per_million_target_tokens": (
            host_seconds
            * RATE_USD_PER_HOUR
            / 3600
            / commit_tokens
            * 1_000_000
            if host_seconds > 0 and commit_tokens > 0
            else None
        ),
        "phase_interval_counts": dict(sorted(phases.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--terminal", type=pathlib.Path, required=True)
    parser.add_argument("--generation", required=True)
    args = parser.parse_args()
    root = args.root
    arms = ("ar", "dflash", "ngram")
    terminals = {arm: arm_terminal(root, arm) for arm in arms}
    errors = {
        arm: validate_runner_terminal(terminals[arm]) for arm in arms
    }
    markers = {}
    for arm in arms:
        marker = root / f"{arm}.SCIENCE_STARTED.json"
        markers[arm] = {
            "path": str(marker),
            "present": marker.is_file(),
            "sha256": sha256(marker) if marker.is_file() else None,
        }
        if not marker.is_file():
            errors[arm].append("science_started_marker")
        diagnostic = root / arm / "observer" / "OBSERVER_DIAGNOSTIC.json"
        if diagnostic.exists():
            errors[arm].append("observer_diagnostic")

    request_hashes = {
        arm: terminals[arm]["workload"]["request_sha256"] for arm in arms
    }
    matched_requests = request_hashes["ar"] == request_hashes["dflash"] == request_hashes["ngram"]
    if not matched_requests:
        errors["dflash"].append("request_identity_mismatch")

    token_ids = {
        arm: [row["output_token_ids"] for row in terminals[arm]["rows"]]
        for arm in arms
    }
    greedy_token_exact = token_ids["ar"] == token_ids["dflash"] == token_ids["ngram"]

    rows = {arm: observer_rows(root, arm) for arm in arms}
    for arm in arms:
        if not rows[arm]:
            errors[arm].append("observer_rows_missing")
    summaries = {
        arm: summarize_arm(rows[arm]) if rows[arm] else None for arm in arms
    }

    mapping_pass = bool(rows["dflash"]) and all(
        row.get("logical_request_id_source") == "ForwardBatch.rids[row]"
        and row.get("physical_request_pool_index_source")
        == "ForwardBatch.req_pool_indices[row]"
        and row.get("kv_table_source")
        == "target_worker.model_runner.req_to_token_pool.req_to_token"
        and row.get("block_size_including_current") == BLOCK_SIZE
        for row in rows["dflash"]
    )
    if not mapping_pass:
        errors["dflash"].append("request_pool_ownership_mapping")

    category_audits = {"zero": False, "partial": False, "full": False}
    next_round_failures = []
    for row in rows["dflash"]:
        audit = row.get("next_round_audit")
        if audit is None:
            continue
        category = audit.get("prior_acceptance_category")
        passed = bool(
            audit.get("pending_bonus_is_current")
            and audit.get("committed_length_continuity")
            and audit.get("kv_prefix_stable")
        )
        if category in category_audits and passed:
            category_audits[category] = True
        if not passed:
            next_round_failures.append(
                {
                    "round_index": row["round_index"],
                    "row_index": row["row_index"],
                    "logical_request_id": row["logical_request_id"],
                    "audit": audit,
                }
            )
    if not all(category_audits.values()):
        errors["dflash"].append("zero_partial_full_next_round_audit_coverage")
    phase_requirements = {
        "ar": {"target_decode"},
        "dflash": {"draft", "target_verify", "acceptance", "kv_commit"},
        "ngram": {"ngram_proposal", "target_verify", "acceptance", "kv_commit"},
    }
    for arm in arms:
        present = (
            set(summaries[arm]["phase_interval_counts"]) if summaries[arm] else set()
        )
        if not phase_requirements[arm].issubset(present):
            errors[arm].append("cuda_phase_ledger_incomplete")

    rates = {
        arm: (
            summaries[arm]["accepted_target_tokens_per_host_component_second"]
            if summaries[arm]
            else None
        )
        for arm in arms
    }
    semantic_pass = (
        greedy_token_exact
        and mapping_pass
        and all(category_audits.values())
        and not next_round_failures
    )
    evidence_complete = not any(errors.values())
    dflash_beats_both = bool(
        all(rate is not None and math.isfinite(rate) and rate > 0 for rate in rates.values())
        and rates["dflash"] > rates["ar"]
        and rates["dflash"] > rates["ngram"]
    )
    best_control = max(rates["ar"] or 0.0, rates["ngram"] or 0.0)
    margin = (
        rates["dflash"] / best_control - 1
        if rates["dflash"] is not None and best_control > 0
        else None
    )
    plausible_20pct_endpoint_reduction = bool(
        semantic_pass and dflash_beats_both and margin is not None and margin >= 0.25
    )
    if not evidence_complete:
        classification = "recoverable_incomplete_component_evidence"
    elif not semantic_pass:
        classification = "scientific_negative_target_or_kv_semantics"
    elif dflash_beats_both and plausible_20pct_endpoint_reduction:
        classification = "component_positive_endpoint_promotion_eligible"
    elif dflash_beats_both:
        classification = "small_positive_stackable_component_evidence"
    else:
        classification = "scientific_negative_component_economics"

    terminal = {
        "schema_version": 1,
        "classification": classification,
        "generation": args.generation,
        "science_consumed": {
            arm: bool(markers[arm]["present"]) for arm in arms
        },
        "historical_request_25": {
            "artifact_sha256": "dfca865f1e4c66b1698c92921d65dec3999c351aa83be64d9987a264d61bf711",
            "replayed": False,
            "used_as_evidence": False,
            "disposition": "consumed_uninterpretable_excluded",
        },
        "workload": {
            "requests": EXPECTED_REQUESTS,
            "prompt_tokens_per_request": EXPECTED_PROMPT_TOKENS,
            "output_tokens_per_request": EXPECTED_OUTPUT_TOKENS,
            "temperature": 0,
            "seed": 20260718,
            "matched_request_hashes": matched_requests,
        },
        "correctness": {
            "greedy_output_token_exact_across_ar_dflash_ngram": greedy_token_exact,
            "request_pool_ownership_mapping_pass": mapping_pass,
            "next_round_audit_category_coverage": category_audits,
            "next_round_failures": next_round_failures,
            "semantic_pass": semantic_pass,
        },
        "component": summaries,
        "economics": {
            "hourly_rate_usd": RATE_USD_PER_HOUR,
            "decision_metric": "accepted_target_tokens_per_host_component_second",
            "rates": rates,
            "dflash_beats_ar_and_ngram": dflash_beats_both,
            "dflash_margin_over_best_control": margin,
            "plausible_20pct_endpoint_reduction": plausible_20pct_endpoint_reduction,
            "endpoint_claim_made": False,
        },
        "errors": errors,
        "evidence_complete": evidence_complete,
        "markers": markers,
        "raw_terminals": {
            arm: str(root / arm / "results" / "TERMINAL.json") for arm in arms
        },
    }
    atomic(args.terminal, terminal)
    if classification == "recoverable_incomplete_component_evidence":
        return 75
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
