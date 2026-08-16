#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pathlib
import re
import tarfile
from collections.abc import Sequence


PROJECT = pathlib.Path(__file__).resolve().parent
EXPECTED_HASHES = {
    "archive": "7b646b16e77121eda710b6b05b49fc8cfe139816c894fbe391f66a2ab257ca53",
    "control_oracle": "5ae3ee1ef81641e778a08063d56cd62c4659470b2da695d8d8bc3e27779dbf7b",
    "director_binding": "97a92eebf8cdf7aebe443ea03a75ce392ae9c5fd5f713717eec14bf5e0137914",
    "endpoint_terminal": "98d8643f5d563943c4f88cd24edaa52872fb20a5f95af9a8f6b5c87a57e50ed5",
}
EXPECTED_REQUESTS = 32
EXPECTED_OUTPUT_TOKENS = 358
EXPECTED_PROMPT_TOKENS = 4214


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def member_bytes(archive: tarfile.TarFile, name: str) -> bytes:
    member = archive.getmember(name)
    handle = archive.extractfile(member)
    if handle is None:
        raise RuntimeError(f"archive_member_unreadable:{name}")
    return handle.read()


def jsonl(value: bytes) -> list[dict]:
    return [json.loads(line) for line in value.splitlines() if line.strip()]


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


class GemmaTokenizerDecoder:
    def __init__(self, path: pathlib.Path) -> None:
        value = json.loads(path.read_text())
        require(value["model"]["type"] == "BPE", "tokenizer_model_not_bpe")
        decoder = value.get("decoder", {})
        require(decoder.get("type") == "Sequence", "tokenizer_decoder_not_sequence")
        decoder_types = [row.get("type") for row in decoder.get("decoders", [])]
        require(
            decoder_types == ["Replace", "ByteFallback", "Fuse"],
            f"tokenizer_decoder_contract_changed:{decoder_types}",
        )
        replace = decoder["decoders"][0]
        require(
            replace.get("pattern", {}).get("String") == "▁"
            and replace.get("content") == " ",
            "tokenizer_replace_contract_changed",
        )
        self.tokens = {token_id: token for token, token_id in value["model"]["vocab"].items()}
        self.special = {
            row["id"] for row in value.get("added_tokens", []) if row.get("special")
        }
        for row in value.get("added_tokens", []):
            self.tokens.setdefault(row["id"], row["content"])

    def decode(self, token_ids: Sequence[int]) -> str:
        value = bytearray()
        for token_id in token_ids:
            if token_id in self.special:
                continue
            require(token_id in self.tokens, f"token_id_unknown:{token_id}")
            token = self.tokens[token_id].replace("▁", " ")
            byte_token = re.fullmatch(r"<0x([0-9A-Fa-f]{2})>", token)
            if byte_token:
                value.append(int(byte_token.group(1), 16))
            else:
                value.extend(token.encode())
        return value.decode("utf-8", errors="replace")

    def token_text(self, token_id: int) -> str:
        return self.decode([token_id])


def parse_response(raw: bytes) -> dict:
    request_ids: set[str] = set()
    text: list[str] = []
    usage: dict | None = None
    done = False
    for line in raw.splitlines():
        if not line.startswith(b"data: "):
            continue
        if line.strip() == b"data: [DONE]":
            done = True
            continue
        row = json.loads(line[6:])
        request_id = row.get("id")
        if request_id:
            request_ids.add(request_id)
        choices = row.get("choices") or []
        if choices:
            text.append(choices[0].get("text") or "")
        if row.get("usage"):
            usage = row["usage"]
    require(len(request_ids) == 1, f"response_rid_ambiguous:{sorted(request_ids)}")
    require(done, f"response_done_missing:{sorted(request_ids)}")
    require(isinstance(usage, dict), f"response_usage_missing:{sorted(request_ids)}")
    return {"rid": next(iter(request_ids)), "text": "".join(text), "usage": usage}


def first_divergence(control: Sequence[int], candidate: Sequence[int]) -> int | None:
    for position, pair in enumerate(zip(control, candidate)):
        if pair[0] != pair[1]:
            return position
    if len(control) != len(candidate):
        return min(len(control), len(candidate))
    return None


def localize(
    archive_path: pathlib.Path,
    terminal_path: pathlib.Path,
    oracle_path: pathlib.Path,
    tokenizer_path: pathlib.Path,
    binding_path: pathlib.Path,
) -> dict:
    observed_hashes = {
        "archive": digest(archive_path),
        "control_oracle": digest(oracle_path),
        "director_binding": digest(binding_path),
        "endpoint_terminal": digest(terminal_path),
        "tokenizer": digest(tokenizer_path),
        "candidate_resume_source": digest(PROJECT / "inputs/endpoint/candidate_resume.py"),
        "decode_equivalent_lm_head_source": digest(
            PROJECT / "inputs/endpoint/decode_equivalent_lm_head.py"
        ),
        "sitecustomize_source": digest(PROJECT / "inputs/endpoint/sitecustomize.py"),
        "token_oracle_source": digest(PROJECT / "inputs/endpoint/token_oracle.py"),
        "token_trace_hook_source": digest(PROJECT / "inputs/endpoint/token_trace_hook.py"),
        "packed_endpoint_source": digest(PROJECT / "inputs/endpoint/packed_m384_endpoint.py"),
    }
    for name, expected in EXPECTED_HASHES.items():
        require(observed_hashes[name] == expected, f"source_hash_mismatch:{name}")

    standalone_terminal_raw = terminal_path.read_bytes()
    endpoint_terminal = json.loads(standalone_terminal_raw)
    endpoint_sources = endpoint_terminal["identity"]["files"]
    for member, observed_name in {
        "input/candidate_resume.py": "candidate_resume_source",
        "input/decode_equivalent_lm_head.py": "decode_equivalent_lm_head_source",
        "input/packed_m384_endpoint.py": "packed_endpoint_source",
        "input/sitecustomize.py": "sitecustomize_source",
        "input/token_oracle.py": "token_oracle_source",
        "input/token_trace_hook.py": "token_trace_hook_source",
    }.items():
        require(
            endpoint_sources[member]["sha256"] == observed_hashes[observed_name],
            f"endpoint_source_identity_mismatch:{member}",
        )
    oracle = json.loads(oracle_path.read_text())
    decoder = GemmaTokenizerDecoder(tokenizer_path)

    with tarfile.open(archive_path, "r:gz") as archive:
        archived_terminal_raw = member_bytes(archive, "artifacts/ENDPOINT_TERMINAL.json")
        candidate_terminal_raw = member_bytes(archive, "artifacts/candidate/TERMINAL.json")
        events_raw = member_bytes(archive, "artifacts/candidate.token-events.jsonl")
        responses = {
            index: member_bytes(archive, f"artifacts/candidate/response-{index:02d}.sse")
            for index in range(EXPECTED_REQUESTS)
        }
        request_rows = {
            index: json.loads(
                member_bytes(archive, f"artifacts/candidate/request-{index:02d}.json")
            )
            for index in range(EXPECTED_REQUESTS)
        }
    require(
        archived_terminal_raw == standalone_terminal_raw,
        "archived_endpoint_terminal_differs_from_bound_terminal",
    )
    candidate_terminal = json.loads(candidate_terminal_raw)
    events = jsonl(events_raw)
    observed_hashes.update(
        {
            "archived_endpoint_terminal_member": digest_bytes(archived_terminal_raw),
            "candidate_terminal_member": digest_bytes(candidate_terminal_raw),
            "candidate_token_events_member": digest_bytes(events_raw),
        }
    )

    control_rows = oracle.get("rows")
    candidate_rows = candidate_terminal.get("rows")
    require(
        isinstance(control_rows, list)
        and isinstance(candidate_rows, list)
        and len(control_rows) == len(candidate_rows) == EXPECTED_REQUESTS,
        "request_row_count_invalid",
    )
    control_by_request = {row["request_sha256"]: row for row in control_rows}
    require(len(control_by_request) == EXPECTED_REQUESTS, "control_request_hash_duplicate")
    candidate_hashes = [row["request_sha256"] for row in candidate_rows]
    control_hashes = [row["request_sha256"] for row in control_rows]
    require(candidate_hashes == control_hashes, "ordered_request_hashes_mismatch")

    target_ids_by_rid: dict[str, list[int]] = collections.defaultdict(list)
    scheduler_rows_by_rid: dict[str, list[dict]] = collections.defaultdict(list)
    final_rows_by_rid: dict[str, list[dict]] = collections.defaultdict(list)
    warmup_rids: set[str] = set()
    prior_at = -float("inf")
    for event_ordinal, event in enumerate(events):
        rid = event.get("rid")
        require(isinstance(rid, str), f"event_rid_missing:{event_ordinal}")
        at_monotonic = event.get("at_monotonic")
        require(
            isinstance(at_monotonic, (int, float)) and at_monotonic >= prior_at,
            f"event_order_invalid:{event_ordinal}",
        )
        prior_at = at_monotonic
        stage = event.get("stage")
        if stage == "scheduler_to_detokenizer":
            values = event.get("scheduler_output_ids_delta")
            require(
                isinstance(values, list) and all(isinstance(item, int) for item in values),
                f"scheduler_delta_invalid:{event_ordinal}:{rid}",
            )
            target_ids_by_rid[rid].extend(values)
            scheduler_rows_by_rid[rid].append(event)
            require(
                event.get("completion_counter") == len(target_ids_by_rid[rid]),
                f"scheduler_completion_counter_invalid:{event_ordinal}:{rid}",
            )
        elif stage == "post_generation_pre_parser_final":
            final_rows_by_rid[rid].append(event)
        else:
            raise RuntimeError(f"event_stage_unknown:{event_ordinal}:{stage}")

    localized_rows: list[dict] = []
    candidate_rids: set[str] = set()
    for index in range(EXPECTED_REQUESTS):
        candidate_row = candidate_rows[index]
        request_row = request_rows[index]
        raw_response = responses[index]
        response = parse_response(raw_response)
        rid = response["rid"]
        candidate_rids.add(rid)
        require(candidate_row["index"] == request_row["index"] == index, f"index_mismatch:{index}")
        require(candidate_row == request_row, f"request_row_member_mismatch:{index}")
        require(
            digest_bytes(raw_response) == candidate_row["response_sha256"],
            f"response_digest_mismatch:{index}",
        )
        require(
            response["usage"].get("prompt_tokens") == EXPECTED_PROMPT_TOKENS
            and response["usage"].get("completion_tokens") == EXPECTED_OUTPUT_TOKENS,
            f"response_usage_invalid:{index}",
        )
        require(rid not in warmup_rids, f"candidate_rid_reused:{index}:{rid}")
        target_ids = target_ids_by_rid[rid]
        scheduler_rows = scheduler_rows_by_rid[rid]
        finals = final_rows_by_rid[rid]
        require(len(target_ids) == EXPECTED_OUTPUT_TOKENS, f"candidate_token_count:{index}")
        require(len(finals) == 1, f"candidate_final_count:{index}:{len(finals)}")
        final = finals[0]
        final_ids = final.get("emitted_token_ids")
        final_scheduler_ids = final.get("scheduler_output_ids")
        final_delta = scheduler_rows[-1]["scheduler_output_ids_delta"]
        require(
            final_ids == final_scheduler_ids == final_delta,
            f"final_target_emitted_transition_mismatch:{index}:{rid}",
        )
        require(
            final.get("completion_counter") == EXPECTED_OUTPUT_TOKENS
            and final.get("prompt_tokens") == EXPECTED_PROMPT_TOKENS,
            f"candidate_final_counter_invalid:{index}:{rid}",
        )
        require(
            bytes.fromhex(final["parser_input_utf8_hex"]).decode("utf-8")
            == decoder.decode(final_ids),
            f"final_parser_bytes_mismatch:{index}:{rid}",
        )
        require(
            response["text"] == decoder.decode(target_ids),
            f"stream_text_mismatch:{index}:{rid}",
        )

        control_row = control_by_request[candidate_row["request_sha256"]]
        control_ids = control_row["emitted_token_ids"]
        position = first_divergence(control_ids, target_ids)
        mismatch_count = sum(left != right for left, right in zip(control_ids, target_ids))
        row = {
            "index": index,
            "request_sha256": candidate_row["request_sha256"],
            "control_rid": control_row["rid"],
            "candidate_rid": rid,
            "status": "exact" if position is None else "divergent",
            "first_divergent_token_position_zero_based": position,
            "matching_prefix_tokens": EXPECTED_OUTPUT_TOKENS if position is None else position,
            "mismatched_token_count": mismatch_count,
            "first_target_to_emitted_inconsistency": None,
        }
        if position is not None:
            row.update(
                {
                    "control_token_id": control_ids[position],
                    "control_token_text": decoder.token_text(control_ids[position]),
                    "candidate_token_id": target_ids[position],
                    "candidate_token_text": decoder.token_text(target_ids[position]),
                }
            )
        localized_rows.append(row)

    extra_rids = set(target_ids_by_rid) - candidate_rids
    require(len(extra_rids) == 1, f"warmup_rid_count_invalid:{sorted(extra_rids)}")
    warmup_rid = next(iter(extra_rids))
    require(
        len(target_ids_by_rid[warmup_rid]) == 1
        and len(final_rows_by_rid[warmup_rid]) == 1,
        f"warmup_trace_invalid:{warmup_rid}",
    )

    affected = [row for row in localized_rows if row["status"] == "divergent"]
    exact = [row for row in localized_rows if row["status"] == "exact"]
    gates = endpoint_terminal["gates"]
    require(
        gates["exact_request_hashes"]
        and not gates["exact_persisted_control_target_tokens"]
        and not gates["exact_target_to_emitted_trace"],
        "bound_terminal_gate_classification_changed",
    )
    require(len(affected) > 0, "expected_semantic_divergence_missing")

    return {
        "schema_version": 1,
        "type": "packed_m384_offline_semantic_localization_result",
        "project": "gemma4_hopper_packed_m384_verifier",
        "source_artifact_hashes": observed_hashes,
        "request_join_method": {
            "primary_key": "request_sha256",
            "candidate_response_to_event_join": "unique SSE id -> token-event rid",
            "control_join": "candidate request_sha256 -> bound oracle request_sha256",
            "event_order": "archive JSONL order cross-checked as nondecreasing at_monotonic and cumulative completion_counter",
            "row_position_used_as_semantic_join": False,
            "completion_order_used_as_semantic_join": False,
            "ordered_request_hashes_exact": True,
            "unique_control_request_hashes": EXPECTED_REQUESTS,
            "unique_candidate_response_rids": len(candidate_rids),
            "excluded_warmup_rid": warmup_rid,
        },
        "first_divergence_by_request": localized_rows,
        "divergence_summary": {
            "complete_requests": EXPECTED_REQUESTS,
            "exact_requests": len(exact),
            "divergent_requests": len(affected),
            "divergent_at_first_token": sum(
                row["first_divergent_token_position_zero_based"] == 0 for row in affected
            ),
            "latest_first_divergence_position_zero_based": max(
                row["first_divergent_token_position_zero_based"] for row in affected
            ),
        },
        "target_to_emitted_trace_diagnosis": {
            "classification": "internally_consistent_no_observer_or_emission_divergence",
            "candidate_scheduler_events": sum(
                len(scheduler_rows_by_rid[rid]) for rid in candidate_rids
            ),
            "candidate_final_events": sum(len(final_rows_by_rid[rid]) for rid in candidate_rids),
            "scheduler_completion_counter_inconsistencies": 0,
            "final_scheduler_to_emitted_inconsistencies": 0,
            "final_parser_byte_inconsistencies": 0,
            "full_stream_text_decode_inconsistencies": 0,
            "candidate_requests_with_first_target_to_emitted_inconsistency": 0,
            "interpretation": (
                "For every candidate request, accumulated scheduler token deltas decode "
                "exactly to the complete SSE text after special-token removal; the final "
                "scheduler delta, tokenizer emitted IDs, and parser bytes also agree."
            ),
        },
        "observer_or_computation_classification": {
            "classification": "genuine_candidate_computation_divergence_before_detokenization",
            "observer_defect": False,
            "request_identity_join_defect": False,
            "serialization_or_result_construction_defect": False,
            "server_emission_path_defect": False,
            "candidate_computation_divergence": True,
            "scope": (
                f"{len(affected)} of {EXPECTED_REQUESTS} hash-identical requests differ "
                "in scheduler token IDs, including "
                f"{sum(row['first_divergent_token_position_zero_based'] == 0 for row in affected)} "
                "at token zero, while all scheduler-to-SSE transitions are exact. "
                "The immutable bytes cannot localize further than the candidate-only "
                "upstream compute path because no logits or margins were persisted."
            ),
            "supporting_component_evidence": {
                "local_d256_relative_l2": 0.026936529204249382,
                "global_d512_relative_l2": 0.029003974050283432,
                "interpretation": (
                    "The settled component gate allowed numerical rather than exact "
                    "equivalence; the endpoint token result therefore supersedes it "
                    "for semantic promotion."
                ),
            },
        },
        "offline_decision_terminal_rebuild": {
            "performed": False,
            "reason": (
                "The original reject gates are reproduced after identity-correct offline "
                "joining; no observer or result-construction repair is supported."
            ),
        },
        "endpoint_performance_disposition": {
            "candidate_service_seconds_per_request": endpoint_terminal[
                "candidate_service_seconds_per_request"
            ],
            "control_service_seconds_per_request": endpoint_terminal[
                "control_service_seconds_per_request"
            ],
            "service_reduction_fraction": endpoint_terminal["service_reduction_fraction"],
            "timing_measurement_valid": True,
            "promotion_safe": False,
            "classification": "semantic_unsafe_performance_positive",
            "component_result_preserved": True,
        },
        "candidate_replay_performed": False,
        "control_replay_performed": False,
        "component_replay_performed": False,
        "gpu_claim_performed": False,
        "next_portfolio_implication": {
            "this_endpoint_candidate": "closed_semantic_unsafe",
            "positive_component": "retain_as_physical_evidence_not_deployment_candidate",
            "smallest_materially_different_future_discriminator": (
                "Capture native-versus-packed logits, top-2 token IDs/margins, and the "
                "attention output at the first target-verification step for the earliest "
                "divergent hash-bound request, using a newly admitted non-replay run."
            ),
            "scheduled_by_this_result": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--archive",
        type=pathlib.Path,
        default=PROJECT / "artifacts/graph-repair/attempt-2/artifacts.tar.gz",
    )
    parser.add_argument(
        "--terminal",
        type=pathlib.Path,
        default=PROJECT / "artifacts/graph-repair/attempt-2/ENDPOINT_TERMINAL.json",
    )
    parser.add_argument(
        "--oracle",
        type=pathlib.Path,
        default=PROJECT / "inputs/endpoint/CONTROL_TOKEN_ORACLE.json",
    )
    parser.add_argument(
        "--tokenizer",
        type=pathlib.Path,
        default=PROJECT / "inputs/checkpoint/tokenizer.json",
    )
    parser.add_argument(
        "--binding",
        type=pathlib.Path,
        default=PROJECT / "DIRECTOR_H100_PACKED_M384_SEMANTIC_LOCALIZATION_20260726T1904Z.json",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=PROJECT / "SEMANTIC_LOCALIZATION_RESULT.json",
    )
    args = parser.parse_args()
    result = localize(
        args.archive.resolve(),
        args.terminal.resolve(),
        args.oracle.resolve(),
        args.tokenizer.resolve(),
        args.binding.resolve(),
    )
    atomic(args.output.resolve(), result)
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "sha256": digest(args.output.resolve()),
                "classification": result["observer_or_computation_classification"][
                    "classification"
                ],
                "divergent_requests": result["divergence_summary"]["divergent_requests"],
                "exact_requests": result["divergence_summary"]["exact_requests"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
