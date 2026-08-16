#!/usr/bin/env python3
import hashlib
import json
import re
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
CAMPAIGN = PROJECT.parents[2] / "campaign_100"
WORKLOADS = CAMPAIGN / "workloads"
sys.path.insert(0, str(WORKLOADS))

from replay_api import openai_transport_tools, validate_arrival_offsets, validate_request
from validate_bundle import load_and_validate


SALT_RE = re.compile(r"[0-9a-f]{64}")
SERVED_MODEL = "glm-4.7-flash-awq"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def bundle():
    return load_and_validate(WORKLOADS)


def fixture(base):
    return next(
        row for row in base["records"]["development"]
        if row["fixture_id"] == "development_prefix_1"
    )


def profile(base):
    return next(
        row for row in base["replay_schedule"]["profiles"]
        if row["profile_id"] == "agent_prefix_c8"
    )


def salt(base, session_index):
    return hashlib.sha256(canonical({
        "base_bundle_sha256": base["manifest"]["bundle_sha256"],
        "tenant_scope": "synthetic_development_tenant",
        "session_index": session_index,
        "isolation_scheme": "v2-per-session-cache-salt",
    })).hexdigest()


def v2_bundle_sha256(base):
    return hashlib.sha256(canonical({
        "schema_version": 2,
        "base_bundle_sha256": base["manifest"]["bundle_sha256"],
        "isolation_scheme": "v2-per-session-cache-salt",
        "cache_salt_encoding": "sha256-hex-256-bit",
        "profile_id": "agent_prefix_c8",
        "served_model_name": SERVED_MODEL,
    })).hexdigest()


def request(base, session_index, request_index, offset, prefix):
    binding = next(
        row for row in base["tokenizer_bindings"]["bindings"]
        if row["fixture_id"] == prefix["fixture_id"]
    )["requests"][request_index]
    return {
        "schema_version": 2,
        "request_id": f"agent-prefix-v2-session-{session_index:02d}-turn-{request_index:02d}",
        "fixture_id": prefix["fixture_id"],
        "request_index": request_index,
        "messages": [
            {"role": "system", "content": prefix["shared_prefix"]["system"]},
            {"role": "user", "content": prefix["requests"][request_index]["user"]},
        ],
        "tools": prefix["shared_prefix"]["tools"],
        "max_output_tokens": prefix["requests"][request_index]["max_output_tokens"],
        "expected_input_tokens": binding["server_reported_input_tokens"],
        "scheduled_offset_ms": offset,
        "tenant_scope": prefix["tenant_scope"],
        "session_index": session_index,
        "cache_salt": salt(base, session_index),
    }


def build_v2_plan():
    base = bundle()
    prefix = fixture(base)
    schedule = profile(base)["arrival"]
    requests = [
        request(base, session, index, session * schedule["session_start_stagger_ms"] + offset, prefix)
        for session in range(schedule["session_count"])
        for index, offset in enumerate(schedule["within_session_offsets_ms"])
    ]
    return {
        "schema_version": 2,
        "v2_bundle_sha256": v2_bundle_sha256(base),
        "base_bundle_sha256": base["manifest"]["bundle_sha256"],
        "profile_id": "agent_prefix_c8",
        "cache_mode": "enabled",
        "served_model_name": SERVED_MODEL,
        "generation": {"seed": 470100, "temperature": 0.0, "top_p": 1.0},
        "requests": requests,
        "required_telemetry": [
            "prefix_cache_queries_total_delta",
            "prefix_cache_hits_total_delta",
            "reused_prompt_tokens_per_request",
            "kv_blocks_peak",
            "ttft_ms",
            "itl_ms",
            "success_and_truncation",
        ],
    }


def v1_request(row):
    fields = {
        "schema_version", "request_id", "fixture_id", "request_index", "messages", "tools",
        "max_output_tokens", "expected_input_tokens", "scheduled_offset_ms",
    }
    result = {key: row[key] for key in fields}
    result["schema_version"] = 1
    return result


def validate_v2_plan(plan):
    base = bundle()
    expected_profile = profile(base)
    if plan.get("schema_version") != 2 or plan.get("base_bundle_sha256") != base["manifest"]["bundle_sha256"]:
        raise ValueError("plan is not bound to the immutable V1 workload bundle")
    if plan.get("v2_bundle_sha256") != v2_bundle_sha256(base) or plan.get("profile_id") != expected_profile["profile_id"]:
        raise ValueError("plan is not bound to the V2 isolation contract")
    if plan.get("cache_mode") != "enabled" or plan.get("served_model_name") != SERVED_MODEL or plan.get("generation") != {"seed": 470100, "temperature": 0.0, "top_p": 1.0}:
        raise ValueError("plan changed a controlled cache or generation setting")
    rows = plan.get("requests")
    if not isinstance(rows, list) or len(rows) != expected_profile["request_count"]:
        raise ValueError("plan request count differs from the frozen profile")
    prefix = fixture(base)
    expected_salts = {session: salt(base, session) for session in range(8)}
    per_session = {session: [] for session in expected_salts}
    for row in rows:
        validate_request(base, v1_request(row))
        session = row.get("session_index")
        if row.get("tenant_scope") != prefix["tenant_scope"] or session not in expected_salts:
            raise ValueError("request tenant/session identity is invalid")
        if not isinstance(row.get("cache_salt"), str) or not SALT_RE.fullmatch(row["cache_salt"]):
            raise ValueError("request cache salt is not a protected 256-bit identity")
        if row["cache_salt"] != expected_salts[session]:
            raise ValueError("request cache salt does not bind the declared session")
        per_session[session].append(row)
    if any(sorted(row["request_index"] for row in rows) != [0, 1, 2] for rows in per_session.values()):
        raise ValueError("each session must contain exactly one immutable three-turn prefix sequence")
    validate_arrival_offsets(expected_profile["arrival"], [v1_request(row) for row in rows])
    return plan


def request_payload(row):
    return {
        "model": SERVED_MODEL,
        "max_tokens": row["max_output_tokens"],
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": 470100,
        "stream": True,
        "stream_options": {"include_usage": True, "continuous_usage_stats": True},
        "messages": row["messages"],
        "tools": openai_transport_tools(row["tools"]),
        "cache_salt": row["cache_salt"],
    }


def main():
    plan = validate_v2_plan(build_v2_plan())
    output = PROJECT / "artifacts"
    output.mkdir(exist_ok=True)
    path = output / "agent_prefix_c8_v2_tenant_isolated.plan.json"
    path.write_bytes(json.dumps(plan, indent=2, sort_keys=True).encode() + b"\n")
    manifest = {
        "schema_version": 2,
        "plan_path": str(path.relative_to(PROJECT)),
        "plan_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "v2_bundle_sha256": plan["v2_bundle_sha256"],
        "base_bundle_sha256": plan["base_bundle_sha256"],
        "validation": "local schema, V1 fixture/tokenizer identity, per-session salt binding, fixed arrival schedule, and HTTP payload construction passed",
        "server_smoke_required": True,
    }
    (output / "V2_REPLAY_AMENDMENT_MANIFEST.json").write_bytes(
        json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    )
    print(path)


if __name__ == "__main__":
    main()
