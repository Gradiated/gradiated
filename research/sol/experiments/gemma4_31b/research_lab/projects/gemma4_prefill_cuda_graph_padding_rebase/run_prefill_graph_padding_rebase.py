#!/usr/bin/env python3
import argparse
import ast
import bisect
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence


OFFICIAL_REVISION = "6c6175fabd8eac2ac7a66eea36e6b21fc0893a75"
OFFICIAL_PARENT_REVISION = "38b29dcd6c2d64477aa92f867b28a5e4650d2c5b"
OFFICIAL_PR_URL = "https://github.com/sgl-project/sglang/pull/31487"
OFFICIAL_COMMIT_URL = (
    "https://github.com/sgl-project/sglang/commit/"
    "6c6175fabd8eac2ac7a66eea36e6b21fc0893a75"
)
OFFICIAL_SOURCE_URL = (
    "https://github.com/sgl-project/sglang/blob/"
    "6c6175fabd8eac2ac7a66eea36e6b21fc0893a75/"
    "python/sglang/srt/model_executor/runner/prefill_cuda_graph_runner.py"
)
MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
LOCKED_SECONDS_PER_REQUEST = 0.625149101968745
TARGET_SECONDS_PER_REQUEST = 0.500119281574996
PADDING_FACTOR = 2

SOURCE_HASHES = {
    "python/sglang/srt/server_args.py": (
        "c5f24152906c1cd7865ec563afb9e682419527a836798bc45bd1466b91633d5c"
    ),
    "python/sglang/srt/managers/schedule_policy.py": (
        "5e5d455072ac169bb998458d4392de42e7dc1051ac915d18dac0e604913f46d8"
    ),
    "python/sglang/srt/managers/scheduler.py": (
        "932d85bf6b22bd89d2ff965c48119618e0d544fd5b65e36b726f4ed108dd615a"
    ),
    "python/sglang/srt/managers/schedule_batch.py": (
        "27e20908294c9d76d0a8ae1199ecac4379232532878013404a8b4fb08842ac43"
    ),
    "python/sglang/srt/model_executor/forward_batch_info.py": (
        "e33f571117e36041a8f8c75787a5f2f45ab38aa6b5b24a4e698a54cbcaec46aa"
    ),
    "python/sglang/srt/model_executor/model_runner.py": (
        "2b246abc1bdb1e976142be54f14b0d8d7fe49b214960852464a42f56bd013918"
    ),
    "python/sglang/srt/model_executor/cuda_graph_config.py": (
        "41283469be12017612f1c0d3d76c73ece43f8894f95d18af95bad9d3754f272f"
    ),
    "python/sglang/srt/model_executor/model_runner_components/cuda_graph_setup.py": (
        "6542408db3cc852c8a78210d0462c9ca74805521843eed13905c9aca2d363ebd"
    ),
    "python/sglang/srt/model_executor/runner/base_cuda_graph_runner.py": (
        "295d50dcb3759e6b55513d34091d2f37466416bf16bf7bb6194e596cdd14a20c"
    ),
    "python/sglang/srt/model_executor/runner/prefill_cuda_graph_runner.py": (
        "498711e4b2607c4256d051ce4c9ed2ba5bdf04f6ee91d55c46734ee572876f1e"
    ),
    "python/sglang/srt/model_executor/runner/eager_runner.py": (
        "d974dd389c979a1295f7749f376f002b5d8860e4a14132f5ab5933e61dfb2a0e"
    ),
    "python/sglang/srt/models/gemma4_causal.py": (
        "9c5f5f5739cbec30284302f266fec1d797a86fb98fa1273a27c97fb5d869d001"
    ),
    "python/sglang/srt/models/gemma4_mm.py": (
        "ea98d5ffc4b2f7188d01b26436b09206d0d46852a5eebb4252b5840598f64aac"
    ),
}

SOURCE_CONTRACTS = {
    "python/sglang/srt/managers/schedule_policy.py": (
        "def add_chunked_req(self, req: Req)",
        "req.set_extend_range(",
    ),
    "python/sglang/srt/managers/scheduler.py": (
        "self.chunked_req = adder.add_chunked_req(self.chunked_req)",
        "self.server_args.enable_dynamic_chunking and self.ps.pp_size > 1",
    ),
    "python/sglang/srt/managers/schedule_batch.py": (
        "input_ids = [r.get_fill_ids()[len(r.prefix_indices) :] for r in reqs]",
        "extend_num_tokens = sum(len(ids) for ids in input_ids)",
        "flatten_arrays_to_pinned_cpu(input_ids, _pin)",
    ),
    "python/sglang/srt/model_executor/forward_batch_info.py": (
        "input_ids=batch.input_ids",
        "num_tokens = len(batch.input_ids) if batch.input_ids is not None else 0",
    ),
    "python/sglang/srt/model_executor/model_runner.py": (
        "self.prefill_cuda_graph_runner.can_run_graph(forward_batch)",
        "self.prefill_cuda_graph_runner.execute(",
        "self.eager_runner.execute(",
    ),
    "python/sglang/srt/model_executor/model_runner_components/cuda_graph_setup.py": (
        "prefill_runner = PrefillCudaGraphRunner(model_runner)",
        "return eager_runner",
    ),
    "python/sglang/srt/model_executor/runner/prefill_cuda_graph_runner.py": (
        "num_tokens = len(forward_batch.input_ids)",
        "padded_num_tokens > num_tokens * _MAX_PREFILL_CUDA_GRAPH_PADDING_FACTOR",
        "static_num_tokens = self._pad_to_bucket(",
        "self.model_runner.model.forward(",
        "return hs[:raw_num_tokens] if full_path else hs",
    ),
    "python/sglang/srt/model_executor/runner/eager_runner.py": (
        "padded_num_tokens=raw_num_tokens",
        "model_runner.model.forward(",
    ),
    "python/sglang/srt/models/gemma4_mm.py": (
        "class Gemma4ForConditionalGeneration",
        "def forward(",
    ),
    "python/sglang/srt/models/gemma4_causal.py": (
        "class Gemma4ForCausalLM",
        "self.logits_processor(",
    ),
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_path(path: Path) -> dict:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_path(path),
    }


def source_path(source_root: Path, relative: str) -> Path:
    return source_root / relative


def verify_sources(source_root: Path) -> tuple[list[dict], dict]:
    manifest = []
    contracts = {}
    for relative, expected_hash in SOURCE_HASHES.items():
        path = source_path(source_root, relative)
        observed_hash = sha256_path(path)
        if observed_hash != expected_hash:
            raise RuntimeError(
                f"official source mismatch for {relative}: "
                f"expected {expected_hash}, observed {observed_hash}"
            )
        source = path.read_text()
        required = SOURCE_CONTRACTS.get(relative, ())
        missing = [token for token in required if token not in source]
        if missing:
            raise RuntimeError(f"source ownership contract missing in {relative}: {missing}")
        manifest.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": observed_hash,
            }
        )
        if required:
            contracts[relative] = {
                "required_tokens": list(required),
                "passed": True,
            }
    manifest_digest = sha256_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    )
    return manifest, {
        "all_passed": True,
        "files": contracts,
        "manifest_sha256": manifest_digest,
    }


def find_class_method(source: str, class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    raise RuntimeError(f"{class_name}.{method_name} not found")


def compile_method(
    source: str,
    class_name: str,
    method_name: str,
    namespace: dict,
):
    method = find_class_method(source, class_name, method_name)
    class_node = ast.ClassDef(
        name=f"Extracted{class_name}",
        bases=[],
        keywords=[],
        body=[method],
        decorator_list=[],
    )
    module = ast.fix_missing_locations(ast.Module(body=[class_node], type_ignores=[]))
    exec(compile(module, f"{OFFICIAL_REVISION}:{class_name}.{method_name}", "exec"), namespace)
    return namespace[f"Extracted{class_name}"]


def extract_official_consumers(source_root: Path, guard_factor: float = PADDING_FACTOR):
    server_source = source_path(
        source_root, "python/sglang/srt/server_args.py"
    ).read_text()
    base_source = source_path(
        source_root,
        "python/sglang/srt/model_executor/runner/base_cuda_graph_runner.py",
    ).read_text()
    prefill_source = source_path(
        source_root,
        "python/sglang/srt/model_executor/runner/prefill_cuda_graph_runner.py",
    ).read_text()

    server_class = compile_method(
        server_source,
        "ServerArgs",
        "_generate_prefill_cuda_graph_batch_sizes",
        {},
    )
    base_class = compile_method(
        base_source,
        "BaseCudaGraphRunner",
        "_pad_to_bucket",
        {"Sequence": Sequence, "bisect": bisect},
    )

    class BreakableCudaGraphBackend:
        pass

    prefill_class = compile_method(
        prefill_source,
        "PrefillCudaGraphRunner",
        "can_run_graph",
        {
            "ForwardBatch": object,
            "BreakableCudaGraphBackend": BreakableCudaGraphBackend,
            "_MAX_PREFILL_CUDA_GRAPH_PADDING_FACTOR": guard_factor,
        },
    )
    prefill_class._pad_to_bucket = staticmethod(base_class._pad_to_bucket)
    return server_class, prefill_class, BreakableCudaGraphBackend


def make_runner(
    source_root: Path, capture_tokens: Sequence[int], guard_factor: float
):
    _, runner_class, backend_class = extract_official_consumers(
        source_root, guard_factor=guard_factor
    )
    runner = runner_class()
    runner._is_full_backend = False
    runner._capture_req_slots = 32
    runner.backend = backend_class()
    runner.capture_hidden_mode = "null"
    runner.max_num_tokens = max(capture_tokens)
    runner.capture_num_tokens = list(capture_tokens)
    runner._has_unsupported_mha_prefix = lambda _: False
    runner._has_inactive_dp_rank = lambda _: False
    return runner


def run_guard_case(runner, raw_tokens: int) -> bool:
    forward_batch = SimpleNamespace(
        batch_size=1,
        input_embeds=None,
        replace_embeds=None,
        forward_mode=SimpleNamespace(is_target_verify=lambda: False),
        capture_hidden_mode="null",
        global_num_tokens_cpu=None,
        can_run_dp_breakable_cuda_graph=True,
        input_ids=range(raw_tokens),
        return_logprob=False,
        extend_logprob_start_lens_cpu=[],
        extend_seq_lens_cpu=[],
    )
    return runner.can_run_graph(forward_batch)


def get_launch_arg(args: Sequence[str], flag: str, default=None):
    if flag not in args:
        return default
    index = args.index(flag)
    if index + 1 >= len(args):
        raise RuntimeError(f"launch flag has no value: {flag}")
    return args[index + 1]


def validate_exact_inputs(
    workload: dict,
    launch: dict,
    terminal: dict,
    config: dict,
    qualified_terminal: dict,
) -> dict:
    args = launch["args"]
    request_hashes = workload["request_sha256"]
    checks = {
        "concurrency_32": workload["concurrency"] == 32,
        "request_hash_count_32": len(request_hashes) == 32
        and len(set(request_hashes)) == 32,
        "prompt_tokens_4214": workload["prompt_tokens"] == 4214,
        "output_tokens_358": workload["output_tokens"] == 358,
        "shared_prefix_tokens_535": workload["shared_prefix_tokens"] == 535,
        "terminal_rows_32": len(terminal["rows"]) == 32,
        "terminal_complete_requests_32": terminal["complete_requests"] == 32,
        "terminal_prompt_rows": all(
            row["prompt_tokens"] == 4214 for row in terminal["rows"]
        ),
        "request_hashes_join": sorted(request_hashes)
        == sorted(row["request_sha256"] for row in terminal["rows"]),
        "dynamic_fp8": get_launch_arg(args, "--quantization") == "fp8",
        "kv_cache_fp8_e5m2": get_launch_arg(args, "--kv-cache-dtype")
        == "fp8_e5m2",
        "tp_size_1": int(get_launch_arg(args, "--tp-size")) == 1,
        "max_running_requests_32": int(
            get_launch_arg(args, "--max-running-requests")
        )
        == 32,
        "chunked_prefill_2048": int(
            get_launch_arg(args, "--chunked-prefill-size")
        )
        == 2048,
        "dynamic_chunking_flag": "--enable-dynamic-chunking" in args,
        "page_size_1": int(get_launch_arg(args, "--page-size")) == 1,
        "triton_prefill": get_launch_arg(args, "--prefill-attention-backend")
        == "triton",
        "gemma4_architecture": config["architectures"]
        == ["Gemma4ForConditionalGeneration"],
        "gemma4_dense": config["text_config"].get("num_experts") is None,
        "gemma4_60_layers": config["text_config"]["num_hidden_layers"] == 60,
        "gemma4_50_local_10_global": (
            config["text_config"]["layer_types"].count("sliding_attention") == 50
            and config["text_config"]["layer_types"].count("full_attention") == 10
        ),
        "gemma4_d256_d512": (
            config["text_config"]["head_dim"] == 256
            and config["text_config"]["global_head_dim"] == 512
        ),
        "gemma4_window_1024": config["text_config"]["sliding_window"] == 1024,
        "qualified_denominator": qualified_terminal["service_seconds_per_request"]
        == LOCKED_SECONDS_PER_REQUEST,
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"exact input contract failed: {failed}")
    return checks


def capture_buckets(source_root: Path, max_tokens: int) -> list[int]:
    server_class, _, _ = extract_official_consumers(source_root)
    return server_class()._generate_prefill_cuda_graph_batch_sizes(max_tokens)


def reconstruct_chunks(
    terminal: dict,
    fresh_tokens_per_request: int,
    chunk_size: int,
    buckets: Sequence[int],
    guard_on_runner,
    guard_off_runner,
) -> list[dict]:
    request_order = sorted(terminal["rows"], key=lambda row: row["first_token_monotonic_s"])
    requests = [
        {
            "request_index": row["index"],
            "request_sha256": row["request_sha256"],
            "remaining": fresh_tokens_per_request,
            "cursor": 0,
            "prefill_completion_order": order,
        }
        for order, row in enumerate(request_order)
    ]
    rows = []
    request_cursor = 0
    while request_cursor < len(requests):
        budget = chunk_size
        segments = []
        while budget and request_cursor < len(requests):
            request = requests[request_cursor]
            take = min(budget, request["remaining"])
            start = request["cursor"]
            end = start + take
            segments.append(
                {
                    "request_index": request["request_index"],
                    "request_sha256": request["request_sha256"],
                    "prefill_completion_order": request["prefill_completion_order"],
                    "fresh_token_row_start": start,
                    "fresh_token_row_end_exclusive": end,
                    "compulsory_rows": take,
                }
            )
            request["remaining"] -= take
            request["cursor"] = end
            budget -= take
            if request["remaining"] == 0:
                request_cursor += 1

        raw_tokens = sum(segment["compulsory_rows"] for segment in segments)
        bucket = next(value for value in buckets if value >= raw_tokens)
        guard_on = run_guard_case(guard_on_runner, raw_tokens)
        guard_off = run_guard_case(guard_off_runner, raw_tokens)
        rows.append(
            {
                "forward_index": len(rows),
                "raw_num_tokens": raw_tokens,
                "capture_bucket": bucket,
                "padding_ratio": bucket / raw_tokens,
                "padded_rows": bucket - raw_tokens,
                "guard_threshold_rows": raw_tokens * PADDING_FACTOR,
                "guard_on_graph_eligible": guard_on,
                "guard_off_graph_eligible": guard_off,
                "guard_on_route": "prefill_cuda_graph_replay" if guard_on else "eager",
                "guard_off_route": "prefill_cuda_graph_replay" if guard_off else "eager",
                "segments": segments,
                "padding_ownership": (
                    "static capture-buffer sentinels only; no request, position, "
                    "KV-cache, logits, or output ownership"
                ),
            }
        )

    if any(request["remaining"] for request in requests):
        raise RuntimeError("chunk reconstruction left unconsumed request rows")
    return rows


def compute_cost_bounds(
    gpu_prices: dict,
    seconds_per_request: float,
    total_tokens_per_request: int,
) -> dict:
    h200 = next(
        row for row in gpu_prices["accelerators"] if row["id"] == "nvidia-h200-sxm"
    )
    rate = h200["production_planning_usd_per_gpu_hour"]
    cost_full = (
        seconds_per_request
        * rate
        / 3600
        / total_tokens_per_request
        * 1_000_000
    )
    return {
        "price_source": {
            "accelerator": h200["id"],
            "planning_usd_per_gpu_hour": rate,
            "evidence_type": h200["planning_evidence_type"],
            "planning_basis": h200["planning_basis"],
        },
        "locked_cost_usd_per_million_total_tokens_full_utilization": cost_full,
        "locked_cost_usd_per_million_total_tokens_90pct_utilization": cost_full / 0.9,
        "guard_on_cost_interval_usd_per_million_total_tokens_full_utilization": [
            cost_full,
            cost_full,
        ],
        "guard_off_cost_interval_usd_per_million_total_tokens_full_utilization": [
            cost_full,
            cost_full,
        ],
        "guard_enabled_cost_reduction_interval_usd_per_million_total_tokens": [
            0.0,
            0.0,
        ],
        "evidence_label": "derived_structural_zero_from_identical_routes",
    }


def git_revision(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def build_terminal(
    *,
    project_root: Path,
    source_root: Path,
    workload_path: Path,
    launch_path: Path,
    terminal_path: Path,
    config_path: Path,
    qualified_terminal_path: Path,
    gpu_prices_path: Path,
    retrieved_at_utc: str,
) -> dict:
    manifest, source_checks = verify_sources(source_root)
    workload = json.loads(workload_path.read_text())
    launch = json.loads(launch_path.read_text())
    c32_terminal = json.loads(terminal_path.read_text())
    config = json.loads(config_path.read_text())
    qualified_terminal = json.loads(qualified_terminal_path.read_text())
    gpu_prices = json.loads(gpu_prices_path.read_text())
    input_checks = validate_exact_inputs(
        workload, launch, c32_terminal, config, qualified_terminal
    )

    chunk_size = int(get_launch_arg(launch["args"], "--chunked-prefill-size"))
    buckets = capture_buckets(source_root, chunk_size)
    if not buckets or buckets[-1] != chunk_size:
        raise RuntimeError("official capture buckets do not reach the exact chunk size")

    guard_on_runner = make_runner(source_root, buckets, PADDING_FACTOR)
    guard_off_runner = make_runner(source_root, buckets, float("inf"))
    fresh_tokens = workload["prompt_tokens"] - workload["shared_prefix_tokens"]
    chunks = reconstruct_chunks(
        c32_terminal,
        fresh_tokens,
        chunk_size,
        buckets,
        guard_on_runner,
        guard_off_runner,
    )

    compulsory_rows = sum(row["raw_num_tokens"] for row in chunks)
    guard_on_padded_rows = sum(
        row["padded_rows"] for row in chunks if row["guard_on_graph_eligible"]
    )
    guard_off_padded_rows = sum(
        row["padded_rows"] for row in chunks if row["guard_off_graph_eligible"]
    )
    differing_routes = [
        row["forward_index"]
        for row in chunks
        if row["guard_on_route"] != row["guard_off_route"]
    ]
    expected_compulsory = workload["concurrency"] * fresh_tokens
    accounting_checks = {
        "compulsory_rows_equal_uncached_prompt_rows": compulsory_rows
        == expected_compulsory
        == int(c32_terminal["cache"]["uncached_prompt_tokens_delta"]),
        "request_segment_rows_exact": all(
            sum(
                segment["compulsory_rows"]
                for row in chunks
                for segment in row["segments"]
                if segment["request_sha256"] == request_hash
            )
            == fresh_tokens
            for request_hash in workload["request_sha256"]
        ),
        "57_full_chunks_plus_992_tail": (
            len(chunks) == 58
            and [row["raw_num_tokens"] for row in chunks].count(2048) == 57
            and chunks[-1]["raw_num_tokens"] == 992
        ),
        "tail_bucket_1024": chunks[-1]["capture_bucket"] == 1024,
        "all_guard_on_graph_eligible": all(
            row["guard_on_graph_eligible"] for row in chunks
        ),
        "guard_on_off_routes_identical": not differing_routes,
        "guard_on_off_padded_rows_identical": guard_on_padded_rows
        == guard_off_padded_rows
        == 32,
    }
    if not all(accounting_checks.values()):
        failed = [name for name, passed in accounting_checks.items() if not passed]
        raise RuntimeError(f"trace accounting failed: {failed}")

    sparse_on = make_runner(source_root, [2816, 3072, 8192], PADDING_FACTOR)
    sparse_off = make_runner(source_root, [2816, 3072, 8192], float("inf"))
    boundary_checks = {
        "upstream_3208_to_8192_guard_on_rejected": not run_guard_case(
            sparse_on, 3208
        ),
        "upstream_3208_to_8192_guard_off_accepted": run_guard_case(
            sparse_off, 3208
        ),
        "boundary_4096_to_8192_guard_on_accepted": run_guard_case(
            make_runner(source_root, [8192], PADDING_FACTOR), 4096
        ),
        "above_boundary_4095_to_8192_guard_on_rejected": not run_guard_case(
            make_runner(source_root, [8192], PADDING_FACTOR), 4095
        ),
    }
    if not all(boundary_checks.values()):
        raise RuntimeError("exact official guard boundary checks failed")

    repo_root = project_root.parents[6]
    script_path = project_root / "run_prefill_graph_padding_rebase.py"
    test_path = project_root / "test_prefill_graph_padding_rebase.py"
    direct_inputs = {
        "workload": describe_path(workload_path),
        "launch": describe_path(launch_path),
        "c32_terminal": describe_path(terminal_path),
        "model_config": describe_path(config_path),
        "qualified_terminal": describe_path(qualified_terminal_path),
        "gpu_prices": describe_path(gpu_prices_path),
        "implementation": describe_path(script_path),
        "focused_tests": describe_path(test_path),
    }
    total_tokens_per_request = workload["prompt_tokens"] + workload["output_tokens"]
    cost_bounds = compute_cost_bounds(
        gpu_prices, LOCKED_SECONDS_PER_REQUEST, total_tokens_per_request
    )

    return {
        "schema_version": 1,
        "project": "gemma4_prefill_cuda_graph_padding_rebase",
        "created_at_utc": retrieved_at_utc,
        "status": "complete",
        "terminal_type": "typed_none_exact_c32_guard_never_crosses",
        "answer": (
            "No. The minimum official current-runtime producer/consumer chain is "
            "source-complete and the exact guard method executes, but all 58 exact "
            "c32 prefill forwards remain graph-eligible with the guard enabled. "
            "Guard-on and guard-off therefore execute identical buckets and both "
            "process 117,728 compulsory plus 32 padded model-token rows."
        ),
        "official_source": {
            "repository": "sgl-project/sglang",
            "pull_request_url": OFFICIAL_PR_URL,
            "commit_url": OFFICIAL_COMMIT_URL,
            "direct_source_url": OFFICIAL_SOURCE_URL,
            "revision": OFFICIAL_REVISION,
            "parent_revision": OFFICIAL_PARENT_REVISION,
            "author_time": "2026-07-18T16:25:30+08:00",
            "retrieved_at_utc": retrieved_at_utc,
            "snapshot_root": str(source_root),
            "files": manifest,
            "manifest_sha256": source_checks["manifest_sha256"],
        },
        "local_implementation": {
            "repository_base_revision": git_revision(repo_root),
            "project_root": str(project_root),
            "script": describe_path(script_path),
            "test": describe_path(test_path),
            "classification": (
                "minimum offline official-method rebase through the real "
                "ScheduleBatch-to-ForwardBatch-to-PrefillCudaGraphRunner ownership "
                "chain; no CUDA execution claim"
            ),
        },
        "scope": {
            "model": "google/gemma-4-31B-it",
            "model_revision": MODEL_REVISION,
            "runtime_revision": OFFICIAL_REVISION,
            "accelerator_target": "NVIDIA H200 SXM",
            "concurrency": workload["concurrency"],
            "prompt_tokens_per_request": workload["prompt_tokens"],
            "shared_prefix_tokens_per_request": workload["shared_prefix_tokens"],
            "fresh_prompt_tokens_per_request": fresh_tokens,
            "completion_tokens_per_request": workload["output_tokens"],
            "chunked_prefill_size": chunk_size,
            "dynamic_chunk_predictor_active": False,
            "dynamic_chunk_predictor_reason": (
                "Official scheduler gates the predictor on pp_size > 1; exact "
                "launch is tp1/pp1, so the configured 2048 chunk budget is unchanged."
            ),
            "authorized_spend_usd": 0.0,
            "actual_spend_usd": 0.0,
            "gpu_claimed_or_used": False,
            "cuda_run": False,
            "ssh_provider_or_endpoint_used": False,
            "checkpoint_shards_read_or_copied": False,
        },
        "producer_consumer_ownership": {
            "semantic_class": "execution_route_preserving",
            "chain": [
                {
                    "owner": "PrefillAdder",
                    "symbol": "add_chunked_req/add_one_req",
                    "contract": (
                        "Owns per-request extend ranges under the 2048 token budget; "
                        "the carried chunk is completed first and the remainder may "
                        "start the next request."
                    ),
                },
                {
                    "owner": "ScheduleBatch",
                    "symbol": "prepare_for_extend",
                    "contract": (
                        "Flattens request-owned uncached token slices into one "
                        "input_ids tensor and records extend lengths and positions."
                    ),
                },
                {
                    "owner": "ForwardBatch",
                    "symbol": "init_new",
                    "contract": (
                        "Borrows ScheduleBatch.input_ids, request-pool indices, "
                        "sequence lengths, output cache locations, and positions "
                        "without changing row ownership."
                    ),
                },
                {
                    "owner": "ModelRunner",
                    "symbol": "_forward_raw",
                    "contract": (
                        "Calls PrefillCudaGraphRunner.can_run_graph for EXTEND; "
                        "true dispatches execute, false dispatches EagerRunner.execute "
                        "on the same live ForwardBatch."
                    ),
                },
                {
                    "owner": "PrefillCudaGraphRunner",
                    "symbol": "can_run_graph",
                    "contract": (
                        "Derives raw rows from len(forward_batch.input_ids), selects "
                        "the next captured token bucket, and rejects only when the "
                        "bucket is greater than two times raw rows."
                    ),
                },
                {
                    "owner": "PrefillCudaGraphRunner",
                    "symbol": "load_batch/execute",
                    "contract": (
                        "Copies request rows into static capture buffers, adds "
                        "non-owned padding sentinels, replays the model body at the "
                        "bucket shape, and slices Full-backend hidden rows back to "
                        "raw rows before the eager logits tail."
                    ),
                },
                {
                    "owner": "Gemma4ForConditionalGeneration/Gemma4ForCausalLM",
                    "symbol": "forward/logits_processor",
                    "contract": (
                        "Consumes identical token IDs, positions, FP8 linear path, "
                        "hybrid d256/d512 attention, E5M2 KV locations, and request "
                        "metadata under graph replay or eager fallback."
                    ),
                },
            ],
            "preserved_semantics": [
                "token IDs and per-request ordering",
                "positions and extend ranges",
                "request-to-token and output-cache ownership",
                "50 local-window and 10 global-attention layer geometry",
                "dynamic-FP8 weights/activations and E5M2 KV representation",
                "logits, sampling, NGRAM decode, and API output semantics",
            ],
            "only_mutable_mechanism": (
                "graph replay eligibility and the resulting number of padded "
                "full-model token rows"
            ),
        },
        "capture_configuration": {
            "backend": "breakable_on_cuda_by_official_default",
            "max_num_tokens": chunk_size,
            "capture_num_tokens": buckets,
            "padding_factor": PADDING_FACTOR,
            "bucket_source": (
                "exact AST execution of "
                "ServerArgs._generate_prefill_cuda_graph_batch_sizes"
            ),
        },
        "exact_c32_trace": {
            "source": {
                "workload_sha256": direct_inputs["workload"]["sha256"],
                "launch_sha256": direct_inputs["launch"]["sha256"],
                "c32_terminal_sha256": direct_inputs["c32_terminal"]["sha256"],
                "request_order": (
                    "measured prefill completion order from first_token_monotonic_s; "
                    "all request lengths are equal, so raw/bucket decisions are "
                    "invariant to the FCFS permutation"
                ),
            },
            "compulsory_rows": compulsory_rows,
            "guard_on_padded_rows": guard_on_padded_rows,
            "guard_off_padded_rows": guard_off_padded_rows,
            "guard_enabled_rows_removed": guard_off_padded_rows
            - guard_on_padded_rows,
            "forward_count": len(chunks),
            "differing_route_forward_indices": differing_routes,
            "forwards": chunks,
        },
        "same_source_causal_comparison": {
            "guard_on": {
                "source_revision": OFFICIAL_REVISION,
                "padding_factor": PADDING_FACTOR,
                "graph_replays": sum(
                    row["guard_on_graph_eligible"] for row in chunks
                ),
                "eager_fallbacks": sum(
                    not row["guard_on_graph_eligible"] for row in chunks
                ),
                "compulsory_model_rows": compulsory_rows,
                "padded_model_rows": guard_on_padded_rows,
                "total_model_rows": compulsory_rows + guard_on_padded_rows,
            },
            "guard_off": {
                "source_revision": OFFICIAL_REVISION,
                "padding_factor": "infinity_offline_control",
                "graph_replays": sum(
                    row["guard_off_graph_eligible"] for row in chunks
                ),
                "eager_fallbacks": sum(
                    not row["guard_off_graph_eligible"] for row in chunks
                ),
                "compulsory_model_rows": compulsory_rows,
                "padded_model_rows": guard_off_padded_rows,
                "total_model_rows": compulsory_rows + guard_off_padded_rows,
            },
            "causal_result": (
                "identical route and tensor shape on every exact forward; the "
                "guard changes zero model rows, launches, eager calls, or graph replays"
            ),
        },
        "complete_bounds": {
            "evidence_label": "analytical_structural_zero_same_source_same_route",
            "locked_seconds_per_request": LOCKED_SECONDS_PER_REQUEST,
            "target_seconds_per_request": TARGET_SECONDS_PER_REQUEST,
            "required_reduction_seconds_per_request": (
                LOCKED_SECONDS_PER_REQUEST - TARGET_SECONDS_PER_REQUEST
            ),
            "guard_enabled_reduction_interval_seconds_per_request": [0.0, 0.0],
            "guard_on_candidate_interval_seconds_per_request": [
                LOCKED_SECONDS_PER_REQUEST,
                LOCKED_SECONDS_PER_REQUEST,
            ],
            "guard_off_control_interval_seconds_per_request": [
                LOCKED_SECONDS_PER_REQUEST,
                LOCKED_SECONDS_PER_REQUEST,
            ],
            "target_reached": False,
            "timing_credit_from_padded_rows": 0.0,
            "cost": cost_bounds,
            "uncertainty": (
                "The causal zero is exact for the hash-bound workload, launch, "
                "capture buckets, and official method: no branch differs. Absolute "
                "current-runtime H200 latency remains unmeasured and is not inferred "
                "from row counts or upstream vendor benchmarks."
            ),
        },
        "focused_offline_checks": {
            "passed": True,
            "source_hashes_and_ownership": source_checks,
            "exact_inputs": input_checks,
            "trace_accounting": accounting_checks,
            "guard_boundaries": boundary_checks,
            "method_execution": [
                "ServerArgs._generate_prefill_cuda_graph_batch_sizes exact AST",
                "BaseCudaGraphRunner._pad_to_bucket exact AST",
                "PrefillCudaGraphRunner.can_run_graph exact AST",
            ],
            "command": "python3 -m unittest -v test_prefill_graph_padding_rebase.py",
        },
        "direct_inputs": direct_inputs,
        "h200_consumer": {
            "type": "none",
            "command": None,
            "reason": (
                "The exact workload never crosses the admitted guard: both arms "
                "would replay the same 58 graph buckets. A causal H200 pair would "
                "require changing the forbidden workload, chunk size, or capture "
                "buckets, so no in-scope nonduplicate real consumer command exists."
            ),
        },
        "decision": {
            "positive_terminal": False,
            "classification": "typed_none_exact_workload_guard_never_crosses",
            "source_complete_consumer_reachable": True,
            "exact_workload_guard_activated": False,
            "portfolio_action": "close_prefill_graph_excess_padding_guard_for_exact_c32",
            "reopen_conditions": [
                "A newly admitted exact workload or launch produces a capture bucket greater than two times raw prefill rows.",
                "A measured current-runtime trace contradicts the hash-bound 2048/992 raw-token reconstruction without changing workload parameters.",
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).parent)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--workload", type=Path)
    parser.add_argument("--launch", type=Path)
    parser.add_argument("--c32-terminal", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--qualified-terminal", type=Path)
    parser.add_argument("--gpu-prices", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--retrieved-at-utc")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    source_root = (args.source_root or project_root / "inputs/official").resolve()
    workload_root = project_root / "inputs/workload"
    retrieved_at_utc = args.retrieved_at_utc or datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    output = (
        args.output
        or project_root / "PREFILL_GRAPH_PADDING_REBASE_OFFLINE_TERMINAL.json"
    ).resolve()

    result = build_terminal(
        project_root=project_root,
        source_root=source_root,
        workload_path=(args.workload or workload_root / "WORKLOAD.json").resolve(),
        launch_path=(args.launch or workload_root / "LAUNCH.json").resolve(),
        terminal_path=(
            args.c32_terminal or workload_root / "C32_TERMINAL.json"
        ).resolve(),
        config_path=(args.config or workload_root / "MODEL_CONFIG.json").resolve(),
        qualified_terminal_path=(
            args.qualified_terminal or workload_root / "QUALIFIED_TERMINAL.json"
        ).resolve(),
        gpu_prices_path=(
            args.gpu_prices or workload_root / "GPU_PRICES.json"
        ).resolve(),
        retrieved_at_utc=retrieved_at_utc,
    )
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
