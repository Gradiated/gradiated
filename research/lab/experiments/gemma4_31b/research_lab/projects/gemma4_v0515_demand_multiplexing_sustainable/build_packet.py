#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
import subprocess
from decimal import Decimal, getcontext
from pathlib import Path


getcontext().prec = 60

PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
WORKSPACE = PROJECT.parents[6]
DEFAULT_SOURCE = WORKSPACE / ".agents/runtime/sglang-v0.5.15-full-checkout"
EXPECTED_COMMIT = "f63458b5beaceabbd9d749b9fc956370e1b649e6"
MODEL = "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd"
)
TARGET_COST = Decimal("0.14")
SUSTAINABLE_UTILIZATION = Decimal("0.90")
MINIMUM_DENSITY = Decimal("1.7227397374")
CALIBRATION_END = 32
SCORED_END = 791
STREAM_A_END = 412
DEPENDENCY_TERMINAL_RELATIVE = (
    "projects/gemma4_upstream_ngram_runtime_rebase/"
    "artifacts/v0515-endpoint-20260725t062540z/retrieved-final/"
    "endpoint-stage/out-endpoint/ENDPOINT_TERMINAL.json"
)
DEPENDENCY_TERMINAL_SHA256 = (
    "7e6ba230931ccf0db83917ae0797e89c4fe983d6f53923fa1fcb84e744893367"
)

BOUND_INPUTS = {
    "TRACE_PACKET.json": (
        "projects/gemma4_upstream_ngram_runtime_rebase/"
        "artifacts/candidate-v0.5.15/inputs/TRACE_PACKET.json"
    ),
    "exact_semantic_rows.jsonl": (
        "projects/gemma4_upstream_ngram_runtime_rebase/"
        "artifacts/candidate-v0.5.15/inputs/exact_semantic_rows.jsonl"
    ),
    "ngram-launch.json": (
        "projects/gemma4_upstream_ngram_runtime_rebase/"
        "artifacts/candidate-v0.5.15/inputs/ngram-launch.json"
    ),
    "requests.jsonl": (
        "projects/gemma4_upstream_ngram_runtime_rebase/"
        "artifacts/candidate-v0.5.15/inputs/requests.jsonl"
    ),
}

SOURCE_FILES = [
    "python/sglang/srt/server_args.py",
    "python/sglang/srt/arg_groups/speculative_hook.py",
    "python/sglang/srt/managers/scheduler.py",
    "python/sglang/srt/managers/schedule_policy.py",
    "python/sglang/srt/managers/scheduler_components/metrics_reporter.py",
    "python/sglang/srt/model_executor/runner/base_cuda_graph_runner.py",
    "python/sglang/srt/model_executor/runner/decode_cuda_graph_runner.py",
    "python/sglang/srt/speculative/ngram_worker.py",
    "python/sglang/srt/speculative/cpp_ngram/ngram_corpus.py",
    "python/sglang/jit_kernel/csrc/ngram_corpus/ngram.cpp",
    "python/sglang/jit_kernel/csrc/ngram_corpus/ngram.h",
    "python/sglang/jit_kernel/csrc/ngram_corpus/param.h",
    "python/sglang/jit_kernel/csrc/ngram_corpus/queue.h",
    "python/sglang/jit_kernel/csrc/ngram_corpus/result.cpp",
    "python/sglang/jit_kernel/csrc/ngram_corpus/result.h",
    "python/sglang/jit_kernel/csrc/ngram_corpus/suffix_automaton.cpp",
    "python/sglang/jit_kernel/csrc/ngram_corpus/suffix_automaton.h",
    "python/sglang/jit_kernel/csrc/ngram_corpus/trie.cpp",
    "python/sglang/jit_kernel/csrc/ngram_corpus/trie.h",
]


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def pretty_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest(path):
    return digest_bytes(path.read_bytes())


def write_bytes(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_bytes(value)
    part.replace(path)


def write_json(path, value):
    write_bytes(path, pretty_bytes(value))


def decimal_string(value):
    return format(value, "f")


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def request_body(template, index):
    value = dict(template["request_body"])
    value.update(
        {
            "model": "google/gemma-4-31B-it",
            "ignore_eos": True,
            "min_tokens": 358,
            "max_tokens": 358,
            "request_id": f"tail-overlap-{index}",
        }
    )
    value["prompt"] = list(value["prompt"])
    value["prompt"][535] = 200000 + index
    return value


def verify_binding():
    binding_path = PROJECT / "DIRECTOR_BINDING.json"
    binding = json.loads(binding_path.read_text())
    rows = {}
    for relative, expected in binding["files"].items():
        path = LAB / relative
        actual = digest(path)
        rows[relative] = {
            "bytes": path.stat().st_size,
            "expected_sha256": expected,
            "actual_sha256": actual,
            "matches": actual == expected,
        }
    constraints = binding["fixed_constraints"]
    constraints_match = (
        Decimal(str(constraints["b200_minimum_aggregate_demand_density"]))
        == MINIMUM_DENSITY
        and constraints["endpoint_queue_peak_max"] == 30
        and constraints["final_queue"] == 0
        and constraints["provider_mutation"] is False
        and constraints["request_bytes_mutable"] is False
        and constraints["semantic_rows_mutable"] is False
        and constraints["within_stream_arrival_order_mutable"] is False
    )
    verified = all(row["matches"] for row in rows.values()) and constraints_match
    result = {
        "binding_path": str(binding_path.relative_to(WORKSPACE)),
        "binding_sha256": digest(binding_path),
        "files": rows,
        "fixed_constraints_match": constraints_match,
        "result": "verified" if verified else "rejected",
        "schema_version": 1,
    }
    if not verified:
        raise RuntimeError("director binding verification failed")
    return binding, result


def load_prices():
    path = WORKSPACE / "research/factory/data/gpu_prices.json"
    raw = json.loads(path.read_text())
    if raw["refreshed_at_utc"] != "2026-07-22T21:42:00Z":
        raise RuntimeError("unexpected price inventory refresh identity")
    by_id = {row["id"]: row for row in raw["accelerators"]}
    rates = {
        accelerator: Decimal(
            str(by_id[accelerator]["production_planning_usd_per_gpu_hour"])
        )
        for accelerator in (
            "nvidia-h200-sxm",
            "nvidia-h100-sxm",
            "nvidia-b200-sxm",
        )
    }
    return path, raw, rates


def economic_row(rate, requests, total_tokens, arrival_span):
    tokens = Decimal(total_tokens)
    count = Decimal(requests)
    raw_elapsed = TARGET_COST * tokens * Decimal(3600) / (Decimal(1000000) * rate)
    sustainable_elapsed = raw_elapsed * SUSTAINABLE_UTILIZATION
    raw_floor_cost = (
        rate * arrival_span / Decimal(3600) * Decimal(1000000) / tokens
    )
    sustainable_floor_cost = raw_floor_cost / SUSTAINABLE_UTILIZATION
    return {
        "arrival_span_seconds": decimal_string(arrival_span),
        "planning_usd_per_gpu_hour": decimal_string(rate),
        "raw_arrival_floor_cost_usd_per_million_total_tokens": decimal_string(
            raw_floor_cost
        ),
        "raw_elapsed_ceiling_seconds": decimal_string(raw_elapsed),
        "raw_service_ceiling_seconds_per_request": decimal_string(raw_elapsed / count),
        "requests": requests,
        "sustainable_90pct_arrival_floor_cost_usd_per_million_total_tokens": decimal_string(
            sustainable_floor_cost
        ),
        "sustainable_90pct_elapsed_ceiling_seconds": decimal_string(
            sustainable_elapsed
        ),
        "sustainable_90pct_service_ceiling_seconds_per_request": decimal_string(
            sustainable_elapsed / count
        ),
        "total_tokens": total_tokens,
    }


def source_causal_map(source_hashes, trace_proof, probe):
    return {
        "evidence_labels": {
            "corpus_equivalence": "executed official v0.5.15 C++ producer/consumer",
            "runtime_interactions": "source-backed",
            "trace_tail_family": "mechanically derived from bound request and semantic bytes",
        },
        "official_identity": {
            "commit": EXPECTED_COMMIT,
            "source_files": source_hashes,
        },
        "scheduler": [
            {
                "claim": "Ingress appends every accepted request to one process scheduler waiting_queue; no tenant-stream queue exists.",
                "source": "python/sglang/srt/managers/scheduler.py:2300",
            },
            {
                "claim": "The launch fixes max-running-requests at 32. Admission uses the shared request pool and token/SWA budgets; excess work remains in waiting_queue.",
                "source": "python/sglang/srt/managers/scheduler.py:2728",
            },
            {
                "claim": "The launch does not set max-queued-requests, so the packet must enforce peak queue <=30 and final queue zero observationally.",
                "source": "python/sglang/srt/managers/scheduler.py:2349",
            },
            {
                "claim": "The exposed num_queue_reqs metric is the shared waiting_queue cardinality, so it is the correct aggregate gate.",
                "source": "python/sglang/srt/managers/scheduler_components/metrics_reporter.py:804",
            },
            {
                "claim": "Decode CUDA graphs capture buckets clamped to the request-pool size and pad eligible batches to a captured bucket; launch max batch 32 therefore does not create a second 32-request stream.",
                "source": "python/sglang/srt/model_executor/runner/base_cuda_graph_runner.py:129",
            },
        ],
        "global_ngram_corpus": [
            {
                "claim": "NGRAMWorker constructs exactly one NgramCorpus per worker; it is process-global across every scheduled request.",
                "source": "python/sglang/srt/speculative/ngram_worker.py:78",
            },
            {
                "claim": "Request IDs namespace only stateful match cursors; the online trie itself has no request or tenant namespace.",
                "source": "python/sglang/srt/speculative/cpp_ngram/ngram_corpus.py:35",
            },
            {
                "claim": "Every decode batch writes each request's last max_trie_depth tokens into the same trie after verification.",
                "source": "python/sglang/srt/speculative/ngram_worker.py:346",
            },
            {
                "claim": "Default BFS matching ranks child branches by recency, and duplicate insertions refresh LRU order. Exact-copy multiplexing can therefore bias proposals and is forbidden.",
                "source": "python/sglang/jit_kernel/csrc/ngram_corpus/trie.cpp:21",
            },
        ],
        "bias_disposition": {
            "calibration_prefix": [0, 32],
            "exact_copy_streams_forbidden": True,
            "mechanical_trace_proof": trace_proof,
            "official_corpus_probe": probe,
            "reason": (
                "Scored request bodies are disjoint. The only mutated prompt token is "
                "position 535, outside the last-18 tail consumed by NGRAM; all 791 "
                "frozen completions are the same 358 copies of token 51935. After the "
                "exact 0..31 calibration prefix completes and queue drains, both scored "
                "streams can only refresh already-present single-branch tails. The "
                "official C++ BFS consumer returned byte-identical isolated and "
                "two-stream proposal tensors for all 358 completion states."
            ),
        },
        "schema_version": 1,
    }


def run_probe(source_root):
    csrc = source_root / "python/sglang/jit_kernel/csrc/ngram_corpus"
    out = PROJECT / "artifacts/corpus_equivalence_probe"
    binary = out / "corpus_equivalence_probe"
    compile_log = out / "compile.json"
    execution_log = out / "execution.json"
    if binary.exists() and execution_log.exists():
        prior = json.loads(execution_log.read_text())
        if (
            prior.get("returncode") == 0
            and prior.get("binary_sha256") == digest(binary)
        ):
            value = json.loads(prior["stdout"])
            if value.get("result") == "isolated_and_two_stream_proposals_exact":
                return {
                    "binary_sha256": digest(binary),
                    "execution_sha256": digest(execution_log),
                    **value,
                }
    command = [
        "g++",
        "-std=c++20",
        "-O2",
        "-pthread",
        f"-I{csrc}",
        str(PROJECT / "corpus_equivalence_probe.cpp"),
        str(csrc / "ngram.cpp"),
        str(csrc / "trie.cpp"),
        str(csrc / "result.cpp"),
        str(csrc / "suffix_automaton.cpp"),
        "-o",
        str(binary),
    ]
    out.mkdir(parents=True, exist_ok=True)
    compiled = subprocess.run(command, text=True, capture_output=True, check=False)
    write_json(
        compile_log,
        {
            "command": command,
            "returncode": compiled.returncode,
            "stderr": compiled.stderr,
            "stdout": compiled.stdout,
        },
    )
    if compiled.returncode:
        raise RuntimeError("corpus probe compilation failed")
    executed = subprocess.run(
        [str(binary)], text=True, capture_output=True, check=False, timeout=120
    )
    write_json(
        execution_log,
        {
            "binary_sha256": digest(binary),
            "returncode": executed.returncode,
            "stderr": executed.stderr,
            "stdout": executed.stdout,
        },
    )
    if executed.returncode:
        raise RuntimeError("corpus probe execution failed")
    value = json.loads(executed.stdout)
    if value["result"] != "isolated_and_two_stream_proposals_exact":
        raise RuntimeError("corpus probe rejected equivalence")
    return {
        "binary_sha256": digest(binary),
        "execution_sha256": digest(execution_log),
        **value,
    }


def build(source_root):
    binding, binding_result = verify_binding()
    write_json(PROJECT / "BINDING_VERIFIED.json", binding_result)

    head = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(source_root), "status", "--short"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    if head != EXPECTED_COMMIT or dirty:
        raise RuntimeError("official source checkout identity mismatch")

    evidence_root = PROJECT / "evidence/official-v0.5.15"
    source_hashes = {}
    for relative in SOURCE_FILES:
        source = source_root / relative
        target = evidence_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_hashes[relative] = {
            "bytes": target.stat().st_size,
            "sha256": digest(target),
        }

    packet_root = PROJECT / "packet"
    input_root = packet_root / "inputs"
    for name, relative in BOUND_INPUTS.items():
        input_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(LAB / relative, input_root / name)

    endpoint_binding_source = (
        LAB
        / "projects/gemma4_upstream_ngram_runtime_rebase/DIRECTOR_ENDPOINT_BINDING.json"
    )
    control_terminal_source = (
        LAB
        / "projects/gemma4_upstream_ngram_runtime_rebase/"
        "artifacts/v0515-discriminator-20260725t060739z/retrieved/out/FINAL_TERMINAL.json"
    )
    (packet_root / "control").mkdir(parents=True, exist_ok=True)
    shutil.copy2(endpoint_binding_source, packet_root / "control/DIRECTOR_ENDPOINT_BINDING.json")
    shutil.copy2(control_terminal_source, packet_root / "control/FINAL_TERMINAL.json")
    dependency_terminal_source = LAB / DEPENDENCY_TERMINAL_RELATIVE
    if digest(dependency_terminal_source) != DEPENDENCY_TERMINAL_SHA256:
        raise RuntimeError("dependency endpoint terminal identity mismatch")
    shutil.copy2(
        dependency_terminal_source,
        packet_root / "control/H200_ENDPOINT_TERMINAL.json",
    )
    dependency_terminal = json.loads(dependency_terminal_source.read_text())
    if (
        dependency_terminal["accepted"] is not False
        or dependency_terminal["gates"]["normalized_semantics_exact"] is not False
        or dependency_terminal["discriminator_terminal"]["first_semantic_divergence"]
        != {"request": 217, "first_output_token_mismatch": 19}
    ):
        raise RuntimeError("dependency endpoint terminal disposition mismatch")

    rows = load_jsonl(input_root / "exact_semantic_rows.jsonl")
    arrivals = [Decimal(str(row["arrival_s"])) for row in rows]
    requests = load_jsonl(input_root / "requests.jsonl")
    if len(rows) != 1036 or len(requests) != 1036:
        raise RuntimeError("bound workload cardinality mismatch")
    if [row["i"] for row in rows] != list(range(1036)):
        raise RuntimeError("semantic row identity mismatch")

    trace = json.loads((input_root / "TRACE_PACKET.json").read_text())
    template = next(
        row for row in trace["primary_groups"] if row["name"] == "primary_c1"
    )["scored"][0]
    bodies = []
    for index in range(SCORED_END):
        body = request_body(template, index)
        actual = hashlib.sha256(
            json.dumps(body, sort_keys=True).encode()
        ).hexdigest()
        if actual != rows[index]["request_sha256"]:
            raise RuntimeError(f"request reconstruction mismatch at {index}")
        bodies.append(body)

    prompt_tails = {tuple(body["prompt"][-18:]) for body in bodies}
    outputs = {tuple(row["semantic"]["output_ids"]) for row in rows[:SCORED_END]}
    if (
        len(prompt_tails) != 1
        or len(outputs) != 1
        or outputs.pop() != (51935,) * 358
    ):
        raise RuntimeError("bound trace tail-family proof failed")
    if len({row["request_sha256"] for row in rows[CALIBRATION_END:SCORED_END]}) != (
        SCORED_END - CALIBRATION_END
    ):
        raise RuntimeError("scored request bodies are not unique")

    probe = run_probe(source_root)
    interval = arrivals[CALIBRATION_END + 1] - arrivals[CALIBRATION_END]
    phase_b = interval / Decimal(2)
    geometry = []
    for index in range(CALIBRATION_END, SCORED_END):
        if index < STREAM_A_END:
            stream_id = "tenant_a"
            origin_index = CALIBRATION_END
            phase = Decimal(0)
        else:
            stream_id = "tenant_b"
            origin_index = STREAM_A_END
            phase = phase_b
        within = arrivals[index] - arrivals[origin_index]
        semantic = {
            key: rows[index]["semantic"][key]
            for key in ("output_ids", "finish_reason", "usage")
        }
        geometry.append(
            {
                "aggregate_release_seconds": decimal_string(phase + within),
                "canonical_request_sha256": rows[index]["request_sha256"],
                "semantic_sha256": digest_bytes(canonical_bytes(semantic)),
                "source_index": index,
                "stream_id": stream_id,
                "stream_origin_source_index": origin_index,
                "stream_phase_seconds": decimal_string(phase),
                "within_stream_release_seconds": decimal_string(within),
            }
        )
    geometry.sort(
        key=lambda row: (
            Decimal(row["aggregate_release_seconds"]),
            row["stream_id"],
            row["source_index"],
        )
    )
    write_bytes(
        packet_root / "geometry.jsonl",
        b"".join(canonical_bytes(row) for row in geometry),
    )

    scored_rows = rows[CALIBRATION_END:SCORED_END]
    total_tokens = sum(row["semantic"]["usage"]["total_tokens"] for row in scored_rows)
    prompt_tokens = sum(
        row["semantic"]["usage"]["prompt_tokens"] for row in scored_rows
    )
    completion_tokens = sum(
        row["semantic"]["usage"]["completion_tokens"] for row in scored_rows
    )
    baseline_span = arrivals[SCORED_END - 1] - arrivals[CALIBRATION_END]
    candidate_span = max(
        Decimal(row["aggregate_release_seconds"]) for row in geometry
    )
    density = baseline_span / candidate_span
    if density < MINIMUM_DENSITY:
        raise RuntimeError("candidate misses density floor")

    price_path, price_inventory, rates = load_prices()
    economics = {
        "baseline_single_stream": {
            accelerator: economic_row(
                rate,
                SCORED_END - CALIBRATION_END,
                total_tokens,
                baseline_span,
            )
            for accelerator, rate in rates.items()
        },
        "candidate_two_stream": {
            accelerator: economic_row(
                rate,
                SCORED_END - CALIBRATION_END,
                total_tokens,
                candidate_span,
            )
            for accelerator, rate in rates.items()
        },
        "density": {
            "baseline_arrival_span_seconds": decimal_string(baseline_span),
            "candidate_arrival_span_seconds": decimal_string(candidate_span),
            "minimum_required": decimal_string(MINIMUM_DENSITY),
            "ratio": decimal_string(density),
        },
        "price_inventory": {
            "fresh_at_build": True,
            "path": str(price_path.relative_to(WORKSPACE)),
            "refreshed_at_utc": price_inventory["refreshed_at_utc"],
            "sha256": digest(price_path),
        },
        "schema_version": 1,
        "target_usd_per_million_total_tokens": decimal_string(TARGET_COST),
    }
    write_json(PROJECT / "ARRIVAL_ECONOMICS.json", economics)

    trace_proof = {
        "all_791_frozen_completion_sequences_identical": True,
        "all_791_frozen_completion_tokens": 51935,
        "all_791_frozen_completion_tokens_per_request": 358,
        "all_791_prompt_last_18_tokens_identical": True,
        "canonical_scored_request_bodies_unique": True,
        "mutation_position": 535,
        "ngram_max_trie_depth": 18,
        "scored_request_count": SCORED_END - CALIBRATION_END,
    }
    causal_map = source_causal_map(source_hashes, trace_proof, probe)
    write_json(PROJECT / "SCHEDULER_CORPUS_CAUSAL_MAP.json", causal_map)
    packet_evidence = packet_root / "evidence"
    packet_evidence.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT / "BINDING_VERIFIED.json", packet_evidence / "BINDING_VERIFIED.json")
    shutil.copy2(PROJECT / "ARRIVAL_ECONOMICS.json", packet_evidence / "ARRIVAL_ECONOMICS.json")
    shutil.copy2(
        PROJECT / "SCHEDULER_CORPUS_CAUSAL_MAP.json",
        packet_evidence / "SCHEDULER_CORPUS_CAUSAL_MAP.json",
    )
    shutil.copy2(PROJECT / "multiplex_runner.py", packet_root / "multiplex_runner.py")

    packet = {
        "calibration": {
            "requests": {"begin": 0, "end_exclusive": CALIBRATION_END},
            "release_policy": "bound arrival_s relative to calibration origin",
            "terminal_gate": (
                "All calibration requests complete with exact frozen semantics, "
                "zero failures, queue final zero, then scored epoch begins."
            ),
        },
        "decision": "typed_none",
        "denominator": {
            "completion_tokens": completion_tokens,
            "prompt_tokens": prompt_tokens,
            "requests": SCORED_END - CALIBRATION_END,
            "total_tokens": total_tokens,
        },
        "execution_identity": {
            "image": IMAGE,
            "launch_sha256": digest(input_root / "ngram-launch.json"),
            "model": MODEL,
            "runtime_commit": EXPECTED_COMMIT,
            "runtime_release": "v0.5.15",
        },
        "geometry": {
            "aggregate_demand_density_ratio": decimal_string(density),
            "aggregate_release_span_seconds": decimal_string(candidate_span),
            "baseline_release_span_seconds": decimal_string(baseline_span),
            "geometry_path": "geometry.jsonl",
            "minimum_density_gate": decimal_string(MINIMUM_DENSITY),
            "phase_policy": "tenant_b begins one-half bound interarrival after tenant_a",
            "streams": [
                {
                    "id": "tenant_a",
                    "source_begin": CALIBRATION_END,
                    "source_end_exclusive": STREAM_A_END,
                    "phase_seconds": "0",
                },
                {
                    "id": "tenant_b",
                    "source_begin": STREAM_A_END,
                    "source_end_exclusive": SCORED_END,
                    "phase_seconds": decimal_string(phase_b),
                },
            ],
        },
        "invariants": {
            "all_frozen_semantics_exact": True,
            "canonical_request_body_duplicates": 0,
            "final_queue": 0,
            "launch_or_flag_changes": 0,
            "peak_queue_max": 30,
            "request_bytes_preserved": True,
            "stream_request_sets_disjoint": True,
            "within_stream_arrival_offsets_preserved": True,
        },
        "not_admitted_gpu_falsifier": {
            "authority": "Not admitted while the scope-matched official endpoint has a known semantic reject.",
            "comparison": (
                "On the same accelerator and official image, use cache flush plus exact "
                "0..31 calibration and queue drain before each arm. Compare one scored "
                "single-stream 32..170 control against the disjoint two-stream split "
                "32..101 and 102..170 at the same half-interval phase."
            ),
            "candidate_density_ratio": "2",
            "gates": {
                "all_normalized_semantics_exact": True,
                "failures": 0,
                "final_queue": 0,
                "native_ngram_activation": True,
                "peak_queue_max": 30,
                "release_drift_abs_max_seconds": "0.25",
            },
            "stop": (
                "Reject before the 759-request endpoint if the discriminator violates "
                "semantics, queue, release, activation, or final-drain gates."
            ),
            "runner": "multiplex_runner.py",
            "runner_sha256": digest(PROJECT / "multiplex_runner.py"),
        },
        "ngram_bias_guard": causal_map["bias_disposition"],
        "production_valid": False,
        "rejection": {
            "classification": "scope_matched_official_runtime_semantic_reject",
            "dependency_terminal": "control/H200_ENDPOINT_TERMINAL.json",
            "dependency_terminal_sha256": DEPENDENCY_TERMINAL_SHA256,
            "first_semantic_divergence": {
                "request": 217,
                "first_output_token_mismatch": 19,
            },
            "reason": (
                "The completed official unmodified v0.5.15 first-791-request H200 "
                "endpoint fails normalized semantics. The offline multiplex geometry "
                "changes batching and cannot inherit semantic validity; this zero-GPU "
                "project therefore cannot return a production-valid packet."
            ),
        },
        "provider_mutation": False,
        "schema_version": 1,
    }
    write_json(packet_root / "REJECTED_ANALYTICAL_GEOMETRY.json", packet)

    manifest_files = []
    for path in sorted(
        p
        for p in packet_root.rglob("*")
        if p.is_file() and p.name not in {"PACKET_MANIFEST.json", "PACKET_ID.json"}
    ):
        manifest_files.append(
            {
                "bytes": path.stat().st_size,
                "path": str(path.relative_to(packet_root)),
                "sha256": digest(path),
            }
        )
    manifest = {
        "files": manifest_files,
        "identity": {
            "image": IMAGE,
            "model": MODEL,
            "runtime_commit": EXPECTED_COMMIT,
        },
        "schema_version": 1,
    }
    write_json(packet_root / "PACKET_MANIFEST.json", manifest)
    packet_id = digest(packet_root / "PACKET_MANIFEST.json")
    write_json(
        packet_root / "PACKET_ID.json",
        {
            "content_address": f"sha256:{packet_id}",
            "manifest": "PACKET_MANIFEST.json",
            "schema_version": 1,
        },
    )

    validation = {
        "binding_verified": True,
        "canonical_scored_request_bodies_unique": True,
        "corpus_equivalence_probe_passed": True,
        "density_gate_passed": density >= MINIMUM_DENSITY,
        "density_ratio": decimal_string(density),
        "packet_content_address": f"sha256:{packet_id}",
        "production_valid": False,
        "provider_mutated": False,
        "result": "typed_none_scope_matched_semantic_reject",
        "scored_request_count": SCORED_END - CALIBRATION_END,
        "schema_version": 1,
    }
    write_json(PROJECT / "VALIDATION_RESULT.json", validation)
    write_json(
        PROJECT / "TYPED_NONE.json",
        {
            "analytical_geometry": {
                "aggregate_demand_density_ratio": decimal_string(density),
                "content_address": f"sha256:{packet_id}",
                "path": "packet",
                "status": "rejected_not_production_valid",
            },
            "candidate_sample_consumed": False,
            "classification": "scope_matched_official_runtime_semantic_reject",
            "decision": "typed_none",
            "dependency_terminal": {
                "first_semantic_divergence": {
                    "request": 217,
                    "first_output_token_mismatch": 19,
                },
                "normalized_semantics_exact": False,
                "path": DEPENDENCY_TERMINAL_RELATIVE,
                "sha256": DEPENDENCY_TERMINAL_SHA256,
            },
            "gpu_claimed": False,
            "provider_mutated": False,
            "reason": (
                "A two-stream disjoint post-calibration geometry reaches the density "
                "floor and passes the official CPU corpus-bias probe, but the newly "
                "completed scope-matched official v0.5.15 H200 endpoint diverges at "
                "request 217. Without a GPU run this project cannot establish that "
                "different batching restores semantics, so no production-valid "
                "multiplexing packet is returned."
            ),
            "reopen_only_if": [
                "A content-bound official v0.5.15 full-trajectory result with exact normalized semantics supersedes the dependency reject.",
                "A new director binding admits a runtime semantic repair and scope-matched multiplex discriminator.",
                "The workload semantic gate changes.",
            ],
            "schema_version": 1,
            "spend_usd": 0.0,
        },
    )
    return validation


def validate_only():
    packet_root = PROJECT / "packet"
    manifest_path = packet_root / "PACKET_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    for row in manifest["files"]:
        path = packet_root / row["path"]
        if path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
            raise RuntimeError("packet manifest mismatch: " + row["path"])
    packet_id = json.loads((packet_root / "PACKET_ID.json").read_text())
    expected = "sha256:" + digest(manifest_path)
    if packet_id["content_address"] != expected:
        raise RuntimeError("packet content address mismatch")
    binding, result = verify_binding()
    del binding
    if result["result"] != "verified":
        raise RuntimeError("director binding no longer verifies")
    validation = json.loads((PROJECT / "VALIDATION_RESULT.json").read_text())
    if validation["packet_content_address"] != expected:
        raise RuntimeError("validation content address mismatch")
    print(expected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        validate_only()
    else:
        print(json.dumps(build(args.source_root.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
