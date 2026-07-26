#!/usr/bin/env python3
"""Offline source and physical-accounting screen for Gemma 4 MXFP6 on MI355X."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
WORKSPACE = next(parent for parent in PROJECT_DIR.parents if parent.name == "workspace")
DEFAULT_OUTPUT = PROJECT_DIR / "MI355X_MXFP6_PHYSICAL_SCREEN.json"
SOURCE_BINDINGS = PROJECT_DIR / "SOURCE_BINDINGS.json"
RUNNER = PROJECT_DIR / "mi355x_mxfp6_exact_runner.py"
CONFIG = (
    PROJECT_DIR.parent
    / "gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/config.json"
)
FP8_SCREEN = (
    PROJECT_DIR.parent
    / "gemma4_mi355x_fp8_runtime_codesign/MI355X_FP8_RUNTIME_SCREEN.json"
)
ACCELERATOR_INVENTORY = WORKSPACE / "research/factory/data/accelerator_inventory.json"
GPU_PRICES = WORKSPACE / "research/factory/data/gpu_prices.json"

EXPECTED_INPUT_HASHES = {
    CONFIG: "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    FP8_SCREEN: "e1bad18d0d2e0d3e281c3502a3b4a25108d0841ac2da85e5fd0fadebe99cc500",
    ACCELERATOR_INVENTORY: "bcb33ac6814400f6ab79faa7e44c0ced2d6fe2ac5d19dc43f4ee10b12d7ea6b8",
    GPU_PRICES: "a6762a032a128e80a5ab655819c9d989949951f1b55032b746b285ed46c9366f",
}

MODEL = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
HIDDEN = 5376
INTERMEDIATE = 21504
VOCAB = 262144
LAYERS = 60
BASELINE_SECONDS = 0.6000950932112802
HURDLE_SECONDS = 0.625149101968745
BLOCK = 32
DATA_BITS = 6
SCALE_BITS = 8

CONSUMER_SHAPES = (
    {
        "name": "sliding_qkv",
        "layers": 50,
        "k": 5376,
        "n": 16384,
        "logical_outputs": {"q": 8192, "k": 4096, "v": 4096},
    },
    {
        "name": "sliding_o",
        "layers": 50,
        "k": 8192,
        "n": 5376,
        "logical_outputs": {"o": 5376},
    },
    {
        "name": "global_qkv",
        "layers": 10,
        "k": 5376,
        "n": 20480,
        "logical_outputs": {"q": 16384, "k": 2048, "v": 2048},
    },
    {
        "name": "global_o",
        "layers": 10,
        "k": 16384,
        "n": 5376,
        "logical_outputs": {"o": 5376},
    },
    {
        "name": "gate_up",
        "layers": 60,
        "k": 5376,
        "n": 43008,
        "logical_outputs": {"gate": 21504, "up": 21504},
    },
    {
        "name": "down",
        "layers": 60,
        "k": 21504,
        "n": 5376,
        "logical_outputs": {"down": 5376},
    },
)

SOURCE_CONTRACTS = {
    "vllm": {
        "vllm/model_executor/layers/quantization/quark/quark.py": (
            "if isinstance(layer, LinearBase):",
            "return QuarkLinearMethod(self)",
        ),
        "vllm/model_executor/layers/quantization/quark/schemes/quark_ocp_mx.py": (
            "self.emulate = not current_platform.supports_mx() or (",
            'self.input_dtype != "mxfp4" or self.weight_dtype != "mxfp4"',
            "kernels for input_dtype={self.input_dtype}",
            "are not yet integrated",
            "dq_w = self.dequant_func(layer.weight, layer.weight_scale, x.dtype)",
            "return F.linear(qdq_x, dq_w, bias)",
        ),
        "vllm/model_executor/layers/quantization/utils/mxfp6_utils.py": (
            "fake_quantize_fp4_fp6_per_group_with_scale",
            "pack_method = create_pack_method(None, dtype=quant_dtype)",
            "dequantize_fp4_fp6_per_group",
        ),
        "vllm/model_executor/layers/quantization/utils/ocp_mx_utils.py": (
            "OCP_MX_BLOCK_SIZE = 32",
            '"mxfp6_e3m2"',
            '"mxfp6_e2m3"',
        ),
        "vllm/model_executor/models/gemma4.py": (
            "self.qkv_proj = QKVParallelLinear(",
            "self.o_proj = RowParallelLinear(",
            "self.gate_up_proj = MergedColumnParallelLinear(",
            "self.down_proj = RowParallelLinear(",
        ),
    },
    "quark": {
        "quark/torch/utils/pack.py": (
            "class Pack_mxfp6(PackMethod):",
            "class Pack_fp6(PackMethod):",
            "This layout is expected by the mfma_scale_f32_16x16x128_f8f6f4 instruction.",
            "input_shape[-1] = input_shape[-1] // 4 * 3",
        ),
    },
    "rocm_libraries": {
        "projects/hipblaslt/clients/bench/src/client.cpp": (
            "3 = B32E8",
            "Block scaling only allows F8/F6/F4",
            "arg.a_type != HIP_R_6F_E2M3",
            "arg.a_type != HIP_R_6F_E3M2",
        ),
        "projects/hipblaslt/clients/common/include/testing_matmul.hpp": (
            "Swizzle MX scale tensor",
            "K/MX",
            "MXUseRocroller()",
        ),
        "projects/hipblaslt/clients/common/src/mxDataGen.cpp": (
            "DGen::ocp_e3m2_mxfp6",
            "GPU expects the data are packed",
            "packData<DT>",
        ),
        "projects/hipblaslt/library/include/hipblaslt/hipblaslt-types.h": (
            "HIP_R_6F_E3M2_EXT",
        ),
        "projects/hipblaslt/library/src/amd_detail/include/auxiliary.hpp": (
            'return "bf6_r";',
            'value == "bf6_r"',
            "HIP_R_6F_E3M2",
        ),
        "projects/hipblaslt/library/src/amd_detail/rocblaslt/src/rocroller/rocroller_host.cpp": (
            "rocRoller::DataType::BF6",
            "rocRoller::Operations::ScaleMode::Separate",
            "blockSize(prob.scaleAType)",
            "blockSize(prob.scaleBType)",
        ),
        "shared/mxdatagenerator/lib/include/mxDataGenerator/ocp_e3m2_mxfp6.hpp": (
            "ocp_e3m2_mxfp6",
        ),
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def row_by_id(rows: list[dict[str, Any]], identifier: str) -> dict[str, Any]:
    matches = [row for row in rows if row.get("id") == identifier]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {identifier} row, found {len(matches)}")
    return matches[0]


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, path)


def run(command: list[str], *, cwd: Path | None = None, input_text: str | None = None) -> None:
    subprocess.run(command, cwd=cwd, input=input_text, text=True, check=True)


def fetch_repository(
    destination: Path, repository: dict[str, Any]
) -> Path:
    run(["git", "init", "-q", str(destination)])
    run(["git", "-C", str(destination), "remote", "add", "origin", repository["url"]])
    run(
        [
            "git",
            "-C",
            str(destination),
            "-c",
            "protocol.version=2",
            "fetch",
            "--depth",
            "1",
            "--filter=blob:none",
            "origin",
            repository["commit"],
        ]
    )
    run(["git", "-C", str(destination), "sparse-checkout", "init", "--no-cone"])
    run(
        ["git", "-C", str(destination), "sparse-checkout", "set", "--stdin"],
        input_text="\n".join(f"/{path}" for path in repository["files"]) + "\n",
    )
    run(["git", "-C", str(destination), "checkout", "-q", "--detach", "FETCH_HEAD"])
    return destination


def verify_source_bindings(
    bindings: dict[str, Any], temporary_root: Path
) -> tuple[dict[str, Any], dict[str, str]]:
    checks: dict[str, Any] = {}
    texts: dict[str, str] = {}
    for name, repository in bindings["repositories"].items():
        root = fetch_repository(temporary_root / name, repository)
        observed_commit = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
        checks[f"{name}:commit"] = {
            "expected": repository["commit"],
            "observed": observed_commit,
            "pass": observed_commit == repository["commit"],
        }
        for relative, expected_hash in repository["files"].items():
            path = root / relative
            observed_hash = sha256(path) if path.is_file() else None
            checks[f"{name}:{relative}"] = {
                "expected_sha256": expected_hash,
                "observed_sha256": observed_hash,
                "pass": observed_hash == expected_hash,
            }
            if path.is_file():
                texts[f"{name}:{relative}"] = path.read_text(errors="replace")

    for repository, files in SOURCE_CONTRACTS.items():
        for relative, fragments in files.items():
            text = texts.get(f"{repository}:{relative}", "")
            missing = [fragment for fragment in fragments if fragment not in text]
            checks[f"contract:{repository}:{relative}"] = {
                "missing_fragments": missing,
                "pass": not missing,
                "required_fragments": fragments,
            }
    failures = [name for name, check in checks.items() if not check["pass"]]
    if failures:
        raise RuntimeError(f"source binding failed: {failures}")
    return checks, texts


def packed_bytes(elements: int) -> dict[str, int]:
    if elements % BLOCK:
        raise ValueError(f"element count {elements} is not divisible by block {BLOCK}")
    data_bytes = elements * DATA_BITS // 8
    scale_bytes = elements * SCALE_BITS // (BLOCK * 8)
    return {
        "data_bytes": data_bytes,
        "scale_bytes": scale_bytes,
        "total_bytes": data_bytes + scale_bytes,
    }


def shape_accounting() -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    total_parameters = 0
    for shape in CONSUMER_SHAPES:
        parameters = shape["layers"] * shape["k"] * shape["n"]
        total_parameters += parameters
        weight = packed_bytes(parameters)
        phases: list[dict[str, Any]] = []
        for m in (32, 384):
            activation_elements = m * shape["k"]
            activation = packed_bytes(activation_elements)
            phases.append(
                {
                    "activation": activation,
                    "bf16_source_read_bytes": activation_elements * 2,
                    "consumer_command": (
                        "hipblaslt-bench --function matmul "
                        f"-m {m} -n {shape['n']} -k {shape['k']} "
                        "--transA N --transB N --a_type bf6_r --b_type bf6_r "
                        "--c_type bf16_r --d_type bf16_r --compute_type f32_r "
                        "--scaleA 3 --scaleB 3 --use_gpu_timer --verify 1"
                    ),
                    "m": m,
                    "output_bf16_bytes": m * shape["n"] * 2,
                    "packing_padding_bytes": 0,
                    "scale_swizzle_padding_bytes": 0,
                }
            )
        rows.append(
            {
                **shape,
                "all_capacity_preserved": True,
                "k_divisible_by_128": shape["k"] % 128 == 0,
                "n_divisible_by_128": shape["n"] % 128 == 0,
                "parameters": parameters,
                "phases": phases,
                "weight": weight,
                "weight_padding_bytes": 0,
            }
        )
    return rows, total_parameters


def main() -> None:
    bindings = load_json(SOURCE_BINDINGS)
    input_checks = {
        str(path): {
            "expected_sha256": expected,
            "observed_sha256": sha256(path),
            "pass": sha256(path) == expected,
        }
        for path, expected in EXPECTED_INPUT_HASHES.items()
    }
    failed_inputs = [path for path, row in input_checks.items() if not row["pass"]]
    if failed_inputs:
        raise RuntimeError(f"bound input mismatch: {failed_inputs}")

    config = load_json(CONFIG)
    fp8_screen = load_json(FP8_SCREEN)
    inventory = load_json(ACCELERATOR_INVENTORY)
    prices = load_json(GPU_PRICES)
    mi355x_inventory = row_by_id(inventory["accelerators"], "amd-mi355x")
    mi355x_price = row_by_id(prices["accelerators"], "amd-mi355x")

    with tempfile.TemporaryDirectory(prefix="mxfp6-source-", dir=PROJECT_DIR) as temporary:
        source_checks, texts = verify_source_bindings(bindings, Path(temporary))

    assertions = {
        "hidden_size": config["text_config"]["hidden_size"] == HIDDEN,
        "intermediate_size": config["text_config"]["intermediate_size"] == INTERMEDIATE,
        "layers": config["text_config"]["num_hidden_layers"] == LAYERS,
        "vocabulary": config["text_config"]["vocab_size"] == VOCAB,
        "fp8_baseline": (
            fp8_screen["physical_cost_screen"]["conservative_screen_seconds_per_request"]
            == BASELINE_SECONDS
        ),
        "mi355x_hurdle": (
            fp8_screen["physical_cost_screen"]["hurdles"]["production_base_2_60"][
                "hurdle_seconds_per_request"
            ]
            == HURDLE_SECONDS
        ),
        "mi355x_gfx950": mi355x_inventory["architecture_profile_id"] == "amd-cdna4",
        "planning_rate": mi355x_price["production_planning_usd_per_gpu_hour"] == 2.6,
    }
    if not all(assertions.values()):
        raise RuntimeError(f"geometry/economic assertion failed: {assertions}")

    shapes, total_parameters = shape_accounting()
    if total_parameters != 29396828160:
        raise RuntimeError(f"unexpected transformer parameter count: {total_parameters}")
    total_mxfp6_weight = packed_bytes(total_parameters)
    baseline_transformer_seconds = sum(
        row["seconds_per_request"]
        for row in fp8_screen["physical_cost_screen"]["line_items"]
        if row["name"]
        in {
            "prefill_fp8_transformer_linears",
            "ordinary_decode_fp8_transformer_linears",
            "target_verification_m384_transformer",
        }
    )
    fixed_non_transformer_seconds = BASELINE_SECONDS - baseline_transformer_seconds

    vllm_ocp = texts[
        "vllm:vllm/model_executor/layers/quantization/quark/schemes/quark_ocp_mx.py"
    ]
    current_vllm_emulates = all(
        fragment in vllm_ocp
        for fragment in (
            "self.emulate = not current_platform.supports_mx() or (",
            'self.input_dtype != "mxfp4" or self.weight_dtype != "mxfp4"',
            "return F.linear(qdq_x, dq_w, bias)",
        )
    )
    direct_consumer_source_complete = all(
        source_checks[key]["pass"]
        for key in source_checks
        if key.startswith("contract:rocm_libraries:")
    )
    producer_layout_source_complete = all(
        source_checks[key]["pass"]
        for key in source_checks
        if key.startswith("contract:quark:")
    )

    result = {
        "classification": "typed_none",
        "decision": {
            "direct_hipblaslt_component_source_complete": direct_consumer_source_complete,
            "exact_shape_static_contract_pass": all(
                row["k_divisible_by_128"]
                and row["n_divisible_by_128"]
                and all(phase["packing_padding_bytes"] == 0 for phase in row["phases"])
                for row in shapes
            ),
            "first_decisive_gate": "current_dense_runtime_native_producer_consumer",
            "interpretation": (
                "Current vLLM recognizes packed MXFP6 weights but forces every dense "
                "MXFP6 activation/weight combination through Quark dequantization, "
                "activation QDQ emulation, and high-precision F.linear. ROCm's maintained "
                "hipBLASLt/RocRoller source has a real E3M2 block-scale consumer, but no "
                "bound current vLLM activation packer or dispatch reaches it. The supplied "
                "exact-shape runner isolates that later consumer, but its input generation "
                "is outside the timed region and no target-MI355X sample exists in scope. "
                "Nominal 6-bit bytes therefore cannot be converted into a strict all-in "
                "whole-request improvement."
            ),
            "producer_layout_source_complete": producer_layout_source_complete,
            "strict_improvement_bound_pass": False,
            "target_mi355x_validation_pass": False,
            "typed_none_reason": (
                "native_mxfp6_activation_producer_and_runtime_dispatch_missing_"
                "with_no_scope_matched_target_timing"
            ),
            "vllm_no_fallback_pass": not current_vllm_emulates,
        },
        "evidence": {
            "geometry_and_economic_assertions": assertions,
            "input_checks": input_checks,
            "source_checks": source_checks,
            "source_observed_at_utc": bindings["observed_at_utc"],
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "identity": {
            "calculator": {
                "path": str(Path(__file__).resolve()),
                "sha256": sha256(Path(__file__)),
            },
            "model": MODEL,
            "revision": REVISION,
            "runner": {"path": str(RUNNER), "sha256": sha256(RUNNER)},
            "source_bindings": {
                "path": str(SOURCE_BINDINGS),
                "sha256": sha256(SOURCE_BINDINGS),
            },
        },
        "physical_accounting": {
            "baseline_fp8_seconds_per_request": BASELINE_SECONDS,
            "baseline_transformer_linear_seconds_per_request": baseline_transformer_seconds,
            "candidate_mxfp6_seconds_per_request": None,
            "candidate_transformer_linear_seconds_per_request": None,
            "economic_hurdle_seconds_per_request": HURDLE_SECONDS,
            "fixed_non_transformer_seconds_per_request": fixed_non_transformer_seconds,
            "reason_candidate_time_is_null": (
                "No target gfx950 timing includes dynamic MXFP6 activation packing, "
                "E8M0 scale production/layout, hipBLASLt GEMM, BF16 output, dispatch, "
                "and fallback for these exact shapes. Source support and nominal bytes "
                "are explicitly inadmissible timing proxies."
            ),
            "strict_improvement_transformer_budget_seconds_per_request": (
                baseline_transformer_seconds
            ),
            "transformer_parameters": total_parameters,
            "weight_representation": {
                **total_mxfp6_weight,
                "block_elements": BLOCK,
                "data_bits_per_element": DATA_BITS,
                "e8m0_scale_bits_per_block": SCALE_BITS,
                "fp8_baseline_data_bytes": total_parameters,
                "nominal_byte_reduction_fraction_not_timing_credit": float(
                    Fraction(7, 32)
                ),
                "padding_bytes": 0,
            },
        },
        "prohibited_actions_respected": [
            "no checkpoint download",
            "no GPU or shared-bench claim",
            "no provider contact or mutation",
            "no paid API",
            "zero spend",
            "preserved MI355X FP8 lifecycle unchanged",
            "FP8 KV attention unchanged",
            "BF16 tied head unchanged",
            "all 60 layers, widths, parameters, tokens, and vocabulary capacity preserved",
        ],
        "representation": {
            "activation": "OCP MXFP6 E3M2 with one E8M0 scale per 32 values",
            "accumulation": "FP32",
            "hipblaslt_cli_dtype": "bf6_r",
            "output": "BF16",
            "weight": "OCP MXFP6 E3M2 with one E8M0 scale per 32 values",
        },
        "schema_version": 1,
        "shapes": shapes,
        "target_discriminator": {
            "coverage": "12 exact consumer calls: six fused transformer linears at M32 and M384",
            "current_execution": "not_run_no_authorized_mi355x_bench",
            "required_evidence": (
                "finite gfx950 warm timing and numerical result for every shape, plus "
                "a timed native dynamic-activation producer and proof of no fallback"
            ),
            "runner": str(RUNNER),
            "runner_limit": (
                "The runner exercises the official hipBLASLt MX data generator and "
                "RocRoller consumer, but hipblasLt-bench prepares packed inputs before "
                "steady-state timing. It cannot by itself charge production activation "
                "packing or prove vLLM dispatch."
            ),
        },
        "terminal": "typed_none",
        "typed_none": {
            "closed_path": (
                "current vLLM dense Quark MXFP6 emulation plus untimed direct "
                "hipBLASLt component"
            ),
            "first_missing_evidence": (
                "one native dynamic E3M2 activation producer feeding the maintained "
                "hipBLASLt/RocRoller consumer in the current dense runtime, with exact "
                "gfx950 all-in timings"
            ),
            "reopen_condition": (
                "current maintained source binds a native packed activation producer "
                "and dense dispatch, and a zero-fallback MI355X component sample charges "
                "producer, scales, layout, padding, GEMM, output, and dispatch"
            ),
        },
    }
    atomic_json(DEFAULT_OUTPUT, result)


if __name__ == "__main__":
    main()
