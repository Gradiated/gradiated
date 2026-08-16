#!/usr/bin/env python3
import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace


PINNED_REVISION = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
SELECTED_REVISION = "6c6175fabd8eac2ac7a66eea36e6b21fc0893a75"
SELECTED_PATH = (
    "python/sglang/srt/model_executor/runner/prefill_cuda_graph_runner.py"
)
GROUP_QUANT_REVISION = "8bb0d8d005004060cbaa843ae6d6378ea46a9c98"
GROUP_QUANT_PATH = "python/sglang/kernels/ops/quantization/fp8_kernel.py"
HPC_OPS_REVISION = "0a6d1930c36079dc08aeee6df41be5ebef195f39"
HPC_OPS_PATH = "python/sglang/srt/layers/attention/hpc_ops_backend.py"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_show(repo: Path, revision: str, source_path: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), "show", f"{revision}:{source_path}"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def git_has_path(repo: Path, revision: str, source_path: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{revision}:{source_path}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def extract_method(source: str, class_name: str, method_name: str):
    tree = ast.parse(source)
    constant = None
    method = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name)
                and target.id == "_MAX_PREFILL_CUDA_GRAPH_PADDING_FACTOR"
                for target in node.targets
            ):
                constant = ast.literal_eval(node.value)
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            method = next(
                (
                    item
                    for item in node.body
                    if isinstance(item, ast.FunctionDef) and item.name == method_name
                ),
                None,
            )
    if constant is None or method is None:
        raise RuntimeError("selected upstream guard or consumer method is absent")
    class_node = ast.ClassDef(
        name="ExtractedPrefillCudaGraphRunner",
        bases=[],
        keywords=[],
        body=[method],
        decorator_list=[],
    )
    module = ast.fix_missing_locations(ast.Module(body=[class_node], type_ignores=[]))

    class BreakableCudaGraphBackend:
        pass

    namespace = {
        "BreakableCudaGraphBackend": BreakableCudaGraphBackend,
        "ForwardBatch": object,
        "_MAX_PREFILL_CUDA_GRAPH_PADDING_FACTOR": constant,
    }
    exec(compile(module, f"{SELECTED_REVISION}:{SELECTED_PATH}", "exec"), namespace)
    return namespace["ExtractedPrefillCudaGraphRunner"], constant, BreakableCudaGraphBackend


def make_runner(extracted_class, backend_class, capture_tokens):
    runner = extracted_class()
    runner._is_full_backend = False
    runner._capture_req_slots = 32
    runner.backend = backend_class()
    runner.capture_hidden_mode = "null"
    runner.max_num_tokens = max(capture_tokens)
    runner.capture_num_tokens = capture_tokens
    runner._has_unsupported_mha_prefix = lambda _: False
    runner._has_inactive_dp_rank = lambda _: False
    runner._pad_to_bucket = lambda value, buckets: next(
        bucket for bucket in buckets if bucket >= value
    )
    return runner


def run_guard_case(runner, raw_tokens):
    forward_mode = SimpleNamespace(is_target_verify=lambda: False)
    forward_batch = SimpleNamespace(
        batch_size=1,
        input_embeds=None,
        replace_embeds=None,
        forward_mode=forward_mode,
        capture_hidden_mode="null",
        global_num_tokens_cpu=None,
        can_run_dp_breakable_cuda_graph=True,
        input_ids=list(range(raw_tokens)),
        return_logprob=False,
        extend_logprob_start_lens_cpu=[],
        extend_seq_lens_cpu=[],
    )
    return runner.can_run_graph(forward_batch)


def check_source_contracts(group_source: str, hpc_source: str) -> dict:
    group_contract = all(
        needle in group_source
        for needle in (
            "group_size == x.shape[-1]",
            "return sglang_per_token_quant_fp8(x)",
            "Whole-row group quant is per-token quant",
        )
    )
    hpc_contract = all(
        needle in hpc_source
        for needle in (
            "_SUPPORTED_HEAD_DIM",
            "head_dim != _SUPPORTED_HEAD_DIM",
            "does not support sliding window",
        )
    )
    if not group_contract or not hpc_contract:
        raise RuntimeError("a rejected-candidate source contract changed")
    return {
        "group_quant_whole_row_routes_to_existing_per_token_kernel": group_contract,
        "hpc_ops_rejects_non_128_and_sliding_window": hpc_contract,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sglang-repo", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--launch", type=Path, required=True)
    parser.add_argument("--attribution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    selected_bytes = git_show(args.sglang_repo, SELECTED_REVISION, SELECTED_PATH)
    group_bytes = git_show(args.sglang_repo, GROUP_QUANT_REVISION, GROUP_QUANT_PATH)
    hpc_bytes = git_show(args.sglang_repo, HPC_OPS_REVISION, HPC_OPS_PATH)
    selected_source = selected_bytes.decode()
    group_source = group_bytes.decode()
    hpc_source = hpc_bytes.decode()

    extracted_class, factor, backend_class = extract_method(
        selected_source, "PrefillCudaGraphRunner", "can_run_graph"
    )
    sparse_runner = make_runner(extracted_class, backend_class, [2816, 3072, 8192])
    exact_prompt_runner = make_runner(extracted_class, backend_class, [8192])
    exact_chunk_runner = make_runner(extracted_class, backend_class, [2048])
    dynamic_checks = {
        "upstream_reported_3208_to_8192_rejected": not run_guard_case(
            sparse_runner, 3208
        ),
        "boundary_4096_to_8192_accepted": run_guard_case(exact_prompt_runner, 4096),
        "exact_prompt_4214_to_8192_accepted": run_guard_case(
            exact_prompt_runner, 4214
        ),
        "exact_chunk_2048_to_2048_accepted": run_guard_case(exact_chunk_runner, 2048),
    }
    if not all(dynamic_checks.values()):
        raise RuntimeError("the extracted upstream consumer failed a guard contract")

    config = json.loads(args.config.read_text())
    text_config = config["text_config"]
    launch = json.loads(args.launch.read_text())
    launch_args = launch["args"]
    attribution = json.loads(args.attribution.read_text())
    prefill_seconds = next(
        row["seconds"]
        for row in attribution["phases"]["prefill"]["boundaries"]
        if row["boundary"] == "attention_kv"
    )
    prefill_total_seconds = attribution["phases"]["prefill"]["seconds"]

    pinned_has_selected_consumer = git_has_path(
        args.sglang_repo, PINNED_REVISION, SELECTED_PATH
    )
    pinned_has_graph_config = git_has_path(
        args.sglang_repo,
        PINNED_REVISION,
        "python/sglang/srt/model_executor/cuda_graph_config.py",
    )
    has_current_graph_config_arg = "--cuda-graph-config" in launch_args
    has_legacy_decode_graph_arg = "--cuda-graph-max-bs" in launch_args
    chunk_size = int(launch_args[launch_args.index("--chunked-prefill-size") + 1])

    source_contracts = check_source_contracts(group_source, hpc_source)
    exact_contracts = {
        "dense_model": text_config.get("num_experts") is None,
        "head_dim_local": text_config["head_dim"] == 256,
        "head_dim_global": text_config["global_head_dim"] == 512,
        "hybrid_sliding_window": text_config["sliding_window"] == 1024,
        "sliding_layers": text_config["layer_types"].count("sliding_attention"),
        "global_layers": text_config["layer_types"].count("full_attention"),
        "prompt_tokens_per_request": 4214,
        "requests": 32,
        "completion_tokens_per_request": 358,
        "chunked_prefill_size": chunk_size,
    }
    selected_activation = {
        "pinned_runtime_has_prefill_consumer": pinned_has_selected_consumer,
        "pinned_runtime_has_cuda_graph_config": pinned_has_graph_config,
        "exact_launch_has_current_cuda_graph_config_arg": has_current_graph_config_arg,
        "exact_launch_has_legacy_decode_cuda_graph_arg": has_legacy_decode_graph_arg,
        "exact_activation_possible_without_runtime_replacement": (
            pinned_has_selected_consumer
            and pinned_has_graph_config
            and has_current_graph_config_arg
        ),
    }
    if selected_activation["exact_activation_possible_without_runtime_replacement"]:
        raise RuntimeError("selected candidate unexpectedly activates on pinned runtime")

    locked_service = 0.625149101968745
    locked_target = 0.500119281574996
    checks = {
        "schema_version": 1,
        "classification": "typed_none_selected_consumer_absent_from_locked_runtime",
        "primary_source_consumer_execution": {
            "method": "PrefillCudaGraphRunner.can_run_graph",
            "method_body": "compiled directly from the selected merge commit AST",
            "padding_factor": factor,
            "cases": dynamic_checks,
        },
        "source_contracts": source_contracts,
        "exact_model_contract": exact_contracts,
        "selected_activation": selected_activation,
        "complete_bound": {
            "locked_qualified_seconds_per_request": locked_service,
            "locked_target_seconds_per_request": locked_target,
            "required_reduction_seconds_per_request": locked_service - locked_target,
            "exact_activated_work_seconds_per_request": 0.0,
            "exact_reduction_lower_seconds_per_request": 0.0,
            "exact_reduction_upper_seconds_per_request": 0.0,
            "exact_candidate_seconds_per_request": locked_service,
            "target_reached": False,
            "profile_prefill_total_seconds_per_32_request_window": prefill_total_seconds,
            "profile_prefill_total_ceiling_seconds_per_request": prefill_total_seconds
            / 32,
            "profile_prefill_attention_seconds_per_32_request_window": prefill_seconds,
            "uncertainty": (
                "The zero exact bound is structural: the locked source and launch "
                "cannot enter the selected consumer. Profile ceilings are context "
                "only and are not credited to the candidate."
            ),
        },
        "direct_inputs": {
            "selected_source": {
                "revision": SELECTED_REVISION,
                "path": SELECTED_PATH,
                "bytes": len(selected_bytes),
                "sha256": sha256_bytes(selected_bytes),
            },
            "group_quant_source": {
                "revision": GROUP_QUANT_REVISION,
                "path": GROUP_QUANT_PATH,
                "bytes": len(group_bytes),
                "sha256": sha256_bytes(group_bytes),
            },
            "hpc_ops_source": {
                "revision": HPC_OPS_REVISION,
                "path": HPC_OPS_PATH,
                "bytes": len(hpc_bytes),
                "sha256": sha256_bytes(hpc_bytes),
            },
            "config": {
                "path": str(args.config.resolve()),
                "bytes": args.config.stat().st_size,
                "sha256": sha256_path(args.config),
            },
            "launch": {
                "path": str(args.launch.resolve()),
                "bytes": args.launch.stat().st_size,
                "sha256": sha256_path(args.launch),
            },
            "attribution": {
                "path": str(args.attribution.resolve()),
                "bytes": args.attribution.stat().st_size,
                "sha256": sha256_path(args.attribution),
            },
        },
        "resource_use": {
            "gpu_claimed_or_used": False,
            "cuda_run": False,
            "ssh_provider_or_endpoint_used": False,
            "checkpoint_shards_read_or_copied": False,
            "spend_usd": 0.0,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(checks, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
