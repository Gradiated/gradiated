#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import pathlib
import random


SOURCE_COMMIT = "127b9e3283f7c2a43234b852ff5c9f1796d53624"
EXPECTED_SOURCE_SHA256 = {
    "python/sglang/srt/layers/gemma4_fused_ops.py": "169a498ad0326b55802e7382ce66102317fb3d66808d57d3daf601f741497c53",
    "python/sglang/srt/models/gemma4_causal.py": "683895c5140c920199713a18885006d17a1b1b3dda0ba01c797af02d09885856",
    "python/sglang/srt/layers/rotary_embedding/base.py": "50b801ec65a3ab07eeb5fc159f462d509a84b9875d1a472f4ad01758dec3d8a8",
    "python/sglang/srt/layers/rotary_embedding/factory.py": "943b2f75edb523999540f1018fbfed06d21a8309847d5ad72e59a50ea9a92821",
    "python/sglang/srt/layers/rotary_embedding/rope_variant.py": "5ae4410dcd9687de7f2a7bebf352a10e2185b0222d8ad850724f4cf54fa4cf9b",
    "sgl-kernel/csrc/elementwise/pos_enc.cu": "bcb566f16d4b280ad970929cf588b887670cf9412cb44c45ca6ec6487c123017",
}
BOUND_EVIDENCE = {
    "checkpoint_config": {
        "relative_path": "../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint/config.json",
        "sha256": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    },
    "profile_summary": {
        "relative_path": "../gemma4_h200_critical_path_profile/PROFILE_SUMMARY.json",
        "sha256": "1979d50e96571982fe43d71071b34e3cad47602f2fd8dc0b94e722dd4043c779",
    },
    "comparator": {
        "relative_path": "../gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json",
        "sha256": "1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3",
    },
}


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def normalize(values: list[float], weight: list[float] | None, eps: float) -> list[float]:
    inverse_rms = 1.0 / math.sqrt(sum(value * value for value in values) / len(values) + eps)
    if weight is None:
        return [value * inverse_rms for value in values]
    return [value * inverse_rms * scale for value, scale in zip(values, weight, strict=True)]


def rope_cache(position: int, head_dim: int, theta: float, rope_angles: int) -> tuple[list[float], list[float]]:
    half = head_dim // 2
    inverse_frequencies = [
        theta ** (-(2 * index) / head_dim) if index < rope_angles else 0.0
        for index in range(half)
    ]
    angles = [position * frequency for frequency in inverse_frequencies]
    return [math.cos(angle) for angle in angles], [math.sin(angle) for angle in angles]


def rotate(values: list[float], cosine: list[float], sine: list[float]) -> list[float]:
    half = len(values) // 2
    first = values[:half]
    second = values[half:]
    return [
        *(x * cos - y * sin for x, y, cos, sin in zip(first, second, cosine, sine, strict=True)),
        *(y * cos + x * sin for x, y, cos, sin in zip(first, second, cosine, sine, strict=True)),
    ]


def sequential_reference(
    values: list[float],
    weight: list[float] | None,
    eps: float,
    cosine: list[float],
    sine: list[float],
    apply_rope: bool,
) -> list[float]:
    normalized = normalize(values, weight, eps)
    return rotate(normalized, cosine, sine) if apply_rope else normalized


def fused_reference(
    values: list[float],
    weight: list[float] | None,
    eps: float,
    cosine: list[float],
    sine: list[float],
    apply_rope: bool,
) -> list[float]:
    half = len(values) // 2
    inverse_rms = 1.0 / math.sqrt(sum(value * value for value in values) / len(values) + eps)
    output0: list[float] = []
    output1: list[float] = []
    for index in range(half):
        scale0 = 1.0 if weight is None else weight[index]
        scale1 = 1.0 if weight is None else weight[half + index]
        first = values[index] * inverse_rms * scale0
        second = values[half + index] * inverse_rms * scale1
        if apply_rope:
            output0.append(first * cosine[index] - second * sine[index])
            output1.append(second * cosine[index] + first * sine[index])
        else:
            output0.append(first)
            output1.append(second)
    return output0 + output1


def oracle_case(name: str, head_dim: int, theta: float, rope_angles: int) -> dict[str, object]:
    generator = random.Random(20260720 + head_dim + rope_angles)
    cosine, sine = rope_cache(4570, head_dim, theta, rope_angles)
    maximum_error = 0.0
    rows: list[dict[str, object]] = []
    for kind in ("q", "k", "v"):
        values = [generator.uniform(-0.2, 0.2) for _ in range(head_dim)]
        weight = None if kind == "v" else [1.0 + generator.uniform(-0.02, 0.02) for _ in range(head_dim)]
        expected = sequential_reference(values, weight, 1e-6, cosine, sine, kind != "v")
        actual = fused_reference(values, weight, 1e-6, cosine, sine, kind != "v")
        error = max(abs(left - right) for left, right in zip(expected, actual, strict=True))
        maximum_error = max(maximum_error, error)
        rows.append({"kind": kind, "maximum_absolute_error": error})
    return {
        "name": name,
        "head_dim": head_dim,
        "rope_angles_per_half": rope_angles,
        "rows": rows,
        "maximum_absolute_error": maximum_error,
        "pass": maximum_error <= 1e-12,
    }


def function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise ValueError(f"missing function {name}")


def source_audit(program_path: pathlib.Path) -> dict[str, object]:
    source = program_path.read_text()
    tree = ast.parse(source)
    wrapper = function_node(tree, "qkv_norm_rope_inplace")
    wrapper_calls = [node for node in ast.walk(wrapper) if isinstance(node, ast.Call)]
    candidate_launches = sum(
        isinstance(call.func, ast.Subscript)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "_qkv_norm_rope_inplace_kernel"
        for call in wrapper_calls
    )
    kernel_start = source.index("def _qkv_norm_rope_inplace_kernel")
    wrapper_start = source.index("def qkv_norm_rope_inplace")
    kernel_source = source[kernel_start:wrapper_start]
    allocation_tokens = ["torch.empty", "torch.zeros", "torch.clone", ".clone("]
    present_allocations = [token for token in allocation_tokens if token in kernel_source]
    return {
        "program_sha256": sha256(program_path),
        "wrapper_candidate_launches": candidate_launches,
        "kernel_store_statements": kernel_source.count("tl.store("),
        "kernel_allocation_tokens": present_allocations,
        "pass": candidate_launches == 1
        and kernel_source.count("tl.store(") == 2
        and not present_allocations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--source-root", type=pathlib.Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    project_root = pathlib.Path(__file__).resolve().parent
    program_path = project_root / "qkv_epilogue_discriminator.py"
    oracle_rows = [
        oracle_case("local", 256, 10000.0, 128),
        oracle_case("global_partial", 512, 1000000.0, 64),
    ]
    evidence_rows: dict[str, object] = {}
    for name, binding in BOUND_EVIDENCE.items():
        path = (project_root / binding["relative_path"]).resolve()
        actual = sha256(path)
        evidence_rows[name] = {
            "path": str(path),
            "expected_sha256": binding["sha256"],
            "actual_sha256": actual,
            "pass": actual == binding["sha256"],
        }
    source_rows: dict[str, object] = {}
    if args.source_root is not None:
        for relative_path, expected in EXPECTED_SOURCE_SHA256.items():
            path = args.source_root / relative_path
            actual = sha256(path)
            source_rows[relative_path] = {
                "expected_sha256": expected,
                "actual_sha256": actual,
                "pass": actual == expected,
            }
    audit = source_audit(program_path)
    local_eliminated_bytes_per_token = 4 * (32 * 256 + 16 * 256)
    global_eliminated_bytes_per_token = 4 * (32 * 512 + 4 * 512)
    conservative_decode_tokens = (358 - 1) * 32
    admitted_tokens = 117728 + conservative_decode_tokens
    eliminated_bytes_per_batch = admitted_tokens * (
        50 * local_eliminated_bytes_per_token
        + 10 * global_eliminated_bytes_per_token
    )
    eliminated_launches_per_batch = (117728 // 2048 + 358 - 1) * 60
    required_batch_saving_seconds = 0.04597286970625021 * 32
    bandwidth_scenarios = {}
    for bandwidth_tb_per_second in (1.0, 2.0, 3.0, 4.8):
        byte_only_batch_seconds = eliminated_bytes_per_batch / (
            bandwidth_tb_per_second * 1e12
        )
        bandwidth_scenarios[str(bandwidth_tb_per_second)] = {
            "byte_only_seconds_per_request": byte_only_batch_seconds / 32,
            "residual_microseconds_required_per_eliminated_launch": (
                required_batch_saving_seconds - byte_only_batch_seconds
            )
            * 1e6
            / eliminated_launches_per_batch,
        }
    result = {
        "schema_version": 1,
        "kind": "gemma4_qkv_epilogue_offline_preparation",
        "scientific_terminal": False,
        "source_commit": SOURCE_COMMIT,
        "geometry": {
            "hidden_size": 5376,
            "layers": 60,
            "query_heads": 32,
            "local": {"layers": 50, "kv_heads": 16, "head_dim": 256, "rotary_fraction": 1.0, "qkv_width": 16384},
            "global": {"layers": 10, "kv_heads": 4, "head_dim": 512, "rotary_fraction": 0.25, "qkv_width": 20480},
        },
        "oracle_rows": oracle_rows,
        "source_audit": audit,
        "bound_evidence": evidence_rows,
        "pinned_source_rows": source_rows,
        "analytical_mechanism": {
            "evidence_type": "analytical",
            "local_eliminated_intermediate_bytes_per_token_layer": local_eliminated_bytes_per_token,
            "global_eliminated_intermediate_bytes_per_token_layer": global_eliminated_bytes_per_token,
            "eliminated_intermediate_bytes_per_batch": eliminated_bytes_per_batch,
            "eliminated_launches_per_batch": eliminated_launches_per_batch,
            "required_batch_saving_seconds": required_batch_saving_seconds,
            "bandwidth_scenarios_tb_per_second": bandwidth_scenarios,
            "interpretation": "Traffic removal alone does not clear the gate at any listed bandwidth. Promotion therefore requires the head-granular candidate to recover tens of microseconds per eliminated token-granular launch through higher decode occupancy as well as one-pass traffic.",
        },
    }
    result["pass"] = bool(
        all(row["pass"] for row in oracle_rows)
        and audit["pass"]
        and all(row["pass"] for row in evidence_rows.values())
        and all(row["pass"] for row in source_rows.values())
    )
    atomic_json(args.output_dir / "OFFLINE_ORACLE.json", result)
    manifest_paths = [
        program_path,
        pathlib.Path(__file__).resolve(),
        project_root / "remote_component.sh",
        project_root / "install_endpoint_patch.py",
        project_root / "remote_endpoint.sh",
        project_root / "run_outer.py",
        project_root / "inputs/exact_mix_runner.py",
    ]
    atomic_json(
        args.output_dir / "INPUT_MANIFEST.json",
        {
            "schema_version": 1,
            "files": [
                {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256(path)}
                for path in manifest_paths
            ],
            "admission": {
                "runtime_image": "docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a",
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "component_gpu": "nvidia-h200-sxm",
                "component_gate_seconds_per_request": 0.04597286970625021,
            },
        },
    )
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
