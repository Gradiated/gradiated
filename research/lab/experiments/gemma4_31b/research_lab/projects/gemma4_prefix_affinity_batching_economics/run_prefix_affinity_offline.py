#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import pathlib
import struct
from dataclasses import dataclass, field
from typing import Callable


ROOT = pathlib.Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECTS = LAB / "projects"
WORKLOAD = (
    PROJECTS
    / "gemma4_causal_parallel_offset_head"
    / "inputs"
    / "qualified_c32_workload.json"
)
BOUND_RUNNER = (
    PROJECTS
    / "gemma4_c32_graph_gap_elision"
    / "inputs"
    / "bound"
    / "exact_runner.py"
)
QUALIFIED_TERMINAL = (
    PROJECTS
    / "gemma4_h200_ngram_decode_equivalent_verifier"
    / "artifacts"
    / "h200-verifier-20260724t103131Z"
    / "retrieved"
    / "artifacts"
    / "candidate-full-c32"
    / "TERMINAL.json"
)
CAMPAIGN = LAB / "CAMPAIGN.md"
OUTPUT = ROOT / "PREFIX_AFFINITY_BATCHING_OFFLINE_TERMINAL.json"

EXPECTED = {
    "workload": "7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d",
    "bound_runner": "143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7",
    "qualified_terminal": "7090c0ebb733f5021c464bc55d82fcd68e2abb52b820408c89724d95c03fd9dd",
}
QUALIFIED_SECONDS_PER_REQUEST = 0.625149101968745
TARGET_SECONDS_PER_REQUEST = 0.500119281574996
WAIT_WINDOW_NS = 50_000_000
BATCH_CAPACITY = 32
REPLICAS = 1
TOKEN_ID_BYTES = 4
QUEUE_RECORD = struct.Struct("<QQIHIQ32s")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def load_bound_runner() -> object:
    spec = importlib.util.spec_from_file_location("bound_exact_runner", BOUND_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("bound runner import spec unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_requests(runner: object) -> list[dict]:
    prefix = runner.tokens("common-prefix", runner.COMMON_TOKENS)
    bodies = []
    for index in range(runner.CONCURRENCY):
        suffix = runner.tokens(
            f"suffix-{index}", runner.PROMPT_TOKENS - runner.COMMON_TOKENS
        )
        suffix[0] = 200000 + index
        bodies.append(
            {
                "model": runner.MODEL,
                "prompt": prefix + suffix,
                "max_tokens": runner.OUTPUT_TOKENS,
                "min_tokens": runner.OUTPUT_TOKENS,
                "ignore_eos": True,
                "temperature": 0,
                "seed": 20260718,
                "stream": True,
                "stream_options": {"include_usage": True},
                "return_token_ids": True,
                "add_special_tokens": False,
            }
        )
    return bodies


def common_prefix_length(values: list[list[int]] | list[bytes]) -> int:
    limit = min(len(value) for value in values)
    for index in range(limit):
        if any(value[index] != values[0][index] for value in values[1:]):
            return index
    return limit


def nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


@dataclass(frozen=True)
class Request:
    index: int
    arrival_ns: int
    prefix_digest: str
    prompt: tuple[int, ...]


@dataclass
class Replica:
    replica_id: int
    cached_prefixes: dict[str, int]
    queue: list[Request] = field(default_factory=list)

    def match(self, request: Request) -> int:
        return self.cached_prefixes.get(request.prefix_digest, 0)


def route_fifo(request: Request, replicas: list[Replica]) -> Replica:
    del request
    return min(replicas, key=lambda replica: (len(replica.queue), replica.replica_id))


def route_affinity(request: Request, replicas: list[Replica]) -> Replica:
    return min(
        replicas,
        key=lambda replica: (
            -replica.match(request),
            len(replica.queue),
            replica.replica_id,
        ),
    )


def admit_fifo(replica: Replica) -> list[Request]:
    return sorted(replica.queue, key=lambda request: (request.arrival_ns, request.index))


def admit_affinity(replica: Replica) -> list[Request]:
    return sorted(
        replica.queue,
        key=lambda request: (
            -replica.match(request),
            request.arrival_ns,
            request.index,
        ),
    )


def replay(
    requests: list[Request],
    route: Callable[[Request, list[Replica]], Replica],
    admit: Callable[[Replica], list[Request]],
    prefix_digest: str,
) -> dict:
    replicas = [
        Replica(replica_id=index, cached_prefixes={prefix_digest: 535})
        for index in range(REPLICAS)
    ]
    routed = []
    for request in requests:
        replica = route(request, replicas)
        replica.queue.append(request)
        routed.append({"request": request.index, "replica": replica.replica_id})
    batches = []
    peak_queued = sum(len(replica.queue) for replica in replicas)
    for replica in replicas:
        if not replica.queue:
            continue
        oldest = min(request.arrival_ns for request in replica.queue)
        full = len(replica.queue) >= BATCH_CAPACITY
        release_ns = oldest if full else oldest + WAIT_WINDOW_NS
        order = admit(replica)
        batches.append(
            {
                "replica": replica.replica_id,
                "request_order": [request.index for request in order],
                "release_ns": release_ns,
                "queue_wait_ns": [
                    release_ns - request.arrival_ns for request in order
                ],
                "occupancy": len(order) / BATCH_CAPACITY,
            }
        )
    return {
        "routed": routed,
        "batches": batches,
        "peak_queued_requests": peak_queued,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, default=OUTPUT)
    args = parser.parse_args()

    direct_hashes = {
        "workload": sha256(WORKLOAD),
        "bound_runner": sha256(BOUND_RUNNER),
        "qualified_terminal": sha256(QUALIFIED_TERMINAL),
        "campaign": sha256(CAMPAIGN),
    }
    for name, expected in EXPECTED.items():
        if direct_hashes[name] != expected:
            raise RuntimeError(
                f"{name} binding mismatch: {direct_hashes[name]} != {expected}"
            )

    workload = json.loads(WORKLOAD.read_text())
    qualified = json.loads(QUALIFIED_TERMINAL.read_text())
    runner = load_bound_runner()
    bodies = build_requests(runner)
    request_bytes = [canonical(body) for body in bodies]
    request_hashes = [hashlib.sha256(value).hexdigest() for value in request_bytes]
    if request_hashes != workload["request_sha256"]:
        raise RuntimeError("reconstructed request hashes do not match exact workload")
    if qualified["service_seconds_per_request"] != QUALIFIED_SECONDS_PER_REQUEST:
        raise RuntimeError("qualified denominator mismatch")
    if qualified["cache"]["cached_prompt_tokens_delta"] != 17120:
        raise RuntimeError("qualified cached-token accounting mismatch")

    prompts = [body["prompt"] for body in bodies]
    token_lcp = common_prefix_length(prompts)
    byte_lcp = common_prefix_length(request_bytes)
    pair_byte_lcps = [
        common_prefix_length([request_bytes[left], request_bytes[right]])
        for left in range(len(request_bytes))
        for right in range(left + 1, len(request_bytes))
    ]
    prefix_tokens = prompts[0][:token_lcp]
    prefix_digest = hashlib.sha256(canonical(prefix_tokens)).hexdigest()
    prompt_digests = [hashlib.sha256(canonical(prompt)).hexdigest() for prompt in prompts]
    depth_after_shared = [prompt[token_lcp] for prompt in prompts]

    arrivals = [
        Request(
            index=index,
            arrival_ns=0,
            prefix_digest=prefix_digest,
            prompt=tuple(prompt),
        )
        for index, prompt in enumerate(prompts)
    ]
    fifo = replay(arrivals, route_fifo, admit_fifo, prefix_digest)
    affinity = replay(arrivals, route_affinity, admit_affinity, prefix_digest)
    fifo_order = [item for batch in fifo["batches"] for item in batch["request_order"]]
    affinity_order = [
        item for batch in affinity["batches"] for item in batch["request_order"]
    ]
    parity = fifo_order == affinity_order == list(range(workload["concurrency"]))

    measured_wall = {
        row["index"]: row["wall_seconds"] for row in qualified["rows"]
    }
    fifo_wait = {
        request_index: wait_ns / 1e9
        for batch in fifo["batches"]
        for request_index, wait_ns in zip(
            batch["request_order"], batch["queue_wait_ns"], strict=True
        )
    }
    affinity_wait = {
        request_index: wait_ns / 1e9
        for batch in affinity["batches"]
        for request_index, wait_ns in zip(
            batch["request_order"], batch["queue_wait_ns"], strict=True
        )
    }

    def completion(wait: dict[int, float]) -> dict:
        values = [wait[index] + measured_wall[index] for index in range(len(bodies))]
        return {
            "p50_seconds_nearest_rank": nearest_rank(values, 0.50),
            "p95_seconds_nearest_rank": nearest_rank(values, 0.95),
            "max_seconds": max(values),
        }

    fifo_completion = completion(fifo_wait)
    affinity_completion = completion(affinity_wait)
    total_prompt_tokens = workload["concurrency"] * workload["prompt_tokens"]
    measured_cached = int(qualified["cache"]["cached_prompt_tokens_delta"])
    cold_intra_window_reuse = (workload["concurrency"] - 1) * token_lcp
    oracle_cached = workload["concurrency"] * token_lcp
    additional_reuse = oracle_cached - measured_cached

    payload_bytes = (
        workload["concurrency"] * workload["prompt_tokens"] * TOKEN_ID_BYTES
    )
    metadata_bytes = workload["concurrency"] * QUEUE_RECORD.size
    queue_bytes = payload_bytes + metadata_bytes
    worst_case_batch_delay_seconds = WAIT_WINDOW_NS / 1e9
    worst_case_service_seconds_per_request = (
        QUALIFIED_SECONDS_PER_REQUEST
        + worst_case_batch_delay_seconds / workload["concurrency"]
    )
    policy_source_hash = sha256(pathlib.Path(__file__).resolve())

    result = {
        "schema_version": 1,
        "kind": "gemma4_prefix_affinity_batching_offline_terminal",
        "classification": "typed_negative_no_additional_exact_prefix_reuse",
        "pass": True,
        "decision": {
            "portfolio_change": "close_prefix_affinity_policy",
            "positive_result": False,
            "reason": (
                "The only shared token prefix is 535 tokens and the qualified "
                "runtime already realizes all 17,120 possible cached tokens. "
                "Reordering and affinity routing cannot create another hit."
            ),
        },
        "bindings": {
            "model": (
                "google/gemma-4-31B-it@"
                "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
            ),
            "paths": {
                "workload": str(WORKLOAD.relative_to(LAB)),
                "bound_runner": str(BOUND_RUNNER.relative_to(LAB)),
                "qualified_terminal": str(QUALIFIED_TERMINAL.relative_to(LAB)),
                "campaign": str(CAMPAIGN.relative_to(LAB)),
                "policy_source": str(pathlib.Path(__file__).resolve().relative_to(LAB)),
            },
            "sha256": {**direct_hashes, "policy_source": policy_source_hash},
            "request_sha256": request_hashes,
            "request_hashes_match_workload": True,
        },
        "identity_measurement": {
            "evidence_label": "measured_from_exact_reconstructed_token_ids_and_request_bytes",
            "requests": len(bodies),
            "unique_requests": len(set(request_hashes)),
            "unique_full_prompts": len(set(prompt_digests)),
            "prompt_tokens_per_request": workload["prompt_tokens"],
            "all_request_token_lcp_tokens": token_lcp,
            "token_lcp_sha256": prefix_digest,
            "tokens_at_first_divergent_position_unique": len(set(depth_after_shared)),
            "all_request_canonical_byte_lcp_bytes": byte_lcp,
            "all_request_canonical_byte_lcp_sha256": hashlib.sha256(
                request_bytes[0][:byte_lcp]
            ).hexdigest(),
            "maximum_pair_canonical_byte_lcp_bytes": max(pair_byte_lcps),
            "byte_note": (
                "Decimal spellings of distinct token IDs share partial bytes, "
                "but no additional complete token identity."
            ),
            "cold_intra_window_reusable_tokens_after_one_seed": cold_intra_window_reuse,
            "warm_state_oracle_cached_tokens": oracle_cached,
            "qualified_measured_cached_tokens": measured_cached,
            "qualified_measured_fresh_tokens": int(
                qualified["cache"]["uncached_prompt_tokens_delta"]
            ),
            "additional_reusable_tokens_under_reordering": additional_reuse,
            "additional_reusable_fraction_of_prompt_work": (
                additional_reuse / total_prompt_tokens
            ),
        },
        "policy": {
            "name": "bounded_prefix_affinity_v1",
            "replicas_in_exact_comparator": REPLICAS,
            "batch_capacity": BATCH_CAPACITY,
            "max_wait_ms": WAIT_WINDOW_NS / 1e6,
            "routing": (
                "maximum resident exact-token prefix, then shortest queue, "
                "then replica ID"
            ),
            "admission": (
                "descending resident exact-token prefix, then arrival ordinal, "
                "then request index; release at full batch or oldest deadline"
            ),
            "fifo_comparator": (
                "shortest queue then replica ID; arrival ordinal then request index"
            ),
            "one_policy_only": True,
            "semantics_preserved": {
                "request_bytes": True,
                "prompt_and_output_tokens": True,
                "model_operations": True,
                "compulsory_fresh_prefill_and_decode": True,
            },
        },
        "replay": {
            "offered_work": {
                "requests": workload["concurrency"],
                "prompt_tokens": total_prompt_tokens,
                "output_tokens": workload["concurrency"]
                * workload["output_tokens"],
                "arrival_ns": [0] * workload["concurrency"],
            },
            "fifo": {
                "order": fifo_order,
                "cache_hit_tokens": measured_cached,
                "incremental_cache_hit_tokens": 0,
                "batch_occupancy": fifo["batches"][0]["occupancy"],
                "queue_wait_ms": [
                    value * 1e3 for value in fifo_wait.values()
                ],
                "completion": fifo_completion,
            },
            "affinity": {
                "order": affinity_order,
                "cache_hit_tokens": measured_cached,
                "incremental_cache_hit_tokens": 0,
                "batch_occupancy": affinity["batches"][0]["occupancy"],
                "queue_wait_ms": [
                    value * 1e3 for value in affinity_wait.values()
                ],
                "completion": affinity_completion,
            },
            "fifo_parity": parity,
        },
        "cost_latency_bounds": {
            "evidence_label": "derived_from_qualified_measured_terminal_and_exact_identity",
            "qualified_service_seconds_per_request": QUALIFIED_SECONDS_PER_REQUEST,
            "target_seconds_per_request": TARGET_SECONDS_PER_REQUEST,
            "oracle_lower_bound_seconds_per_request": QUALIFIED_SECONDS_PER_REQUEST,
            "realizable_zero_wait_seconds_per_request": QUALIFIED_SECONDS_PER_REQUEST,
            "bounded_wait_upper_seconds_per_request_at_c32": (
                worst_case_service_seconds_per_request
            ),
            "oracle_cost_reduction_fraction": 0.0,
            "realizable_cost_reduction_fraction": 0.0,
            "bounded_wait_cost_change_fraction": (
                worst_case_service_seconds_per_request
                / QUALIFIED_SECONDS_PER_REQUEST
                - 1
            ),
            "measured_batch_seconds": qualified["batch_seconds"],
            "measured_completion_fifo": fifo_completion,
            "realizable_completion_affinity": affinity_completion,
            "bounded_completion_p95_seconds": (
                affinity_completion["p95_seconds_nearest_rank"]
                + worst_case_batch_delay_seconds
            ),
            "break_even": {
                "type": "none",
                "finite_arrival_or_reuse_rate": False,
                "reason": (
                    "The exact identity graph supplies zero incremental reusable "
                    "tokens at every admissible within-window arrival rate; any "
                    "positive scheduling or waiting overhead therefore cannot break even."
                ),
            },
        },
        "memory_bounds": {
            "evidence_label": "derived_portable_queue_contract",
            "peak_queued_requests": affinity["peak_queued_requests"],
            "uint32_prompt_payload_bytes_upper_bound": payload_bytes,
            "packed_metadata_bytes": metadata_bytes,
            "packed_metadata_bytes_per_request": QUEUE_RECORD.size,
            "total_queue_bytes_upper_bound": queue_bytes,
            "total_queue_mib_upper_bound": queue_bytes / 2**20,
            "additional_kv_cache_tokens": 0,
            "additional_kv_cache_bytes": 0,
            "note": (
                "Payload bound assumes one conservative uint32 copy per queued "
                "token; an implementation may retain references. Interpreter "
                "heap is not an admitted runtime allocation."
            ),
        },
        "falsifier": {
            "positive_policy_requires": (
                "At least one exact prompt-prefix token beyond position 535 shared "
                "by two requests and not already credited by the qualified cache."
            ),
            "observed": (
                "All 32 token IDs at position 535 are distinct and all full prompts "
                "are unique; measured cached tokens equal the warm-state oracle."
            ),
            "falsified": True,
        },
        "exact_runtime_consumer": {
            "type": "none",
            "command": None,
            "reason": (
                "No additional identity exists for a runtime discriminator to "
                "consume, and this zero-cost project forbids GPU/provider use."
            ),
        },
        "assumptions": {
            "measured": [
                "Qualified c32 service time, request completions, per-request wall time, and cache counters are read from the bound terminal.",
                "All request bytes and token IDs are reconstructed by the bound exact runner and verified against all 32 workload request hashes.",
            ],
            "derived": [
                "Prefix graph, FIFO/affinity replay, quantiles, waiting bound, and packed queue-memory bound.",
                "Zero additional cache reuse makes the cost lower bound independent of unknown exposed-prefill wall share.",
            ],
            "inferred": [
                "Any nonzero production scheduler overhead can only worsen the zero-reuse policy."
            ],
        },
        "execution": {
            "gpu_used": False,
            "provider_used": False,
            "synthetic_prefixes_added": False,
            "policy_sweep": False,
            "reproduce_command": (
                "python3 research/lab/experiments/gemma4_31b/research_lab/"
                "projects/gemma4_prefix_affinity_batching_economics/"
                "run_prefix_affinity_offline.py"
            ),
        },
    }
    if token_lcp != 535 or additional_reuse != 0 or not parity:
        raise RuntimeError("scientific invariants failed")
    atomic(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
