#!/usr/bin/env python3
import hashlib
import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[6]
GIB = 1 << 30


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def atomic(path, value):
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    part.replace(path)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def selected(rows, identifier):
    matches = [row for row in rows if row["id"] == identifier]
    require(len(matches) == 1, f"expected_one_{identifier}")
    return matches[0]


def parse_memory_evidence(path):
    text = path.read_text(errors="strict").replace("\r", "\n")
    patterns = {
        "initial_available_gib": r"Load weight begin\. avail mem=([0-9.]+) GB",
        "weight_gib": r"Load weight end\..*mem usage=([0-9.]+) GB",
        "full_pool_tokens": r"full_layer_tokens=(\d+)",
        "swa_pool_tokens": r"swa_layer_tokens=(\d+)",
        "pool_gib": r"SWAKVPool mem usage: ([0-9.]+) GB",
        "pool_end_available_gib": r"Memory pool end\. avail mem=([0-9.]+) GB",
        "graph_gib": r"Capture cuda graph end\..*mem usage=([0-9.]+) GB",
        "post_graph_available_gib": (
            r"Capture cuda graph end\..*avail mem=([0-9.]+) GB"
        ),
    }
    values = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, text)
        require(match is not None, f"missing_memory_evidence:{name}")
        values[name] = float(match.group(1))
    values["full_pool_tokens"] = int(values["full_pool_tokens"])
    values["swa_pool_tokens"] = int(values["swa_pool_tokens"])
    values["pre_pool_non_weight_gib"] = round(
        values["initial_available_gib"]
        - values["weight_gib"]
        - values["pool_gib"]
        - values["pool_end_available_gib"],
        6,
    )
    return values


def workload(rows, begin, end):
    arm = rows[begin:end]
    require([row["i"] for row in arm] == list(range(begin, end)), "request_ids")
    return {
        "begin": begin,
        "end_exclusive": end,
        "requests": len(arm),
        "prompt_tokens": sum(row["usage"]["prompt_tokens"] for row in arm),
        "completion_tokens": sum(
            row["usage"]["completion_tokens"] for row in arm
        ),
        "total_tokens": sum(row["usage"]["total_tokens"] for row in arm),
        "last_bound_arrival_seconds": max(row["scheduled_s"] for row in arm),
    }


def main():
    binding = load(ROOT / "DIRECTOR_BINDING.json")
    verified_files = {}
    for raw_path, expected in binding["files"].items():
        path = Path(raw_path)
        actual = digest(path)
        require(actual == expected, f"director_binding_mismatch:{path}")
        verified_files[str(path)] = {
            "sha256": actual,
            "bytes": path.stat().st_size,
        }

    packet_root = ROOT / "packet"
    candidate_root = packet_root / "candidate-v0.5.15"
    candidate = load(candidate_root / "CANDIDATE_RUNTIME.json")
    require(candidate["candidate"]["release"] == "v0.5.15", "release")
    require(
        candidate["candidate"]["commit"]
        == "f63458b5beaceabbd9d749b9fc956370e1b649e6",
        "commit",
    )
    require(
        candidate["candidate"]["official_image"]
        == (
            "docker.io/lmsysorg/sglang@"
            "sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd"
        ),
        "image",
    )
    require(all(candidate["source_contract"].values()), "source_contract")
    candidate_manifest = load(candidate_root / "SHA256SUMS.json")
    for relative, expected in candidate_manifest.items():
        path = candidate_root / relative
        require(path.is_file(), f"candidate_file_missing:{relative}")
        require(digest(path) == expected, f"candidate_file_mismatch:{relative}")

    source_support = packet_root / "source-support"
    require(
        (source_support / "UPSTREAM_COMMIT").read_text().strip()
        == candidate["candidate"]["commit"],
        "source_support_commit",
    )
    dockerfile = (candidate_root / "source/docker/Dockerfile").read_text()
    fp8_source = (source_support / "fp8.py").read_text()
    model_runner_source = (source_support / "model_runner.py").read_text()
    fused_qk_source = (
        source_support / "fused_qk_rmsnorm_rope_gate.py"
    ).read_text()
    speculative_hook_source = (
        candidate_root / "source/python/sglang/srt/arg_groups/speculative_hook.py"
    ).read_text()
    require("CHOSEN_TORCH_CUDA_ARCH_LIST='9.0;10.0;10.3'" in dockerfile, "sm90")
    require(
        "is_sm90_supported() and not is_sm100_supported()" in fp8_source,
        "fp8_sm90",
    )
    require("torch.float8_e5m2" in model_runner_source, "e5m2")
    require("Only available on NVIDIA Hopper+ (sm_90+)" in fused_qk_source, "qk")
    require(
        "server_args.speculative_num_draft_tokens = 12"
        in speculative_hook_source,
        "ngram_depth",
    )

    accelerator_inventory = load(
        WORKSPACE / "research/factory/data/accelerator_inventory.json"
    )
    h100 = selected(accelerator_inventory["accelerators"], "nvidia-h100-sxm")
    require(h100["memory"]["capacity_gb"] == 80, "h100_capacity")
    require("fp8" in h100["numeric_formats"], "h100_fp8")
    require(h100["architecture_profile_id"] == "nvidia-sm90", "h100_sm90")

    price_inventory = load(WORKSPACE / "research/factory/data/gpu_prices.json")
    h100_price = selected(price_inventory["accelerators"], "nvidia-h100-sxm")
    planning_rate = h100_price["production_planning_usd_per_gpu_hour"]
    require(planning_rate == 2.8, "h100_planning_rate")

    config = load(packet_root / "config.json")["text_config"]
    checkpoint_manifest = load(packet_root / "CHECKPOINT_MANIFEST.json")
    model_index = load(packet_root / "model.safetensors.index.json")
    require(
        checkpoint_manifest["revision"]
        == "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "checkpoint_revision",
    )
    require(
        checkpoint_manifest["total_bytes"] == 62578655208,
        "checkpoint_total_bytes",
    )
    require(
        model_index["metadata"]["total_parameters"] == 32682372656,
        "checkpoint_parameters",
    )
    layer_types = config["layer_types"]
    full_layers = layer_types.count("full_attention")
    swa_layers = layer_types.count("sliding_attention")
    require((full_layers, swa_layers) == (10, 50), "layer_geometry")
    require(config["sliding_window"] == 1024, "sliding_window")
    require(config["attention_k_eq_v"] is True, "attention_k_eq_v")

    full_bytes_per_token = (
        2
        * full_layers
        * config["num_global_key_value_heads"]
        * config["global_head_dim"]
    )
    swa_bytes_per_token = (
        2 * swa_layers * config["num_key_value_heads"] * config["head_dim"]
    )
    require(full_bytes_per_token == 40960, "full_kv_bytes")
    require(swa_bytes_per_token == 409600, "swa_kv_bytes")

    memory_evidence_path = ROOT / "evidence/h200_same_shape_server.stderr"
    observed = parse_memory_evidence(memory_evidence_path)
    observed_pool_bytes = (
        observed["full_pool_tokens"] * full_bytes_per_token
        + observed["swa_pool_tokens"] * swa_bytes_per_token
    )
    observed_pool_gib = observed_pool_bytes / GIB
    require(abs(observed_pool_gib - observed["pool_gib"]) < 0.02, "kv_reconcile")

    nominal_h100_bytes = int(h100["memory"]["capacity_gb"] * 1_000_000_000)
    conservative_h100_gib = nominal_h100_bytes / GIB
    mem_fraction_static = 0.85
    static_budget_gib = conservative_h100_gib * mem_fraction_static
    kv_budget_gib = (
        static_budget_gib
        - observed["weight_gib"]
        - observed["pre_pool_non_weight_gib"]
    )
    pool_ratio = 0.8
    allocation_bytes_per_full_token = (
        full_bytes_per_token + pool_ratio * swa_bytes_per_token
    )
    full_pool_token_floor = math.floor(
        kv_budget_gib * GIB / allocation_bytes_per_full_token
    )
    swa_pool_token_floor = math.floor(full_pool_token_floor * pool_ratio)
    post_graph_headroom_gib = (
        conservative_h100_gib
        - static_budget_gib
        - observed["graph_gib"]
    )
    require(kv_budget_gib > 0, "positive_kv_budget")
    require(post_graph_headroom_gib >= 8.0, "graph_headroom")

    request_rows = [
        json.loads(line)
        for line in (candidate_root / "inputs/requests.jsonl")
        .read_text()
        .splitlines()
    ]
    discriminator = workload(request_rows, 0, 171)
    endpoint = workload(request_rows, 0, 791)
    post_calibration = workload(request_rows, 32, 791)
    require(endpoint["total_tokens"] == 3616452, "endpoint_tokens")
    require(post_calibration["total_tokens"] == 3470148, "post_calibration_tokens")

    target_cost = 0.14
    sustainable_utilization = 0.90
    for arm in (post_calibration, endpoint):
        arm["raw_elapsed_ceiling_seconds"] = round(
            target_cost
            * arm["total_tokens"]
            * 3600
            / (planning_rate * 1_000_000),
            12,
        )
        arm["raw_service_ceiling_seconds_per_request"] = round(
            arm["raw_elapsed_ceiling_seconds"] / arm["requests"],
            12,
        )
        arm["sustainable_90pct_elapsed_ceiling_seconds"] = round(
            arm["raw_elapsed_ceiling_seconds"] * sustainable_utilization,
            12,
        )
        arm["sustainable_90pct_service_ceiling_seconds_per_request"] = round(
            arm["sustainable_90pct_elapsed_ceiling_seconds"] / arm["requests"],
            12,
        )

    draft_depth = 12
    per_request_full_tokens = 4572 + draft_depth
    per_request_swa_tokens = config["sliding_window"] + draft_depth
    full_context_concurrency_floor = min(
        full_pool_token_floor // per_request_full_tokens,
        swa_pool_token_floor // per_request_swa_tokens,
    )
    require(full_context_concurrency_floor >= 18, "fit_concurrency_floor")

    local_snapshot = {
        "candidate_runtime": digest(candidate_root / "CANDIDATE_RUNTIME.json"),
        "candidate_manifest": digest(candidate_root / "SHA256SUMS.json"),
        "runner": digest(packet_root / "h100_matched_runner.py"),
        "requests": digest(candidate_root / "inputs/requests.jsonl"),
        "semantic_rows": digest(
            candidate_root / "inputs/exact_semantic_rows.jsonl"
        ),
        "input_manifest": digest(candidate_root / "inputs/INPUT_MANIFEST.json"),
        "launch": digest(candidate_root / "inputs/ngram-launch.json"),
        "trace_packet": digest(candidate_root / "inputs/TRACE_PACKET.json"),
        "checkpoint_manifest": digest(packet_root / "CHECKPOINT_MANIFEST.json"),
        "config": digest(packet_root / "config.json"),
        "model_index": digest(packet_root / "model.safetensors.index.json"),
        "memory_evidence": digest(memory_evidence_path),
    }
    require(
        local_snapshot["candidate_runtime"]
        == binding["files"][
            "/root/workspace/research/lab/experiments/gemma4_31b/research_lab/"
            "projects/gemma4_upstream_ngram_runtime_rebase/artifacts/"
            "candidate-v0.5.15/CANDIDATE_RUNTIME.json"
        ],
        "candidate_snapshot",
    )
    require(
        local_snapshot["requests"]
        == binding["files"][
            "/root/workspace/research/lab/experiments/gemma4_31b/research_lab/"
            "projects/gemma4_upstream_ngram_runtime_rebase/artifacts/"
            "candidate-v0.5.15/inputs/requests.jsonl"
        ],
        "request_snapshot",
    )
    require(
        local_snapshot["semantic_rows"]
        == binding["files"][
            "/root/workspace/research/lab/experiments/gemma4_31b/research_lab/"
            "projects/gemma4_upstream_ngram_runtime_rebase/artifacts/"
            "candidate-v0.5.15/inputs/exact_semantic_rows.jsonl"
        ],
        "semantic_snapshot",
    )

    analysis = {
        "schema_version": 1,
        "result": "analytical_h100_fit_and_economic_hurdle",
        "evidence_labels": {
            "h100_capacity_and_sm90": "source-backed shared inventory",
            "h100_price": "derived shared planning inventory",
            "weight_graph_and_allocator_sizes": (
                "measured on v0.5.13 H200 SM90 with the same model, launch "
                "geometry, FP8 representation, E5M2 KV, and depth-12 NGRAM"
            ),
            "h100_fit": "conservative analytical lower bound",
            "h100_throughput": "unmeasured",
        },
        "binding_verified": True,
        "verified_files": verified_files,
        "architecture": {
            "accelerator": "nvidia-h100-sxm",
            "sm_count": h100["execution"]["compute_units"],
            "hbm_capacity_inventory_gb": h100["memory"]["capacity_gb"],
            "hbm_capacity_conservative_gib": conservative_h100_gib,
            "hbm_bandwidth_gb_s": h100["memory"]["bandwidth_gb_s"],
            "numeric_format": "fp8",
        },
        "memory": {
            "checkpoint_total_bytes": checkpoint_manifest["total_bytes"],
            "checkpoint_total_parameters": model_index["metadata"][
                "total_parameters"
            ],
            "model_weight_runtime_gib_measured": observed["weight_gib"],
            "pre_pool_non_weight_gib_measured": observed[
                "pre_pool_non_weight_gib"
            ],
            "cuda_graph_gib_measured_same_shape": observed["graph_gib"],
            "static_fraction": mem_fraction_static,
            "static_budget_conservative_gib": static_budget_gib,
            "kv_budget_conservative_gib": kv_budget_gib,
            "post_graph_headroom_conservative_gib": post_graph_headroom_gib,
            "full_attention_layers": full_layers,
            "sliding_attention_layers": swa_layers,
            "full_kv_bytes_per_token": full_bytes_per_token,
            "swa_kv_bytes_per_token": swa_bytes_per_token,
            "swa_full_pool_ratio": pool_ratio,
            "full_pool_token_floor": full_pool_token_floor,
            "swa_pool_token_floor": swa_pool_token_floor,
            "full_context_concurrency_floor": full_context_concurrency_floor,
            "per_request_full_tokens_with_drafts": per_request_full_tokens,
            "per_request_swa_tokens_with_drafts": per_request_swa_tokens,
            "observed_h200_pool_reconciliation_gib": observed_pool_gib,
        },
        "economics": {
            "planning_usd_per_gpu_hour": planning_rate,
            "target_usd_per_million_total_tokens": target_cost,
            "sustainable_utilization": sustainable_utilization,
            "post_calibration_759": post_calibration,
            "endpoint_791": endpoint,
        },
        "support": {
            "official_image_sm90_arch": {
                "supported": True,
                "source": "packet/candidate-v0.5.15/source/docker/Dockerfile",
            },
            "dynamic_fp8_sm90_path": {
                "supported": True,
                "source": "packet/source-support/fp8.py",
            },
            "fp8_e5m2_kv": {
                "supported": True,
                "source": "packet/source-support/model_runner.py",
            },
            "gemma_hybrid_attention": True,
            "triton_prefill_decode_and_target_verify": True,
            "native_ngram_depth_12": {
                "supported": True,
                "source": (
                    "packet/candidate-v0.5.15/source/python/sglang/srt/"
                    "arg_groups/speculative_hook.py"
                ),
            },
            "ngram_cuda_graph_capture": True,
            "fused_qk_norm_rope_hopper": {
                "supported": True,
                "source": (
                    "packet/source-support/fused_qk_rmsnorm_rope_gate.py"
                ),
            },
            "single_gpu_tp1_no_peer_topology_dependency": True,
        },
        "bound_feature_trace": [
            {
                "feature": "BF16 activations plus dynamic FP8 weights",
                "status": "official_sm90_path",
                "evidence": "packet/source-support/fp8.py",
                "h100_risk": "Auto-selected GEMM implementation can change latency.",
            },
            {
                "feature": "FP8 E5M2 KV cache",
                "status": "official_cuda_dtype_and_pool_path",
                "evidence": "packet/source-support/model_runner.py",
                "h100_risk": "Capacity only; dtype is native to SM90.",
            },
            {
                "feature": "Gemma 4 five-local/one-global hybrid attention",
                "status": "official_model_and_hybrid_dispatch",
                "evidence": (
                    "packet/candidate-v0.5.15/source/python/sglang/srt/"
                    "models/gemma4_causal.py"
                ),
                "h100_risk": (
                    "Lower HBM bandwidth and L2 than H200 can increase service time."
                ),
            },
            {
                "feature": (
                    "Triton prefill, decode, target verify, page size 1, "
                    "and eight KV splits"
                ),
                "status": "official_cuda_triton_path",
                "evidence": (
                    "packet/candidate-v0.5.15/source/python/sglang/srt/"
                    "layers/attention/triton_backend.py"
                ),
                "h100_risk": "Exact SM occupancy and split efficiency are unmeasured.",
            },
            {
                "feature": "Native NGRAM with default depth 12",
                "status": "official_registered_cpu_producer_and_cuda_consumer",
                "evidence": (
                    "packet/candidate-v0.5.15/source/python/sglang/srt/"
                    "arg_groups/speculative_hook.py"
                ),
                "h100_risk": "Activation and semantics require the 171-request arm.",
            },
            {
                "feature": "NGRAM CUDA graphs through batch size 32",
                "status": "official_capture_geometry",
                "evidence": (
                    "packet/candidate-v0.5.15/source/python/sglang/srt/"
                    "model_executor/runner/decode_cuda_graph_runner.py"
                ),
                "h100_risk": "Graph allocation must pass the live H100 fit parser.",
            },
            {
                "feature": "Fused Q/K RMSNorm and RoPE",
                "status": "official_hopper_path",
                "evidence": "packet/source-support/fused_qk_rmsnorm_rope_gate.py",
                "h100_risk": "None beyond the live SM90 import/kernel smoke.",
            },
            {
                "feature": "Dynamic chunking 2048 and one continuous decode step",
                "status": "hardware_independent_scheduler_contract",
                "evidence": (
                    "packet/candidate-v0.5.15/source/python/sglang/srt/server_args.py"
                ),
                "h100_risk": "Queue trajectory is unmeasured and remains an endpoint gate.",
            },
            {
                "feature": "Gemma 4 tool parser and metrics",
                "status": "host_side_runtime_contract",
                "evidence": "digest-bound official image and exact launch validation",
                "h100_risk": "No accelerator-specific dependency.",
            },
            {
                "feature": "TP=1 single GPU",
                "status": "no_peer_collective_required",
                "evidence": "exact launch plus accelerator inventory",
                "h100_risk": "No NVLink/topology dependency.",
            },
        ],
        "risks_requiring_direct_measurement": [
            "Official v0.5.15 startup allocation and CUDA graph capture on an actual H100.",
            "H100 service time, queue trajectory, native NGRAM activation, and exact semantics.",
            "CUDA 12.9 image compatibility with the future H100 bench driver.",
        ],
    }
    atomic(ROOT / "H100_FIT_HURDLE.json", analysis)

    launch = candidate["reproduction"]["container"]["command"]
    packet = {
        "schema_version": 1,
        "decision": "nominate_one",
        "authority": {
            "current_provider_spend_usd": 0,
            "gpu_claim_authorized": False,
            "required_future_authority": (
                "Director-authorized H100 bench plus positive spend reservation."
            ),
        },
        "hardware": {
            "accelerator": "nvidia-h100-sxm",
            "count": 1,
            "minimum_hbm_gb": 80,
            "topology": "single GPU; TP=1; NVLink not required",
            "resident_state": (
                "No H100 bench exists in current pool; require the exact checkpoint "
                "snapshot and digest-pinned image or empty capacity for staging."
            ),
        },
        "identity": {
            "model": binding["model"],
            "checkpoint_manifest": local_snapshot["checkpoint_manifest"],
            "runtime_release": candidate["candidate"]["release"],
            "runtime_commit": candidate["candidate"]["commit"],
            "image": candidate["candidate"]["official_image"],
            "image_platform": candidate["candidate"]["official_image_platform"],
            "runner_sha256": local_snapshot["runner"],
            "launch_sha256": local_snapshot["launch"],
            "requests_sha256": local_snapshot["requests"],
            "semantic_rows_sha256": local_snapshot["semantic_rows"],
        },
        "preclaim_materialization": {
            "status": "required_before_future_claim",
            "reason": (
                "The current zero-cost phase forbids model-weight copies. Before "
                "claiming a future H100, materialize the CHECKPOINT_MANIFEST-bound "
                "bytes under this project or admit an immutable project-local "
                "snapshot under an amended storage contract; never resolve the "
                "other project's mutable path after claim."
            ),
            "source_manifest": "packet/CHECKPOINT_MANIFEST.json",
            "candidate_snapshot": "packet/candidate-v0.5.15",
        },
        "launch": {
            "container_command": launch,
            "container_runtime_options": candidate["reproduction"]["container"][
                "runtime_options"
            ],
            "checkpoint_mount_target": "/work/checkpoint",
            "no_flag_change": True,
        },
        "arms": [
            {
                "name": "activation_fit_semantic_discriminator",
                "requests": 171,
                "command": [
                    "env",
                    "UPSTREAM_REBASE_ROOT=/absolute/project/packet/candidate-v0.5.15",
                    "UPSTREAM_REBASE_OUT=/absolute/project/artifacts/h100-discriminator",
                    "UPSTREAM_REBASE_REQUESTS=171",
                    "python3",
                    "/absolute/project/packet/h100_matched_runner.py",
                ],
                "gates": {
                    "server_start_and_graph_capture_complete": True,
                    "analytical_full_pool_token_floor": full_pool_token_floor,
                    "analytical_swa_pool_token_floor": swa_pool_token_floor,
                    "required_full_pool_tokens_at_least": (
                        18 * per_request_full_tokens
                    ),
                    "required_swa_pool_tokens_at_least": (
                        18 * per_request_swa_tokens
                    ),
                    "post_graph_available_gib_at_least": 8.0,
                    "all_normalized_semantics_exact": True,
                    "failures": 0,
                    "max_spec_accept_length_greater_than": 1,
                    "release_drift_seconds_abs_max": 0.25,
                },
            },
            {
                "name": "conditional_matched_endpoint",
                "condition": (
                    "Run once only after every discriminator gate passes, using a "
                    "fresh identical container so corpus state starts empty."
                ),
                "requests": 791,
                "command": [
                    "env",
                    "UPSTREAM_REBASE_ROOT=/absolute/project/packet/candidate-v0.5.15",
                    "UPSTREAM_REBASE_OUT=/absolute/project/artifacts/h100-endpoint",
                    "UPSTREAM_REBASE_REQUESTS=791",
                    "python3",
                    "/absolute/project/packet/h100_matched_runner.py",
                ],
                "gates": {
                    "all_normalized_semantics_exact": True,
                    "failures": 0,
                    "max_spec_accept_length_greater_than": 1,
                    "queue_peak_at_most": 30,
                    "queue_final": 0,
                    "raw_elapsed_seconds_at_most": endpoint[
                        "raw_elapsed_ceiling_seconds"
                    ],
                    "raw_service_seconds_per_request_at_most": endpoint[
                        "raw_service_ceiling_seconds_per_request"
                    ],
                    "sustainable_90pct_service_seconds_per_request_at_most": endpoint[
                        "sustainable_90pct_service_ceiling_seconds_per_request"
                    ],
                },
            },
        ],
        "deadline": {
            "max_claimed_minutes": 45,
            "release": (
                "Release available when unoccupied and healthy; maintenance if "
                "resident state is unsafe or requires director disposition."
            ),
        },
        "local_snapshot_sha256": local_snapshot,
    }
    atomic(ROOT / "H100_EXECUTION_PACKET.json", packet)

    manifest = {}
    for path in sorted(
        [
            ROOT / "DIRECTOR_BINDING.json",
            ROOT / "H100_FIT_HURDLE.json",
            ROOT / "H100_EXECUTION_PACKET.json",
            ROOT / "derive_h100_packet.py",
            memory_evidence_path,
            packet_root / "CHECKPOINT_MANIFEST.json",
            packet_root / "config.json",
            packet_root / "model.safetensors.index.json",
            packet_root / "h100_matched_runner.py",
            source_support / "UPSTREAM_COMMIT",
            source_support / "fp8.py",
            source_support / "fused_qk_rmsnorm_rope_gate.py",
            source_support / "model_runner.py",
            candidate_root / "CANDIDATE_RUNTIME.json",
            candidate_root / "SHA256SUMS.json",
            candidate_root / "inputs/INPUT_MANIFEST.json",
            candidate_root / "inputs/TRACE_PACKET.json",
            candidate_root / "inputs/exact_semantic_rows.jsonl",
            candidate_root / "inputs/ngram-launch.json",
            candidate_root / "inputs/requests.jsonl",
        ]
    ):
        manifest[str(path.relative_to(ROOT))] = {
            "sha256": digest(path),
            "bytes": path.stat().st_size,
        }
    atomic(ROOT / "PACKET_MANIFEST.json", manifest)
    print(
        json.dumps(
            {
                "decision": packet["decision"],
                "full_pool_token_floor": full_pool_token_floor,
                "post_graph_headroom_gib": post_graph_headroom_gib,
                "raw_service_ceiling_seconds_per_request": endpoint[
                    "raw_service_ceiling_seconds_per_request"
                ],
                "sustainable_90pct_service_ceiling_seconds_per_request": endpoint[
                    "sustainable_90pct_service_ceiling_seconds_per_request"
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
