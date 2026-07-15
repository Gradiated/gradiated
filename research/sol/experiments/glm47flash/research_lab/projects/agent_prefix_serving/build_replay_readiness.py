#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
CAMPAIGN = PROJECT.parents[2] / "campaign_100"
WORKLOADS = CAMPAIGN / "workloads"
sys.path.insert(0, str(WORKLOADS))

from replay_api import load_plan
from validate_bundle import load_and_validate


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def request(bundle, fixture_id, request_index, request_id, offset, cache_salt):
    fixture = next(
        row
        for row in bundle["records"]["development"]
        if row["fixture_id"] == fixture_id
    )
    binding = next(
        row for row in bundle["tokenizer_bindings"]["bindings"]
        if row["fixture_id"] == fixture_id
    )["requests"][request_index]
    return {
        "schema_version": 1,
        "request_id": request_id,
        "fixture_id": fixture_id,
        "request_index": request_index,
        "messages": [
            {"role": "system", "content": fixture["shared_prefix"]["system"]},
            {"role": "user", "content": fixture["requests"][request_index]["user"]},
        ],
        "tools": fixture["shared_prefix"]["tools"],
        "max_output_tokens": fixture["requests"][request_index]["max_output_tokens"],
        "expected_input_tokens": binding["server_reported_input_tokens"],
        "scheduled_offset_ms": offset,
        "cache_salt": cache_salt,
    }


def main():
    bundle = load_and_validate(WORKLOADS)
    profile = next(
        row for row in bundle["replay_schedule"]["profiles"]
        if row["profile_id"] == "agent_prefix_c8"
    )
    fixture_id = "development_prefix_1"
    session_count = profile["arrival"]["session_count"]
    offsets = profile["arrival"]["within_session_offsets_ms"]
    stagger = profile["arrival"]["session_start_stagger_ms"]
    salts = [
        hashlib.sha256(canonical({
            "bundle_sha256": bundle["manifest"]["bundle_sha256"],
            "fixture_id": fixture_id,
            "tenant_scope": "synthetic_development_tenant",
            "session_index": session,
        })).hexdigest()
        for session in range(session_count)
    ]
    measured = [
        request(
            bundle,
            fixture_id,
            request_index,
            f"agent-prefix-session-{session:02d}-turn-{request_index:02d}",
            session * stagger + offset,
            salts[session],
        )
        for session in range(session_count)
        for request_index, offset in enumerate(offsets)
    ]
    warmups = [
        request(bundle, fixture_id, index, f"agent-prefix-warmup-{index:02d}", 0, salts[0])
        for index in range(profile["warmup"]["request_count"])
    ]
    plan = {
        "schema_version": 1,
        "bundle_sha256": bundle["manifest"]["bundle_sha256"],
        "profile_id": profile["profile_id"],
        "cache_mode": profile["cache"]["prefix_cache"],
        "warmup_requests": warmups,
        "requests": measured,
    }
    output = PROJECT / "artifacts"
    output.mkdir(exist_ok=True)
    plan_path = output / "agent_prefix_c8_tenant_isolated.plan.json"
    plan_path.write_bytes(canonical(plan) + b"\n")
    try:
        load_plan(bundle, plan_path)
        isolation_plan_validation = {"accepted": True, "error": None}
    except Exception as error:
        isolation_plan_validation = {"accepted": False, "error": str(error)}
    input_tokens = sum(row["expected_input_tokens"] for row in measured)
    shared_prefix_tokens = next(
        row for row in bundle["tokenizer_bindings"]["bindings"]
        if row["fixture_id"] == fixture_id
    )["exact_common_prefix_tokens"]
    cacheable_prefix_tokens = shared_prefix_tokens // 16 * 16
    reusable_tokens_upper_bound = session_count * (len(offsets) - 1) * cacheable_prefix_tokens
    kv_capacity_tokens = 333_488
    max_resident_tokens = sum(
        row["expected_input_tokens"] + row["max_output_tokens"] for row in measured
    )
    artifact = {
        "schema_version": 1,
        "evidence_label": "derived",
        "question": "Does the frozen development agent-prefix replay have tenant-safe, material exact reuse before a paid cache control?",
        "bundle_sha256": bundle["manifest"]["bundle_sha256"],
        "profile_id": profile["profile_id"],
        "plan": {"path": str(plan_path.relative_to(PROJECT)), "sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest()},
        "isolation": {
            "tenant_scope": "synthetic_development_tenant",
            "session_count": session_count,
            "distinct_cache_salts": len(set(salts)),
            "cache_salt_length": len(salts[0]),
            "cross_session_reuse_possible": False,
            "mechanism": "vLLM request cache_salt differs per session and is identical within that session",
            "frozen_runner_accepts_cache_salt": isolation_plan_validation["accepted"],
            "frozen_runner_rejection": isolation_plan_validation["error"],
        },
        "reuse_bound": {
            "measured_requests": len(measured),
            "input_tokens": input_tokens,
            "exact_common_prefix_tokens": shared_prefix_tokens,
            "cache_block_tokens_assumed": 16,
            "cacheable_full_block_prefix_tokens": cacheable_prefix_tokens,
            "cold_requests": session_count,
            "potential_reuse_requests": session_count * (len(offsets) - 1),
            "potential_reused_prefill_tokens": reusable_tokens_upper_bound,
            "potential_reused_prefill_share": reusable_tokens_upper_bound / input_tokens,
        },
        "kv_capacity_bound": {
            "source": "V21 L40S server stdout",
            "available_kv_tokens": kv_capacity_tokens,
            "maximum_all_request_prompt_plus_cap_tokens": max_resident_tokens,
            "upper_bound_utilization": max_resident_tokens / kv_capacity_tokens,
            "interpretation": "capacity cannot explain a cache miss for this profile under the V21 stack",
        },
        "admission": {
            "paid_control_ready": False,
            "blocker": "The frozen replay schema rejects cache_salt, so its claimed session/tenant isolation is not conveyed to vLLM. Separately, 100 ms offsets do not establish that each prior prefill completes before the next request.",
            "next_cheapest_falsifier": "Create a versioned workload-bundle amendment that adds cache_salt to the replay schema and HTTP payload, regenerates tokenizer/manifest identities, and validates a local cache-on smoke with per-request cache query, hit, and reused-token telemetry.",
        },
    }
    artifact_path = output / "PREFIX_REPLAY_READINESS.json"
    artifact_path.write_bytes(json.dumps(artifact, indent=2, sort_keys=True).encode() + b"\n")
    print(artifact_path)


if __name__ == "__main__":
    main()
