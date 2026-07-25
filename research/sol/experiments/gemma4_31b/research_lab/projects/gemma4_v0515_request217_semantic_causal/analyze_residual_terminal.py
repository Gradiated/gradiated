#!/usr/bin/env python3

import hashlib
import io
import json
import tarfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
PROJECTS = PROJECT.parent
RUNTIME_SOURCE = Path(
    "/root/workspace/.agents/runtime/sglang-v0.5.15-full-checkout"
)
ARTIFACT = PROJECT / "artifacts/request217-decode-20260725t072904z"
RETRIEVED = ARTIFACT / "retrieved"
OUT = RETRIEVED / "out"
PRIOR_REQUESTS = (
    PROJECTS
    / "gemma4_upstream_ngram_runtime_rebase"
    / "artifacts/v0515-endpoint-20260725t062540z"
    / "retrieved-final/endpoint-stage/out-endpoint/requests.jsonl"
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text())


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def canonical_jsonl_hash(values) -> str:
    payload = "".join(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
        for value in values
    )
    return sha256_bytes(payload.encode())


def run_lengths(values):
    runs = []
    for value in values:
        if runs and runs[-1]["token"] == value:
            runs[-1]["count"] += 1
        else:
            runs.append({"token": value, "count": 1})
    return runs


def arg_value(args, name):
    index = args.index(name)
    return args[index + 1]


def excerpt_hash(path: Path, start: int, end: int) -> str:
    lines = path.read_text().splitlines(keepends=True)
    return sha256_bytes("".join(lines[start - 1 : end]).encode())


def verify_archive():
    expected_archive_hash = (
        ARTIFACT / "compact.tar.gz.sha256"
    ).read_text().split()[0]
    archive_hash = sha256_file(ARTIFACT / "compact.tar.gz")
    assert archive_hash == expected_archive_hash
    members = {}
    with tarfile.open(ARTIFACT / "compact.tar.gz", "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            extracted = archive.extractfile(member)
            assert extracted is not None
            payload = extracted.read()
            local_path = RETRIEVED / member.name
            assert local_path.read_bytes() == payload
            members[member.name] = {
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
            }
    return archive_hash, members


def verify_source():
    source_paths = {
        "model_runner": RUNTIME_SOURCE
        / "python/sglang/srt/model_executor/model_runner.py",
        "hybrid_backend": RUNTIME_SOURCE
        / "python/sglang/srt/layers/attention/hybrid_attn_backend.py",
        "base_backend": RUNTIME_SOURCE
        / "python/sglang/srt/layers/attention/base_attn_backend.py",
        "triton_backend": RUNTIME_SOURCE
        / "python/sglang/srt/layers/attention/triton_backend.py",
        "server_args": RUNTIME_SOURCE / "python/sglang/srt/server_args.py",
    }
    expected_hashes = {
        "model_runner": "91fcb5873f26679498eec052c68e1d91102af79cdf7d0486dd5aa9f68e839171",
        "hybrid_backend": "9ed86790c5f00ce6b156aa7eccbe716f03fe49f6eacda805f47f3d277ea4ff04",
        "base_backend": "d7912f9b66bab506dd51ad9f8a78bcd4de401eaf0bce0da0118bf661418b6e52",
        "triton_backend": "c09161c77e4586064c0d70c5dda4f943378510a4facb187590ac31e17b0e6e73",
        "server_args": "555c2555bd93ed1596ccd57984ce4fc17e6ef6ba29c0146566b8d4d887d36e0a",
    }
    for name, path in source_paths.items():
        assert sha256_file(path) == expected_hashes[name]

    model_runner = source_paths["model_runner"].read_text()
    hybrid = source_paths["hybrid_backend"].read_text()
    base = source_paths["base_backend"].read_text()
    triton = source_paths["triton_backend"].read_text()
    assert (
        "if self.decode_attention_backend_str != self.prefill_attention_backend_str:"
        in model_runner
    )
    assert (
        'if self.model_runner.server_args.speculative_attention_mode == "decode"'
        in hybrid
    )
    assert "return backend.forward_extend(" in hybrid
    assert "elif forward_batch.forward_mode.is_decode():" in base
    assert "return self.forward_extend(" in base
    assert "and forward_batch.forward_mode.is_target_verify()" in triton
    assert "self.extend_attention_fwd(" in triton

    ranges = {
        "model_runner": (2531, 2567),
        "hybrid_backend_select": (28, 52),
        "hybrid_backend_forward_extend": (125, 138),
        "base_backend_dispatch": (158, 201),
        "triton_target_verify_extend": (1280, 1368),
        "server_args_mode": (1637, 1643),
        "server_args_backend_resolution": (6461, 6472),
    }
    range_paths = {
        "model_runner": source_paths["model_runner"],
        "hybrid_backend_select": source_paths["hybrid_backend"],
        "hybrid_backend_forward_extend": source_paths["hybrid_backend"],
        "base_backend_dispatch": source_paths["base_backend"],
        "triton_target_verify_extend": source_paths["triton_backend"],
        "server_args_mode": source_paths["server_args"],
        "server_args_backend_resolution": source_paths["server_args"],
    }
    return {
        name: {
            "path": str(source_paths[name]),
            "sha256": expected_hashes[name],
        }
        for name in source_paths
    }, {
        name: {
            "path": str(range_paths[name]),
            "lines": list(line_range),
            "sha256": excerpt_hash(range_paths[name], *line_range),
        }
        for name, line_range in ranges.items()
    }


def main():
    archive_hash, archive_members = verify_archive()
    source_files, source_excerpts = verify_source()
    terminal = load_json(OUT / "FINAL_TERMINAL.json")
    activation = load_json(OUT / "ACTIVATION_IDENTITY.json")
    invocation = load_json(OUT / "INVOCATION_STATE.json")
    launch = load_json(PROJECT / "inputs/decode_attention_launch.json")["args"]
    rows = load_jsonl(OUT / "requests.jsonl")
    telemetry = load_jsonl(OUT / "telemetry.jsonl")
    prior_rows = load_jsonl(PRIOR_REQUESTS)[:218]

    assert sha256_file(OUT / "FINAL_TERMINAL.json") == (
        "ed726a2f0d7af3305365ee9fba78747d7a31271b763f5f18737375ede7d80e12"
    )
    assert activation["launch_args"] == launch
    assert activation["container_identity"]["actual_command"][3:] == launch
    assert activation["container_identity"]["expected_command"][3:] == launch
    assert invocation == {
        "phase": "candidate_requests_0_through_217",
        "requests": 218,
        "science_started": True,
    }
    assert len(rows) == 218
    assert [row["i"] for row in rows] == list(range(218))
    assert all("error" not in row for row in rows)

    mismatches = [
        {
            "request": row["i"],
            "first_output_token_mismatch": row["first_output_token_mismatch"],
        }
        for row in rows
        if not row["semantic_matches_bound"]
    ]
    max_release_drift = max(
        abs(row["released_s"] - row["arrival_s"]) for row in rows
    )
    accept_lengths = [
        row["metrics"]["sglang:spec_accept_length"]
        for row in telemetry
        if "metrics" in row
        and "sglang:spec_accept_length" in row["metrics"]
    ]
    recomputed_decision = {
        "all_218_complete": len(rows) == 218,
        "failures_zero": True,
        "native_ngram_activation_observed": max(accept_lengths) > 1,
        "normalized_semantics_exact": not mismatches,
        "release_drift_bounded": max_release_drift <= 0.25,
        "request_217_token_19_exact": rows[217][
            "first_output_token_mismatch"
        ]
        is None,
    }
    assert terminal["decision"] == recomputed_decision
    assert terminal["first_semantic_divergence"] == mismatches[0]
    assert terminal["max_spec_accept_length"] == max(accept_lengths)
    assert terminal["requests"] == len(rows)

    current_semantic_hash = canonical_jsonl_hash(
        row["semantic"] for row in rows
    )
    prior_semantic_hash = canonical_jsonl_hash(
        row["semantic"] for row in prior_rows
    )
    assert current_semantic_hash == prior_semantic_hash

    request_217 = rows[217]
    request_217_prior = prior_rows[217]
    assert request_217["semantic"] == request_217_prior["semantic"]
    assert request_217["first_output_token_mismatch"] == 19
    assert run_lengths(request_217["semantic"]["output_ids"]) == [
        {"token": 51935, "count": 19},
        {"token": 3055, "count": 339},
    ]

    prefill_backend = arg_value(launch, "--prefill-attention-backend")
    decode_backend = arg_value(launch, "--decode-attention-backend")
    speculative_mode = arg_value(launch, "--speculative-attention-mode")
    assert prefill_backend == decode_backend == "triton"
    assert speculative_mode == "decode"

    telemetry_monotonic = all(
        telemetry[index]["elapsed_s"] >= telemetry[index - 1]["elapsed_s"]
        for index in range(1, len(telemetry))
    )
    request_217_metrics = [
        row["metrics"]
        for row in telemetry
        if request_217["released_s"]
        <= row["elapsed_s"]
        <= request_217["completed_s"]
        and "metrics" in row
    ]
    assert telemetry_monotonic
    assert any(
        metrics.get("sglang:spec_accept_length") == 12.0
        for metrics in request_217_metrics
    )

    verification = {
        "schema_version": 1,
        "result": "mechanically_verified",
        "archive": {
            "path": str(ARTIFACT / "compact.tar.gz"),
            "sha256": archive_hash,
            "all_members_match_retrieved_bytes": True,
            "members": archive_members,
        },
        "terminal": {
            "path": str(OUT / "FINAL_TERMINAL.json"),
            "sha256": sha256_file(OUT / "FINAL_TERMINAL.json"),
            "decision_recomputed_exactly": True,
            "first_semantic_divergence": mismatches[0],
        },
        "identity": {
            "launch_matches_activation_actual_and_expected_command": True,
            "prefill_attention_backend": prefill_backend,
            "decode_attention_backend": decode_backend,
            "speculative_attention_mode": speculative_mode,
            "runtime_commit": activation["candidate_commit"],
            "runtime_image": activation["candidate_image"],
        },
        "requests": {
            "complete_rows": len(rows),
            "failures": 0,
            "max_release_drift_seconds": max_release_drift,
            "first_218_semantics_sha256": current_semantic_hash,
            "prior_endpoint_first_218_semantics_sha256": prior_semantic_hash,
            "all_first_218_semantics_identical_to_prior_endpoint": True,
            "request_217_output_runs": run_lengths(
                request_217["semantic"]["output_ids"]
            ),
        },
        "telemetry": {
            "rows": len(telemetry),
            "elapsed_monotonic": telemetry_monotonic,
            "max_spec_accept_length": max(accept_lengths),
            "max_running_requests": max(
                row["metrics"]["sglang:num_running_reqs"]
                for row in telemetry
                if "metrics" in row
            ),
            "max_queue_requests": max(
                row["metrics"]["sglang:num_queue_reqs"]
                for row in telemetry
                if "metrics" in row
            ),
            "request_217_window_observed_accept_length_12": True,
        },
        "source_files": source_files,
        "source_excerpts": source_excerpts,
    }
    verification_path = PROJECT / "RESIDUAL_MECHANICAL_VERIFICATION.json"
    verification_path.write_text(
        json.dumps(verification, indent=2, sort_keys=True) + "\n"
    )

    typed_none = {
        "schema_version": 1,
        "result": "typed_none",
        "classification": "no_materially_distinct_exactness_preserving_repair_candidate",
        "mechanical_verification": {
            "path": verification_path.name,
            "sha256": sha256_file(verification_path),
        },
        "measured": {
            "candidate_sample_consumed": True,
            "complete_requests": 218,
            "failures": 0,
            "native_ngram_activation_observed": True,
            "request_217_divergence": {
                "output_token_index": 19,
                "actual_token": 3055,
                "bound_token": 51935,
            },
            "candidate_and_prior_first_218_semantics_identical": True,
            "first_218_semantics_sha256": current_semantic_hash,
        },
        "source_derived": {
            "launch_backend_pair": {
                "prefill": prefill_backend,
                "decode": decode_backend,
            },
            "hybrid_backend_constructed": False,
            "speculative_attention_mode_runtime_routing_activated": False,
            "causal_chain": [
                "ServerArgs resolves both explicit per-mode attention backends to triton.",
                "ModelRunner constructs HybridAttnBackend only when the resolved backend names differ.",
                "The speculative_attention_mode runtime read that selects a backend is inside HybridAttnBackend.",
                "Without HybridAttnBackend, TARGET_VERIFY reaches the single Triton backend.",
                "Base AttentionBackend dispatches every non-DECODE mode, including TARGET_VERIFY, to forward_extend.",
                "Triton TARGET_VERIFY therefore retains extend_attention_fwd with its tree mask; the flag does not invoke forward_decode or decode_attention_fwd.",
                "The unchanged execution path explains the byte-identical first-218 semantic trajectory and preserved request-217 verifier-bonus divergence.",
            ],
        },
        "inferred": {
            "remaining_scientific_boundary": "multi-token TARGET_VERIFY state/attention/numerical dataflow before the greedy verifier bonus",
            "same_backend_wrapper_patch": "not_materially_distinct: constructing two Triton objects would still call Triton forward_extend for TARGET_VERIFY",
            "alternate_backend_launch": "not_causal: it would be a backend replacement/sweep and still a multi-token extend path, without evidence that it preserves ordinary-decode logits",
            "serial_decode_verification": "not_economic: it removes the depth-12 target-transformer amortization that makes native NGRAM competitive and adds proposal/verification overhead to ordinary decode",
        },
        "candidate": None,
        "discriminator_packet": None,
        "replay_prohibited": [
            "request217_decode_attention_semantic_discriminator",
            "rejected_791_request_endpoint",
        ],
        "next_action": "Close this v0.5.15 request-217 semantic-repair route; no further H200 sample is justified by the bound evidence.",
    }
    typed_none_path = PROJECT / "TYPED_NONE.json"
    typed_none_path.write_text(
        json.dumps(typed_none, indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps(
            {
                "verification": {
                    "path": str(verification_path),
                    "sha256": sha256_file(verification_path),
                },
                "typed_none": {
                    "path": str(typed_none_path),
                    "sha256": sha256_file(typed_none_path),
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
