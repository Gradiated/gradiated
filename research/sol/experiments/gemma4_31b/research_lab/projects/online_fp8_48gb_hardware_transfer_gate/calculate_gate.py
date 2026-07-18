#!/usr/bin/env python3
"""Build the content-bound online-FP8 48-GiB transfer gate."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
WORKSPACE = LAB.parents[4]

SOURCES = {
    "gpu_prices": WORKSPACE / "research/factory/data/gpu_prices.json",
    "accelerator_inventory": WORKSPACE / "research/factory/data/accelerator_inventory.json",
    "online_fp8_identity": LAB / "projects/l40s_online_fp8_actual_consumer_floor/artifacts/DIRECTOR_IDENTITY_ASSERTION.json",
    "c12_queue_capacity": LAB / "projects/l40s_fp8_c12_c14_background_queue_bound/QUEUE_BOUND.json",
    "attention_kv_residual": LAB / "projects/l40s_fp8_attention_kv_residual_floor/ATTENTION_KV_RESIDUAL_FLOOR.json",
    "prior_48gb_screen": LAB / "projects/w4_48gb_hardware_price_screen/HARDWARE_SCREEN.json",
}

EXPECTED_HASHES = {
    "gpu_prices": "3f403d67a92fc91be85bbd27dede85f5f91c3fd2df25ef8dcef2a344acbd1e01",
    "accelerator_inventory": "bcb33ac6814400f6ab79faa7e44c0ced2d6fe2ac5d19dc43f4ee10b12d7ea6b8",
    "online_fp8_identity": "dd98a5ab4dbc24187b439c49f7801bb412093f80e7ff2552777f8b4451dc6174",
    "c12_queue_capacity": "14f9254098e14c95272863e8b4119fdaaf6d833f4c01a531b9fbd204b506d965",
    "attention_kv_residual": "f38704b6ae0e47e389643062c239a492d430079bf80754d8819f9a36b79aef08",
    "prior_48gb_screen": "6d8695147d3c72995e5e0089288e5191e66e727192207f667f2b9adfbf846a20",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> dict:
    path = SOURCES[name]
    actual = sha256(path)
    if actual != EXPECTED_HASHES[name]:
        raise RuntimeError(f"source_hash_mismatch:{name}:{actual}")
    return json.loads(path.read_text())


def one(rows: list[dict], ident: str) -> dict:
    matches = [row for row in rows if row["id"] == ident]
    if len(matches) != 1:
        raise RuntimeError(f"inventory_identity_count:{ident}:{len(matches)}")
    return matches[0]


prices = load("gpu_prices")
inventory = load("accelerator_inventory")
identity = load("online_fp8_identity")
queue = load("c12_queue_capacity")
residual = load("attention_kv_residual")
prior = load("prior_48gb_screen")

now = dt.datetime.now(dt.timezone.utc)
price_time = dt.datetime.fromisoformat(prices["refreshed_at_utc"].replace("Z", "+00:00"))
inventory_time = dt.datetime.fromisoformat(inventory["reviewed_at_utc"].replace("Z", "+00:00"))
price_age_days = (now - price_time).total_seconds() / 86400
inventory_age_days = (now - inventory_time).total_seconds() / 86400
assert price_age_days <= prices["refresh_interval_days"]
assert inventory_age_days <= inventory["review_interval_days"]

l40s = one(inventory["accelerators"], "nvidia-l40s")
rtx = one(inventory["accelerators"], "nvidia-rtx-6000-ada")
a40 = one(inventory["accelerators"], "nvidia-a40")
l40s_price = one(prices["accelerators"], "nvidia-l40s")

assert identity["pass"] is True
exact = identity["extracted"]
assert exact["fp8_consumer"] == [["vllm.model_executor.layers.quantization.fp8.Fp8LinearMethod", "1d6ef3182fb5c72808414cdf14177131121f2b8fb6e94012696f0fdde4f74c48"]]
assert l40s["architecture_profile_id"] == rtx["architecture_profile_id"] == "nvidia-sm89"
assert l40s["execution"]["compute_units"] == rtx["execution"]["compute_units"] == 142
assert l40s["cache"]["last_level_mb"] == rtx["cache"]["last_level_mb"] == 96
assert l40s["memory"]["capacity_gb"] == rtx["memory"]["capacity_gb"] == 48
assert "fp8" in l40s["numeric_formats"] and "fp8" in rtx["numeric_formats"]
assert "fp8" not in a40["numeric_formats"]

capacity_rows = {row["concurrency"]: row for row in queue["memory_capacity"]["rows"]}
c12 = capacity_rows[12]
c14 = capacity_rows[14]
assert c12["peak_headroom_gib"] >= 0.25
assert c14["peak_headroom_gib"] < 0.25

strict_cost = queue["identities"]["strict_market_cost_usd_per_request"]
factors = queue["identities"]["all_in_scenario_factors"]["planning_base"]
all_in_factor = (
    factors["non_gpu"]
    * factors["reliability"]
    * factors["replica_headroom"]
    * factors["storage_orchestration"]
    / factors["utilization"]
)
l40s_rate = l40s_price["production_planning_usd_per_gpu_hour"]
l40s_required_rps = l40s_rate * all_in_factor / (3600 * strict_cost)
assert abs(l40s_required_rps - queue["identities"]["strict_planning_hurdle_requests_per_second"]) < 1e-12

prior_rtx = next(row for row in prior["candidates"] if row["id"] == "nvidia-rtx-6000-ada")
listing_rate = prior_rtx["observed_public_rate_usd_per_gpu_hour"]
assert listing_rate == 0.77
candidate_required_rps = listing_rate * all_in_factor / (3600 * strict_cost)
candidate_service_ceiling = 1.0 / candidate_required_rps
parity_throughput_ratio = listing_rate / l40s_rate
parity_max_slowdown = 1.0 / parity_throughput_ratio
ten_percent_better_ratio = listing_rate / (0.9 * l40s_rate)
ten_percent_better_max_slowdown = 1.0 / ten_percent_better_ratio

shapes = exact["shapes"]
shape_rows = [
    {"name": name, "k": dims[0], "n": dims[1]}
    for name, dims in shapes.items()
]

gate = {
    "schema_version": 1,
    "generated_utc": now.isoformat().replace("+00:00", "Z"),
    "decision": "conditional_matched_hardware_arm",
    "nominee": "nvidia-rtx-6000-ada",
    "evidence_scope": "content-bound shared inventory/pricing plus derived arithmetic; no provider query, GPU, image, checkpoint, compilation, live-owner observation, or throughput transfer",
    "identities": {
        "model": exact["model"],
        "revision": exact["revision"],
        "runtime_image": exact["runtime_image"],
        "consumer": exact["fp8_consumer"][0],
        "workload": exact["workload"],
        "tp": 1,
        "operating_concurrency": 12,
        "exact_linear_shapes": shape_rows,
    },
    "freshness": {
        "gpu_prices_refreshed_at_utc": prices["refreshed_at_utc"],
        "gpu_prices_age_days": price_age_days,
        "gpu_prices_fresh": True,
        "accelerator_inventory_reviewed_at_utc": inventory["reviewed_at_utc"],
        "accelerator_inventory_age_days": inventory_age_days,
        "accelerator_inventory_current": True,
    },
    "candidate_set": {
        "inventory_bound_48_gb_ids": ["nvidia-a40", "nvidia-l40s", "nvidia-rtx-6000-ada"],
        "comparator": {
            "id": l40s["id"],
            "architecture": l40s["architecture_profile_id"],
            "sm_count": l40s["execution"]["compute_units"],
            "tensor_formats": l40s["numeric_formats"],
            "memory_capacity_gb": l40s["memory"]["capacity_gb"],
            "memory_bandwidth_gb_s": l40s["memory"]["bandwidth_gb_s"],
            "l2_mb": l40s["cache"]["last_level_mb"],
            "power_w": l40s["power_w"],
            "topology": l40s["interconnect"]["topology"],
            "planning_rate_usd_per_gpu_hour": l40s_rate,
        },
        "nominee": {
            "id": rtx["id"],
            "architecture": rtx["architecture_profile_id"],
            "sm_count": rtx["execution"]["compute_units"],
            "tensor_formats": rtx["numeric_formats"],
            "memory_capacity_gb": rtx["memory"]["capacity_gb"],
            "memory_bandwidth_gb_s": rtx["memory"]["bandwidth_gb_s"],
            "l2_mb": rtx["cache"]["last_level_mb"],
            "power_w": rtx["power_w"],
            "topology": rtx["interconnect"]["topology"],
            "availability_class": rtx["availability"],
            "price_inventory_id": rtx["price_inventory_id"],
            "compatibility": "same SM89 profile, 142 SMs, 96-MB L2, CUDA stack and native FP8 as L40S; this is source/architecture admission only and fresh exact-image execution remains mandatory",
        },
        "rejected": [{
            "id": a40["id"],
            "reason": "shared inventory binds SM86 and no native FP8; it is not content-bound compatible with the exact SM89 online-FP8 consumer/kernel lane",
        }],
    },
    "capacity_gate": {
        "usable_envelope_gib": c12["usable_envelope_gib"],
        "minimum_required_logical_headroom_gib": 0.25,
        "c12": c12,
        "c14_rejected": c14,
        "decision": "c12 passes the logical gate with 0.827762 GiB peak-context headroom; c14 fails the 0.25-GiB rule and is excluded",
        "runtime_rule": "candidate peak_reserved_gib plus 0.25 must be <=44.704; logical accounting cannot substitute for measured allocator telemetry",
    },
    "economics": {
        "strict_market_cost_usd_per_request": strict_cost,
        "planning_all_in_factor": all_in_factor,
        "l40s": {
            "committed_planning_rate_usd_per_gpu_hour": l40s_rate,
            "strict_required_completed_rps": l40s_required_rps,
            "whole_service_ceiling_seconds_per_request": 1.0 / l40s_required_rps,
        },
        "rtx_6000_ada": {
            "provisional_public_on_demand_listing_usd_per_gpu_hour": listing_rate,
            "listing_source_id": prior_rtx["rate_evidence"],
            "production_planning_rate_status": "missing_from_fresh_shared_price_inventory",
            "quote_cap_usd_per_gpu_hour": listing_rate,
            "strict_required_completed_rps_at_quote_cap": candidate_required_rps,
            "whole_service_ceiling_seconds_per_request_at_quote_cap": candidate_service_ceiling,
            "formula_required_rps_at_quote_q": "q * 1.4415758823529419 / (3600 * 0.000614287)",
        },
        "versus_l40s_at_quote_cap": {
            "equal_all_in_minimum_throughput_ratio": parity_throughput_ratio,
            "equal_all_in_maximum_request_time_slowdown": parity_max_slowdown,
            "ten_percent_better_minimum_throughput_ratio": ten_percent_better_ratio,
            "ten_percent_better_maximum_request_time_slowdown": ten_percent_better_max_slowdown,
            "transfer_prohibited": "These ratios are decision thresholds only. No L40S component or endpoint throughput is assigned to RTX 6000 Ada.",
        },
    },
    "activation_trigger": {
        "name": "VALID_L40S_FP8_C12_TERMINAL_AND_MATCHED_QUOTE",
        "l40s_required": [
            "typed terminal from l40s_fp8_single_rank_context_falsifier",
            "FP8_CONTEXT_ADMISSION=true",
            "actual NCCL/CUDA TP=PP=DP=1 identity and teardown pass",
            "sentinel plus all six c12 M=12 and M=3679 rows have finite positive CUDA/wall distributions and output-consuming BF16 oracles",
            "actual peak reserve leaves >=0.25 GiB in the 44.704-GiB envelope",
            "request-weighted component total is below 1.229949102 seconds/request",
        ],
        "availability_quote_required": [
            "current written quote for dedicated RTX 6000 Ada 48-GB ECC, non-vGPU, active-cooled server placement",
            "CUDA compute capability 8.9 and driver compatibility with the exact pinned image are stated or execution-probed",
            "12-24 month committed, non-preemptible terms at 8-64 GPU scale with region, topology and included services",
            "comparable all-in GPU rate <=0.77 USD/GPU-hour",
            "one self-service or provider-confirmed experimental allocation is obtainable within the prospective budget",
        ],
        "false_branch": "If either the L40S scientific terminal or availability/quote gate fails, expire this arm with no provider create.",
    },
    "matched_arm": {
        "question": "Does the exact online-FP8 c12 component retain enough performance on RTX 6000 Ada to justify a later complete-request endpoint at its written committed rate?",
        "comparator": "fresh L40S rerun and RTX 6000 Ada candidate using identical pinned image, immutable staged bytes, single-rank NCCL context, warmup/repetition/order, and exact shapes; do not compare against historical timing rows alone",
        "program": [
            "sentinel actual Fp8OnlineLinearMethod process/apply for sliding QKV 5376->16384 at M=12",
            "all six exact linears at decode M=12 and fresh-prompt M=3679 with matched actual BF16 output-consuming oracle",
            "actual BF16 ParallelLMHead and actual FP8 KV writer under the same accounting used by the L40S terminal",
        ],
        "required_measurements": [
            "per-shape raw CUDA-event and wall distributions, medians, p95, CV and arm order",
            "finite/nontrivial output oracle and exact selected kernel symbols/source hashes",
            "kernel grid/block, registers/thread, static/dynamic shared memory and achieved occupancy",
            "dram__bytes_read.sum, dram__bytes_write.sum, lts__t_bytes.sum",
            "sm__throughput.avg.pct_of_peak_sustained_elapsed, smsp__inst_executed_pipe_tensor.sum",
            "peak allocated/reserved, KV/workspace bytes and the >=0.25-GiB c12 reserve check",
            "SM/memory clocks, power, temperature and thermal/power throttle reasons",
            "provider meter, failures/reloads and authenticated cleanup inventory",
        ],
        "decision_rules": [
            "Any kernel/runtime/oracle/allocator mismatch closes compatibility without a throughput inference.",
            "Report candidate/comparator component-time ratios directly; at a 0.77 quote, >1.428571x is worse than L40S equal-cost parity and >1.285714x misses the 10%-better sensitivity.",
            "A component pass cannot claim the strict 0.501943 completed-rps endpoint gate; it only admits one later complete-request test with hardware-specific residuals.",
        ],
        "prospective_budget": {
            "wall_clock_minutes": 35,
            "provider_exposure_minutes": 20,
            "compute": "0.30 RTX 6000 Ada GPU-hours plus 1 local CPU-hour",
            "storage": "one 100-GiB boot disk; 512 MiB retained plus 2 GiB temporary artifacts",
            "spend_usd": 0.45,
            "lifecycle": "one allocation, one matched primary, no paid repair; authenticated zero-resource cleanup",
        },
    },
    "uncertainty": [
        "The shared price inventory has no RTX 6000 Ada committed planning join; the 0.77 rate is a same-day public on-demand prior, not a production rate.",
        "Same SM89 architecture strongly narrows compatibility risk but does not establish exact-image execution, sustained clocks, thermal behavior, or throughput.",
        "Component ratios do not transfer to whole-request throughput; a matched endpoint is still required after a component pass.",
    ],
}

manifest = {
    "schema_version": 1,
    "generated_utc": gate["generated_utc"],
    "generator": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).resolve())},
    "sources": {
        name: {"path": str(path), "sha256": EXPECTED_HASHES[name]}
        for name, path in SOURCES.items()
    },
    "outputs": {},
    "checks": {
        "source_hashes_match": True,
        "price_fresh": True,
        "inventory_current": True,
        "exact_consumer_identity_pass": True,
        "only_inventory_48gb_candidates_compared": True,
        "nominee_same_sm89_native_fp8": True,
        "c12_headroom_at_least_0_25_gib": True,
        "c14_excluded": True,
        "no_throughput_transfer": True,
        "no_live_owner_observation": True,
        "no_provider_gpu_image_checkpoint": True,
    },
}

gate_path = PROJECT / "HARDWARE_GATE.json"
manifest_path = PROJECT / "SOURCE_MANIFEST.json"
gate_path.write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n")
manifest["outputs"]["HARDWARE_GATE.json"] = sha256(gate_path)
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
print(json.dumps({
    "decision": gate["decision"],
    "nominee": gate["nominee"],
    "gate_sha256": sha256(gate_path),
    "manifest_sha256": sha256(manifest_path),
}, indent=2))
