from __future__ import annotations

from decimal import Decimal, getcontext
import hashlib
import json
from pathlib import Path
import subprocess

from later_pair_workload import canonical, workload_identity


getcontext().prec = 50

ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECTS = ROOT.parent
REPO = ROOT.parents[6]
DEPENDENCY = PROJECTS / "gemma4_l40s_dual_kv4_allocator_0953_integration"
RUNTIME = REPO / ".agents/runtime/gemma4_global_kv_sglang"

PHYSICAL_BYTES = 48_305_799_168
MEM_FRACTION_STATIC = Decimal("0.953")
STATIC_LIMIT_BYTES = int(Decimal(PHYSICAL_BYTES) * MEM_FRACTION_STATIC)
DYNAMIC_RESERVE_BYTES = PHYSICAL_BYTES - STATIC_LIMIT_BYTES
PROMPT_TOKENS = 4_214
OUTPUT_TOKENS = 358
SHARED_PREFIX_TOKENS = 535
MAX_LIVE_SEQUENCE_TOKENS = PROMPT_TOKENS + OUTPUT_TOKENS - 1
WINDOW = 1_024
CHUNKED_PREFILL_TOKENS = 2_048
CONTEXT_LENGTH = 5_000
REQUEST_ROW_CONTEXT_LENGTH = CONTEXT_LENGTH + 4

DEPENDENCY_BINDINGS = {
    "allocator_terminal": (
        DEPENDENCY / "L40S_DUAL_KV4_ALLOCATOR_0953_OFFLINE_TERMINAL.json",
        "e98777580a46ef458e1ea704ceea6fc827030150fe4efa8e67ef380e99fd0090",
    ),
    "packet_manifest": (
        DEPENDENCY / "L40S_DUAL_KV4_SM89_PACKET_MANIFEST.json",
        "2f2e4f4bd1f0a178c77bf17a7834dad5f3920eaa63820982b4afa2e28182e5bb",
    ),
}

RUNTIME_SOURCES = (
    "python/sglang/srt/server_args.py",
    "python/sglang/srt/managers/scheduler.py",
    "python/sglang/srt/mem_cache/memory_pool.py",
    "python/sglang/srt/mem_cache/allocation_sizing.py",
    "python/sglang/srt/mem_cache/kv_cache_configurator.py",
    "python/sglang/srt/model_executor/model_runner.py",
    "python/sglang/srt/model_executor/pool_configurator.py",
    "python/sglang/srt/model_executor/cuda_graph_config.py",
    "python/sglang/srt/model_executor/model_runner_components/cuda_graph_setup.py",
    "python/sglang/srt/model_executor/runner/base_cuda_graph_runner.py",
    "python/sglang/srt/model_executor/runner/decode_cuda_graph_runner.py",
    "python/sglang/srt/model_executor/runner_utils/buffers.py",
)

COMPOSITION_SOURCES = (
    "dual_kv4_contract.py",
    "sglang_dual_kv4.py",
    "sglang_local_kv4_outlier.py",
    "sglang_global_tiered_kv4.py",
    "local_kv4_outlier_cuda.cu",
    "global_tiered_kv4_cuda.cu",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def direct(path: Path, evidence: str = "direct") -> dict:
    return {
        "path": str(path),
        "sha256": sha256(path),
        "evidence": evidence,
    }


def interval(lower: int, upper: int) -> dict:
    return {"lower": lower, "upper": upper}


def capacities(concurrency: int) -> dict:
    maximum_live = SHARED_PREFIX_TOKENS + concurrency * (
        MAX_LIVE_SEQUENCE_TOKENS - SHARED_PREFIX_TOKENS
    )
    local_rows = concurrency * WINDOW
    return {
        "canonical_physical_rows_with_sentinel": maximum_live + 1,
        "maximum_live_physical_rows": maximum_live,
        "local_swa_rows_excluding_sentinel": local_rows,
        "local_payload_rows_including_sentinel": local_rows + 1,
        "global_recent_rows": local_rows + CHUNKED_PREFILL_TOKENS,
        "global_recent_steady_rows": local_rows,
        "global_recent_prefill_spill_rows": CHUNKED_PREFILL_TOKENS,
        "global_old_rows": maximum_live - local_rows,
    }


def static_components(concurrency: int) -> dict:
    cap = capacities(concurrency)
    return {
        "transformer_linear_e4m3": 29_396_828_160,
        "tied_embedding_lm_head_bf16": 2_818_572_288,
        "local_kv4_payload_including_page_one_sentinel": (
            cap["local_payload_rows_including_sentinel"] * 230_400
        ),
        "global_recent_e5m2_payload": cap["global_recent_rows"] * 40_960,
        "global_old_kv4_outlier_payload": cap["global_old_rows"] * 23_680,
        "global_two_int32_physical_directories": (
            cap["canonical_physical_rows_with_sentinel"] * 2 * 4
        ),
        "global_old_and_recent_int32_free_stacks": (
            (cap["global_old_rows"] + cap["global_recent_rows"]) * 4
        ),
    }


def request_token_pool_bytes(concurrency: int) -> dict:
    rows = concurrency + 1
    table = rows * REQUEST_ROW_CONTEXT_LENGTH * 4
    generations = rows * 8
    return {
        "request_slots": concurrency,
        "padding_row": 1,
        "rows": rows,
        "columns": REQUEST_ROW_CONTEXT_LENGTH,
        "req_to_token_int32_bytes": table,
        "req_generation_int64_bytes": generations,
        "total_bytes": table + generations,
        "ledger_ownership": (
            "persistent runtime context allocation enclosed by the 0.047 "
            "dynamic reserve; shown here but not added to static or above reserve"
        ),
    }


def memory_ledger(concurrency: int, c32_terminal: dict) -> dict:
    components = static_components(concurrency)
    uncertainty = {
        "all_other_checkpoint_tensors": interval(0, 933_949_144),
        "fp8_weight_scales": interval(0, 16_777_216),
        "global_eight_allocation_rounding": interval(0, 16_777_216),
    }
    static_lower = sum(components.values())
    static_upper = static_lower + sum(row["upper"] for row in uncertainty.values())
    cap = capacities(concurrency)
    persistent = request_token_pool_bytes(concurrency)

    dynamic_detail = {
        "reserve_bytes": DYNAMIC_RESERVE_BYTES,
        "request_token_pool": persistent,
        "cuda_graph_pool": {
            "ownership": (
                "DecodeCudaGraphRunner and its backend own captured graph allocations; "
                "DecodeInputBuffers owns max-bs-shaped persistent replay buffers"
            ),
            "accounting": (
                "enclosed once by dynamic_reserve_bytes and never added to static"
            ),
            "c32_observed_interval_bytes": c32_terminal["memory"]["dynamic"][
                "assigned_components_bytes"
            ]["c32_cuda_graph_interval"],
            "c48_bytes": None,
            "c48_reason": (
                "not measured and not transferred from c32; the static lower bound "
                "already fails before graph capture"
            ),
        },
        "scheduler_and_allocator": {
            "ownership": (
                "Scheduler owns CPU request lists; ReqToTokenPool owns request slots "
                "and the int32 token table; SWATokenToKVPoolAllocator owns canonical "
                "physical ids; compact directories own only recent/old locations"
            ),
            "accounting": (
                "GPU request-table, metadata, allocator fragmentation, and unitemized "
                "runtime allocations are enclosed by dynamic_reserve_bytes"
            ),
        },
        "producer_consumer_scratch": {
            "ownership": (
                "composition creates route tensors and index_select inputs transiently; "
                "local/global CUDA consumers return one output tensor and declare no "
                "persistent private workspace"
            ),
            "accounting": (
                "transient tensors and decode split workspace are enclosed by "
                "dynamic_reserve_bytes and are not representation payload"
            ),
        },
        "required_conservative_interval_bytes": interval(
            DYNAMIC_RESERVE_BYTES, DYNAMIC_RESERVE_BYTES
        ),
        "margin_interval_bytes": interval(0, 0),
    }
    required_lower = static_lower + DYNAMIC_RESERVE_BYTES
    required_upper = static_upper + DYNAMIC_RESERVE_BYTES
    return {
        "concurrency": concurrency,
        "capacities": cap,
        "physical_bytes": PHYSICAL_BYTES,
        "split": {
            "mem_fraction_static": str(MEM_FRACTION_STATIC),
            "static_limit_bytes": STATIC_LIMIT_BYTES,
            "dynamic_reserve_bytes": DYNAMIC_RESERVE_BYTES,
            "identity": (
                "static_limit_bytes + dynamic_reserve_bytes == physical_bytes"
            ),
        },
        "static": {
            "components_bytes": components,
            "uncertainty_bytes": uncertainty,
            "required_interval_bytes": interval(static_lower, static_upper),
            "margin_interval_bytes": interval(
                STATIC_LIMIT_BYTES - static_upper,
                STATIC_LIMIT_BYTES - static_lower,
            ),
            "candidate_favorable_fit": static_lower <= STATIC_LIMIT_BYTES,
            "conservative_fit": static_upper <= STATIC_LIMIT_BYTES,
        },
        "dynamic": dynamic_detail,
        "complete_physical": {
            "required_interval_bytes": interval(required_lower, required_upper),
            "margin_interval_bytes": interval(
                PHYSICAL_BYTES - required_upper,
                PHYSICAL_BYTES - required_lower,
            ),
            "candidate_favorable_fit": required_lower <= PHYSICAL_BYTES,
            "conservative_fit": required_upper <= PHYSICAL_BYTES,
            "non_double_counting": (
                "the entire 0.047 reserve is charged once; request/token tables, graph "
                "pools, activation/context allocations, scheduler metadata, allocator "
                "fragmentation, decode workspace, and producer/consumer scratch are "
                "subledgers of that reserve and are never added above it"
            ),
        },
    }


def capture_sizes(max_bs: int) -> list[int]:
    values = [1, 2, 4, 8, 12] + list(range(16, 257, 8))
    values = [value for value in values if value <= max_bs]
    if max_bs not in values:
        values.append(max_bs)
    return values


def require_needles(path: Path, needles: tuple[str, ...]) -> None:
    text = path.read_text()
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise RuntimeError(f"source contract changed in {path}: {missing}")


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> None:
    for path, expected in DEPENDENCY_BINDINGS.values():
        if sha256(path) != expected:
            raise RuntimeError(f"bound dependency changed: {path}")
    runtime_commit = subprocess.check_output(
        ["git", "-C", str(RUNTIME), "rev-parse", "HEAD"], text=True
    ).strip()
    if runtime_commit != "c6a6200a1a778a799ba61c395ac292317f01ebc9":
        raise RuntimeError(f"runtime commit changed: {runtime_commit}")

    require_needles(
        DEPENDENCY / "sglang_dual_kv4.py",
        (
            "if size != PHYSICAL_CAPACITY - 1 or size_swa != LOCAL_CAPACITY:",
            'raise ValueError("fixed c32 allocator capacities changed")',
            "max_total_num_tokens=PHYSICAL_CAPACITY - 1",
            "swa_max_total_num_tokens=LOCAL_CAPACITY",
        ),
    )
    require_needles(
        RUNTIME / "python/sglang/srt/managers/scheduler.py",
        (
            "def get_num_allocatable_reqs(self, running_bs):",
            "res = min(res, self.req_to_token_pool.available_size())",
            "max_running_requests=self.max_running_requests",
        ),
    )
    require_needles(
        RUNTIME / "python/sglang/srt/model_executor/runner/base_cuda_graph_runner.py",
        (
            "capture_bs = list(server_args.cuda_graph_config.decode.bs)",
            "num_max_requests = model_runner.req_to_token_pool.size",
            "capture_bs = [bs for bs in capture_bs if bs <= num_max_requests]",
        ),
    )
    require_needles(
        RUNTIME / "python/sglang/srt/mem_cache/memory_pool.py",
        (
            "self._alloc_size = size + 1",
            "(self._alloc_size, max_context_len), dtype=torch.int32",
            "self.free_slots = list(range(1, self._alloc_size))",
        ),
    )

    c32_terminal = json.loads(
        DEPENDENCY_BINDINGS["allocator_terminal"][0].read_text()
    )
    c32 = memory_ledger(32, c32_terminal)
    c48 = memory_ledger(48, c32_terminal)
    if c32["static"]["components_bytes"] != c32_terminal["memory"]["static"][
        "components_bytes"
    ]:
        raise RuntimeError("c32 ledger reconstruction differs from bound terminal")
    if c48["static"]["candidate_favorable_fit"]:
        raise RuntimeError("fixed c48 unexpectedly fits")

    packet = ROOT / "packet"
    c32_workload = workload_identity(32)
    source_workload = json.loads((DEPENDENCY / "packet/WORKLOAD.json").read_text())
    if canonical(c32_workload) != canonical(source_workload):
        raise RuntimeError("c32 workload regeneration differs from bound workload")
    c48_workload = workload_identity(48)
    write_json(packet / "C32_WORKLOAD.json", c32_workload)
    write_json(packet / "C48_WORKLOAD.json", c48_workload)

    target_h200_seconds = Decimal("0.500119281574996")
    h200_rate = Decimal("3.25")
    l40s_rate = Decimal("1.1")
    utilization = Decimal("0.9")
    total_tokens = Decimal(PROMPT_TOKENS + OUTPUT_TOKENS)
    target_cost_per_million = (
        h200_rate
        * target_h200_seconds
        * Decimal(1_000_000)
        / (Decimal(3_600) * utilization * total_tokens)
    )
    c48_seconds_per_request_hurdle = (
        target_h200_seconds * h200_rate / l40s_rate
    )
    c48_batch_seconds_hurdle = (
        Decimal(48) * c48_seconds_per_request_hurdle
    )

    source_bindings = {
        "dependencies": {
            name: {
                "path": str(path),
                "sha256": expected,
                "evidence": "direct immutable input",
            }
            for name, (path, expected) in DEPENDENCY_BINDINGS.items()
        },
        "campaign": direct(LAB / "CAMPAIGN.md"),
        "gpu_price_inventory": direct(REPO / "research/factory/data/gpu_prices.json"),
        "accelerator_inventory": direct(
            REPO / "research/factory/data/accelerator_inventory.json"
        ),
        "runtime_commit": runtime_commit,
        "runtime_sources": {
            relative: direct(RUNTIME / relative) for relative in RUNTIME_SOURCES
        },
        "composition_sources": {
            relative: direct(DEPENDENCY / relative)
            for relative in COMPOSITION_SOURCES
        },
    }

    terminal = {
        "schema_version": 1,
        "kind": "l40s_dual_kv4_c48_saturation_offline_terminal",
        "project": ROOT.name,
        "classification": "typed_none_fixed_c48_static_capacity_negative",
        "decision": "close_fixed_c48_saturation_only",
        "pass": False,
        "candidate_sample_consumed": False,
        "gpu_used": False,
        "provider_interaction": False,
        "actual_spend_usd": 0.0,
        "direct_bindings": source_bindings,
        "fixed_contract": {
            "runtime_commit": runtime_commit,
            "runtime_image": (
                "docker.io/lmsysorg/sglang@sha256:"
                "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
            ),
            "model": "google/gemma-4-31B-it",
            "model_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "accelerator": "one NVIDIA L40S SM89",
            "mem_fraction_static": "0.953",
            "concurrency": 48,
            "prompt_tokens_per_request": PROMPT_TOKENS,
            "output_tokens_per_request": OUTPUT_TOKENS,
            "total_tokens_per_request": PROMPT_TOKENS + OUTPUT_TOKENS,
            "shared_prefix_tokens": SHARED_PREFIX_TOKENS,
            "page_size": 1,
            "local_window": WINDOW,
            "local_layers": 50,
            "global_layers": 10,
            "chunked_prefill_tokens": CHUNKED_PREFILL_TOKENS,
            "representation": (
                "50 local D256 group-64 KV4-plus-four-outlier layers; 10 global "
                "D512 recent-1024-E5M2/old-group-64-KV4-plus-eight-outlier layers"
            ),
        },
        "raw_ledgers": {"c32_reconstructed": c32, "c48": c48},
        "scaling_and_ownership": {
            "shared_terms": [
                "transformer_linear_e4m3",
                "tied_embedding_lm_head_bf16",
                "all_other_checkpoint_tensors",
                "fp8_weight_scales",
                "global_eight_allocation_rounding",
                "global_recent_prefill_spill_rows",
                "dynamic_reserve_bytes",
            ],
            "concurrency_scaled_terms": {
                "maximum_live_physical_rows": (
                    "535 + c * (4571 - 535)"
                ),
                "local_payload_rows": "c * 1024 + one shared sentinel",
                "global_recent_rows": "c * 1024 + one shared 2048-row spill",
                "global_old_rows": (
                    "maximum_live_physical_rows - c * 1024"
                ),
                "physical_directories": (
                    "two shared int32 locations per canonical physical id"
                ),
                "free_stacks": (
                    "one shared int32 slot per compact recent/old row"
                ),
                "request_token_pool": (
                    "(c + one graph-padding row) * (5000 + 4) int32 cells plus "
                    "one int64 generation per row; enclosed by dynamic reserve"
                ),
            },
            "rounding": {
                "static_limit": (
                    "floor(48,305,799,168 * Decimal('0.953')) = 46,035,426,607"
                ),
                "page_rounding": "page size one; no row alignment loss",
                "allocation_rounding": (
                    "the inherited candidate-conservative upper ledger retains one "
                    "fixed 16,777,216-byte bound across the eight global allocations"
                ),
            },
        },
        "runtime_reachability": {
            "scheduler": {
                "result": "generic_scheduler_can_admit_48_if_pool_has_48_slots",
                "symbols": [
                    "Scheduler.get_num_allocatable_reqs",
                    "Scheduler._get_new_batch_prefill_raw",
                    "ReqToTokenPool.available_size",
                    "ReqToTokenPool.alloc",
                ],
                "proof": (
                    "admission is capped by pp_max_micro_batch_size and available "
                    "request slots; --max-running-requests 48 would supply 48 slots"
                ),
            },
            "batch_construction": {
                "result": "generic_request_and_token_tables_are_c48_shape_capable",
                "symbols": [
                    "KVCacheConfigurator._build_req_to_token_pool",
                    "ReqToTokenPool.__init__",
                    "DecodeInputBuffers.create",
                ],
                "padding_ownership": (
                    "ReqToTokenPool reserves row zero as the CUDA-graph padding row; "
                    "real request slots are 1..48"
                ),
            },
            "cuda_graph": {
                "result": "generic_decode_graph_path_has_an_exact_48_bucket",
                "required_config": {
                    "max_running_requests": 48,
                    "cuda_graph_max_bs_decode": 48,
                },
                "decode_capture_sizes": capture_sizes(48),
                "symbols": [
                    "ServerArgs._generate_decode_cuda_graph_batch_sizes",
                    "get_batch_sizes_to_capture",
                    "DecodeCudaGraphRunner.can_run_graph",
                    "DecodeInputBuffers.create",
                    "capture_decode_graph",
                ],
                "ownership": (
                    "the graph runner/back-end owns captured graph pools and "
                    "max-bs replay buffers; these remain inside dynamic reserve"
                ),
            },
            "dual_kv_composition": {
                "result": "current_project_local_composition_is_c32_locked",
                "symbols": [
                    "FixedDualKV4PoolConfigurator._fixed",
                    "DualKV4SWAKVPool.__init__",
                    "GlobalTieredKVPool.__init__",
                ],
                "blocking_checks": [
                    "size must equal PHYSICAL_CAPACITY - 1",
                    "size_swa must equal LOCAL_CAPACITY",
                    "fixed pool returns c32 capacities",
                ],
                "minimum_c48_source_composition": (
                    "mechanically bind PHYSICAL_CAPACITY=194264, "
                    "LOCAL_CAPACITY=49152, RECENT_CAPACITY=51200, "
                    "OLD_CAPACITY=145111 and the corresponding fixed KV byte guard; "
                    "no CLI flag alone changes these source-owned arenas"
                ),
                "implemented": False,
                "reason": (
                    "the candidate-favorable static ledger fails by more than 3.04 GB; "
                    "implementing or running a c48 composition cannot change that gate"
                ),
            },
        },
        "economic_hurdle": {
            "evidence": "derived from current shared committed-rate inventory",
            "production_l40s_usd_per_gpu_hour": str(l40s_rate),
            "production_h200_usd_per_gpu_hour": str(h200_rate),
            "utilization": str(utilization),
            "total_tokens_per_request": int(total_tokens),
            "campaign_h200_target_seconds_per_request": str(target_h200_seconds),
            "campaign_target_usd_per_million_total_tokens": str(
                target_cost_per_million
            ),
            "symbolic_cost_equation": (
                "C48_usd_per_M = 1.1 * B48_s * 1e6 / "
                "(3600 * 0.9 * 48 * 4572)"
            ),
            "symbolic_terminal_inequality": (
                "B48_s / 48 <= 0.500119281574996 * 3.25 / 1.1"
            ),
            "equivalent_c48_seconds_per_request_hurdle": str(
                c48_seconds_per_request_hurdle
            ),
            "equivalent_c48_batch_wall_seconds_hurdle": str(
                c48_batch_seconds_hurdle
            ),
            "pair_interpretation": (
                "c48 improves same-L40S throughput over c32 iff B48/48 < B32/32; "
                "campaign qualification additionally requires B48/48 <= "
                "1.4776251501079427 seconds"
            ),
            "performance_transfer": False,
        },
        "workload_bytes": {
            "terminal_builder": direct(ROOT / "build_offline_terminal.py"),
            "generator": direct(ROOT / "later_pair_workload.py"),
            "c32": direct(packet / "C32_WORKLOAD.json"),
            "c48": direct(packet / "C48_WORKLOAD.json"),
            "launcher_guard": direct(ROOT / "run_later_c32_c48.sh"),
            "c32_matches_bound_workload": True,
            "c48_extends_the_same_seeded_request_family": True,
        },
        "focused_offline_checks": [
            {
                "check": "dependency direct hashes and pinned runtime commit",
                "result": "pass",
            },
            {
                "check": "c32 ledger exactly reconstructs bound static components",
                "result": "pass",
            },
            {
                "check": "c32 generated workload byte-semantics match bound workload",
                "result": "pass",
            },
            {
                "check": (
                    "scheduler slot cap, request padding row, graph bucket clamp, "
                    "and c32 composition hard guards remain present"
                ),
                "result": "pass",
            },
            {
                "check": "candidate-favorable c48 static lower bound",
                "result": "fail_capacity",
                "shortfall_bytes": (
                    c48["static"]["required_interval_bytes"]["lower"]
                    - STATIC_LIMIT_BYTES
                ),
                "physical_overflow_before_dynamic_reserve_bytes": (
                    c48["static"]["required_interval_bytes"]["lower"]
                    - PHYSICAL_BYTES
                ),
            },
        ],
        "later_measurement": {
            "type": "none",
            "reason": (
                "fixed c48 exceeds the immutable 0.953 static limit by "
                "3,040,544,877 bytes even at the candidate-favorable lower bound; "
                "no GPU command is scientifically or economically admissible"
            ),
            "guard_command": (
                "bash run_later_c32_c48.sh  # verifies both workload identities, "
                "prints the typed-none reason, and exits 78 without GPU/provider access"
            ),
        },
        "scope_of_negative": (
            "fixed c48 saturation only; does not close dual-KV c32 or alternative "
            "capacity geometries"
        ),
    }
    write_json(ROOT / "L40S_DUAL_KV4_C48_SATURATION_OFFLINE_TERMINAL.json", terminal)


if __name__ == "__main__":
    main()
