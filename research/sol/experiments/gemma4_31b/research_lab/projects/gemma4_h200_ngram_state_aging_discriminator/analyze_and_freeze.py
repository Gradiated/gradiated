#!/usr/bin/env python3
"""Hash-check the director binding, localize the stock transition, and freeze one arm."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import statistics


PROJECT = Path(__file__).resolve().parent
CONTROL = PROJECT / "inputs/control"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def metric(path: Path, name: str) -> float | None:
    for line in path.read_text().splitlines():
        if line.startswith(name + "{") or line.startswith(name + " "):
            return float(line.rsplit(" ", 1)[1])
    return None


def main() -> None:
    binding = json.loads((PROJECT / "DIRECTOR_BINDING.json").read_text())
    mapping = {
        "qualified_binding": CONTROL / "EVIDENCE_BINDING.json",
        "immutable_consumer": CONTROL / "IMMUTABLE_CONSUMER_v2.json",
        "sustainable_terminal": CONTROL / "FINAL_TERMINAL.json",
        "request_rows": CONTROL / "requests.jsonl",
        "final_metrics": CONTROL / "metrics-after.prom",
        "ngram_worker_source": PROJECT / "inputs/source/ngram_worker.py",
        "ngram_verify_source": PROJECT / "inputs/source/ngram_info.py",
    }
    hash_rows = {}
    for key, path in mapping.items():
        actual = digest(path)
        expected = binding["authoritative_inputs"][key]["sha256"]
        hash_rows[key] = {
            "project_local_path": str(path.relative_to(PROJECT)),
            "expected_sha256": expected,
            "actual_sha256": actual,
            "match": actual == expected,
        }
    if not all(row["match"] for row in hash_rows.values()):
        raise RuntimeError("director_binding_hash_mismatch")

    rows = [
        json.loads(line) for line in (CONTROL / "requests.jsonl").read_text().splitlines()
    ]
    windows = []
    for lower in range(0, len(rows), 100):
        group = rows[lower : lower + 100]
        latency = [row["timing"]["latency_seconds"] for row in group]
        queue = [row["client_started_s"] - row["scheduled_s"] for row in group]
        windows.append(
            {
                "begin": lower,
                "end_exclusive": lower + len(group),
                "latency_mean_seconds": statistics.mean(latency),
                "latency_median_seconds": statistics.median(latency),
                "latency_max_seconds": max(latency),
                "client_queue_mean_seconds": statistics.mean(queue),
                "client_queue_max_seconds": max(queue),
            }
        )

    power = [
        json.loads(line) for line in (CONTROL / "power.jsonl").read_text().splitlines()
    ]
    first_wall = power[0]["t"]
    parsed_power = []
    for row in power:
        pieces = [part.strip() for part in row["smi"].split(",")]
        parsed_power.append(
            {
                "elapsed_seconds": row["t"] - first_wall,
                "gpu_utilization_percent": float(pieces[1]),
                "power_watts": float(pieces[2]),
                "hbm_mib": int(pieces[3]),
            }
        )
    initial_hbm = parsed_power[0]["hbm_mib"]
    hbm_steps = []
    prior = initial_hbm
    for row in parsed_power:
        if row["hbm_mib"] != prior:
            if abs(row["hbm_mib"] - prior) >= 128:
                hbm_steps.append(
                    {
                        "elapsed_seconds": row["elapsed_seconds"],
                        "from_mib": prior,
                        "to_mib": row["hbm_mib"],
                        "approx_scheduled_request_index": int(
                            row["elapsed_seconds"]
                            * binding["measured_control"][
                                "arrival_rate_requests_per_second"
                            ]
                        ),
                    }
                )
            prior = row["hbm_mib"]

    before = CONTROL / "metrics-before-primary.prom"
    after = CONTROL / "metrics-after.prom"
    metrics = {}
    for name in [
        "sglang:max_total_num_tokens",
        "sglang:kv_available_tokens",
        "sglang:kv_evictable_tokens",
        "sglang:kv_used_tokens",
        "sglang:swa_available_tokens",
        "sglang:swa_evictable_tokens",
        "sglang:swa_used_tokens",
        "sglang:cached_tokens_total",
        "sglang:evicted_tokens_total",
        "sglang:eviction_duration_seconds_count",
        "sglang:eviction_duration_seconds_sum",
        "sglang:num_queue_reqs",
        "sglang:spec_accept_length",
        "sglang:spec_accept_rate",
    ]:
        metrics[name] = {
            "before": metric(before, name),
            "after": metric(after, name),
        }

    localization = {
        "kind": "persisted_stock_transition_localization",
        "evidence_labels": {
            "request_windows": "measured",
            "power_hbm": "measured",
            "final_cache_metrics": "measured",
            "ngram_mechanism": "source-backed",
            "causal_attribution_before_candidate": "unresolved",
        },
        "binding_hashes": hash_rows,
        "request_windows": windows,
        "hbm": {
            "initial_mib": initial_hbm,
            "final_mib": parsed_power[-1]["hbm_mib"],
            "growth_mib": parsed_power[-1]["hbm_mib"] - initial_hbm,
            "large_steps": hbm_steps,
        },
        "cache_metrics": metrics,
        "source_localization": {
            "ngram": (
                "NGRAMWorker retains one process-global NgramCorpus; every verify "
                "enqueues an 18-token-tail batch_put and the next prepare synchronizes "
                "the asynchronous insert worker before batch_get. Trie construction "
                "preallocates all 10,000,000 TrieNode objects; only reset clears online "
                "trie and match state."
            ),
            "competing_cache": (
                "The GPU HBM step cannot be the CPU online-trie allocation itself. "
                "The final SWA pool had only 982 free tokens while 4,820,278 SWA "
                "tokens had been evicted; final full-KV availability was 5,852. "
                "Per-time corpus operations and simultaneous cache occupancy are "
                "therefore required to separate corpus saturation from SWA/KV churn."
            ),
        },
    }
    atomic(PROJECT / "CONTROL_LOCALIZATION.json", localization)

    source_files = sorted(
        path
        for path in (PROJECT / "intervention").iterdir()
        if path.is_file()
    )
    candidate = {
        "schema_version": 1,
        "kind": "frozen_single_ngram_corpus_lifetime_candidate",
        "decision": {
            "rollover_after_distinct_primary_requests": 650,
            "derivation": (
                "Reset 50 admissions before the persisted stable-through-700 boundary, "
                "leaving 386 requests to test immediate and durable recovery."
            ),
            "operation": "NgramCorpus.reset() once at the first batch reaching the bound",
            "prefix_swa_kv_cache_operation_at_boundary": "none",
            "semantics": "target-verified, intended semantics-preserving",
        },
        "workload": {
            "scheduled_requests": 1036,
            "arrival_spacing_seconds": 0.6946101132986054,
            "max_workers": 32,
            "prompt_tokens": 4214,
            "completion_tokens": 358,
            "request_bytes_source": "inputs/control/TRACE_PACKET.json",
            "stock_comparator": "inputs/control/requests.jsonl",
        },
        "instrumentation": {
            "corpus": [
                "synchronize time",
                "batch_get time",
                "batch_put enqueue time",
                "online trie used/capacity",
                "native and Python match-state counts",
                "pending inserts",
            ],
            "runtime": [
                "target verify time",
                "total NGRAM forward time",
                "SWA/KV occupancy and eviction",
                "HBM/utilization/power",
                "server/client queue",
                "per-100-request latency",
            ],
        },
        "files": {
            str(path.relative_to(PROJECT)): {
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
            for path in source_files
        }
        | {
            "remote_candidate.py": {
                "bytes": (PROJECT / "remote_candidate.py").stat().st_size,
                "sha256": digest(PROJECT / "remote_candidate.py"),
            }
        },
    }
    atomic(PROJECT / "CANDIDATE_PACKET.json", candidate)


if __name__ == "__main__":
    main()
