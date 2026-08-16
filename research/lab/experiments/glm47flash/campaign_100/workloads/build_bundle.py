#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


SEED = 470100
TOKENIZER_SOURCE_FILES = {
    "tokenizer.json": {"bytes": 20217442, "sha256": "19e773648cb4e65de8660ea6365e10acca112d42a854923df93db4a6f333a82d"},
    "tokenizer_config.json": {"bytes": 7226, "sha256": "31a173e2797ddc8b72ac996803513e627fc28d7aad02cfcce321a431d865c86d"},
    "chat_template.jinja": {"bytes": 3120, "sha256": "d63ad536c3c81880043e22ec7fd08db42b4d8fb7c89c7138bc562bfa25281375"},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def with_hash(record):
    result = dict(record)
    result["content_sha256"] = sha256_bytes(canonical(record))
    return result


def fixed_record(split, suffix):
    return with_hash({
        "schema_version": 1,
        "fixture_id": f"{split}_fixed_{suffix}",
        "split": split,
        "workload_class": "fixed_8k_1k",
        "seed": SEED + suffix,
        "content_representation": "length_only",
        "input_tokens": 8192,
        "max_output_tokens": 1024,
        "prefix_identity": {"kind": "unavailable_length_only"},
        "provenance": {
            "source": "published_style_anchor_as_specified_by_campaign_plan",
            "reuse_status": "length_only_public_distribution",
            "content_included": False,
            "claim_limit": "length comparability only; no exact prefix or semantic trace claim",
        },
        "tokenizer_binding": {"status": "exact_count_by_contract", "tokenizer": "model_input_token_ids"},
    })


def append_record(split, suffix):
    if split == "development":
        path, function, parameters = "src/math.py", "clamp", "value, low, high"
        source = "def clamp(value, low, high):\n    return max(low, min(high, value))\n"
    else:
        path, function, parameters = "src/range.py", "span", "start, stop, step"
        source = "def span(start, stop, step):\n    return tuple(range(start, stop, step))\n"
    session = {
        "system": f"You are the deterministic {split} repository assistant. Use tools only when required.",
        "turns": [
            {"role": "user", "content": f"Inspect {path} and report the public function names."},
            {"role": "assistant", "tool_call": {"name": "read_file", "arguments": {"path": path}}},
            {"role": "tool", "name": "read_file", "content": source},
            {"role": "assistant", "content": f"The public function is {function}."},
            {"role": "user", "content": f"Now state these parameter names in order: {parameters}."},
        ],
    }
    return with_hash({
        "schema_version": 1,
        "fixture_id": f"{split}_append_{suffix}",
        "split": split,
        "workload_class": "agent_append",
        "seed": SEED + 100 + suffix,
        "content_representation": "synthetic_raw_messages",
        "session": session,
        "append_boundaries": [1, 3, 5],
        "pause_time_ms": [0, 250, 500],
        "max_output_tokens": 128,
        "prefix_identity": {"kind": "not_claimed_across_sessions"},
        "tool_schema_size_bytes": 151,
        "tool_result_size_bytes": len(session["turns"][2]["content"].encode()),
        "provenance": {
            "source": "campaign_authored_deterministic_synthetic_fixture",
            "reuse_status": "synthetic_owned",
            "content_included": True,
            "claim_limit": "structural agent-append fixture; not an empirical frequency distribution",
        },
        "tokenizer_binding": {
            "status": "required_before_gpu_replay",
            "model": "zai-org/GLM-4.7-Flash",
            "checkpoint_revision": "75fce70",
            "raw_message_sha256": sha256_bytes(canonical(session)),
        },
    })


def prefix_record(split, suffix):
    prefix_role = "coding" if split == "development" else "review"
    symbols = ["synthetic_alpha", "synthetic_beta", "synthetic_gamma"] if split == "development" else ["synthetic_delta", "synthetic_epsilon", "synthetic_zeta"]
    prefix = {
        "system": f"You are a tenant-safe deterministic {prefix_role} assistant.",
        "tools": [{
            "name": "lookup_symbol",
            "description": "Return a symbol signature from the synthetic repository.",
            "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        }],
    }
    prefix_hash = sha256_bytes(canonical(prefix))
    requests = [{"prefix_sha256": prefix_hash, "user": f"Look up {symbol}.", "max_output_tokens": 96} for symbol in symbols]
    return with_hash({
        "schema_version": 1,
        "fixture_id": f"{split}_prefix_{suffix}",
        "split": split,
        "workload_class": "agent_prefix",
        "seed": SEED + 200 + suffix,
        "content_representation": "synthetic_raw_messages",
        "tenant_scope": f"synthetic_{split}_tenant",
        "shared_prefix": prefix,
        "prefix_identity": {"kind": "exact_sha256", "sha256": prefix_hash},
        "requests": requests,
        "pause_time_ms": [0, 100, 100],
        "provenance": {
            "source": "campaign_authored_deterministic_synthetic_fixture",
            "reuse_status": "synthetic_owned",
            "content_included": True,
            "claim_limit": "exact synthetic prefix identity only; no cross-tenant reuse claim",
        },
        "tokenizer_binding": {
            "status": "required_before_gpu_replay",
            "model": "zai-org/GLM-4.7-Flash",
            "checkpoint_revision": "75fce70",
            "raw_message_sha256": sha256_bytes(canonical({"prefix": prefix, "requests": requests})),
        },
    })


def write_json(path, value):
    path.write_bytes(canonical(value) + b"\n")


def write_jsonl(path, records):
    path.write_bytes(b"".join(canonical(record) + b"\n" for record in records))


def replay_schedule():
    def profile(profile_id, workload_class, split, request_count, max_concurrency, arrival, warmup_count, cache):
        return {
            "profile_id": profile_id,
            "workload_class": workload_class,
            "split": split,
            "request_count": request_count,
            "max_concurrency": max_concurrency,
            "arrival": arrival,
            "warmup": {
                "request_count": warmup_count,
                "max_concurrency": 1,
                "excluded_from_measurement": True,
                "completion_required_before_measurement": True,
            },
            "cache": cache,
            "repetitions": 1 if split == "development" else 3,
            "configuration_repetitions": {
                "stock_bf16": 1 if split == "development" else 3,
                "stock_tuned_bf16": 1 if split == "development" else 3,
            },
        }

    disabled_cache = {
        "prefix_cache": "disabled",
        "reset_before_each_repetition": True,
        "reason": "length-only geometry has no admissible exact prefix identity",
    }
    exact_session_cache = {
        "prefix_cache": "enabled",
        "reset_before_each_repetition": True,
        "cold_request_count_per_session": 1,
        "reuse_scope": "same synthetic session and tenant only",
        "cross_tenant_reuse_allowed": False,
    }
    isolated_append_cache = {
        "prefix_cache": "disabled",
        "reset_before_each_repetition": True,
        "reason": "one fully bound growing-session prompt per synthetic session; cross-session reuse is forbidden",
    }
    profiles = [
        profile("development_smoke", "all", "development", 5, 1, {"kind": "closed_loop", "inter_request_delay_ms": 0}, 2, disabled_cache),
        profile("fixed_8k_1k_c1", "fixed_8k_1k", "development", 4, 1, {"kind": "closed_loop", "inter_request_delay_ms": 0}, 1, disabled_cache),
        profile("fixed_8k_1k_c8", "fixed_8k_1k", "development", 16, 8, {"kind": "closed_loop", "inter_request_delay_ms": 0}, 4, disabled_cache),
        profile("fixed_8k_1k_c32", "fixed_8k_1k", "development", 256, 32, {"kind": "closed_loop", "inter_request_delay_ms": 0}, 32, disabled_cache),
        profile(
            "agent_append_c8",
            "agent_append",
            "development",
            8,
            8,
            {"kind": "fixed_interval", "inter_arrival_ms": 125, "provenance": "campaign_synthetic_control"},
            1,
            isolated_append_cache,
        ),
        profile(
            "agent_prefix_c8",
            "agent_prefix",
            "development",
            24,
            8,
            {"kind": "session_relative", "session_count": 8, "session_start_stagger_ms": 125, "within_session_offsets_ms": [0, 100, 200]},
            3,
            exact_session_cache,
        ),
        profile(
            "aa_agentperf_length_screen_c8",
            "aa_agentperf_length_only_geometry",
            "development",
            64,
            8,
            {"kind": "fixed_interval", "inter_arrival_ms": 125, "provenance": "campaign_synthetic_control"},
            8,
            disabled_cache,
        ),
        profile("holdout_fixed_8k_1k_c32", "fixed_8k_1k", "holdout", 256, 32, {"kind": "closed_loop", "inter_request_delay_ms": 0}, 32, disabled_cache),
        profile(
            "holdout_agent_append_c8",
            "agent_append",
            "holdout",
            8,
            8,
            {"kind": "fixed_interval", "inter_arrival_ms": 125, "provenance": "campaign_synthetic_control"},
            1,
            isolated_append_cache,
        ),
        profile(
            "holdout_agent_prefix_c8",
            "agent_prefix",
            "holdout",
            24,
            8,
            {"kind": "session_relative", "session_count": 8, "session_start_stagger_ms": 125, "within_session_offsets_ms": [0, 100, 200]},
            3,
            exact_session_cache,
        ),
    ]
    return {
        "schema_version": 1,
        "schedule_id": "glm47flash_campaign_100_replay_schedule_v1",
        "profiles": profiles,
        "measurement_order": [profile["profile_id"] for profile in profiles],
        "phase_b_sequence": {
            "cheapest_falsification_profiles": ["development_smoke", "fixed_8k_1k_c1", "fixed_8k_1k_c8"],
            "maximum_measured_requests_before_headline": 25,
            "headline_profile_only_after_prior_slo_pass": "fixed_8k_1k_c32",
        },
        "timeout": {"per_request_seconds": 180, "profile_seconds": 1800},
        "request_failure_policy": "record every typed failure and fail the profile closed",
    }


def aa_agentperf_length_only_geometry():
    return {
        "schema_version": 1,
        "geometry_id": "glm47flash_campaign_100_aa_agentperf_length_only_v1",
        "content_representation": "length_only_geometry",
        "source_artifact": {
            "path": "../../../workloads/aa-agentperf-public-proxy-v1.json",
            "sha256": "11077a458480b8ac5ee2f78f7fa75dc95076eedfb13a30f53bb8163ec2ede1a1",
            "source_label": "local deterministic proxy derived from AA-AgentPerf public workload geometry",
        },
        "public_basis": {
            "minimum_input_tokens": 5000,
            "maximum_input_tokens": 131000,
            "approximate_mean_input_tokens": 27000,
            "median_tool_delay_milliseconds": 1000,
            "dynamic_prefixes_reported": True,
            "concurrent_sessions_reported": True,
            "private_test_set_used": False,
        },
        "foundry_synthetic_length_histogram": [
            {"input_tokens": 5000, "count": 8},
            {"input_tokens": 10000, "count": 8},
            {"input_tokens": 16000, "count": 8},
            {"input_tokens": 22000, "count": 8},
            {"input_tokens": 27000, "count": 8},
            {"input_tokens": 32000, "count": 8},
            {"input_tokens": 45000, "count": 7},
            {"input_tokens": 48250, "count": 8},
            {"input_tokens": 131000, "count": 1},
        ],
        "synthetic_controls": {
            "request_count": 64,
            "max_concurrency": 8,
            "output_tokens_are_imported": False,
            "arrival_process_is_imported": False,
            "prefix_identity_is_imported": False,
            "semantic_content_is_imported": False,
        },
        "claim_limit": "Length-range stress geometry only; no benchmark, prefix-reuse, quality, demand, provider, performance, or cost claim.",
        "claim_gates": {
            "aa_agentperf_score_claim_permitted": False,
            "measured_performance_claim_permitted": False,
            "provider_performance_claim_permitted": False,
            "cost_claim_permitted": False,
        },
    }


def build_bundle(output):
    output.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parent
    for script in ["build_bundle.py", "validate_bundle.py", "replay_api.py", "RUNNER_INTERFACE.md"]:
        target = (output / script).resolve()
        if target != (source / script).resolve():
            target.write_bytes((source / script).read_bytes())
    tokenizer_bindings = json.loads((source / "TOKENIZER_BINDINGS.json").read_text())
    if tokenizer_bindings.get("source_files") != TOKENIZER_SOURCE_FILES:
        raise ValueError("source tokenizer bindings differ from the frozen source-file identities")
    tokenizer_target = (output / "TOKENIZER_BINDINGS.json").resolve()
    if tokenizer_target != (source / "TOKENIZER_BINDINGS.json").resolve():
        tokenizer_target.write_bytes((source / "TOKENIZER_BINDINGS.json").read_bytes())
    schedule = replay_schedule()
    geometry = aa_agentperf_length_only_geometry()
    proxy_path = source.parents[2] / "workloads" / "aa-agentperf-public-proxy-v1.json"
    if sha256_bytes(proxy_path.read_bytes()) != geometry["source_artifact"]["sha256"]:
        raise ValueError("local AA-AgentPerf public-geometry proxy identity drifted")
    write_json(output / "REPLAY_SCHEDULE.json", schedule)
    write_json(output / "AA_AGENTPERF_LENGTH_ONLY_GEOMETRY.json", geometry)
    bindings_sha256 = sha256_bytes((output / "TOKENIZER_BINDINGS.json").read_bytes())
    schedule_sha256 = sha256_bytes((output / "REPLAY_SCHEDULE.json").read_bytes())
    geometry_sha256 = sha256_bytes((output / "AA_AGENTPERF_LENGTH_ONLY_GEOMETRY.json").read_bytes())
    contract = {
        "schema_version": 1,
        "bundle_name": "glm47flash_campaign_100_workloads_v1",
        "frozen_seed": SEED,
        "required_classes": ["fixed_8k_1k", "agent_append", "agent_prefix"],
        "splits": ["development", "holdout"],
        "service_contract": {
            "max_p95_ttft_ms": 10_000,
            "max_p95_inter_token_latency_ms": 100,
            "min_request_success_rate": 0.99,
            "silent_truncation_allowed": False,
        },
        "sampling_contract": {"temperature": 0.0, "top_p": 1.0, "deterministic_greedy": True},
        "tokenizer_contract": {
            "model": "zai-org/GLM-4.7-Flash",
            "checkpoint_revision": "75fce70",
            "exact_tokenizer_output_required_before_replay": True,
            "fail_if_revision_or_chat_template_unrecorded": True,
            "bindings_file": "TOKENIZER_BINDINGS.json",
            "bindings_sha256": bindings_sha256,
        },
        "replay_schedule": {"file": "REPLAY_SCHEDULE.json", "sha256": schedule_sha256},
        "aa_agentperf_length_only_geometry": {"file": "AA_AGENTPERF_LENGTH_ONLY_GEOMETRY.json", "sha256": geometry_sha256},
        "claims": {
            "empirical_public_trace_content_included": False,
            "exact_prefix_identity_allowed_for": "synthetic_owned records only",
            "length_only_records_allow_semantic_claims": False,
        },
    }
    provenance = {
        "schema_version": 1,
        "included_sources": [
            {"name": "campaign synthetic fixtures", "status": "synthetic_owned"},
            {"name": "fixed 8192/1024 plan anchor", "status": "length_only_public_distribution"},
        ],
        "excluded_sources": [{
            "path": "../../../overnight/direct-codex-prior/codex.jsonl",
            "reason": "local transcript has no verified public license and may contain private session content",
        }],
        "known_gap": "No legally verified raw UW TraceLab trajectory was available locally; empirical distribution claims are forbidden.",
    }
    development = [fixed_record("development", 1), append_record("development", 1), prefix_record("development", 1)]
    holdout = [fixed_record("holdout", 2), append_record("holdout", 2), prefix_record("holdout", 2)]
    write_json(output / "contract.json", contract)
    write_json(output / "provenance.json", provenance)
    write_jsonl(output / "development.jsonl", development)
    write_jsonl(output / "holdout.jsonl", holdout)
    names = [
        "contract.json", "provenance.json", "development.jsonl", "holdout.jsonl",
        "TOKENIZER_BINDINGS.json", "REPLAY_SCHEDULE.json", "AA_AGENTPERF_LENGTH_ONLY_GEOMETRY.json",
        "build_bundle.py", "validate_bundle.py", "replay_api.py", "RUNNER_INTERFACE.md",
    ]
    files = {name: sha256_bytes((output / name).read_bytes()) for name in names}
    manifest = {
        "schema_version": 1,
        "files": files,
        "bundle_sha256": sha256_bytes(canonical(files)),
        "immutability": "Any byte change creates a new bundle identity and invalidates this manifest.",
    }
    write_json(output / "FROZEN_MANIFEST.json", manifest)
    return manifest


if __name__ == "__main__":
    build_bundle(Path(__file__).resolve().parent)
