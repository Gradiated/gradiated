#!/usr/bin/env python3
"""Bound cache eligibility without a provider allocation."""

import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
PLAN = PROJECT / "artifacts" / "agent_prefix_c8_v2_tenant_isolated.plan.json"
V21_SUMMARY = (
    PROJECT.parents[2]
    / "campaign_100"
    / "allocations"
    / "nebius_l40s_vllm_awq_prefill65k_v21"
    / "summary.json"
)
BLOCK_TOKENS = 16


def metric_percentile(metric, key):
    for row in json.loads(V21_SUMMARY.read_text())["allocation_result"]["performance"]["profiles"]:
        if row["concurrency"] == 8:
            return row[metric][key]
    raise ValueError("V21 c8 profile is missing")


def build_bound():
    plan = json.loads(PLAN.read_text())
    requests = plan["requests"]
    sessions = {}
    for row in requests:
        sessions.setdefault(row["session_index"], []).append(row)
    for rows in sessions.values():
        rows.sort(key=lambda row: row["scheduled_offset_ms"])

    input_tokens = sum(row["expected_input_tokens"] for row in requests)
    reusable_tokens = BLOCK_TOKENS * 11
    potential_reuse_requests = sum(max(0, len(rows) - 1) for rows in sessions.values())
    minimum_hits_for_five_percent = int(input_tokens * 0.05 // reusable_tokens) + 1

    latencies = {
        "optimistic_zero_intercept_scaled_c1": 580.348089 * 183 / 8192,
        "v21_c1_observed": 580.348089,
        "v21_c8_p50_observed": metric_percentile("ttft_ms", "p50"),
        "v21_c8_p95_observed": metric_percentile("ttft_ms", "p95"),
        "v21_c8_p95_scheduler_step_proxy": metric_percentile("tpot_ms", "p95"),
    }
    cases = []
    for name, latency_ms in latencies.items():
        hits = 0
        for rows in sessions.values():
            for predecessor, successor in zip(rows, rows[1:]):
                if predecessor["scheduled_offset_ms"] + latency_ms <= successor["scheduled_offset_ms"]:
                    hits += 1
        cases.append(
            {
                "case": name,
                "assumption": "cache insertion occurs at predecessor scheduler-step completion",
                "latency_ms": latency_ms,
                "eligible_reuse_requests": hits,
                "eligible_reused_tokens": hits * reusable_tokens,
                "eligible_reused_input_share": hits * reusable_tokens / input_tokens,
                "clears_five_percent_input_target": hits >= minimum_hits_for_five_percent,
            }
        )

    return {
        "schema_version": 1,
        "evidence_class": "derived simulation from frozen schedule and measured V21 telemetry",
        "question": "Can the frozen 100 ms within-session gaps make enough exact prefixes cache-eligible to clear the 5% target?",
        "inputs": {
            "plan_sha256": __import__("hashlib").sha256(PLAN.read_bytes()).hexdigest(),
            "v21_summary": str(V21_SUMMARY),
            "session_count": len(sessions),
            "requests": len(requests),
            "within_session_gap_ms": 100,
            "input_tokens": input_tokens,
            "full_cache_block_tokens": BLOCK_TOKENS,
            "reusable_tokens_per_hit": reusable_tokens,
            "potential_reuse_requests": potential_reuse_requests,
            "potential_reused_input_share": potential_reuse_requests * reusable_tokens / input_tokens,
            "minimum_hits_for_five_percent": minimum_hits_for_five_percent,
        },
        "cases": cases,
        "source_audit": {
            "runtime": "vllm-0.15.0",
            "source_commit": "f176443446f659dbab5315e056e605d8984fd976",
            "source_files": {
                "vllm/v1/core/kv_cache_manager.py": {
                    "sha256": "770f754b33b5ecef9e403ac41baea34b18100e45a0d24f69859d006b04e1470e",
                    "lines": "164-204,360-376,475-484",
                    "finding": "cache lookup is scheduler-visible and full blocks are committed by allocate_slots; cache hits cap at prompt_length minus one",
                },
                "vllm/v1/core/sched/scheduler.py": {
                    "sha256": "96f7360982899fffdbd627f51e3daf8afbe7a79fad5dc17d6dc0eb093aa516a0",
                    "lines": "710-719,1913-1924",
                    "finding": "scheduler allocates and commits cache blocks before the next scheduler iteration",
                },
                "vllm/v1/request.py": {
                    "sha256": "1adfbf02cf4d5e5783504dba4fbdbbd0b35dc32a7be4e27c048c16ccc7eb0a9f",
                    "lines": "160-164,208-209",
                    "finding": "block hashes are initialized and extended as tokens are appended",
                },
            },
            "interpretation": "V21 TTFT is not the cache-availability latency; V21 TPOT p95 is a measured scheduler-step proxy, not a direct V2 measurement",
        },
        "decision_rule": "kill paid smoke if no latency case supported by scope-matched evidence reaches two eligible hits; preserve only if timing-feasible reuse is material and later measured.",
    }


def main():
    output = PROJECT / "artifacts" / "ARRIVAL_CACHE_AVAILABILITY_BOUND.json"
    output.write_text(json.dumps(build_bound(), indent=2, sort_keys=True) + "\n")
    print(output)


if __name__ == "__main__":
    main()
