#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import math
import os
import random
import statistics
import subprocess
import sys
import time
import traceback
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from paged_fp8_contract import (
    CASES,
    CONCURRENCIES,
    EXPECTED_IMAGE,
    EXPECTED_SIGNATURE_PARAMETERS,
    EXPECTED_SOURCE_HASHES,
    EXPECTED_VLLM_VERSION,
    PAGE_SIZE,
    REPETITIONS,
    REQUIRED_NCU_METRICS,
    SENTINEL_CASES,
    WARMUPS,
    aggregate_economics,
    assert_context_byte_trend,
    atomic_json,
    balanced_pair_orders,
    block_table,
    decode_slot_mapping,
    evaluate_rows,
    full_slot_mapping,
    parse_ncu_csv,
    sentinel_continuation,
    sha256_file,
    utc_now,
)


@dataclass
class Runtime:
    torch: Any
    vllm: Any
    VllmConfig: Any
    CacheConfig: Any
    Attention: Any
    CommonAttentionMetadata: Any
    TritonAttentionBackend: Any
    set_current_vllm_config: Any
    set_forward_context: Any
    set_default_torch_dtype: Any
    unified_kv_cache_update: Any
    unified_attention_with_output: Any


@dataclass
class ExactModelConfig:
    q_heads: int
    kv_heads: int
    head_dim: int
    dtype: Any
    is_hybrid: bool = True
    is_mm_prefix_lm: bool = False
    use_mla: bool = False
    max_model_len: int = 4571

    def get_num_attention_heads(self, parallel_config: Any) -> int:
        return self.q_heads // parallel_config.tensor_parallel_size

    def get_num_kv_heads(self, parallel_config: Any) -> int:
        return max(1, self.kv_heads // parallel_config.tensor_parallel_size)

    def get_head_size(self) -> int:
        return self.head_dim


def load_runtime() -> Runtime:
    import torch
    import vllm
    from vllm.config import CacheConfig, VllmConfig, set_current_vllm_config
    from vllm.forward_context import set_forward_context
    from vllm.model_executor.layers.attention.attention import (
        Attention,
        unified_attention_with_output,
        unified_kv_cache_update,
    )
    from vllm.v1.attention.backend import CommonAttentionMetadata
    from vllm.v1.attention.backends.triton_attn import TritonAttentionBackend
    from vllm.utils.torch_utils import set_default_torch_dtype

    return Runtime(
        torch=torch,
        vllm=vllm,
        VllmConfig=VllmConfig,
        CacheConfig=CacheConfig,
        Attention=Attention,
        CommonAttentionMetadata=CommonAttentionMetadata,
        TritonAttentionBackend=TritonAttentionBackend,
        set_current_vllm_config=set_current_vllm_config,
        set_forward_context=set_forward_context,
        set_default_torch_dtype=set_default_torch_dtype,
        unified_kv_cache_update=unified_kv_cache_update,
        unified_attention_with_output=unified_attention_with_output,
    )


def parameter_names(callable_object: Any) -> tuple[str, ...]:
    return tuple(inspect.signature(callable_object).parameters)


def require_signature(name: str, callable_object: Any) -> str:
    actual = parameter_names(callable_object)
    expected = EXPECTED_SIGNATURE_PARAMETERS[name]
    if actual != expected:
        raise RuntimeError(
            f"{name} signature mismatch: expected {expected}, observed {actual}"
        )
    return str(inspect.signature(callable_object))


def source_identity(runtime: Runtime, image_digest: str) -> dict[str, Any]:
    if image_digest != EXPECTED_IMAGE:
        raise RuntimeError("immutable image digest does not match the readiness contract")
    if runtime.vllm.__version__ != EXPECTED_VLLM_VERSION:
        raise RuntimeError(
            f"vLLM revision mismatch: {runtime.vllm.__version__!r}"
        )
    package_root = Path(runtime.vllm.__file__).resolve().parent.parent
    observed = {}
    for relative, expected in EXPECTED_SOURCE_HASHES.items():
        path = package_root / relative
        actual = sha256_file(path)
        observed[relative] = {"path": str(path), "sha256": actual}
        if actual != expected:
            raise RuntimeError(f"source identity mismatch for {relative}")
    signatures = {
        "set_current_vllm_config": require_signature(
            "set_current_vllm_config", runtime.set_current_vllm_config
        ),
        "metadata_builder_init": None,
        "metadata_builder_build": None,
        "unified_kv_cache_update": require_signature(
            "unified_kv_cache_update", runtime.unified_kv_cache_update
        ),
        "unified_attention_with_output": require_signature(
            "unified_attention_with_output",
            runtime.unified_attention_with_output,
        ),
    }
    return {
        "pass": True,
        "image": image_digest,
        "vllm_version": runtime.vllm.__version__,
        "source_files": observed,
        "signatures": signatures,
    }


def make_vllm_config(runtime: Runtime, case: Any, arm: str) -> Any:
    cache_dtype = "auto" if arm == "bf16" else "fp8_e4m3"
    cache_config = runtime.CacheConfig(
        block_size=PAGE_SIZE,
        cache_dtype=cache_dtype,
        sliding_window=case.sliding_window,
        enable_prefix_caching=False,
        calculate_kv_scales=False,
    )
    exact_geometry = ExactModelConfig(
        q_heads=case.q_heads,
        kv_heads=case.kv_heads,
        head_dim=case.head_dim,
        dtype=runtime.torch.bfloat16,
    )
    # VllmConfig is a pinned Pydantic dataclass.  Its ordinary constructor
    # invokes __post_init__, which in turn validates/downloads a complete
    # ModelConfig.  The registered-Attention source consumes only the fields
    # below, so construct the declared config object without running that
    # producer-side lifecycle and attach the exact consumer contract directly.
    try:
        from vllm.config import AttentionConfig, CompilationConfig, ParallelConfig

        parallel_config = ParallelConfig()
        compilation_config = CompilationConfig()
        # The pinned CustomOp.default_on() contract requires exactly one
        # explicit mode.  This is a consumer-only runtime setting; it does
        # not alter geometry, cache dtype, or the numerical gates.
        compilation_config.custom_ops = ["all"]
        attention_config = AttentionConfig()
    except ImportError:
        # CPU-mocked construction tests intentionally do not install vLLM.
        parallel_config = SimpleNamespace(
            tensor_parallel_size=1,
            decode_context_parallel_size=1,
            prefill_context_parallel_size=1,
        )
        compilation_config = SimpleNamespace(static_forward_context={})
        attention_config = SimpleNamespace(use_non_causal=False)

    config = object.__new__(runtime.VllmConfig)
    for name, value in {
        "model_config": exact_geometry,
        "cache_config": cache_config,
        "parallel_config": parallel_config,
        "compilation_config": compilation_config,
        "attention_config": attention_config,
    }.items():
        object.__setattr__(config, name, value)
    return config


def construct_registered_layer(
    runtime: Runtime,
    case: Any,
    arm: str,
    layer_name: str,
) -> tuple[Any, Any, Any, dict[str, Any]]:
    config = make_vllm_config(runtime, case, arm)
    dtype_context = (
        runtime.set_default_torch_dtype(runtime.torch.bfloat16)
        if hasattr(runtime, "set_default_torch_dtype")
        else nullcontext()
    )
    with runtime.set_current_vllm_config(config), dtype_context:
        layer = runtime.Attention(
            case.q_heads,
            case.head_dim,
            case.head_dim ** -0.5,
            num_kv_heads=case.kv_heads,
            cache_config=config.cache_config,
            per_layer_sliding_window=case.sliding_window,
            prefix=layer_name,
            attn_backend=runtime.TritonAttentionBackend,
        )
    if config.compilation_config.static_forward_context.get(layer_name) is not layer:
        raise RuntimeError("Attention layer did not register in static_forward_context")
    kv_cache_spec = layer.get_kv_cache_spec(config)
    builder_cls = layer.attn_backend.get_builder_cls()
    require_signature("metadata_builder_init", builder_cls.__init__)
    require_signature("metadata_builder_build", builder_cls.build)
    builder = builder_cls(
        kv_cache_spec,
        [layer_name],
        config,
        runtime.torch.device("cuda"),
    )
    trace = {
        "pass": True,
        "config_context_entered": True,
        "registered_layer_name": layer_name,
        "attention_class": f"{type(layer).__module__}.{type(layer).__name__}",
        "backend_class": (
            f"{layer.attn_backend.__module__}.{layer.attn_backend.__name__}"
        ),
        "implementation_class": f"{type(layer.impl).__module__}.{type(layer.impl).__name__}",
        "kv_cache_spec_class": (
            f"{type(kv_cache_spec).__module__}.{type(kv_cache_spec).__name__}"
        ),
        "metadata_builder_class": f"{builder_cls.__module__}.{builder_cls.__name__}",
        "metadata_builder_init_signature": str(inspect.signature(builder_cls.__init__)),
        "metadata_builder_build_signature": str(inspect.signature(builder.build)),
    }
    return config, layer, builder, trace


def native_decode_metadata(
    runtime: Runtime,
    builder: Any,
    case: Any,
    concurrency: int,
    block_table_tensor: Any,
    decode_slots: Any,
) -> tuple[Any, Any]:
    query_start_cpu = runtime.torch.arange(
        concurrency + 1, dtype=runtime.torch.int32, device="cpu"
    )
    common = runtime.CommonAttentionMetadata(
        query_start_loc=query_start_cpu.to("cuda"),
        query_start_loc_cpu=query_start_cpu,
        seq_lens=runtime.torch.full(
            (concurrency,), case.context, dtype=runtime.torch.int32, device="cuda"
        ),
        num_reqs=concurrency,
        num_actual_tokens=concurrency,
        max_query_len=1,
        max_seq_len=case.context,
        block_table_tensor=block_table_tensor,
        slot_mapping=decode_slots,
        causal=True,
    )
    metadata = builder.build(
        common_prefix_len=0,
        common_attn_metadata=common,
        fast_build=False,
    )
    if metadata is None:
        raise RuntimeError("native metadata builder returned None")
    return common, metadata


def _tensor_geometry(runtime: Runtime, case: Any, concurrency: int, seed: int) -> dict[str, Any]:
    torch = runtime.torch
    generator = torch.Generator(device="cuda")
    generator.manual_seed(seed)
    key = torch.empty(
        (concurrency, case.context, case.kv_heads, case.head_dim),
        dtype=torch.bfloat16,
        device="cuda",
    ).uniform_(-0.25, 0.25, generator=generator)
    value = torch.empty_like(key).uniform_(-0.25, 0.25, generator=generator)
    query = torch.empty(
        (concurrency, case.q_heads, case.head_dim),
        dtype=torch.bfloat16,
        device="cuda",
    ).uniform_(-0.25, 0.25, generator=generator)
    return {"query": query, "key": key, "value": value}


def ensure_cuda_kv_scales(runtime: Runtime, layer: Any) -> None:
    torch = runtime.torch
    for name in ("_k_scale", "_v_scale"):
        scale = getattr(layer, name, None)
        if scale is None or not hasattr(scale, "to"):
            scale = torch.ones((), dtype=torch.float32, device="cuda")
        elif getattr(getattr(scale, "device", None), "type", None) != "cuda":
            scale = scale.to("cuda")
        setattr(layer, name, scale)


def prepare_arm(
    runtime: Runtime,
    case: Any,
    concurrency: int,
    arm: str,
    tensors: dict[str, Any],
) -> dict[str, Any]:
    torch = runtime.torch
    layer_name = f"paged_{case.name}_c{concurrency}_{arm}"
    config, layer, builder, trace = construct_registered_layer(
        runtime, case, arm, layer_name
    )
    pages = math.ceil(case.context / PAGE_SIZE)
    table = torch.tensor(
        block_table(case, concurrency), dtype=torch.int32, device="cuda"
    )
    all_slots = torch.tensor(
        full_slot_mapping(case, concurrency), dtype=torch.int64, device="cuda"
    )
    last_slots = torch.tensor(
        decode_slot_mapping(case, concurrency), dtype=torch.int64, device="cuda"
    )
    num_blocks = concurrency * pages
    cache_dtype = "auto" if arm == "bf16" else "fp8_e4m3"
    cache_shape = layer.attn_backend.get_kv_cache_shape(
        num_blocks,
        PAGE_SIZE,
        case.kv_heads,
        case.head_dim,
        cache_dtype,
    )
    layer.kv_cache = torch.empty(
        cache_shape, dtype=layer.kv_cache_torch_dtype, device="cuda"
    )
    ensure_cuda_kv_scales(runtime, layer)
    common, metadata = native_decode_metadata(
        runtime, builder, case, concurrency, table, last_slots
    )
    key_flat = tensors["key"].reshape(
        concurrency * case.context, case.kv_heads, case.head_dim
    )
    value_flat = tensors["value"].reshape_as(key_flat)
    with runtime.set_forward_context(
        {layer_name: metadata},
        config,
        num_tokens=concurrency * case.context,
        slot_mapping={layer_name: all_slots},
        skip_compiled=True,
    ):
        dependency = runtime.unified_kv_cache_update(
            key_flat, value_flat, layer_name
        )
    output = torch.empty_like(tensors["query"])
    return {
        "arm": arm,
        "config": config,
        "layer": layer,
        "layer_name": layer_name,
        "metadata": metadata,
        "common_metadata": common,
        "decode_slots": last_slots,
        "dependency": dependency,
        "output": output,
        "trace": {
            **trace,
            "common_metadata_class": (
                f"{type(common).__module__}.{type(common).__name__}"
            ),
            "metadata_class": f"{type(metadata).__module__}.{type(metadata).__name__}",
            "cache_shape": list(cache_shape),
            "cache_dtype": str(layer.kv_cache.dtype),
            "producer_slots": int(all_slots.numel()),
            "query_shape": list(tensors["query"].shape),
            "key_shape": list(key_flat.shape),
            "value_shape": list(value_flat.shape),
        },
    }


def consume_once(runtime: Runtime, prepared: dict[str, Any], tensors: dict[str, Any]) -> Any:
    case_output = prepared["output"]
    concurrency = tensors["query"].shape[0]
    key_last = tensors["key"][:, -1]
    value_last = tensors["value"][:, -1]
    with runtime.set_forward_context(
        {prepared["layer_name"]: prepared["metadata"]},
        prepared["config"],
        num_tokens=concurrency,
        slot_mapping={prepared["layer_name"]: prepared["decode_slots"]},
        skip_compiled=True,
    ):
        runtime.unified_attention_with_output(
            tensors["query"],
            key_last,
            value_last,
            case_output,
            prepared["layer_name"],
            kv_cache_dummy_dep=prepared["dependency"],
        )
    return case_output


def dense_reference(runtime: Runtime, case: Any, tensors: dict[str, Any]) -> Any:
    torch = runtime.torch
    query = tensors["query"].float()
    keys = tensors["key"]
    values = tensors["value"]
    group = case.q_heads // case.kv_heads
    output = torch.empty_like(query)
    scale = case.head_dim ** -0.5
    for kv_head in range(case.kv_heads):
        start = kv_head * group
        stop = start + group
        scores = torch.einsum(
            "bgd,bsd->bgs",
            query[:, start:stop],
            keys[:, :, kv_head].float(),
        )
        probabilities = torch.softmax(scores * scale, dim=-1)
        output[:, start:stop] = torch.einsum(
            "bgs,bsd->bgd",
            probabilities,
            values[:, :, kv_head].float(),
        )
    return output


def oracle(runtime: Runtime, candidate: Any, reference: Any) -> dict[str, Any]:
    torch = runtime.torch
    candidate_flat = candidate.float().flatten()
    reference_flat = reference.float().flatten()
    cosine = float(
        torch.nn.functional.cosine_similarity(
            candidate_flat, reference_flat, dim=0
        ).item()
    )
    denominator = torch.linalg.vector_norm(reference_flat).clamp_min(1e-12)
    nrmse = float(
        (torch.linalg.vector_norm(candidate_flat - reference_flat) / denominator).item()
    )
    return {
        "finite": bool(
            torch.isfinite(candidate_flat).all().item()
            and torch.isfinite(reference_flat).all().item()
        ),
        "nonzero": bool(
            candidate_flat.abs().max().item() > 1e-6
            and reference_flat.abs().max().item() > 1e-6
        ),
        "cosine": cosine,
        "normalized_rmse": nrmse,
    }


def timed_pair(
    runtime: Runtime,
    case: Any,
    concurrency: int,
    seed: int,
) -> dict[str, Any]:
    torch = runtime.torch
    tensors = _tensor_geometry(runtime, case, concurrency, seed)
    prepared = {
        arm: prepare_arm(runtime, case, concurrency, arm, tensors)
        for arm in ("bf16", "fp8_e4m3")
    }
    for arm in prepared:
        for _ in range(WARMUPS):
            consume_once(runtime, prepared[arm], tensors)
    torch.cuda.synchronize()

    event_ms = {arm: [] for arm in prepared}
    wall_ms = {arm: [] for arm in prepared}
    checksums = {arm: [] for arm in prepared}
    for first, second in balanced_pair_orders(REPETITIONS, seed):
        for arm in (first, second):
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)
            wall_start = time.perf_counter()
            start_event.record()
            output = consume_once(runtime, prepared[arm], tensors)
            end_event.record()
            end_event.synchronize()
            wall_ms[arm].append((time.perf_counter() - wall_start) * 1000.0)
            event_ms[arm].append(float(start_event.elapsed_time(end_event)))
            checksums[arm].append(float(output.float().sum().item()))

    bf16_output = consume_once(runtime, prepared["bf16"], tensors).detach().clone()
    fp8_output = consume_once(runtime, prepared["fp8_e4m3"], tensors).detach().clone()
    reference = dense_reference(runtime, case, tensors)
    row = {
        "schema_version": 1,
        "case": case.name,
        "family": case.family,
        "context": case.context,
        "concurrency": concurrency,
        "producer_slots": concurrency * case.context,
        "native_trace": {
            "pass": True,
            "bf16": prepared["bf16"]["trace"],
            "fp8_e4m3": prepared["fp8_e4m3"]["trace"],
        },
        "timing": {},
        "oracles": {
            "bf16_vs_reference": oracle(runtime, bf16_output, reference),
            "fp8_vs_bf16": oracle(runtime, fp8_output, bf16_output),
        },
        "counters": {},
    }
    for arm in prepared:
        row["timing"][arm] = {
            "warmups": WARMUPS,
            "repetitions": REPETITIONS,
            "serialized_cuda_event_interval_union_ms_p50": statistics.median(
                event_ms[arm]
            ),
            "synchronized_wall_ms_p50": statistics.median(wall_ms[arm]),
            "event_ms": event_ms[arm],
            "wall_ms": wall_ms[arm],
            "output_checksum_sha256": hashlib.sha256(
                json.dumps(checksums[arm], separators=(",", ":")).encode()
            ).hexdigest(),
        }
    return row


def counter_worker(
    runtime: Runtime,
    case: Any,
    concurrency: int,
    arm: str,
    seed: int,
    output: Path,
) -> None:
    torch = runtime.torch
    tensors = _tensor_geometry(runtime, case, concurrency, seed)
    prepared = prepare_arm(runtime, case, concurrency, arm, tensors)
    for _ in range(3):
        consume_once(runtime, prepared, tensors)
    torch.cuda.synchronize()
    range_name = f"h100_paged_fp8::{case.name}::c{concurrency}::{arm}"
    atomic_json(
        output.with_suffix(".science_started.json"),
        {"range": range_name, "started_at_utc": utc_now()},
    )
    torch.cuda.nvtx.range_push(range_name)
    result = consume_once(runtime, prepared, tensors)
    torch.cuda.nvtx.range_pop()
    torch.cuda.synchronize()
    terminal = {
        "pass": bool(torch.isfinite(result).all().item()),
        "range": range_name,
        "output_checksum": float(result.float().sum().item()),
        "completed_at_utc": utc_now(),
    }
    atomic_json(output, terminal)
    if not terminal["pass"]:
        raise RuntimeError("counter consumer produced non-finite output")


def ensure_h100(runtime: Runtime) -> None:
    torch = runtime.torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available")
    if "H100" not in torch.cuda.get_device_name():
        raise RuntimeError(f"expected H100, got {torch.cuda.get_device_name()}")
    if tuple(torch.cuda.get_device_capability()) != (9, 0):
        raise RuntimeError("expected SM90")


def _run_checked(command: list[str], stdout: Path | None = None) -> None:
    if stdout is None:
        completed = subprocess.run(command, check=False)
    else:
        with stdout.open("w", encoding="utf-8") as handle:
            completed = subprocess.run(
                command, stdout=handle, stderr=subprocess.STDOUT, check=False
            )
    if completed.returncode:
        raise RuntimeError(
            f"subprocess failed with exit {completed.returncode}: {command}"
        )


def worker_command(
    script: Path,
    mode: str,
    case_name: str,
    concurrency: int,
    output: Path,
    seed: int,
    image_digest: str,
    arm: str | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(script),
        mode,
        "--case",
        case_name,
        "--concurrency",
        str(concurrency),
        "--output",
        str(output),
        "--seed",
        str(seed),
        "--image-digest",
        image_digest,
    ]
    if arm is not None:
        command.extend(["--arm", arm])
    return command


def capture_counters(
    script: Path,
    case_name: str,
    concurrency: int,
    arm: str,
    output_root: Path,
    seed: int,
    image_digest: str,
) -> dict[str, Any]:
    stem = f"{case_name}-c{concurrency}-{arm}"
    worker_output = output_root / f"{stem}.counter-worker.json"
    csv_output = output_root / f"{stem}.ncu.csv"
    range_name = f"h100_paged_fp8::{case_name}::c{concurrency}::{arm}"
    command = [
        "ncu",
        "--nvtx",
        "--nvtx-include",
        f"{range_name}/",
        "--target-processes",
        "all",
        "--page",
        "raw",
        "--csv",
        "--metrics",
        ",".join(REQUIRED_NCU_METRICS),
        "--log-file",
        str(csv_output),
        *worker_command(
            script,
            "counter-worker",
            case_name,
            concurrency,
            worker_output,
            seed,
            image_digest,
            arm,
        ),
    ]
    _run_checked(command)
    worker_terminal = json.loads(worker_output.read_text())
    if not worker_terminal.get("pass") or worker_terminal.get("range") != range_name:
        raise RuntimeError("counter worker terminal is missing or mismatched")
    normalized = parse_ncu_csv(csv_output, range_name)
    normalized["command"] = command
    normalized["raw_csv_sha256"] = sha256_file(csv_output)
    normalized["worker_terminal_sha256"] = sha256_file(worker_output)
    return normalized


def measured_row(
    script: Path,
    case_name: str,
    concurrency: int,
    output_root: Path,
    seed: int,
    image_digest: str,
) -> dict[str, Any]:
    timing_output = output_root / f"{case_name}-c{concurrency}.timing.json"
    _run_checked(
        worker_command(
            script,
            "pair-worker",
            case_name,
            concurrency,
            timing_output,
            seed,
            image_digest,
        )
    )
    row = json.loads(timing_output.read_text())
    row["timing_artifact_sha256"] = sha256_file(timing_output)
    row["counters"] = {
        arm: capture_counters(
            script,
            case_name,
            concurrency,
            arm,
            output_root,
            seed,
            image_digest,
        )
        for arm in ("bf16", "fp8_e4m3")
    }
    atomic_json(timing_output, row)
    row["timing_artifact_sha256"] = sha256_file(timing_output)
    return row


def orchestrate(args: argparse.Namespace) -> int:
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()
    terminal_path = output_root / "H100_PAGED_FP8_EXECUTION_TERMINAL.json"
    result = {
        "schema_version": 1,
        "type": "h100_paged_fp8_execution_terminal",
        "pass": False,
        "result": "integration_error",
        "started_at_utc": utc_now(),
        "identity_contract": str(args.readiness.resolve()),
        "identity_contract_sha256": sha256_file(args.readiness.resolve()),
        "provider_create_allowed": False,
        "scientific_sample_consumed": False,
    }
    try:
        readiness = json.loads(args.readiness.read_text())
        expected_program = readiness["source"]["files"]["paged_fp8_execution.py"]
        if expected_program != sha256_file(script):
            raise RuntimeError("program hash differs from readiness terminal")

        sentinel_rows = [
            measured_row(
                script, case_name, 8, output_root, args.seed, args.image_digest
            )
            for case_name in SENTINEL_CASES
        ]
        sentinel = sentinel_continuation(
            sentinel_rows, args.absolute_deadline_utc
        )
        atomic_json(output_root / "SENTINEL.json", sentinel)
        result["scientific_sample_consumed"] = True
        result["sentinel"] = sentinel
        if not sentinel["conditional_sweep_allowed"]:
            result["result"] = "sentinel_reject"
            result["pass"] = False
            atomic_json(terminal_path, result)
            return 2

        rows_by_key = {
            (row["case"], row["concurrency"]): row for row in sentinel_rows
        }
        for concurrency in CONCURRENCIES:
            for case_name in CASES:
                key = (case_name, concurrency)
                if key not in rows_by_key:
                    rows_by_key[key] = measured_row(
                        script,
                        case_name,
                        concurrency,
                        output_root,
                        args.seed,
                        args.image_digest,
                    )
        evaluated = evaluate_rows(rows_by_key.values())
        if not all(row["pass"] for row in evaluated):
            result["result"] = "sweep_reject"
            result["rows"] = evaluated
            atomic_json(terminal_path, result)
            return 3
        assert_context_byte_trend(evaluated)
        economics = aggregate_economics(evaluated)
        result.update(
            {
                "pass": economics["pass"],
                "result": (
                    "mechanism_accept" if economics["pass"] else "economic_reject"
                ),
                "rows": evaluated,
                "economics": economics,
                "completed_at_utc": utc_now(),
            }
        )
        atomic_json(terminal_path, result)
        return 0 if result["pass"] else 4
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
        result["completed_at_utc"] = utc_now()
        atomic_json(terminal_path, result)
        return 1


def recovery_worker(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    result = {
        "schema_version": 1,
        "type": "h100_paged_fp8_recovery_terminal",
        "pass": False,
        "result": "integration_error",
        "started_at_utc": utc_now(),
        "identity_contract": str(args.readiness.resolve()),
        "identity_contract_sha256": sha256_file(args.readiness.resolve()),
        "provider_create_allowed": False,
        "scientific_sample_consumed": False,
        "scope": {"case": "local1024", "concurrency": 8},
    }
    try:
        readiness = json.loads(args.readiness.read_text())
        script = Path(__file__).resolve()
        if readiness["source"]["files"]["paged_fp8_execution.py"] != sha256_file(script):
            raise RuntimeError("program hash differs from readiness terminal")
        runtime = load_runtime()
        ensure_h100(runtime)
        identity = source_identity(runtime, args.image_digest)
        primitive_output = output.parent / "local1024-c8.primitive.timing.json"
        primitive_command = worker_command(
            script, "pair-worker", "local1024", 8, primitive_output, args.seed, args.image_digest
        )
        primitive = subprocess.run(
            primitive_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        primitive_timing = {}
        if primitive_output.exists():
            try:
                primitive_timing = json.loads(primitive_output.read_text())
            except Exception as exc:
                primitive_timing = {
                    "error": {"type": type(exc).__name__, "message": str(exc)}
                }
        primitive_capture = {
            "schema_version": 1,
            "type": "primitive_pair_worker_capture",
            "command": primitive_command,
            "returncode": primitive.returncode,
            "stdout": primitive.stdout,
            "stderr": primitive.stderr,
            "traceback": primitive_timing.get("error", {}).get("traceback", ""),
            "timing_artifact": str(primitive_output),
            "captured_at_utc": utc_now(),
        }
        atomic_json(output.parent / "primitive-pair-worker.capture.json", primitive_capture)
        if primitive.returncode != 0:
            result["error"] = {
                "type": "PrimitivePairWorkerError",
                "message": "primitive pair-worker returned nonzero",
                **primitive_capture,
            }
            result["completed_at_utc"] = utc_now()
            atomic_json(output, result)
            return 1
        row = primitive_timing
        row["timing_artifact_sha256"] = sha256_file(primitive_output)
        row["counters"] = {
            arm: capture_counters(
                script, "local1024", 8, arm, output.parent, args.seed, args.image_digest
            )
            for arm in ("bf16", "fp8_e4m3")
        }
        atomic_json(primitive_output, row)
        evaluated = evaluate_rows([row])[0]
        result.update(
            {
                "pass": evaluated["pass"],
                "result": "recovery_row_complete" if evaluated["pass"] else "recovery_row_reject",
                "identity": identity,
                "row": evaluated,
                "scientific_sample_consumed": True,
                "completed_at_utc": utc_now(),
            }
        )
    except Exception as exc:
        result["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        result["completed_at_utc"] = utc_now()
    atomic_json(output, result)
    return 0 if result["pass"] else 1


def worker(args: argparse.Namespace) -> int:
    result = {"pass": False, "started_at_utc": utc_now()}
    try:
        runtime = load_runtime()
        ensure_h100(runtime)
        result["identity"] = source_identity(runtime, args.image_digest)
        case = CASES[args.case]
        if args.mode == "pair-worker":
            result = timed_pair(runtime, case, args.concurrency, args.seed)
            result["identity"] = source_identity(runtime, args.image_digest)
            result["pass"] = True
        else:
            counter_worker(
                runtime,
                case,
                args.concurrency,
                args.arm,
                args.seed,
                args.output,
            )
            return 0
    except Exception as exc:
        result["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    atomic_json(args.output, result)
    return 0 if result.get("pass") else 1


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser()
    subparsers = command.add_subparsers(dest="mode", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--readiness", type=Path, required=True)
    run.add_argument("--absolute-deadline-utc", required=True)
    run.add_argument("--image-digest", default=EXPECTED_IMAGE)
    run.add_argument("--seed", type=int, default=17)
    recovery = subparsers.add_parser("recovery-worker")
    recovery.add_argument("--output", type=Path, required=True)
    recovery.add_argument("--readiness", type=Path, required=True)
    recovery.add_argument("--absolute-deadline-utc", required=True)
    recovery.add_argument("--image-digest", default=EXPECTED_IMAGE)
    recovery.add_argument("--seed", type=int, default=17)
    for name in ("pair-worker", "counter-worker"):
        worker_parser = subparsers.add_parser(name)
        worker_parser.add_argument("--case", choices=tuple(CASES), required=True)
        worker_parser.add_argument(
            "--concurrency", choices=CONCURRENCIES, type=int, required=True
        )
        worker_parser.add_argument("--output", type=Path, required=True)
        worker_parser.add_argument("--seed", type=int, default=17)
        worker_parser.add_argument("--image-digest", default=EXPECTED_IMAGE)
        if name == "counter-worker":
            worker_parser.add_argument(
                "--arm", choices=("bf16", "fp8_e4m3"), required=True
            )
    return command


def main() -> int:
    args = parser().parse_args()
    if args.mode == "run":
        return orchestrate(args)
    if args.mode == "recovery-worker":
        return recovery_worker(args)
    return worker(args)


if __name__ == "__main__":
    raise SystemExit(main())
