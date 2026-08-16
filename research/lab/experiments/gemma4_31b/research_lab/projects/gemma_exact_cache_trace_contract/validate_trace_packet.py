#!/usr/bin/env python3
"""Offline validator for TRACE_PACKET.json; writes a typed terminal."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PACKET = ROOT / "TRACE_PACKET.json"
TERMINAL = ROOT / "TRACE_TERMINAL.json"
TOKENIZER = (
    ROOT.parent
    / "sglang_h200_matched_endpoint_falsifier"
    / "artifacts/checkpoint-owner-20260717T072831Z/checkpoint/tokenizer.json"
)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def lcp(left: list[int], right: list[int]) -> int:
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    return min(len(left), len(right))


def main() -> int:
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}
    try:
        packet = json.loads(PACKET.read_text())
        tokenizer = json.loads(TOKENIZER.read_text())
        special = {int(row["id"]) for row in tokenizer["added_tokens"] if row.get("special")}
        vocab_size = len(tokenizer["model"]["vocab"])
        checks["schema"] = packet["schema_version"] == 1 and packet["kind"] == "exact_gemma_primary_cache_trace_contract"
        checks["model_revision"] = packet["identity"]["model"] == "google/gemma-4-31B-it" and packet["identity"]["revision"] == "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
        checks["tokenizer_identity"] = packet["identity"]["tokenizer_json_sha256"] == sha(TOKENIZER.read_bytes()) and packet["identity"]["tokenizer_vocab_size"] == vocab_size
        checks["exact_image_runtime"] = packet["identity"]["runtime_observed_vllm"] == "0.19.1.dev6+g6d4a8e6d2"
        checks["cache_arithmetic"] = packet["target"]["nearest_integer_common_prefix_tokens"] == 535 and packet["target"]["block_size_tokens"] == 16 and packet["target"]["maximum_cacheable_common_tokens"] == 528
        checks["group_geometry"] = [g["concurrency"] for g in packet["primary_groups"]] == [1, 4, 8, 16]

        all_primary: list[tuple[str, list[int]]] = []
        suffix_hashes: list[str] = []
        request_ids: list[str] = []
        intra_lcps: dict[str, list[int]] = {}
        bodies_valid = True
        ids_valid = True
        exact_lengths = True
        for group in packet["primary_groups"]:
            records = [group["warmup"], *group["scored"]]
            prompts = [row["request_body"]["prompt"] for row in records]
            exact_lengths &= len(records[1:]) == group["concurrency"] and all(len(p) == 4214 for p in prompts)
            group_lcps = [lcp(prompts[i], prompts[j]) for i in range(len(prompts)) for j in range(i + 1, len(prompts))]
            intra_lcps[group["name"]] = group_lcps
            for row in records:
                body = row["request_body"]
                prompt = body["prompt"]
                expected_output = 1 if row["role"] == "warmup" else 358
                ids_valid &= all(isinstance(x, int) and 0 <= x < vocab_size and x not in special for x in prompt)
                bodies_valid &= (
                    "prompt_token_ids" not in body
                    and body.get("add_special_tokens") is False
                    and body.get("max_tokens") == expected_output
                    and body.get("min_tokens") == expected_output
                    and body.get("ignore_eos") is True
                    and body.get("return_token_ids") is True
                    and row["prompt_tokens_sha256"] == sha(canonical(prompt))
                    and row["request_body_sha256"] == sha(canonical(body))
                )
                request_ids.append(row["request_id"])
                suffix_hashes.append(sha(canonical(prompt[535:])))
                all_primary.append((row["request_id"], prompt))

        checks["exact_prompt_and_scored_output_lengths"] = exact_lengths
        checks["token_ids_in_verified_vocab_and_not_special"] = ids_valid
        checks["request_schema_and_content_hashes"] = bodies_valid
        checks["intra_group_lcp_exact_535"] = all(all(value == 535 for value in values) for values in intra_lcps.values())
        cross_lcps = [
            lcp(a_prompt, b_prompt)
            for a_index, (a_id, a_prompt) in enumerate(all_primary)
            for b_id, b_prompt in all_primary[a_index + 1 :]
            if a_id.split("-")[2] != b_id.split("-")[2]
        ]
        # The request ID split above is intentionally not relied on for the final
        # cross-group proof: compare each group's first prompt explicitly.
        group_firsts = [g["warmup"]["request_body"]["prompt"] for g in packet["primary_groups"]]
        cross_group_first_lcps = [lcp(group_firsts[i], group_firsts[j]) for i in range(4) for j in range(i + 1, 4)]
        checks["cross_group_lcp_zero"] = all(value == 0 for value in cross_group_first_lcps)
        checks["all_suffixes_distinct"] = len(suffix_hashes) == len(set(suffix_hashes))
        checks["request_ids_unique"] = len(request_ids) == len(set(request_ids))

        separate = packet["separate_10k_stream"]
        separate_body = separate["request_body"]
        separate_prompt = separate_body["prompt"]
        separate_lcps = [lcp(separate_prompt, prompt) for _, prompt in all_primary]
        checks["separate_10k_exact_and_disjoint"] = (
            len(separate_prompt) == 10000
            and all(value == 0 for value in separate_lcps)
            and separate_body.get("max_tokens") == 358
            and separate_body.get("min_tokens") == 358
            and separate_body.get("add_special_tokens") is False
            and separate["prompt_tokens_sha256"] == sha(canonical(separate_prompt))
            and separate["request_body_sha256"] == sha(canonical(separate_body))
        )
        checks["runner_contract"] = (
            packet["runner_contract"]["required_request_field"] == "prompt"
            and packet["runner_contract"]["forbidden_request_field"] == "prompt_token_ids"
            and "delta(vllm:prefix_cache_hits)" in packet["runner_contract"]["cache_metric_equation"]
            and "maximum simultaneous in-flight" in packet["runner_contract"]["barrier_assertion"]
        )
        details = {
            "intra_group_pairwise_lcp_unique_values": {k: sorted(set(v)) for k, v in intra_lcps.items()},
            "cross_group_first_prompt_lcps": cross_group_first_lcps,
            "separate_10k_to_primary_lcp_unique_values": sorted(set(separate_lcps)),
            "primary_requests_including_warmups": len(all_primary),
            "scored_primary_requests": sum(g["concurrency"] for g in packet["primary_groups"]),
            "unique_suffix_hashes": len(set(suffix_hashes)),
            "intended_common_fraction": 535 / 4214,
            "maximum_cacheable_fraction": 528 / 4214,
        }
    except Exception as exc:
        checks["validator_exception_free"] = False
        details = {"exception_type": type(exc).__name__, "message": str(exc)}
    else:
        checks["validator_exception_free"] = True

    passed = all(checks.values())
    terminal = {
        "schema_version": 1,
        "kind": "exact_gemma_cache_trace_terminal",
        "status": "pass" if passed else "none",
        "pass": passed,
        "classification": "offline deterministic trace validation; no live cache realization claim",
        "checks": checks,
        "details": details,
        "trace_packet_sha256": sha(PACKET.read_bytes()) if PACKET.exists() else None,
        "validator_sha256": sha(Path(__file__).read_bytes()),
        "finished_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "provider_mutation": "forbidden_and_not_attempted",
        "spend_usd": 0.0,
        "next_action": (
            "Offer the packet to the active exact-image owner only if it does not delay or weaken that owner's final-program gate; live hit/query deltas remain mandatory."
            if passed
            else "Do not consume the packet; inspect failed checks."
        ),
    }
    TERMINAL.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
