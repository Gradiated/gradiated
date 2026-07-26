from __future__ import annotations

import ast
import csv
import hashlib
import json
import math
import subprocess
from pathlib import Path

from bridge_contract import (
    BASELINE_SECONDS_PER_REQUEST,
    BASELINE_TRANSFORMER_SECONDS,
    CONVERSION_AMORTIZATION_HURDLE_SECONDS,
    CONVERSION_AMORTIZATION_REQUESTS,
    LINEAR_SHAPES,
    PHASES,
    TARGET_SECONDS_PER_REQUEST,
    candidate_runtime_budget_seconds,
    candidate_transformer_budget_seconds,
    per_shape_timing_hurdles,
    phase_runtime_hurdles,
    total_transformer_parameters,
    unchanged_seconds_per_request,
)


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
BASELINE_PROJECT = LAB / "projects" / "gemma4_mi355x_fp8_runtime_codesign"
VLLM = PROJECT / "inputs" / "pinned" / "vllm"
AITER = PROJECT / "inputs" / "pinned" / "aiter"
PATCH = PROJECT / "patches" / "vllm_aiter_ptpc_bridge.patch"
CPU_OUTPUT = PROJECT / "CPU_FIXTURE_RESULTS.json"
SOURCE_OUTPUT = PROJECT / "SOURCE_BINDINGS.json"
SCREEN_OUTPUT = PROJECT / "MI355X_AITER_FP8_LINEAR_BRIDGE_SCREEN.json"
VLLM_COMMIT = "0164022c907014a27e81c514cd4dff6091904c2b"
AITER_COMMIT = "6c48c5fa0e7c299adcf1987c8f4817720ceab311"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def require_fragments(path: Path, fragments: list[str]) -> dict:
    source = path.read_text()
    ast.parse(source)
    missing = [fragment for fragment in fragments if fragment not in source]
    return {
        "path": str(path.relative_to(PROJECT)),
        "sha256": sha256_file(path),
        "missing_fragments": missing,
        "pass": not missing,
    }


def source_checks() -> dict:
    checks = {
        "fp8_config_dispatch": require_fragments(
            VLLM / "vllm/model_executor/layers/quantization/fp8.py",
            [
                "_use_aiter_hipbmm_ptpc_online_linear",
                "on_gfx950() and rocm_aiter_ops.is_linear_hipbmm_enabled()",
                "AiterFp8PtpcOnlineLinearMethod",
                "return online_method",
            ],
        ),
        "online_ptpc_producer": require_fragments(
            VLLM / "vllm/model_executor/layers/quantization/online/fp8.py",
            [
                "class Fp8PtpcOnlineLinearMethod",
                "weight_quant_key = kFp8StaticChannelSym",
                "activation_quant_key = kFp8DynamicTokenSym",
                "use_per_token_if_dynamic=True",
                "class AiterFp8PtpcOnlineLinearMethod",
                "AiterHipbMMPerTokenFp8ScaledMMLinearKernel",
                "requires the hipb_mm FP8 consumer",
            ],
        ),
        "aiter_consumer": require_fragments(
            VLLM / "vllm/model_executor/kernels/linear/scaled_mm/aiter.py",
            [
                "class AiterHipbMMPerTokenFp8ScaledMMLinearKernel",
                "requires per token activation scales and per channel weight scales.",
                "shuffled_w = rocm_aiter_ops.shuffle_weight(w.t().contiguous())",
                "rocm_aiter_ops.hipb_mm_fp8(A, B, As, Bs, bias, out_dtype)",
            ],
        ),
        "registered_consumer": require_fragments(
            VLLM / "vllm/_aiter_ops.py",
            [
                "def _rocm_aiter_hipb_mm_fp8_impl",
                "from aiter import hipb_mm",
                "scaleA=As",
                "scaleB=Bs",
                "bpreshuffle=True",
                'op_name="rocm_aiter_hipb_mm_fp8"',
            ],
        ),
        "maintained_aiter_op": require_fragments(
            AITER / "aiter/ops/gradlib.py",
            [
                '@compile_ops("module_hipbsolgemm", gen_fake=gen_hipb_mm_fake_tensor)',
                "def hipb_mm(",
                "scaleA: Optional[torch.Tensor]",
                "scaleB: Optional[torch.Tensor]",
                "bpreshuffle: Optional[bool]",
            ],
        ),
        "gemma_forward": require_fragments(
            VLLM / "vllm/model_executor/models/gemma4.py",
            [
                "self.qkv_proj = QKVParallelLinear(",
                "self.o_proj = RowParallelLinear(",
                "self.gate_up_proj = MergedColumnParallelLinear(",
                "self.down_proj = RowParallelLinear(",
                "quant_config=quant_config",
                "self.lm_head = self.lm_head.tie_weights(self.model.embed_tokens)",
            ],
        ),
    }
    return {
        "checks": checks,
        "pass": all(check["pass"] for check in checks.values()),
    }


def exact_shape_checks() -> dict:
    rows = []
    for phase_name, phase in PHASES.items():
        for shape in LINEAR_SHAPES:
            row = {
                "phase": phase_name,
                "shape": shape.name,
                "checkpoint_weight_layout": [shape.n, shape.k],
                "producer_qweight_layout": [shape.k, shape.n],
                "producer_weight_scale_layout": [shape.n, 1],
                "consumer_bpreshuffle_view_layout": [shape.k, shape.n],
                "consumer_weight_scale_layout": [1, shape.n],
                "activation_layout": [phase["m"], shape.k],
                "activation_scale_layout": [phase["m"], 1],
                "output_layout": [phase["m"], shape.n],
                "n_divisible_by_16": shape.n % 16 == 0,
                "k_divisible_by_16": shape.k % 16 == 0,
                "consumer_can_implement": (
                    shape.n >= 16
                    and shape.n % 16 == 0
                    and shape.k % 16 == 0
                ),
            }
            rows.append(row)
    return {
        "rows": rows,
        "pass": len(rows) == 18
        and all(row["consumer_can_implement"] for row in rows),
    }


def numerical_checks() -> dict:
    import torch

    fp8_dtype = torch.float8_e4m3fn
    fp8_max = torch.finfo(fp8_dtype).max
    rows = []
    for shape_index, shape in enumerate(LINEAR_SHAPES):
        for phase_index, (phase_name, phase) in enumerate(PHASES.items()):
            m = min(4, phase["m"])
            generator = torch.Generator().manual_seed(
                12_000 + shape_index * 101 + phase_index
            )
            x = torch.randn((m, shape.k), generator=generator, dtype=torch.float32)
            weight = torch.randn(
                (16, shape.k), generator=generator, dtype=torch.float32
            )
            x[0].zero_()
            weight[0].zero_()
            if m > 1:
                x[1, 0] = 64.0
                weight[1, 0] = -64.0

            x_scale = (
                x.abs().amax(dim=1, keepdim=True).clamp_min(1e-12) / fp8_max
            )
            weight_scale = (
                weight.abs().amax(dim=1, keepdim=True).clamp_min(1e-12)
                / fp8_max
            )
            x_q = (x / x_scale).clamp(-fp8_max, fp8_max).to(fp8_dtype)
            weight_q = (
                (weight / weight_scale).clamp(-fp8_max, fp8_max).to(fp8_dtype)
            )
            candidate = (x_q.float() * x_scale) @ (
                weight_q.float() * weight_scale
            ).t()
            reference = x @ weight.t()
            difference = candidate - reference
            reference_norm = torch.linalg.vector_norm(reference)
            relative_l2 = (
                torch.linalg.vector_norm(difference) / reference_norm.clamp_min(1e-12)
            ).item()
            cosine = torch.nn.functional.cosine_similarity(
                candidate.flatten(), reference.flatten(), dim=0, eps=1e-12
            ).item()
            finite = bool(torch.isfinite(candidate).all().item())
            zero_row_exact = bool(torch.count_nonzero(candidate[0]).item() == 0)
            rows.append(
                {
                    "phase": phase_name,
                    "shape": shape.name,
                    "tested_activation_shape": [m, shape.k],
                    "tested_weight_shape": [16, shape.k],
                    "activation_scale_shape": list(x_scale.shape),
                    "weight_scale_shape": list(weight_scale.shape),
                    "relative_l2": relative_l2,
                    "cosine": cosine,
                    "max_abs_error": difference.abs().max().item(),
                    "finite": finite,
                    "zero_row_exact": zero_row_exact,
                    "pass": (
                        finite
                        and zero_row_exact
                        and relative_l2 <= 0.02
                        and cosine >= 0.995
                    ),
                }
            )
    return {
        "dtype": str(fp8_dtype),
        "oracle": "FP32 accumulation of BF16-representable producer inputs",
        "relative_l2_max": 0.02,
        "cosine_min": 0.995,
        "rows": rows,
        "pass": all(row["pass"] for row in rows),
    }


def tuned_direct_consumer_check() -> dict:
    exact = {(shape.n, shape.k) for shape in LINEAR_SHAPES}
    files = [
        AITER / "aiter/configs/a8w8_bpreshuffle_tuned_gemm.csv",
        AITER / "aiter/configs/a8w8_tuned_gemm.csv",
    ]
    exact_rows = []
    for path in files:
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                if (
                    row.get("gfx") == "gfx950"
                    and row.get("q_dtype_w") == "torch.float8_e4m3fn"
                    and (int(row["N"]), int(row["K"])) in exact
                ):
                    exact_rows.append({"file": path.name, **row})
    return {
        "files": [
            {
                "path": str(path.relative_to(PROJECT)),
                "sha256": sha256_file(path),
            }
            for path in files
        ],
        "exact_gemma_rows": exact_rows,
        "selected_consumer": "AiterHipbMMPerTokenFp8ScaledMMLinearKernel",
        "interpretation": (
            "The two tuned direct AITER rowwise/preshuffle selectors have no "
            "exact Gemma N,K row. The preregistered generic maintained hipb_mm "
            "consumer is therefore selected once; no kernel or layout sweep occurs."
        ),
        "pass": not exact_rows,
    }


def main() -> None:
    baseline = json.loads(
        (BASELINE_PROJECT / "MI355X_FP8_RUNTIME_SCREEN.json").read_text()
    )
    source_bindings = json.loads(
        (BASELINE_PROJECT / "SOURCE_BINDINGS.json").read_text()
    )
    commits = {
        "vllm": git("rev-parse", "HEAD", cwd=VLLM),
        "aiter": git("rev-parse", "HEAD", cwd=AITER),
    }
    patch_applied = (
        subprocess.run(
            [
                "git",
                "-C",
                str(VLLM),
                "apply",
                "--unidiff-zero",
                "--reverse",
                "--check",
                str(PATCH),
            ],
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )
    if CPU_OUTPUT.exists():
        cpu_artifact = json.loads(CPU_OUTPUT.read_text())
        reusable_cpu_artifact = (
            cpu_artifact.get("pass") is True
            and cpu_artifact["identity"]["commits"] == commits
            and cpu_artifact["identity"]["patch_applied"] is True
            and cpu_artifact["source"]["checks"]["fp8_config_dispatch"]["sha256"]
            == sha256_file(
                VLLM / "vllm/model_executor/layers/quantization/fp8.py"
            )
            and cpu_artifact["source"]["checks"]["online_ptpc_producer"]["sha256"]
            == sha256_file(
                VLLM
                / "vllm/model_executor/layers/quantization/online/fp8.py"
            )
        )
    else:
        reusable_cpu_artifact = False
    if not reusable_cpu_artifact:
        source = source_checks()
        shapes = exact_shape_checks()
        numerical = numerical_checks()
        tuned = tuned_direct_consumer_check()
        identity_pass = (
            commits == {"vllm": VLLM_COMMIT, "aiter": AITER_COMMIT}
            and patch_applied
            and source_bindings["repositories"]["vllm"]["commit"] == VLLM_COMMIT
            and source_bindings["repositories"]["aiter"]["commit"] == AITER_COMMIT
            and math.isclose(
                baseline["physical_cost_screen"][
                    "conservative_screen_seconds_per_request"
                ],
                BASELINE_SECONDS_PER_REQUEST,
                rel_tol=0.0,
                abs_tol=1e-15,
            )
        )
        cpu_pass = (
            identity_pass
            and source["pass"]
            and shapes["pass"]
            and numerical["pass"]
        )
        cpu_artifact = {
            "schema_version": 1,
            "classification": "pass" if cpu_pass else "fail",
            "identity": {
                "commits": commits,
                "expected_commits": {
                    "vllm": VLLM_COMMIT,
                    "aiter": AITER_COMMIT,
                },
                "patch_applied": patch_applied,
                "patch_sha256": sha256_file(PATCH),
                "pass": identity_pass,
            },
            "source": source,
            "exact_shapes": shapes,
            "numerical": numerical,
            "consumer_choice": tuned,
            "pass": cpu_pass,
        }
        atomic_json(CPU_OUTPUT, cpu_artifact)
    cpu_pass = cpu_artifact["pass"]
    changed_vllm_files = [
        "vllm/model_executor/layers/quantization/fp8.py",
        "vllm/model_executor/layers/quantization/online/fp8.py",
    ]
    bound_consumer_files = [
        "vllm/model_executor/kernels/linear/scaled_mm/aiter.py",
        "vllm/_aiter_ops.py",
        "vllm/model_executor/models/gemma4.py",
    ]
    aiter_consumer_files = [
        "aiter/ops/gradlib.py",
        "aiter/configs/a8w8_bpreshuffle_tuned_gemm.csv",
        "aiter/configs/a8w8_tuned_gemm.csv",
    ]
    source_artifact = {
        "schema_version": 1,
        "repositories": {
            "vllm": {
                "url": "https://github.com/vllm-project/vllm.git",
                "commit": VLLM_COMMIT,
                "changed_files": {
                    path: {
                        "original_sha256": sha256_bytes(
                            subprocess.check_output(
                                ["git", "-C", str(VLLM), "show", f"HEAD:{path}"]
                            )
                        ),
                        "patched_sha256": sha256_file(VLLM / path),
                    }
                    for path in changed_vllm_files
                },
                "bound_consumer_files": {
                    path: sha256_file(VLLM / path)
                    for path in bound_consumer_files
                },
            },
            "aiter": {
                "url": "https://github.com/ROCm/aiter.git",
                "commit": AITER_COMMIT,
                "bound_consumer_files": {
                    path: sha256_file(AITER / path)
                    for path in aiter_consumer_files
                },
            },
        },
        "patch": {
            "path": str(PATCH.relative_to(PROJECT)),
            "sha256": sha256_file(PATCH),
            "applies_to_vllm_commit": VLLM_COMMIT,
        },
        "programs": {
            path.name: sha256_file(path)
            for path in [
                PROJECT / "bridge_contract.py",
                PROJECT / "run_cpu_bridge_screen.py",
                PROJECT / "mi355x_aiter_fp8_linear_bridge_bench.py",
            ]
        },
        "inherited_source_bindings": {
            "path": "../gemma4_mi355x_fp8_runtime_codesign/SOURCE_BINDINGS.json",
            "sha256": sha256_file(
                BASELINE_PROJECT / "SOURCE_BINDINGS.json"
            ),
        },
    }
    atomic_json(SOURCE_OUTPUT, source_artifact)

    output_channels = sum(shape.n * shape.layers for shape in LINEAR_SHAPES)
    per_channel_scale_bytes = output_channels * 4
    scalar_scale_bytes = sum(shape.layers for shape in LINEAR_SHAPES) * 4
    transformer_fp8_bytes = total_transformer_parameters()
    runtime_budget = candidate_runtime_budget_seconds()
    transformer_budget = candidate_transformer_budget_seconds()
    classification = (
        "source_complete_measurement_candidate" if cpu_pass else "none"
    )
    screen = {
        "schema_version": 1,
        "classification": classification,
        "terminal": classification,
        "decision": {
            "result": classification,
            "source_complete": cpu_pass,
            "target_mi355x_measured": False,
            "interpretation": (
                "The exact pinned Gemma forward now selects one fail-closed "
                "gfx950 PTPC producer-to-AITER-hipb_mm consumer bridge. CPU "
                "source/layout/scale/numerical gates pass. This is the "
                "contracted source-complete measurement candidate, not a "
                "target-throughput claim; the finite runner must keep all "
                "measured candidate costs within the bound below."
                if cpu_pass
                else "A required source, shape, layout, or numerical gate failed."
            ),
        },
        "identity": {
            "model": "google/gemma-4-31B-it",
            "model_revision": baseline["scope"]["revision"],
            "checkpoint_copied_or_downloaded": False,
            "vllm_commit": VLLM_COMMIT,
            "aiter_commit": AITER_COMMIT,
            "patch": {
                "path": str(PATCH.relative_to(PROJECT)),
                "sha256": sha256_file(PATCH),
            },
            "cpu_fixture": {
                "path": str(CPU_OUTPUT.relative_to(PROJECT)),
                "sha256": sha256_file(CPU_OUTPUT),
            },
            "source_bindings": {
                "path": str(SOURCE_OUTPUT.relative_to(PROJECT)),
                "sha256": sha256_file(SOURCE_OUTPUT),
            },
            "baseline_screen": {
                "path": "../gemma4_mi355x_fp8_runtime_codesign/MI355X_FP8_RUNTIME_SCREEN.json",
                "sha256": sha256_file(
                    BASELINE_PROJECT / "MI355X_FP8_RUNTIME_SCREEN.json"
                ),
            },
        },
        "producer_consumer": {
            "selection": (
                "Fp8Config.get_quant_method -> "
                "AiterFp8PtpcOnlineLinearMethod"
            ),
            "weight_producer": (
                "Fp8PtpcOnlineLinearMethod.process_weights_after_loading -> "
                "ops.scaled_fp8_quant(use_per_token_if_dynamic=True)"
            ),
            "activation_producer": (
                "FP8ScaledMMLinearKernel.apply_weights -> "
                "QuantFP8(dynamic, GroupShape.PER_TOKEN)"
            ),
            "consumer": (
                "AiterHipbMMPerTokenFp8ScaledMMLinearKernel.apply_scaled_mm -> "
                "rocm_aiter_ops.hipb_mm_fp8 -> aiter.hipb_mm(bpreshuffle=True)"
            ),
            "weight_dtype": "torch.float8_e4m3fn",
            "activation_dtype": "torch.float8_e4m3fn",
            "output_dtype": "torch.bfloat16",
            "weight_scale": "static FP32 per output channel [N,1], then [1,N]",
            "activation_scale": "dynamic FP32 per token [M,1]",
            "weight_layout": (
                "BF16 [N,K] -> FP8 [K,N] -> shuffle([N,K]).T noncontiguous "
                "bpreshuffle view [K,N]"
            ),
            "fallback_policy": "fail closed during layer creation; any fallback is none",
            "tied_embedding_and_head": "unchanged BF16 tied weight",
        },
        "geometry": {
            "phases": PHASES,
            "linear_shapes": [shape.as_dict() for shape in LINEAR_SHAPES],
            "executed_transformer_linear_parameters": total_transformer_parameters(),
            "all_layers_parameters_requests_tokens_and_rows_preserved": True,
        },
        "physical_hypothesis": {
            "mechanism": (
                "The current per-tensor producer rejects all AITER PTPC "
                "consumers. Per-output-channel load-time weights plus dynamic "
                "per-token activations make the generic gfx950 hipb_mm path "
                "reachable; preshuffling removes weight-layout work from each "
                "forward. Only a 2.486% reduction in the inherited transformer "
                "linear account is needed."
            ),
            "predicted_resource_movement": (
                "Higher effective matrix/HBM utilization at M32 and fewer "
                "runtime layout operations; prefill and M384 remain separately timed."
            ),
            "falsifier": (
                "Any exact shape fallback, relative-L2 >0.02, cosine <0.995, "
                "nonfinite output, or fully charged request time above the target."
            ),
        },
        "memory": {
            "transformer_fp8_weight_shadow_bytes": transformer_fp8_bytes,
            "per_channel_scale_bytes": per_channel_scale_bytes,
            "replaced_scalar_scale_bytes": scalar_scale_bytes,
            "incremental_scale_bytes": (
                per_channel_scale_bytes - scalar_scale_bytes
            ),
            "steady_transformer_shadow_plus_scales_bytes": (
                transformer_fp8_bytes + per_channel_scale_bytes
            ),
            "preshuffle_extra_steady_bytes": 0,
            "preshuffle_rule": (
                "The shuffled parameter replaces the unshuffled FP8 parameter; "
                "the finite runner measures conversion peak and rejects OOM."
            ),
            "baseline_two_x_runtime_fragmentation_envelope_bytes": baseline[
                "memory_and_topology"
            ]["conservative_two_x_runtime_fragmentation_envelope_bytes"],
            "mi355x_decimal_capacity_bytes": baseline["memory_and_topology"][
                "mi355x_decimal_capacity_bytes"
            ],
            "fits_in_inherited_two_x_envelope": (
                baseline["memory_and_topology"][
                    "conservative_two_x_runtime_fragmentation_envelope_bytes"
                ]
                + 2 * (per_channel_scale_bytes - scalar_scale_bytes)
                <= baseline["memory_and_topology"]["mi355x_decimal_capacity_bytes"]
            ),
        },
        "full_request_accounting": {
            "preserved_baseline_seconds_per_request": BASELINE_SECONDS_PER_REQUEST,
            "preserved_baseline_transformer_seconds_per_request": sum(
                BASELINE_TRANSFORMER_SECONDS.values()
            ),
            "all_unchanged_components_seconds_per_request": (
                unchanged_seconds_per_request()
            ),
            "target_seconds_per_request": TARGET_SECONDS_PER_REQUEST,
            "candidate_transformer_total_hurdle_seconds_per_request": (
                transformer_budget
            ),
            "candidate_runtime_apply_hurdle_seconds_per_request": runtime_budget,
            "load_conversion_amortization_hurdle_seconds_per_request": (
                CONVERSION_AMORTIZATION_HURDLE_SECONDS
            ),
            "load_conversion_amortization_requests": (
                CONVERSION_AMORTIZATION_REQUESTS
            ),
            "phase_runtime_hurdles_seconds_per_request": phase_runtime_hurdles(),
            "per_shape_p95_hurdles": per_shape_timing_hurdles(),
            "acceptance_formula": (
                "unchanged + sum(candidate apply p95 * layers * phase "
                "request_multiplier) + (all exact layer conversion seconds + "
                "AITER initialization seconds)/10000 <= target"
            ),
            "candidate_ceiling_seconds_per_request": TARGET_SECONDS_PER_REQUEST,
            "unmeasured_performance_credit_seconds": 0.0,
        },
        "cost_charge_map": {
            "weight_conversion": "measured by the target runner and amortized over 10000 requests",
            "preshuffle_and_layout": "inside measured load conversion",
            "weight_memory_and_scales": "explicit byte account above plus target peak allocation",
            "dynamic_activation_quant_and_reduction": "inside every timed method.apply",
            "consumer_and_output_write": "inside every timed method.apply",
            "synchronization": "per-sample device event synchronization",
            "launch": (
                "inside method.apply measurement while the inherited full "
                "0.039301875 s/request launch reserve is also retained"
            ),
            "fallback": "invalidates the candidate; zero fallback credit",
            "service": "inherited 0.04 s/request reserve retained in unchanged components",
            "all_other_components": "retained byte-for-byte from the baseline screen",
        },
        "target_measurement_program": {
            "path": "mi355x_aiter_fp8_linear_bridge_bench.py",
            "hardware": "one AMD MI355X / gfx950",
            "required_environment": {
                "VLLM_ROCM_USE_AITER": "1",
                "VLLM_ROCM_USE_AITER_LINEAR": "1",
                "VLLM_ROCM_USE_AITER_LINEAR_HIPBMM": "1",
            },
            "command": (
                "python3 mi355x_aiter_fp8_linear_bridge_bench.py "
                "--vllm-root /absolute/patched/vllm "
                "--output /absolute/MI355X_AITER_FP8_LINEAR_BRIDGE_MEASUREMENT.json"
            ),
            "finite_work": {
                "smoke_shapes": 1,
                "exact_shapes": len(LINEAR_SHAPES),
                "phases_per_shape": len(PHASES),
                "warmups_per_arm": 3,
                "timed_samples_per_arm": 20,
                "arms": ["current_per_tensor_control", "aiter_ptpc_candidate"],
            },
            "candidate_result_rule": (
                "source_complete_measurement_candidate only when the runner "
                "emits classification=pass; otherwise typed none"
            ),
        },
        "tests": [
            "git -C inputs/pinned/vllm apply --unidiff-zero --check patches/vllm_aiter_ptpc_bridge.patch",
            "python3 -m py_compile patched fp8.py patched online/fp8.py",
            "PYTHONPATH=<cached torch> python3 run_cpu_bridge_screen.py",
        ],
        "evidence_boundary": (
            "Source-backed and CPU-executed integration candidate. No MI355X, "
            "provider, checkpoint, endpoint, quality, or deployment measurement "
            "was used or claimed."
        ),
        "prohibited_actions_respected": [
            "zero provider spend",
            "no GPU claim",
            "no provider contact or mutation",
            "no checkpoint copy or download",
            "no bridge, scale, layout, kernel, or format sweep",
            "preserved baseline falsifier unmodified",
        ],
    }
    atomic_json(SCREEN_OUTPUT, screen)
    if not cpu_pass:
        raise SystemExit("CPU/source bridge gate failed")


if __name__ == "__main__":
    main()
