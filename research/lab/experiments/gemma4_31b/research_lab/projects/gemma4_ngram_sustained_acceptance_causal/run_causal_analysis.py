#!/usr/bin/env python3
import hashlib
import json
import pathlib
import subprocess


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
WORKSPACE = PROJECT.parents[6]
PINNED = WORKSPACE / ".agents/runtime/sglang-v0.5.13-source"
CPP = PINNED / "python/sglang/jit_kernel/csrc/ngram_corpus"
TAIL = (
    LAB
    / "projects/gemma4_h200_ngram_tail_arrival_stream/artifacts/"
    "streamed-tail-20260725t023925z/out"
)
AGING = (
    LAB
    / "projects/gemma4_h200_ngram_state_aging_discriminator/artifacts/"
    "state-aging-20260724t145451z/retrieved/out"
)
CONFIG = (
    LAB
    / "projects/gemma4_h200_ngram_decode_equivalent_verifier/"
    "inputs/checkpoint/config.json"
)
LAUNCH = (
    LAB
    / "projects/gemma4_h200_ngram_tail_arrival_stream/"
    "inputs/bound/ngram-launch.json"
)
ARTIFACT = PROJECT / "artifacts/causal-source-probe"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    return [json.loads(line) for line in path.open()]


def first_low_acceptance(telemetry, threshold=8):
    for row in telemetry:
        metrics = row["metrics"]
        value = metrics.get("sglang:spec_accept_length")
        if value is not None and value < threshold:
            return {
                "elapsed_seconds": row.get(
                    "elapsed_s", row.get("elapsed_wall_seconds")
                ),
                "accept_length": value,
                "accept_rate": metrics.get("sglang:spec_accept_rate"),
                "running_requests": metrics.get("sglang:num_running_reqs"),
                "queued_requests": metrics.get("sglang:num_queue_reqs"),
            }
    raise RuntimeError("no low-acceptance telemetry row")


def divergent_requests(request_rows):
    result = []
    for row in request_rows:
        output = row.get("output_ids")
        if output is None:
            output = row["semantic"]["output_ids"]
        if len(set(output)) > 1:
            result.append(
                {
                    "request_index": row["i"],
                    "completed_seconds": row["completed_s"],
                    "first_non_dominant_offset": next(
                        i for i, token in enumerate(output) if token != 51935
                    ),
                    "non_dominant_tokens": sorted(set(output) - {51935}),
                    "dominant_tokens": output.count(51935),
                    "output_tokens": len(output),
                }
            )
    return result


def main():
    expected = {
        "ngram_worker.py": "27721b777cae08657ec9854ec0137a0db50afd49d84809503312fa43e399b554",
        "ngram_info.py": "ffa88c663e1893c306710ac801da0693d8248ebcfd1a5bc705c157f90657af1c",
        "trie.cpp": "9f14f2d05521427a0782db8c6058bbda1191dd09baf535e202c7412f82496ac9",
        "param.h": "e0a4c0899655d322f21421a62ab58b7cca4e2874150756388f9ed143f4c62233",
        "result.cpp": "d675ffef9de8cbfb37c5b6534836634474eab0b404ff43a87facb0ab85365bc1",
    }
    source_paths = {
        "ngram_worker.py": PINNED / "python/sglang/srt/speculative/ngram_worker.py",
        "ngram_info.py": PINNED / "python/sglang/srt/speculative/ngram_info.py",
        "trie.cpp": CPP / "trie.cpp",
        "param.h": CPP / "param.h",
        "result.cpp": CPP / "result.cpp",
    }
    observed = {name: digest(path) for name, path in source_paths.items()}
    if observed != expected:
        raise RuntimeError({"expected": expected, "observed": observed})

    bound_paths = {
        "checkpoint_config": CONFIG,
        "launch": LAUNCH,
        "tail_terminal": TAIL / "FINAL_TERMINAL.json",
        "tail_telemetry": TAIL / "telemetry.jsonl",
        "tail_requests": TAIL / "requests.jsonl",
        "aging_telemetry": AGING / "telemetry.jsonl",
        "aging_requests": AGING / "requests.jsonl",
    }
    expected_bound = {
        "checkpoint_config": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
        "launch": "8349853a7eac9e73211f5d3081c834c05f78e0fd292ddbe5acb921b1824a523d",
        "tail_terminal": "8c92c806ff758fc9b6bc3f75ce6b2d3f3b8ac4cbcaf0b7d096fefc8cdd2c7b73",
        "tail_telemetry": "9985bef41ff9f6bc98243b98c99eb5d2f10d725fe9dee6a084b1a53efe3d0915",
        "tail_requests": "5658b431b4db0e445d320c5e90a1fcd7c50ae437e5a1809ee068ca068ada4deb",
        "aging_telemetry": "9aaf97c3a289d5cf1abf6597fddd6fd32c312195bdb27a5f12b1e24820b2bef6",
        "aging_requests": "a703ff70c079084bf88b577f765f78c0e43a49ed2814207d430875d66571e477",
    }
    observed_bound = {name: digest(path) for name, path in bound_paths.items()}
    if observed_bound != expected_bound:
        raise RuntimeError(
            {"expected_bound": expected_bound, "observed_bound": observed_bound}
        )

    ARTIFACT.mkdir(parents=True, exist_ok=True)
    binary = ARTIFACT / "ngram_tree_probe"
    command = [
        "g++",
        "-std=c++17",
        "-O2",
        "-I",
        str(CPP),
        str(PROJECT / "ngram_tree_probe.cpp"),
        str(CPP / "trie.cpp"),
        str(CPP / "result.cpp"),
        "-o",
        str(binary),
    ]
    compile_result = subprocess.run(command, text=True, capture_output=True)
    if compile_result.returncode:
        raise RuntimeError(compile_result.stderr)
    probe_result = subprocess.run([str(binary)], text=True, capture_output=True)
    if probe_result.returncode:
        raise RuntimeError(probe_result.stderr)
    probe_rows = [json.loads(line) for line in probe_result.stdout.splitlines()]
    binary.unlink()

    config = json.loads(CONFIG.read_text())["text_config"]
    tail_terminal = json.loads((TAIL / "FINAL_TERMINAL.json").read_text())
    observed_accept_length = tail_terminal["primary"]["metrics_after"][
        "sglang:spec_accept_length"
    ]
    output_tokens = 358
    observed_rounds = output_tokens / observed_accept_length
    full_depth_rounds = output_tokens / 12
    full_depth_reduction = 1 - full_depth_rounds / observed_rounds
    result = {
        "schema_version": 1,
        "classification": "source_bound_offline_causal_probe",
        "source_identity": {
            "sglang_commit": subprocess.run(
                ["git", "-C", str(PINNED), "rev-parse", "HEAD"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip(),
            "sha256": observed,
            "bound_input_sha256": observed_bound,
        },
        "gemma_geometry": {
            "layers": config["num_hidden_layers"],
            "hidden_size": config["hidden_size"],
            "intermediate_size": config["intermediate_size"],
            "vocab_size": config["vocab_size"],
            "attention_heads": config["num_attention_heads"],
            "local_kv_heads": config["num_key_value_heads"],
            "global_kv_heads": config["num_global_key_value_heads"],
            "local_head_dim": config["head_dim"],
            "global_head_dim": config["global_head_dim"],
            "sliding_window": config["sliding_window"],
            "local_layers": config["layer_types"].count("sliding_attention"),
            "global_layers": config["layer_types"].count("full_attention"),
        },
        "ngram_geometry": {
            "draft_rows_per_request": 12,
            "proposed_drafts_per_request": 11,
            "max_trie_depth": 18,
            "bfs_breadth": [1, 10],
            "match_type_control": "BFS",
            "candidate_policy": "request_local_verified_trunk",
        },
        "bound_telemetry": {
            "tail_first_low_acceptance": first_low_acceptance(
                rows(TAIL / "telemetry.jsonl")
            ),
            "aging_first_low_acceptance": first_low_acceptance(
                rows(AGING / "telemetry.jsonl")
            ),
            "tail_divergent_requests": divergent_requests(
                rows(TAIL / "requests.jsonl")
            ),
            "aging_divergent_requests": divergent_requests(
                rows(AGING / "requests.jsonl")
            ),
            "tail_final_accept_length": tail_terminal["primary"]["metrics_after"][
                "sglang:spec_accept_length"
            ],
            "tail_final_accept_rate": tail_terminal["primary"]["metrics_after"][
                "sglang:spec_accept_rate"
            ],
            "tail_peak_queue": tail_terminal["primary"]["queue"][
                "max_server_queue_requests"
            ],
            "tail_elapsed_seconds": tail_terminal["primary"]["elapsed_seconds"],
        },
        "exact_source_probe": probe_rows,
        "negative_discriminators": {
            "built_in_frequency_mode": (
                "rejected: exact pinned Trie::buildFrequency accepts only four "
                "dominant drafts after both the bound three-token transient and "
                "the persistent-alternate-after-four-normal sequence"
            ),
            "global_max_breadth_one": (
                "rejected as the candidate: the structural proxy restores eleven "
                "dominant drafts after the transient, but accepts zero when the "
                "persistent alternate is the most recent global branch"
            ),
        },
        "causal_chain": [
            (
                "NGRAMWorker._update_ngram_corpus inserts every request's last "
                "18 accepted target tokens into one global online corpus after "
                "each verify step"
            ),
            (
                "Trie::buildRecency gives recent children fixed breadth "
                "entitlement with no request-local ownership or support gate"
            ),
            (
                "the exact request-32 three-token transient makes the pinned "
                "source probe accept four drafts, exactly reproducing the final "
                "metric length 5.0 (four drafts plus bonus)"
            ),
            (
                "at c32, length 5 instead of 12 expands a 358-token completion "
                f"from about {full_depth_rounds:.2f} to {observed_rounds:.2f} "
                "fixed target-verify rounds"
            ),
            (
                "each round materializes 12 rows/request through the 60-layer "
                "Gemma target and its 262144-way LM head, so the extra rounds "
                "increase KV allocation/free/move traffic and queueing"
            ),
        ],
        "derived_load_amplification": {
            "evidence_label": "derived from bound metric and fixed source geometry",
            "output_tokens_per_request": output_tokens,
            "observed_rounds_at_accept_length_5": observed_rounds,
            "rounds_at_accept_length_12": full_depth_rounds,
            "target_round_and_row_reduction_if_restored": full_depth_reduction,
            "c32_target_rows_per_round": 32 * 12,
        },
        "candidate": {
            "name": "request_local_verified_trunk",
            "source_symbols": [
                "NGRAMWorker._prepare_draft_tokens",
                "NGRAMWorker._update_ngram_corpus",
                "NgramVerifyInput._fill_requests",
                "ngram::Trie::buildRecency",
            ],
            "source_delta": (
                "retain a bounded per-rid trie containing only that request's "
                "target-verified tokens; at the next draft step reserve its "
                "longest verified continuation as the trunk, then fill unused "
                "rows from the unchanged global buildRecency tree. Seed and "
                "update the local trie only from target-accepted output_ids, "
                "erase it with the existing finished-rid cleanup, and fall back "
                "to the current global tree until a local continuation exists"
            ),
            "material_distinction": (
                "keeps depth 12 and all requests on NGRAM; unlike the closed "
                "threshold-8 bypass it changes neither scheduling nor the target "
                "verification gate, and unlike a global frequency/breadth tune "
                "it prevents one request's branch from displacing another "
                "request's already verified path"
            ),
            "semantics": (
                "target-semantics preserving: all 12 rows still pass through the "
                "unchanged target verifier; only draft-tree topology changes"
            ),
            "predicted_primary_change": (
                "after a rare request diverges, unaffected requests retain their "
                "own accepted trunk instead of inheriting the rare global branch; "
                "their accepted drafts should remain near 11 while target rows "
                "remain 12/request"
            ),
            "predicted_physical_change": (
                "fewer target-verify rounds per 358-token completion, reducing "
                "12-row Gemma target forwards, KV allocate/free/move traffic, and "
                "acceptance synchronization critical time"
            ),
            "predicted_counters": {
                "spec_accept_length": (
                    "unaffected requests remain near 12 after the first rare branch, "
                    "instead of the measured collapse to 5"
                ),
                "spec_accept_rate": (
                    "unaffected-request rate remains near 1.0 instead of about 0.364"
                ),
                "target_verify_rounds_per_358_tokens": (
                    f"fall from about {observed_rounds:.2f} toward "
                    f"{full_depth_rounds:.2f}"
                ),
                "target_rows_per_completion": (
                    f"fall by up to {full_depth_reduction:.3%} at unchanged "
                    "12 rows/round"
                ),
                "kv_slots": (
                    "allocations and rejected-slot frees per completion decrease "
                    "with target-verify round count"
                ),
                "queue": "peak below the measured 41 and no positive terminal drift",
                "gpu_utilization": "may stay saturated; useful tokens/forward must increase",
            },
            "minimal_endpoint_arm": {
                "kind": "candidate_only_full_arrival_1036",
                "control_replay": False,
                "source_or_server_delta": (
                    "apply only the hash-bound request-local verified-trunk "
                    "overlay; retain the pinned image/model/launch, global BFS "
                    "fallback, c32, depth 12, and all other source"
                ),
                "requests": 1036,
                "release_policy": "every request at its bound arrival_s",
                "required_observations": [
                    "normalized 1036/1036 semantic equality",
                    "zero failures and retractions",
                    (
                        "per-request acceptance histogram keyed around the first "
                        "rare-output insertion"
                    ),
                    "target verify forward count and rows",
                    "KV slot allocations and rejected-slot frees",
                    "peak/final queue and release drift",
                    "elapsed seconds and planning cost",
                ],
                "falsification": (
                    "reject if unaffected requests lose accepted depth after the "
                    "first rare output, target rounds do not fall, peak queue "
                    "exceeds 30, final queue is nonzero, release drift grows, "
                    "normalized semantics differ, or cost exceeds $0.14/M"
                ),
            },
        },
    }
    output = ARTIFACT / "RESULT.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (ARTIFACT / "probe.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in probe_rows)
    )
    (ARTIFACT / "CANDIDATE_ARM.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_identity": result["source_identity"],
                "candidate": result["candidate"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(output)


if __name__ == "__main__":
    main()
