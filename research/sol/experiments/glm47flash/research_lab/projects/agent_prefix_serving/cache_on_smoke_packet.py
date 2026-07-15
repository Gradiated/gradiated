#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

from v2_replay_contract import PROJECT, SERVED_MODEL, build_v2_plan, canonical, validate_v2_plan


METRICS = ("prefix_cache_queries_total", "prefix_cache_hits_total")


def metric_totals(text):
    totals = {name: 0.0 for name in METRICS}
    for line in text.splitlines():
        if not line or line.startswith("#") or " " not in line:
            continue
        name, raw = line.rsplit(" ", 1)
        base = name.split("{", 1)[0]
        for metric in METRICS:
            if base.endswith(metric):
                try:
                    totals[metric] += float(raw)
                except ValueError:
                    pass
    return totals


def evaluate_smoke(before, after, outcomes):
    deltas = {metric: after[metric] - before[metric] for metric in METRICS}
    failures = []
    if not outcomes or any(row.get("status") != "success" for row in outcomes):
        failures.append("request_success")
    if deltas["prefix_cache_queries_total"] <= 0:
        failures.append("prefix_cache_queries_total_delta")
    if deltas["prefix_cache_hits_total"] <= 0:
        failures.append("prefix_cache_hits_total_delta")
    cached = []
    for row in outcomes:
        usage = row.get("usage")
        details = usage.get("prompt_tokens_details") if isinstance(usage, dict) else None
        value = details.get("cached_tokens") if isinstance(details, dict) else None
        if not isinstance(value, int) or value < 0:
            failures.append("prompt_tokens_details.cached_tokens")
            continue
        cached.append(value)
    if not cached or sum(cached) <= 0:
        failures.append("nonzero_per_request_cached_tokens")
    return {
        "pass": not failures,
        "failures": sorted(set(failures)),
        "metrics_before": before,
        "metrics_after": after,
        "metrics_delta": deltas,
        "cached_prompt_tokens": sum(cached),
        "cached_prompt_tokens_per_request": cached,
    }


def packet():
    plan = validate_v2_plan(build_v2_plan())
    v21_command = (
        "vllm serve /workspace/model-awq --tokenizer /input/tokenizer "
        f"--served-model-name {SERVED_MODEL} --host 127.0.0.1 --port 30000 "
        "--max-model-len 32768 --max-num-seqs 8 --max-num-batched-tokens 65536 "
        "--gpu-memory-utilization 0.90 --enable-prefix-caching --enable-prompt-tokens-details "
        "--quantization compressed-tensors --dtype bfloat16 --generation-config vllm "
        "--enable-auto-tool-choice --tool-call-parser glm47 --reasoning-parser glm45 --seed 1234"
    )
    return {
        "schema_version": 1,
        "experiment_id": "glm47-agent-prefix-v2-cache-on-smoke",
        "question": "Does the tenant-isolated V2 replay yield observed same-session prefix reuse on the V21 AWQ/vLLM/L40S stack?",
        "hypothesis": "Per-session cache salts permit reuse only within each three-turn session, producing nonzero vLLM cache counters and cached prompt-token details without changing request semantics.",
        "v2_plan_sha256": hashlib.sha256(canonical(plan)).hexdigest(),
        "v2_bundle_sha256": plan["v2_bundle_sha256"],
        "controls": {
            "model": "/workspace/model-awq",
            "served_model_name": SERVED_MODEL,
            "tokenizer": "/input/tokenizer",
            "checkpoint_revision": "75fce70",
            "runtime": "vLLM 0.15.0",
            "hardware": "NVIDIA L40S",
            "max_num_batched_tokens": 65536,
            "max_num_seqs": 8,
            "generation": plan["generation"],
        },
        "changed_variables": ["enable_prefix_caching", "enable_prompt_tokens_details", "per-session cache_salt"],
        "server_command": v21_command,
        "measurement": {
            "runner": "v2_cache_smoke_runner.py --base-url <server> --output <artifact-directory>; the runner performs exactly two cache-reset repetitions and fails closed",
            "warmup": "execute V2 plan's three warmup requests, then POST /flush_cache and record a successful reset before measured requests",
            "measured": "execute all 24 V2 requests at the immutable session-relative offsets; capture raw payload SHA-256, raw SSE SHA-256, final usage, and cache_salt per request",
            "metrics": "save raw /metrics before and after measured replay; parse aggregate prefix_cache_queries_total and prefix_cache_hits_total deltas",
            "required_usage_field": "usage.prompt_tokens_details.cached_tokens",
        },
        "acceptance": {
            "cache_observability": "strictly positive aggregate query and hit deltas plus strictly positive sum of per-request cached_tokens",
            "tenant_safety": "every measured row retains its V2 session-index-derived cache salt; no salt may be shared by two sessions",
            "service": "all 24 requests succeed without truncation; TTFT p95 <= 10000 ms and ITL p95 <= 100 ms",
            "semantic": "same deterministic output-digest sequence on a repeated cache-on smoke before any cache-off/on comparison",
        },
        "typed_failure_or_partial_artifact": {
            "missing_usage_cache_detail": "telemetry_unobservable; do not infer reused tokens from latency or aggregate counters",
            "missing_or_zero_cache_counter": "cache_mechanism_not_observed; stop before matched control",
            "request_failure_or_truncation": "service_gate_failed; preserve rows and stop",
            "output_digest_divergence": "semantic_identity_failed; reject candidate",
            "partial_artifact": "operational_failure; archive available raw artifacts but make no performance or cache claim",
        },
        "stop_and_cleanup": {
            "timeout_seconds": 1800,
            "allocation_exposure_cap_usd": 0.45,
            "session_total_cap_usd": 1.50,
            "owner": "assigned by later director handoff",
            "watchdog": "absolute provider cleanup deadline at 60 minutes from allocation creation",
            "teardown": "stop server, terminate allocation, then verify zero active instances and retain provider/billing evidence",
        },
        "artifact_contract": [
            "immutable plan and packet hashes",
            "server command and startup log",
            "request payload and SSE digests with salts",
            "metrics-before.prom and metrics-after.prom",
            "per-request outcomes including usage.prompt_tokens_details.cached_tokens",
            "SLO/semantic result, cost ledger, provider inventory, and cleanup verification",
        ],
    }


def main():
    output = PROJECT / "artifacts"
    output.mkdir(exist_ok=True)
    value = packet()
    path = output / "V2_CACHE_ON_SMOKE_PACKET.json"
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")
    print(path)


if __name__ == "__main__":
    main()
