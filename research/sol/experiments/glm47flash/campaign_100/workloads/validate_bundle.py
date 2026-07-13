#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


class BundleError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise BundleError(f"invalid JSON {path.name}: {error}") from error


def read_jsonl(path):
    try:
        return [json.loads(line) for line in path.read_text().splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise BundleError(f"invalid JSONL {path.name}: {error}") from error


def load_and_validate(root):
    root = Path(root)
    manifest = read_json(root / "FROZEN_MANIFEST.json")
    expected_files = {
        "contract.json", "provenance.json", "development.jsonl", "holdout.jsonl",
        "TOKENIZER_BINDINGS.json", "REPLAY_SCHEDULE.json", "AA_AGENTPERF_LENGTH_ONLY_GEOMETRY.json",
        "build_bundle.py", "validate_bundle.py", "replay_api.py", "RUNNER_INTERFACE.md",
    }
    if set(manifest.get("files", {})) != expected_files:
        raise BundleError("manifest file set is not exact")
    for name, expected in manifest["files"].items():
        try:
            actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        except OSError as error:
            raise BundleError(f"missing bundle file {name}") from error
        if actual != expected:
            raise BundleError(f"file hash mismatch: {name}")
    bundle_hash = hashlib.sha256(canonical(manifest["files"])).hexdigest()
    if bundle_hash != manifest.get("bundle_sha256"):
        raise BundleError("bundle identity mismatch")
    contract = read_json(root / "contract.json")
    tokenizer_bindings = read_json(root / "TOKENIZER_BINDINGS.json")
    replay_schedule = read_json(root / "REPLAY_SCHEDULE.json")
    aa_geometry = read_json(root / "AA_AGENTPERF_LENGTH_ONLY_GEOMETRY.json")
    binding_hash = hashlib.sha256((root / "TOKENIZER_BINDINGS.json").read_bytes()).hexdigest()
    schedule_hash = hashlib.sha256((root / "REPLAY_SCHEDULE.json").read_bytes()).hexdigest()
    geometry_hash = hashlib.sha256((root / "AA_AGENTPERF_LENGTH_ONLY_GEOMETRY.json").read_bytes()).hexdigest()
    if contract.get("tokenizer_contract", {}).get("bindings_sha256") != binding_hash:
        raise BundleError("tokenizer bindings are not bound into the workload contract")
    if contract.get("replay_schedule") != {"file": "REPLAY_SCHEDULE.json", "sha256": schedule_hash}:
        raise BundleError("replay schedule is not bound into the workload contract")
    if contract.get("aa_agentperf_length_only_geometry") != {"file": "AA_AGENTPERF_LENGTH_ONLY_GEOMETRY.json", "sha256": geometry_hash}:
        raise BundleError("AA-AgentPerf length-only geometry is not bound into the workload contract")
    frozen_service = {
        "max_p95_ttft_ms": 10_000,
        "max_p95_inter_token_latency_ms": 100,
        "min_request_success_rate": 0.99,
        "silent_truncation_allowed": False,
    }
    if contract.get("service_contract") != frozen_service:
        raise BundleError("service thresholds differ from controlling plan")
    required = {"fixed_8k_1k", "agent_append", "agent_prefix"}
    if set(contract.get("required_classes", [])) != required:
        raise BundleError("required workload classes missing")
    records = {split: read_jsonl(root / f"{split}.jsonl") for split in ["development", "holdout"]}
    ids = set()
    for split, rows in records.items():
        if {row.get("workload_class") for row in rows} != required:
            raise BundleError(f"{split} class set is not exact")
        for row in rows:
            if row.get("split") != split or row.get("fixture_id") in ids:
                raise BundleError("split mismatch or duplicate fixture id")
            ids.add(row["fixture_id"])
            payload = dict(row)
            record_hash = payload.pop("content_sha256", None)
            if hashlib.sha256(canonical(payload)).hexdigest() != record_hash:
                raise BundleError(f"record hash mismatch: {row.get('fixture_id')}")
            status = row.get("provenance", {}).get("reuse_status")
            if status not in {"synthetic_owned", "length_only_public_distribution"}:
                raise BundleError(f"unverified provenance: {row.get('fixture_id')}")
            if row["workload_class"] == "fixed_8k_1k":
                if (row.get("input_tokens"), row.get("max_output_tokens"), row.get("content_representation")) != (8192, 1024, "length_only"):
                    raise BundleError("fixed anchor changed")
                if row.get("prefix_identity", {}).get("kind") != "unavailable_length_only":
                    raise BundleError("length-only record claims prefix identity")
            if row["workload_class"] == "agent_prefix":
                prefix_hash = hashlib.sha256(canonical(row.get("shared_prefix"))).hexdigest()
                if row.get("prefix_identity") != {"kind": "exact_sha256", "sha256": prefix_hash}:
                    raise BundleError("synthetic prefix identity mismatch")
                if any(request.get("prefix_sha256") != prefix_hash for request in row.get("requests", [])):
                    raise BundleError("request prefix identity mismatch")
    validate_tokenizer_bindings(tokenizer_bindings, records)
    validate_replay_schedule(replay_schedule)
    validate_aa_geometry(aa_geometry)
    return {
        "manifest": manifest,
        "contract": contract,
        "records": records,
        "tokenizer_bindings": tokenizer_bindings,
        "replay_schedule": replay_schedule,
        "aa_agentperf_length_only_geometry": aa_geometry,
    }


def validate_tokenizer_bindings(bindings, records):
    expected_source_files = {
        "tokenizer.json": {"bytes": 20217442, "sha256": "19e773648cb4e65de8660ea6365e10acca112d42a854923df93db4a6f333a82d"},
        "tokenizer_config.json": {"bytes": 7226, "sha256": "31a173e2797ddc8b72ac996803513e627fc28d7aad02cfcce321a431d865c86d"},
        "chat_template.jinja": {"bytes": 3120, "sha256": "d63ad536c3c81880043e22ec7fd08db42b4d8fb7c89c7138bc562bfa25281375"},
    }
    if bindings.get("model") != "zai-org/GLM-4.7-Flash":
        raise BundleError("tokenizer model binding drifted")
    if bindings.get("requested_revision") != "75fce70" or bindings.get("resolved_revision") != "75fce703a93da3705c4cf8d3caadbac1d1072c78":
        raise BundleError("tokenizer revision binding drifted")
    if bindings.get("source_files") != expected_source_files:
        raise BundleError("tokenizer source file identity drifted")
    if bindings.get("tokenizer_implementation") != {"package": "@huggingface/transformers", "version": "4.2.0"}:
        raise BundleError("tokenizer implementation binding drifted")
    if bindings.get("sampling") != {"add_generation_prompt": True}:
        raise BundleError("tokenizer chat-template sampling binding drifted")
    content_records = {
        row["fixture_id"]: row
        for split in records.values()
        for row in split
        if row.get("content_representation") != "length_only"
    }
    rows = bindings.get("bindings")
    if not isinstance(rows, list) or {row.get("fixture_id") for row in rows} != set(content_records):
        raise BundleError("tokenizer fixture binding set is not exact")
    token_hashes_by_split = {"development": set(), "holdout": set()}
    for row in rows:
        fixture = content_records[row["fixture_id"]]
        if row.get("raw_message_sha256") != fixture.get("tokenizer_binding", {}).get("raw_message_sha256"):
            raise BundleError("tokenizer raw-message binding mismatch")
        if fixture["workload_class"] == "agent_append":
            if not isinstance(row.get("input_tokens"), int) or row["input_tokens"] <= 0:
                raise BundleError("append tokenizer count is missing")
            token_hashes = [row.get("token_ids_u32le_sha256")]
        else:
            request_rows = row.get("requests")
            if not isinstance(request_rows, list) or len(request_rows) != len(fixture.get("requests", [])):
                raise BundleError("prefix tokenizer request binding set is not exact")
            expected_users = [request["user"] for request in fixture["requests"]]
            if [request.get("user") for request in request_rows] != expected_users:
                raise BundleError("prefix tokenizer request order drifted")
            if not isinstance(row.get("exact_common_prefix_tokens"), int) or row["exact_common_prefix_tokens"] <= 0:
                raise BundleError("exact common prefix token count is missing")
            token_hashes = [request.get("token_ids_u32le_sha256") for request in request_rows]
        if any(not isinstance(value, str) or len(value) != 64 for value in token_hashes):
            raise BundleError("tokenizer token-id hash is missing")
        token_hashes_by_split[fixture["split"]].update(token_hashes)
    if token_hashes_by_split["development"] & token_hashes_by_split["holdout"]:
        raise BundleError("development and holdout tokenizer bindings overlap")


def validate_replay_schedule(schedule):
    required_profiles = {
        "development_smoke", "fixed_8k_1k_c1", "fixed_8k_1k_c8", "fixed_8k_1k_c32",
        "agent_append_c8", "agent_prefix_c8", "aa_agentperf_length_screen_c8",
        "holdout_fixed_8k_1k_c32", "holdout_agent_append_c8", "holdout_agent_prefix_c8",
    }
    profiles = schedule.get("profiles")
    if not isinstance(profiles, list) or {profile.get("profile_id") for profile in profiles} != required_profiles:
        raise BundleError("replay profile set is not exact")
    if schedule.get("measurement_order") != [profile["profile_id"] for profile in profiles]:
        raise BundleError("replay measurement order is ambiguous")
    if schedule.get("phase_b_sequence") != {
        "cheapest_falsification_profiles": ["development_smoke", "fixed_8k_1k_c1", "fixed_8k_1k_c8"],
        "maximum_measured_requests_before_headline": 25,
        "headline_profile_only_after_prior_slo_pass": "fixed_8k_1k_c32",
    }:
        raise BundleError("phase-B falsification sequence drifted")
    for profile in profiles:
        if not isinstance(profile.get("request_count"), int) or profile["request_count"] <= 0:
            raise BundleError("replay request count is not explicit")
        if not isinstance(profile.get("max_concurrency"), int) or not 0 < profile["max_concurrency"] <= profile["request_count"]:
            raise BundleError("replay concurrency is invalid")
        if not isinstance(profile.get("arrival"), dict) or "kind" not in profile["arrival"]:
            raise BundleError("replay arrival schedule is missing")
        warmup = profile.get("warmup")
        if not isinstance(warmup, dict) or warmup.get("excluded_from_measurement") is not True or warmup.get("completion_required_before_measurement") is not True:
            raise BundleError("replay warmup policy is incomplete")
        cache = profile.get("cache")
        if not isinstance(cache, dict) or cache.get("reset_before_each_repetition") is not True:
            raise BundleError("replay cache policy is incomplete")
        expected_repetitions = 1 if profile.get("split") == "development" else 3
        if profile.get("repetitions") != expected_repetitions or profile.get("configuration_repetitions") != {
            "stock_bf16": expected_repetitions,
            "stock_tuned_bf16": expected_repetitions,
        }:
            raise BundleError("per-configuration replay repetitions drifted")


def validate_aa_geometry(geometry):
    if geometry.get("content_representation") != "length_only_geometry":
        raise BundleError("AA-AgentPerf proxy must remain length-only geometry")
    basis = geometry.get("public_basis", {})
    if (basis.get("minimum_input_tokens"), basis.get("maximum_input_tokens"), basis.get("approximate_mean_input_tokens")) != (5000, 131000, 27000):
        raise BundleError("AA-AgentPerf public length basis drifted")
    if geometry.get("source_artifact") != {
        "path": "../../../workloads/aa-agentperf-public-proxy-v1.json",
        "sha256": "11077a458480b8ac5ee2f78f7fa75dc95076eedfb13a30f53bb8163ec2ede1a1",
        "source_label": "local deterministic proxy derived from AA-AgentPerf public workload geometry",
    }:
        raise BundleError("AA-AgentPerf local proxy identity drifted")
    histogram = geometry.get("foundry_synthetic_length_histogram")
    if not isinstance(histogram, list) or sum(row.get("count", 0) for row in histogram) != 64:
        raise BundleError("AA-AgentPerf length-only histogram count drifted")
    total_tokens = sum(row.get("input_tokens", 0) * row.get("count", 0) for row in histogram)
    if total_tokens != 1_728_000:
        raise BundleError("AA-AgentPerf length-only histogram mean drifted")
    controls = geometry.get("synthetic_controls", {})
    if any(controls.get(key) is not False for key in ["output_tokens_are_imported", "arrival_process_is_imported", "prefix_identity_is_imported", "semantic_content_is_imported"]):
        raise BundleError("AA-AgentPerf non-length data was imported")
    gates = geometry.get("claim_gates", {})
    if any(gates.get(key) is not False for key in ["aa_agentperf_score_claim_permitted", "measured_performance_claim_permitted", "provider_performance_claim_permitted", "cost_claim_permitted"]):
        raise BundleError("AA-AgentPerf claim gates must fail closed")


if __name__ == "__main__":
    import sys
    try:
        result = load_and_validate(Path(__file__).resolve().parent)
    except BundleError as error:
        print(f"INVALID: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(result["manifest"]["bundle_sha256"])
