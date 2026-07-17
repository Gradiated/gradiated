#!/usr/bin/env python3
"""Build the deterministic exact-Gemma cache-trace packet.

This is intentionally stdlib-only.  Token IDs are submitted directly through
vLLM's CompletionRequest.prompt field, so construction needs the verified
tokenizer vocabulary and special-token identities but no host tokenizer wheel.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CHECKPOINT = (
    ROOT.parent
    / "sglang_h200_matched_endpoint_falsifier"
    / "artifacts/checkpoint-owner-20260717T072831Z/checkpoint"
)
TOKENIZER = CHECKPOINT / "tokenizer.json"
TOKENIZER_CONFIG = CHECKPOINT / "tokenizer_config.json"
MODEL = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
IMAGE = (
    "vllm/vllm-openai:gemma4@sha256:"
    "952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
)
IMAGE_VLLM = "0.19.1.dev6+g6d4a8e6d2"
SEED = "gemma4-exact-cache-trace-v1-20260717"
INPUT_TOKENS = 4214
OUTPUT_TOKENS = 358
COMMON_TOKENS = 535
BLOCK_SIZE = 16
MAX_CACHEABLE = (COMMON_TOKENS // BLOCK_SIZE) * BLOCK_SIZE
VOCAB_MIN = 1000
VOCAB_MAX_EXCLUSIVE = 250000


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def token_stream(label: str, count: int) -> list[int]:
    span = VOCAB_MAX_EXCLUSIVE - VOCAB_MIN
    out: list[int] = []
    counter = 0
    while len(out) < count:
        digest = hashlib.sha256(f"{SEED}|{label}|{counter}".encode()).digest()
        for offset in range(0, len(digest), 4):
            out.append(VOCAB_MIN + int.from_bytes(digest[offset : offset + 4], "big") % span)
            if len(out) == count:
                break
        counter += 1
    return out


def request_record(request_id: str, prompt: list[int], output_tokens: int) -> dict:
    body = {
        "model": MODEL,
        "prompt": prompt,
        "max_tokens": output_tokens,
        "min_tokens": output_tokens,
        "ignore_eos": True,
        "temperature": 0,
        "seed": 20260717,
        "stop": [],
        "stop_token_ids": [],
        "stream": True,
        "stream_options": {"include_usage": True},
        "return_token_ids": True,
        "add_special_tokens": False,
        "request_id": request_id,
    }
    return {
        "request_id": request_id,
        "prompt_tokens_sha256": sha_bytes(canonical_bytes(prompt)),
        "request_body_sha256": sha_bytes(canonical_bytes(body)),
        "request_body": body,
    }


def main() -> None:
    tokenizer = json.loads(TOKENIZER.read_text())
    vocab = tokenizer["model"]["vocab"]
    special_ids = sorted(
        int(row["id"]) for row in tokenizer["added_tokens"] if row.get("special") is True
    )
    assert len(vocab) == 262144
    assert not set(range(VOCAB_MIN, VOCAB_MAX_EXCLUSIVE)).intersection(special_ids)

    groups = []
    all_primary: list[dict] = []
    for group_index, concurrency in enumerate((1, 4, 8, 16)):
        name = f"primary_c{concurrency}"
        prefix = token_stream(f"{name}|prefix", COMMON_TOKENS)
        # Make cross-group LCP zero by construction, independently of PRNG output.
        prefix[0] = 180000 + group_index
        members = []
        for member_index, role in enumerate(["warmup"] + [f"scored_{i}" for i in range(concurrency)]):
            suffix = token_stream(f"{name}|{role}|suffix", INPUT_TOKENS - COMMON_TOKENS)
            # Distinct first suffix token proves that no member shares token 536.
            suffix[0] = 200000 + group_index * 100 + member_index
            output_tokens = 1 if role == "warmup" else OUTPUT_TOKENS
            record = request_record(f"cache-{name}-{role}", prefix + suffix, output_tokens)
            record["role"] = role
            members.append(record)
            all_primary.append(record)
        warmup, scored = members[0], members[1:]
        groups.append(
            {
                "name": name,
                "concurrency": concurrency,
                "warmup": warmup,
                "scored": scored,
                "common_prefix_tokens": COMMON_TOKENS,
                "maximum_cacheable_common_tokens": MAX_CACHEABLE,
                "ordering": [
                    "capture raw Prometheus snapshot before_warmup",
                    "submit only warmup; wait for HTTP terminal, one generated token, and exact 4214 server prompt tokens",
                    "capture raw Prometheus snapshot after_warmup",
                    f"arm a {concurrency + 1}-party start barrier, then release exactly {concurrency} scored requests together",
                    "wait for every scored stream terminal and atomically persist raw responses",
                    "capture raw Prometheus snapshot after_scored",
                ],
                "metrics_assertions": {
                    "warmup_query_delta_tokens": INPUT_TOKENS,
                    "scored_query_delta_tokens": concurrency * INPUT_TOKENS,
                    "maximum_scored_hit_delta_tokens_if_prefix_resident": concurrency * MAX_CACHEABLE,
                    "realized_cached_prompt_fraction_formula": (
                        "(prefix_cache_hits_after_scored-prefix_cache_hits_after_warmup) / "
                        "sum(scored server usage.prompt_tokens)"
                    ),
                    "contamination_guard": (
                        "0 <= scored hit delta <= concurrency*528 and scored query delta == concurrency*4214; "
                        "otherwise the group is invalid, not a cache claim"
                    ),
                },
            }
        )

    separate_ids = token_stream("separate_10k_single_stream", 10000)
    separate_ids[0] = 190000
    separate = request_record("cache-separate-10k", separate_ids, OUTPUT_TOKENS)
    separate.update(
        {
            "role": "scored_separate_single_stream",
            "concurrency": 1,
            "input_tokens": 10000,
            "output_tokens": OUTPUT_TOKENS,
            "ordering": "run after the primary groups with its own before/after metrics snapshots",
            "cache_assertion": (
                "pairwise LCP with every primary request is zero; require query delta 10000 and hit delta zero"
            ),
        }
    )

    source_evidence = {
        "schema_version": 1,
        "classification": "measured CPU-safe inspection inside exact immutable image",
        "image": IMAGE,
        "observed_vllm_version": IMAGE_VLLM,
        "exact_image_files_sha256": {
            "vllm/entrypoints/openai/completion/protocol.py": "d529d72221c54beb3b2ddd54aa431b6bb6f9c7f0553db57768d8a1bf5f8d9b20",
            "vllm/config/cache.py": "0f5728cafef37cc6af9b4ebc440a2cf0458e49f28f39268e20399aae15c696b3",
            "vllm/v1/core/kv_cache_utils.py": "3bccb51ba52e0a42422ff2f91ee55cf82ae1a71f8a839fa97281352d324da1a4",
            "vllm/v1/core/kv_cache_manager.py": "0df69b7626195cbaabb33013d1e05ba6660243369171367f87313e4221bfffc8",
            "vllm/v1/metrics/loggers.py": "1720518a60a492add47b8d6a30d6aee86c097c25bc5b11edb2affead9cad2ba6",
        },
        "observed_contract": {
            "completion_token_id_field": "prompt",
            "forbidden_non_schema_field": "prompt_token_ids",
            "add_special_tokens_must_be_false": True,
            "default_cache_block_tokens": BLOCK_SIZE,
            "hashing": "only full 16-token blocks are hashed",
            "cache_hit_limit": "request.num_tokens-1, then block-aligned; last prompt token must be recomputed",
            "query_counter_semantics": "request.num_tokens per cache lookup",
            "hit_counter_semantics": "number of cached tokens returned by longest-prefix lookup",
            "prometheus_counters": ["vllm:prefix_cache_queries", "vllm:prefix_cache_hits"],
        },
        "nontransferable_prior_warning": (
            "The lab's vllm@ab0a20d15129b322f911db578b50c6b35b3167e7 source snapshot is not the "
            "exact image revision. This packet uses the image-observed 6d4a8e6d2 source contract."
        ),
    }
    (ROOT / "EXACT_IMAGE_SOURCE_EVIDENCE.json").write_text(
        json.dumps(source_evidence, indent=2, sort_keys=True) + "\n"
    )

    packet = {
        "schema_version": 1,
        "kind": "exact_gemma_primary_cache_trace_contract",
        "classification": "deterministic offline construction; realized cache reads require live counter deltas",
        "identity": {
            "model": MODEL,
            "revision": REVISION,
            "runtime_image": IMAGE,
            "runtime_observed_vllm": IMAGE_VLLM,
            "checkpoint_index_sha256": "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2",
            "tokenizer_json_sha256": sha_file(TOKENIZER),
            "tokenizer_config_sha256": sha_file(TOKENIZER_CONFIG),
            "tokenizer_vocab_size": len(vocab),
            "tokenizer_special_ids": special_ids,
            "token_id_transport": "OpenAI /v1/completions request_body.prompt list[int]",
        },
        "target": {
            "reported_cached_prompt_fraction": 0.127,
            "reported_cached_prompt_tokens_per_4214": 0.127 * INPUT_TOKENS,
            "nearest_integer_common_prefix_tokens": COMMON_TOKENS,
            "intended_common_fraction": COMMON_TOKENS / INPUT_TOKENS,
            "block_size_tokens": BLOCK_SIZE,
            "maximum_cacheable_common_tokens": MAX_CACHEABLE,
            "maximum_cacheable_fraction": MAX_CACHEABLE / INPUT_TOKENS,
            "block_rounding_loss_tokens": COMMON_TOKENS - MAX_CACHEABLE,
            "interpretation": (
                "535 common tokens is the nearest integer construction to 12.7%; exact-image APC can credit at "
                "most 528 full-block tokens. Only scored vllm:prefix_cache_hits deltas establish realization."
            ),
        },
        "primary_groups": groups,
        "separate_10k_stream": separate,
        "runner_contract": {
            "endpoint": "/v1/completions",
            "required_request_field": "prompt",
            "forbidden_request_field": "prompt_token_ids",
            "metrics_snapshot_regex": [
                "^vllm:prefix_cache_queries(?:_total)?(?:\\{[^}]*\\})?\\s+",
                "^vllm:prefix_cache_hits(?:_total)?(?:\\{[^}]*\\})?\\s+",
            ],
            "raw_evidence": [
                "canonical submitted request bytes and SHA-256",
                "raw streaming response chunks and SHA-256",
                "returned prompt token IDs equal submitted prompt list",
                "complete output token IDs count 358 for scored requests",
                "server usage prompt_tokens equals 4214 (or 10000 for separate stream)",
                "before_warmup, after_warmup, after_scored raw Prometheus snapshots per primary group",
                "monotonic submit/start/first-token/end timestamps and maximum simultaneous in flight",
            ],
            "barrier_assertion": (
                "No scored future may issue network I/O before every scored worker is armed; coordinator releases "
                "one barrier and observed maximum simultaneous in-flight must equal the labeled concurrency."
            ),
            "warmup_exclusion": (
                "Warmups request one output token and are setup only. Cache fraction, throughput, output, and "
                "latency aggregates use scored requests and after_warmup-to-after_scored counter deltas only."
            ),
            "cache_metric_equation": (
                "realized_cache_read_fraction = delta(vllm:prefix_cache_hits) / "
                "sum(scored response usage.prompt_tokens)"
            ),
            "failure_policy": (
                "Construction does not assert 12.7% realized. Missing counters, query-delta mismatch, returned-token "
                "mismatch, output truncation, barrier failure, or hit delta above the construction bound invalidates the arm."
            ),
        },
        "determinism": {
            "seed": SEED,
            "canonical_json": "UTF-8, sort_keys=True, separators=(',', ':')",
            "cross_group_lcp_tokens": 0,
            "intra_group_pairwise_lcp_tokens": COMMON_TOKENS,
            "all_suffixes_distinct": True,
            "separate_10k_lcp_with_primary_tokens": 0,
        },
    }
    (ROOT / "TRACE_PACKET.json").write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
