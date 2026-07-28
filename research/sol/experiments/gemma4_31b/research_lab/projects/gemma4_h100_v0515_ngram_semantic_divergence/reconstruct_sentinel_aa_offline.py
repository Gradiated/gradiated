#!/usr/bin/env python3
import hashlib
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, value):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main():
    binding_path = ROOT / "DIRECTOR_SENTINEL_AA_OFFLINE_RECONSTRUCTION_BINDING.json"
    binding = json.loads(binding_path.read_text())
    verified = {}
    superseded = ROOT / binding["supersedes"]["path"]
    superseded_actual = digest(superseded)
    verified["supersedes"] = {"path": binding["supersedes"]["path"], "expected": binding["supersedes"]["sha256"], "actual": superseded_actual, "pass": superseded_actual == binding["supersedes"]["sha256"]}
    for name, item in binding["immutable_inputs"].items():
        path = ROOT / item["path"]
        actual = digest(path)
        verified[name] = {"path": item["path"], "expected": item["sha256"], "actual": actual, "pass": actual == item["sha256"]}
    if not all(value["pass"] for value in verified.values()):
        raise RuntimeError("immutable_hash_mismatch")

    trace_path = ROOT / binding["immutable_inputs"]["trace"]["path"]
    trace = [json.loads(line) for line in trace_path.read_text().splitlines() if line]
    target = [row for row in trace if row.get("event") == "target_accept_kv"]
    scheduler = [row for row in trace if row.get("event") == "scheduler_emit"]
    errors = [row for row in trace if row.get("event") == "instrumentation_error"]
    scheduler_by_rid = {}
    for row in scheduler:
        scheduler_by_rid.setdefault(row["rid"], []).append(row)
    target_offsets = {}
    logical_kv_before = {}
    invariants = []
    for row in target:
        rid = row["rid"]
        offset = target_offsets.get(rid, 0)
        linked = scheduler_by_rid.get(rid, [])[offset] if offset < len(scheduler_by_rid.get(rid, [])) else None
        target_offsets[rid] = offset + 1
        accepted = row["accepted_tokens"]
        kv_before = logical_kv_before.get(rid, row["kv_committed_len_before"])
        raw_kv_delta = linked is not None and linked["kv_committed_len_after"] - row["kv_committed_len_before"] == row["accept_len"]
        carried_kv_delta = linked is not None and linked["kv_committed_len_after"] - kv_before == row["accept_len"]
        checks = {
            "target_equals_accepted": accepted == row["target_argmax_chain"],
            "accept_length": len(accepted) == row["accept_len"],
            "scheduler_equals_accepted": linked is not None and linked["scheduler_emitted_tokens"] == accepted,
            "kv_delta": raw_kv_delta or carried_kv_delta,
            "draft_row_slice": len(row["drafts"]) == 12,
            "not_padded": row["batch_row"] < row["raw_batch_size"],
        }
        invariants.append({"rid": rid, "step": offset, "raw_kv_committed_len_before": row["kv_committed_len_before"], "reconstructed_kv_committed_len_before": kv_before, "kv_predecessor_mode": "raw_trace" if raw_kv_delta else "prior_scheduler_relay" if carried_kv_delta else "none", "checks": checks, "pass": all(checks.values())})
        if linked is not None:
            logical_kv_before[rid] = linked["kv_committed_len_after"]

    response_paths = [
        "isolated_a_1_response",
        "isolated_a_2_response",
        "cobatched_ab_response",
    ]
    responses = []
    for key in response_paths:
        path = ROOT / binding["immutable_inputs"][key]["path"]
        responses.extend(json.loads(path.read_text()))
    response_facts = [{"rid": row["rid"], "length": len(row["output_ids"]), "sha256": hashlib.sha256(json.dumps(row["output_ids"], separators=(",", ":")).encode()).hexdigest(), "complete": isinstance(row["output_ids"], list) and len(row["output_ids"]) == 358} for row in responses]
    all_outputs_equal = len({fact["sha256"] for fact in response_facts}) == 1

    runtime_rids = sorted({row["rid"] for row in target})
    single_rids = sorted({row["rid"] for row in target if row["raw_batch_size"] == 1})
    cobatch_rids = sorted({row["rid"] for row in target if row["raw_batch_size"] == 2})
    if len(single_rids) != 2 or len(cobatch_rids) != 2:
        raise RuntimeError("unexpected_runtime_partition")
    arm_rows = json.loads((ROOT / binding["immutable_inputs"]["arms"]["path"]).read_text())["arms"]
    logical = {
        "isolated_a": [arm_rows[0]["bodies"][0]["request_id"], arm_rows[1]["bodies"][0]["request_id"]],
        "cobatched": [body["request_id"] for body in arm_rows[2]["bodies"]],
    }
    permutations = []
    for order in itertools.permutations(cobatch_rids):
        mapping = dict(zip(logical["cobatched"], order))
        permutations.append({"logical_to_runtime_rid": mapping, "linked_output_sha256s": [fact["sha256"] for fact in response_facts if fact["rid"] in mapping]})
    mapping_invariant = len({tuple(row["linked_output_sha256s"]) for row in permutations}) == 1
    conditions = {
        "trace_shape": len(trace) == 256 and len(target) == 128 and len(scheduler) == 128 and not errors,
        "invariants": len(invariants) == 128 and all(row["pass"] for row in invariants),
        "responses": len(response_facts) == 4 and all(row["complete"] for row in response_facts) and all_outputs_equal,
        "runtime_partition": len(runtime_rids) == 4 and len(single_rids) == 2 and len(cobatch_rids) == 2,
        "permutation_invariant": mapping_invariant and len(permutations) == 2,
    }
    classification = "sentinel_exact_equivalence_class" if all(conditions.values()) else "typed_indeterminate_mapping_sensitive"
    result = {
        "schema_version": 1,
        "classification": classification,
        "immutable_hashes": verified,
        "trace_summary": {"rows": len(trace), "target_accept_rows": len(target), "scheduler_rows": len(scheduler), "instrumentation_errors": errors, "runtime_rids": runtime_rids},
        "invariants": {"total": len(invariants), "passing": sum(row["pass"] for row in invariants), "rows": invariants},
        "responses": {"facts": response_facts, "all_complete_358": all(row["complete"] for row in response_facts), "all_identical": all_outputs_equal},
        "provenance": {"isolated_runtime_rids": single_rids, "co_batched_runtime_rid_equivalence_class": cobatch_rids, "logical_labels": logical, "permitted_co_batch_assignments": permutations, "exact_rid_to_logical_label_unobserved": True, "mapping_invariant": mapping_invariant},
        "decision_conditions": conditions,
        "historical_request_277": "unresolved_and_not_replayed",
    }
    atomic(ROOT / "SENTINEL_AA_OFFLINE_RECONSTRUCTION_RESULT.json", result)
    terminal = {"schema_version": 1, "classification": classification, "actual_spend_usd": 0.9055, "result_sha256": digest(ROOT / "SENTINEL_AA_OFFLINE_RECONSTRUCTION_RESULT.json"), "provider_or_gpu_used": False, "historical_request_277": "unresolved_and_not_replayed"}
    atomic(ROOT / "SENTINEL_AA_OFFLINE_RECONSTRUCTION_TERMINAL.json", terminal)
    status = json.loads((ROOT / "STATUS.json").read_text())
    status.update({"status": "complete", "active_session": None, "actual_spend_usd": 0.9055, "summary": classification, "next_action": "Decision-bearing offline reconstruction is complete; historical request 277 remains unresolved.", "terminal_artifact": "SENTINEL_AA_OFFLINE_RECONSTRUCTION_TERMINAL.json"})
    atomic(ROOT / "STATUS.json", status)
    print(json.dumps({"classification": classification, "conditions": conditions}, sort_keys=True))


if __name__ == "__main__":
    main()
