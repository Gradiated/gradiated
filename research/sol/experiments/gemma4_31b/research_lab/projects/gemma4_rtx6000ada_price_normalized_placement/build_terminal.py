import hashlib
import json
from decimal import Decimal, getcontext
from pathlib import Path


getcontext().prec = 40

PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
REPO = next(parent for parent in PROJECT.parents if (parent / ".git").exists())
SOURCE_CAPTURE = PROJECT / "evidence" / "RTX6000ADA_VENUE_SOURCE_CAPTURE_2026-07-28.json"
OUTPUT = PROJECT / "RTX6000ADA_PRICE_NORMALIZED_PLACEMENT_TERMINAL.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000000000001")))


def hurdle(
    venue: str,
    capacity_type: str,
    compute_rate: str,
    storage_usd_per_100gb_month: str | None,
    current_rate: bool,
    production_disposition: str,
) -> dict:
    rate = Decimal(compute_rate)
    storage_hourly = (
        Decimal(storage_usd_per_100gb_month) / Decimal(730)
        if storage_usd_per_100gb_month is not None
        else None
    )
    raw_service = PRICE_TIME_BUDGET / rate
    result = {
        "venue": venue,
        "capacity_type": capacity_type,
        "compute_usd_per_gpu_hour": float(rate),
        "current_rate": current_rate,
        "raw_90pct_gpu_only_max_seconds_per_request": number(raw_service),
        "raw_required_rtx_to_l40s_service_time_ratio_for_equal_compute_cost": number(
            L40S_PLANNING_RATE / rate
        ),
        "raw_required_ratio_to_later_measured_l40s_endpoint": (
            f"{number(raw_service)} / T_l40s_measured_s_per_request"
        ),
        "production_disposition": production_disposition,
    }
    if storage_hourly is None:
        result.update(
            {
                "standardized_100gb_storage_usd_per_hour": "unknown",
                "lower_bound_all_in_max_seconds_per_request_at_availability_factor_1": "unknown",
                "all_in_required_ratio_to_later_measured_l40s_endpoint": "unknown",
            }
        )
    else:
        effective_rate = rate + storage_hourly
        storage_adjusted = PRICE_TIME_BUDGET / effective_rate
        all_in = storage_adjusted / BURDEN_EXCLUDING_AVAILABILITY
        result.update(
            {
                "standardized_100gb_storage_usd_per_hour": number(storage_hourly),
                "storage_adjusted_90pct_max_seconds_per_request": number(storage_adjusted),
                "lower_bound_all_in_max_seconds_per_request_at_availability_factor_1": number(
                    all_in
                ),
                "all_in_required_ratio_to_later_measured_l40s_endpoint": (
                    f"{number(all_in)} / (A_venue * T_l40s_measured_s_per_request)"
                ),
            }
        )
    return result


CAMPAIGN = LAB / "CAMPAIGN.md"
ACCELERATOR_INVENTORY = REPO / "research" / "factory" / "data" / "accelerator_inventory.json"
PRICE_INVENTORY = REPO / "research" / "factory" / "data" / "gpu_prices.json"
L40S_PROJECT = PROJECT.parent / "gemma4_l40s_dual_kv4_allocator_0953_integration"
L40S_TERMINAL = L40S_PROJECT / "L40S_DUAL_KV4_ALLOCATOR_0953_OFFLINE_TERMINAL.json"
L40S_READY = L40S_PROJECT / "L40S_DUAL_KV4_SM89_COMPONENT_READY.json"
ARCHIVED_RUNPOD = (
    PROJECT.parent
    / "exact_market_venue_decision_surface"
    / "artifacts"
    / "runpod-readonly-snapshot.json"
)

QUALIFIED_H200_SECONDS = Decimal("0.625149101968745")
TARGET_H200_SECONDS = Decimal("0.500119281574996")
H200_PLANNING_RATE = Decimal("3.25")
L40S_PLANNING_RATE = Decimal("1.10")
PRICE_TIME_BUDGET = H200_PLANNING_RATE * TARGET_H200_SECONDS
TOKENS_PER_REQUEST = Decimal(4214 + 358)
UTILIZATION = Decimal("0.90")
TARGET_USD_PER_MILLION_TOKENS = (
    PRICE_TIME_BUDGET
    / Decimal(3600)
    / UTILIZATION
    * Decimal(1_000_000)
    / TOKENS_PER_REQUEST
)
BURDEN_FACTORS = {
    "replica_headroom": Decimal("1.10"),
    "non_gpu": Decimal("1.05"),
    "failure_reload": Decimal("1.03"),
    "storage_orchestration": Decimal("1.03"),
}
BURDEN_EXCLUDING_AVAILABILITY = Decimal(1)
for factor in BURDEN_FACTORS.values():
    BURDEN_EXCLUDING_AVAILABILITY *= factor

with SOURCE_CAPTURE.open() as source_file:
    source_capture = json.load(source_file)

venue_hurdles = [
    hurdle(
        "RunPod Community Cloud",
        "on_demand_community_dedicated_while_running",
        "0.74",
        "10",
        True,
        "supplementary_only: peer-provider availability and host consistency are not a sustainable production base",
    ),
    hurdle(
        "RunPod Secure Cloud",
        "on_demand_nonpreemptible",
        "0.84",
        "10",
        True,
        "production_lead: exact current per-region stock, usable bytes, driver, clocks, and SLA remain authenticated checks",
    ),
    hurdle(
        "Verda",
        "spot_preemptible",
        "0.364",
        "20",
        True,
        "supplementary_only: provider may evict without warning",
    ),
    hurdle(
        "Verda",
        "on_demand_nonpreemptible",
        "1.04",
        "20",
        True,
        "production_lead: exact current stock, usable bytes, driver, sustained clocks, and SLA remain authenticated checks",
    ),
    hurdle(
        "Verda",
        "one_year_committed_nonpreemptible_derived_8pct_discount",
        str(Decimal("1.04") * Decimal("0.92")),
        "20",
        True,
        "production_lead: public self-service committed rate; capacity and exact runtime checks remain open",
    ),
    hurdle(
        "Verda",
        "two_year_committed_nonpreemptible_derived_25pct_discount",
        str(Decimal("1.04") * Decimal("0.75")),
        "20",
        True,
        "headline_committed_lead: public self-service rate; up-front term, capacity, runtime, and SLA checks remain open",
    ),
    hurdle(
        "QuantaCloud",
        "on_demand_hourly",
        "0.71",
        None,
        True,
        "incomplete_surface: no public CPU/RAM/storage/network/region/driver/custom-container join",
    ),
]

terminal = {
    "schema_version": 1,
    "kind": "rtx6000ada_price_normalized_placement_terminal",
    "project": PROJECT.name,
    "generated_at_utc": source_capture["captured_at_utc"],
    "evidence_type": "source_backed_and_derived_no_gpu_measurement",
    "question": "Can a commercially obtainable single RTX 6000 Ada run the exact Gemma 4 31B dual-KV path at a sustainable cost at least 20% below the fixed qualified H200 result?",
    "decision": "preserve_production_lead_no_experiment_route",
    "pass": True,
    "placement_promoted": False,
    "matched_rtx_measurement_exists": False,
    "claim_test": {
        "hypothesis": "At least one current full-card RTX 6000 Ada venue has a transparent production rate and runtime surface whose later matched endpoint could clear the fixed price-normalized hurdle.",
        "falsification_rule": "Reject a venue if no current direct rate/access join exists, the full-device or runtime contract is incompatible, or a matched endpoint exceeds its burden-adjusted service-time hurdle. Do not infer RTX throughput from L40S or specifications.",
        "result": "Current direct listings make the placement economically plausible, but no venue has a permitted authenticated route and public sources do not prove exact usable bytes, current regional stock, host driver, sustained clocks, or endpoint throughput.",
    },
    "scope": {
        "provider_api_used": False,
        "provider_account_or_console_used": False,
        "credentials_used": False,
        "sales_contacted": False,
        "purchase_reservation_or_terms_accepted": False,
        "ssh_used": False,
        "gpu_or_cuda_used": False,
        "endpoint_called": False,
        "provider_spend_usd": 0.0,
        "candidate_sample_consumed": False,
        "throughput_inferred": False,
    },
    "identities": {
        "model": "google/gemma-4-31B-it",
        "model_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "workload": {
            "concurrency": 32,
            "prompt_tokens": 4214,
            "output_tokens": 358,
            "total_tokens": 4572,
            "cache_prompt_fraction": 0.127,
            "mode": "text-only non-reasoning campaign mix",
        },
        "representation": {
            "local_layers": 50,
            "local": "D256 group-64 KV4 plus O4",
            "global_layers": 10,
            "global": "D512 recent-1024 E5M2 plus old group-64 KV4 and O8",
            "mem_fraction_static": 0.953,
            "page_size": 1,
        },
        "runtime": {
            "commit": "c6a6200a1a778a799ba61c395ac292317f01ebc9",
            "image": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6",
        },
        "direct_bindings": {
            "campaign": {"path": str(CAMPAIGN), "sha256": sha256(CAMPAIGN)},
            "accelerator_inventory": {
                "path": str(ACCELERATOR_INVENTORY),
                "sha256": sha256(ACCELERATOR_INVENTORY),
            },
            "price_inventory": {
                "path": str(PRICE_INVENTORY),
                "sha256": sha256(PRICE_INVENTORY),
                "rtx6000ada_join_present": False,
                "l40s_planning_usd_per_hour": 1.1,
                "h200_planning_usd_per_hour": 3.25,
            },
            "l40s_dual_kv_offline_terminal": {
                "path": str(L40S_TERMINAL),
                "sha256": sha256(L40S_TERMINAL),
            },
            "l40s_component_ready_current_dependency_check": {
                "path": str(L40S_READY),
                "sha256": sha256(L40S_READY),
                "scope": "L40S-only offline readiness; no RTX execution or throughput transfer",
            },
            "archived_runpod_control_plane_snapshot": {
                "path": str(ARCHIVED_RUNPOD),
                "sha256": sha256(ARCHIVED_RUNPOD),
                "scope": "2026-07-17 diagnostic only; no current stock or project authority",
            },
            "source_capture": {
                "path": str(SOURCE_CAPTURE),
                "sha256": sha256(SOURCE_CAPTURE),
            },
        },
    },
    "current_venue_surface": {
        "commercial_surface_source_complete": True,
        "execution_surface_source_complete": False,
        "source_complete_current_venues": [
            {
                "venue": "RunPod",
                "sku": "one RTX 6000 Ada Pod",
                "device": "dedicated physical GPU while running; 48 GB GDDR6 ECC advertised",
                "bundle": "10 vCPUs, 167 GB RAM; storage separate",
                "rates": {
                    "community_on_demand_usd_per_gpu_hour": 0.74,
                    "secure_on_demand_usd_per_gpu_hour": 0.84,
                    "spot": "not published for this Pod SKU",
                    "three_or_six_month_savings_plan": "available in principle; exact RTX 6000 Ada rate not public",
                    "twelve_or_twenty_four_month_committed": "not publicly listed for this SKU",
                },
                "billing_minimum": "per-second charges but at least one hour of prepaid balance is required to deploy",
                "storage": "$0.10/GB-month running local container or volume disk; $0.07/GB-month network volume under 1 TB",
                "network": "no ingress/egress fee; public TCP/HTTP and SSH depend on template; global private networking is 100 Mbps",
                "regions": "31-region product claim and multi-continent NVIDIA Pod locations; exact current RTX stock is console-only",
                "custom_runtime": "custom NVIDIA container image/start command supported; nested Docker is not, so the pinned image must be the Pod container",
                "availability": "Secure Cloud uses T3/T4 data centers; Community Cloud uses vetted peer providers; no exact RTX SLA or public stock count",
                "missing_authenticated_checks": [
                    "current RTX stock and exact region",
                    "nvidia-smi memory.total >= 48305799168 bytes",
                    "ECC enabled and no vGPU/MIG carveout",
                    "host driver satisfies the pinned image",
                    "sustained clocks, power limit, and thermal behavior",
                ],
            },
            {
                "venue": "Verda",
                "sku": "1x RTX 6000 Ada 48GB GPU instance",
                "device": "dedicated GPU instance advertised; exact pass-through mode and usable bytes are not public",
                "bundle": "10 CPUs, 60 GB RAM; storage separate",
                "rates": {
                    "on_demand_usd_per_gpu_hour": 1.04,
                    "spot_preemptible_usd_per_gpu_hour": 0.364,
                    "one_year_committed_derived_usd_per_gpu_hour": 0.9568,
                    "two_year_committed_derived_usd_per_gpu_hour": 0.78,
                },
                "billing_minimum": "on-demand uses refundable prepaid ten-minute increments; long terms are paid up front",
                "storage": "$0.20/GiB-month NVMe or shared NVMe",
                "network": "SSH-capable VM; no public RTX-specific network bundle or egress join found",
                "regions": "FIN-01, FIN-02, FIN-03 in Helsinki; exact current RTX stock is console/CLI-only",
                "custom_runtime": "Ubuntu/Jupyter images, SSH, startup scripts, and an Ubuntu 24.04 CUDA 13 open-docker image are documented",
                "availability": "spot may be evicted without warning; public page gives no exact RTX SLA or stock count",
                "missing_authenticated_checks": [
                    "current RTX stock and exact Helsinki site",
                    "nvidia-smi memory.total >= 48305799168 bytes",
                    "ECC enabled and no vGPU/MIG carveout",
                    "host driver and NVIDIA container runtime satisfy the pinned image",
                    "sustained clocks, power limit, and thermal behavior",
                    "whether 60 GB host RAM is sufficient for this exact runtime load path",
                ],
            },
        ],
        "incomplete_or_noncurrent_venues": [
            {
                "venue": "QuantaCloud",
                "rate": "$0.71/GPU-hour",
                "reason": "Current direct listing lacks a CPU/RAM/storage/network/region/driver/custom-container join and permits equivalent-or-better substitution.",
            },
            {
                "venue": "Spheron",
                "rate": "$0.67/hour on-demand and $0.29/hour spot as of 2026-05-02",
                "reason": "The provider warns the rate may have changed and its current July catalog does not list RTX 6000 Ada.",
            },
            {
                "venue": "Vast.ai and price aggregators",
                "reason": "Marketplace/aggregator rows are not a stable full-device production bundle and were excluded from the base case.",
            },
        ],
    },
    "hardware_and_runtime_requirements": {
        "vendor_reported_hardware": {
            "gpu": "NVIDIA RTX 6000 Ada Generation AD102",
            "compute_capability": "8.9 / sm_89",
            "enabled_sms": 142,
            "l2_kib": 98304,
            "advertised_memory": "48 GB GDDR6 ECC",
            "memory_bandwidth_gb_s": 960,
            "pcie": "Gen4 x16",
            "board_power_w": 300,
            "thermal_solution": "active",
            "format_capability": ["FP8", "FP16", "BF16", "TF32", "INT8", "INT4"],
        },
        "exact_fail_closed_launch_requirements": [
            "One exclusive, unsliced RTX 6000 Ada whose guest reports at least 48,305,799,168 usable bytes; the public 48 GB label is not byte proof.",
            "ECC enabled, no MIG/vGPU memory carveout, and no competing compute process.",
            "Host NVIDIA driver compatible with the digest-pinned SGLang image and NVIDIA compute/utility device exposure.",
            "CUDA Toolkit 11.8 or newer for native sm_89 cubins; compile both project-local custom extensions for sm_89.",
            "Preserve E5M2 and packed INT4 producer/consumer semantics through the exact fixed dual-KV runner; format capability is not execution proof.",
            "Run the component correctness/resource/timing pairs first, then one exact c32 endpoint only after both margins satisfy the bound.",
            "Record nvidia-smi identity, memory.total, ECC, clocks, power limit, thermals, driver, CUDA, container digest, compiler resources, and matched endpoint telemetry.",
        ],
        "transfer_boundary": "The shared 142-SM/96-MiB-L2/sm_89 class, higher listed bandwidth, and lower power are priors only. No L40S latency, throughput, compiled-resource, quality, or sustained-clock value transfers.",
    },
    "price_normalized_gate": {
        "fixed_qualified_h200_seconds_per_request": float(QUALIFIED_H200_SECONDS),
        "fixed_h200_target_seconds_per_request": float(TARGET_H200_SECONDS),
        "h200_planning_usd_per_hour": float(H200_PLANNING_RATE),
        "price_time_budget_usd_seconds_per_request_hour": number(PRICE_TIME_BUDGET),
        "workload_total_tokens_per_request": int(TOKENS_PER_REQUEST),
        "fixed_utilization": float(UTILIZATION),
        "derived_gpu_only_target_usd_per_million_total_tokens": number(
            TARGET_USD_PER_MILLION_TOKENS
        ),
        "symbolic": {
            "raw_90pct_gate": "P_rtx * T_rtx <= 3.25 * 0.500119281574996 = 1.625387665118737",
            "max_rtx_compute_rate": "P_rtx,max(T_rtx) = 1.625387665118737 / T_rtx",
            "max_rtx_service_time": "T_rtx,max(P_rtx) = 1.625387665118737 / P_rtx",
            "l40s_campaign_hurdle": "T_l40s <= 1.625387665118737 / 1.10 = 1.4776251501079427 seconds/request",
            "required_ratio_to_later_l40s_endpoint": "T_rtx / T_l40s_measured <= (1.625387665118737 / P_rtx) / T_l40s_measured",
            "equal_cost_ratio_vs_l40s": "T_rtx / T_l40s_measured <= 1.10 / P_rtx when both use the same burden factors",
            "burden_adjusted_max_compute_rate": "P_rtx,max = 1.625387665118737 / (T_rtx * 1.2253395 * A_venue) - S_hourly",
        },
        "planning_sensitivity": {
            "evidence_label": "derived sensitivity, not measured venue overhead",
            "standardized_storage": "100 GB/GiB at each provider's published running persistent-storage rate, divided by 730 hours/month",
            "replica_headroom": 1.1,
            "non_gpu": 1.05,
            "failure_reload": 1.03,
            "storage_orchestration": 1.03,
            "combined_burden_excluding_availability": number(
                BURDEN_EXCLUDING_AVAILABILITY
            ),
            "availability_factor": "A_venue >= 1 remains unknown until a matching capacity/SLA and failure trace exist",
            "interpretation": "The A=1 all-in rows are optimistic lower-bound hurdles. Community and spot capacity cannot support a sustainable production claim from price alone.",
        },
        "venue_hurdles": venue_hurdles,
    },
    "access_and_experiment_route": {
        "authenticated_route_exists_for_this_project": False,
        "configured_controller_found": False,
        "lab_bench_available": False,
        "archived_account_evidence": "A July 17 RunPod read-only snapshot exists, but it showed zero Pods and no valid GPU inventory result; it is stale, not RTX-specific, and not authority.",
        "why_no_route_is_named": "The project explicitly forbids provider APIs, credentials, accounts, purchases, reservations, SSH, and endpoints, and the current shared GPU inventory is empty. Public deploy links are market evidence, not experimental authority.",
        "future_route_if_authorized": "A later director may bind one current Secure Cloud or Verda full-card instance, current stock/rate, spend reservation, immutable image/runner, and durable owner; this terminal does not request or authorize that mutation.",
    },
    "result": {
        "commercial_rate_join_closed": True,
        "best_current_public_on_demand_candidate": "RunPod Secure Cloud at $0.84/GPU-hour",
        "best_current_public_12_24_month_candidate": "Verda two-year self-service at a derived $0.78/GPU-hour",
        "production_conclusion": "Both rates leave a wide symbolic service-time envelope, but no sustainable cost claim exists until a matched RTX endpoint measures service time and actual burden/availability.",
        "decision_reason": "Preserve the placement as a production lead because current direct rates and dedicated access exist; do not admit an experiment because this project has no permitted authenticated route and critical device/runtime/stock facts require an authenticated instance.",
    },
    "uncertainty_and_competing_explanations": [
        "RunPod and Verda public SKU pages do not prove current per-region stock.",
        "Advertised 48 GB does not prove the exact guest-visible usable byte count required by the fixed 0.953 ledger.",
        "No source guarantees RTX-specific sustained clocks, power limit, or thermal behavior.",
        "Verda's 60 GB host RAM may or may not suffice for the exact load path; RunPod's 167 GB is more conservative, but neither was measured.",
        "A cheaper workstation GPU may suffer a runtime, clock, virtualization, host, or availability penalty large enough to consume the price advantage.",
        "Conversely, the RTX may match or outperform the L40S on this workload, but bandwidth and shared silicon cannot establish that.",
        "Availability factor A_venue is unbounded by public SKU pages; therefore all A=1 burden-adjusted rows are optimistic sensitivities.",
    ],
    "source_table": source_capture["sources"],
    "next_action": "Director: keep this as a production lead, not an active paid route. If authenticated full-card stock and positive spend authority are later supplied, bind exact usable memory/driver/container facts, run matched RTX components, then one c32 endpoint; otherwise make no provider mutation.",
}

serialized = json.dumps(terminal, indent=2, sort_keys=True) + "\n"
OUTPUT.write_text(serialized)

loaded = json.loads(OUTPUT.read_text())
assert loaded["decision"] == "preserve_production_lead_no_experiment_route"
assert loaded["scope"]["provider_spend_usd"] == 0.0
assert loaded["matched_rtx_measurement_exists"] is False
assert abs(
    loaded["price_normalized_gate"]["price_time_budget_usd_seconds_per_request_hour"]
    - 1.625387665119
) < 1e-12
assert len(loaded["price_normalized_gate"]["venue_hurdles"]) == 7
print(OUTPUT)
