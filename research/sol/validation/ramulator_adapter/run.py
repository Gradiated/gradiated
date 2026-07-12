from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from .normalize import build_report, content_identity, normalize_stats, validate_report
from .trace import (
    CONTEXT_TOKENS,
    EXECUTABLE_PATTERN_IDS,
    PAGE_TOKENS,
    PATTERN_SPECS,
    REQUEST_BYTES,
    SEED,
    generate_trace,
    summarize_trace,
)


EXPECTED_REPOSITORY = "https://github.com/CMU-SAFARI/ramulator2.git"
EXPECTED_COMMIT = "38c51d40a976c6b07fbc09de869a7e08dc187d29"
EXPECTED_TAG = "v2.1.0"
PRISTINE_PARAM_SHA256 = (
    "c46d37cc7f14b03ea017db6c32603a7cfcbea5a61595ca8b2afdc3f3d9152c42"
)
PATCHED_PARAM_SHA256 = (
    "e0035c646a68f74d2de683816f5a7eef6b104642f4bd81fbae5ee3ff024cdb71"
)
GEOMETRIES = {
    "representative_hbm_transaction_32b": {
        "transactions_per_selected_token": 1,
        "bytes_per_selected_token": 32,
        "scope": "one representative HBM transaction per selected token",
    },
    "bf16_mla_record_1152b": {
        "transactions_per_selected_token": 36,
        "bytes_per_selected_token": 1152,
        "scope": "36 contiguous HBM transactions per selected token matching one synthetic one-layer 1,152-byte BF16 MLA record",
    },
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(source_root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(source_root), *args],
        check=True,
        capture_output=True,
    ).stdout


def _relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _source_identity(source_root: Path, repo_root: Path) -> dict[str, Any]:
    repository = _git(source_root, "remote", "get-url", "origin").decode().strip()
    commit = _git(source_root, "rev-parse", "HEAD").decode().strip()
    tag = _git(source_root, "describe", "--tags", "--exact-match").decode().strip()
    if (
        repository != EXPECTED_REPOSITORY
        or commit != EXPECTED_COMMIT
        or tag != EXPECTED_TAG
    ):
        raise ValueError(
            "Ramulator2 source identity does not match the pinned stable tag"
        )
    param_path = source_root / "src/ramulator/base/param.h"
    patched_param_sha = _sha256_file(param_path)
    pristine_param = _git(source_root, "show", "HEAD:src/ramulator/base/param.h")
    if _sha256_bytes(pristine_param) != PRISTINE_PARAM_SHA256:
        raise ValueError("pristine param.h hash mismatch")
    if patched_param_sha != PATCHED_PARAM_SHA256:
        raise ValueError("patched param.h hash mismatch")
    patch_diff = _git(source_root, "diff", "--", "src/ramulator/base/param.h")
    codegen_diff = _git(source_root, "diff", "--", "src/ramulator/dram/impl")
    codegen_files = (
        _git(source_root, "diff", "--name-only", "--", "src/ramulator/dram/impl")
        .decode()
        .splitlines()
    )
    files = {}
    for relative in (
        "README.md",
        "LICENSE",
        "python/ramulator/dram/hbm3.py",
        "python/ramulator/frontend/external.py",
        "src/ramulator/dram/impl/HBM3.cpp",
        "src/ramulator/frontend/impl/external.cpp",
        "src/ramulator/frontend/impl/memory_trace/readwrite_trace.cpp",
        "src/ramulator/controller/controller_base.cpp",
    ):
        path = source_root / relative
        files[relative] = {
            "executed_file_sha256": _sha256_file(path),
            "pristine_file_sha256": _sha256_bytes(
                _git(source_root, "show", f"HEAD:{relative}")
            ),
        }
    return {
        "name": "Ramulator2",
        "validation_status": "succeeded",
        "repository": repository,
        "ref_kind": "stable_tag",
        "tag": tag,
        "tag_object": _git(source_root, "rev-parse", f"{tag}^{{tag}}").decode().strip(),
        "commit": commit,
        "default_branch_at_discovery": "main",
        "default_branch_commit_at_discovery": "99a0e1e87a9321587492fef5b0bd6197928f8d68",
        "source_root": _relative(source_root, repo_root),
        "license": "MIT",
        "pristine_source_build": False,
        "selection_reason": "The official v2.1.0 stable tag supports HBM3/HBM4 pseudochannels, exposes Python-native structured controller statistics, and includes the newer validation workflows and aggregated fixes. It supersedes the v2.0a baseline without using an unreleased branch.",
        "compatibility_patch": {
            "scope": "cxx_dependent_template_disambiguation_only",
            "reason": "AppleClang 16 rejects the pinned source without the standard dependent-template disambiguator.",
            "pristine_file_sha256": PRISTINE_PARAM_SHA256,
            "patched_file_sha256": patched_param_sha,
            "unified_diff_sha256": _sha256_bytes(patch_diff),
            "unified_diff": patch_diff.decode(),
            "semantic_model_change": False,
        },
        "official_codegen": {
            "executed_during_default_build": True,
            "changed_generated_file_count": len(codegen_files),
            "changed_generated_files": codegen_files,
            "generated_diff_sha256": _sha256_bytes(codegen_diff),
            "source_of_truth": "pinned official Python DRAM definitions",
        },
        "files": files,
    }


def _build_native_runner(
    source_root: Path, raw_root: Path, repo_root: Path
) -> dict[str, Any]:
    runner_source = repo_root / "validation/ramulator_adapter/native/drain_runner.cpp"
    runner_binary = raw_root / "native/drain_runner"
    runner_binary.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "xcrun",
        "clang++",
        "-std=c++20",
        "-O2",
        "-I",
        str(source_root / "src"),
        str(runner_source),
        "-L",
        str(source_root),
        "-lramulator",
        f"-Wl,-rpath,{source_root}",
        "-o",
        str(runner_binary),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return {
        "role": "external_addr_vec_injector_with_callback_drain",
        "semantic_model_change": False,
        "injection_contract": "at most one request is attempted before each memory-system tick; ticking continues after final acceptance until every request callback completes",
        "source": {
            "path": _relative(runner_source, repo_root),
            "sha256": _sha256_file(runner_source),
        },
        "binary": {
            "path": _relative(runner_binary, repo_root),
            "sha256": _sha256_file(runner_binary),
        },
        "compile_command": shlex.join(command),
    }


def _build_identity(
    source_root: Path, raw_root: Path, repo_root: Path
) -> dict[str, Any]:
    library = source_root / "libramulator.dylib"
    extensions = sorted((source_root / "python/ramulator").glob("_ramulator.*.so"))
    if not library.is_file() or len(extensions) != 1:
        raise ValueError("Ramulator2 native build outputs are missing")
    compiler = subprocess.run(
        ["xcrun", "clang++", "--version"], check=True, capture_output=True, text=True
    ).stdout
    cmake = subprocess.run(
        [sys.executable.rsplit("/", 1)[0] + "/cmake", "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()[0]
    return {
        "status": "succeeded",
        "pristine_source_build": False,
        "build_system": "CMake with Ninja",
        "configuration_command": "cmake -S artifacts/external/ramulator2-v2.1.0 -B artifacts/external/ramulator2-v2.1.0/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DPython_EXECUTABLE=/Users/js/dev/vllm-study/.venv/bin/python",
        "build_command": "cmake --build artifacts/external/ramulator2-v2.1.0/build --parallel 8",
        "compiler": compiler.strip(),
        "cmake": cmake,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "library": {
            "path": _relative(library, repo_root),
            "sha256": _sha256_file(library),
        },
        "python_extension": {
            "path": _relative(extensions[0], repo_root),
            "sha256": _sha256_file(extensions[0]),
        },
        "native_drain_runner": _build_native_runner(source_root, raw_root, repo_root),
    }


def _components(ramulator: Any) -> dict[str, Any]:
    frontend = ramulator.frontend.External(clock_ratio=1)
    dram = ramulator.dram.HBM3(org_preset="HBM3_8Gb_8hi", timing_preset="HBM3_6400Mbps")
    controller = ramulator.controller.HBM34(
        dram=dram,
        scheduler=ramulator.scheduler.FRFCFS(),
        row_policy=ramulator.row_policy.Open(),
        addr_mapper=ramulator.addr_mapper.PassThroughAddrMapper(),
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
    )
    memory = ramulator.memory_system.GenericDRAM(
        clock_ratio=1,
        controllers=[controller],
        channel_mapper=ramulator.channel_mapper.PassThroughChannelMapper(),
    )
    config = {
        "frontend": frontend.to_config(),
        "memory_system": memory.to_config(),
    }
    return config


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def _run_cases(
    source_root: Path,
    raw_root: Path,
    repo_root: Path,
    runner_path: Path,
) -> list[dict[str, Any]]:
    sys.path.insert(0, str(source_root / "python"))
    import ramulator

    cases = []
    config = _components(ramulator)
    for geometry_id, geometry in GEOMETRIES.items():
        for pattern_id in EXECUTABLE_PATTERN_IDS:
            records = generate_trace(
                pattern_id,
                transactions_per_token=geometry["transactions_per_selected_token"],
            )
            case_root = raw_root / geometry_id / pattern_id
            trace_path = case_root / "trace.txt"
            case_root.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(
                "\n".join(record.render() for record in records) + "\n"
            )
            config_path = case_root / "config.json"
            _write_json(config_path, config)
            normalized_runs = []
            raw_runs = []
            for replay_index in range(2):
                raw_path = case_root / f"stats-replay-{replay_index + 1}.json"
                process = subprocess.run(
                    [
                        str(runner_path),
                        str(config_path),
                        str(trace_path),
                        str(raw_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                stats = json.loads(raw_path.read_text())
                raw_runs.append(
                    {
                        "path": _relative(raw_path, repo_root),
                        "sha256": _sha256_file(raw_path),
                        "stdout_sha256": _sha256_bytes(process.stdout.encode()),
                        "stderr_sha256": _sha256_bytes(process.stderr.encode()),
                    }
                )
                normalized_runs.append(normalize_stats(stats))
            cases.append(
                {
                    "geometry_id": geometry_id,
                    "geometry_contract": geometry,
                    "pattern_id": pattern_id,
                    "pattern_contract": PATTERN_SPECS[pattern_id],
                    "trace_summary": summarize_trace(records),
                    "trace_artifact": {
                        "path": _relative(trace_path, repo_root),
                        "sha256": _sha256_file(trace_path),
                    },
                    "config_artifact": {
                        "path": _relative(config_path, repo_root),
                        "sha256": _sha256_file(config_path),
                        "config": config,
                    },
                    "raw_stats_artifacts": raw_runs,
                    "runs": normalized_runs,
                }
            )
    return cases


def _ratio(candidate: float, baseline: float) -> float | None:
    return candidate / baseline if baseline else None


def _comparison(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    candidate_run = candidate["comparison_run"]
    baseline_run = baseline["comparison_run"]
    cycles_permitted = (
        candidate["request_conservation_passed"]
        and baseline["request_conservation_passed"]
        and candidate["deterministic_replay_passed"]
        and baseline["deterministic_replay_passed"]
        and candidate["native_drain_accounting_passed"]
        and baseline["native_drain_accounting_passed"]
    )
    latency_permitted = (
        cycles_permitted
        and candidate_run["served_read_count"] == baseline_run["served_read_count"]
        and candidate_run["completion_fraction"] == 1.0
        and baseline_run["completion_fraction"] == 1.0
    )
    locality_permitted = (
        cycles_permitted
        and candidate_run["row_outcome_count"] == baseline_run["row_outcome_count"]
        and candidate_run["row_outcome_coverage"] == 1.0
        and baseline_run["row_outcome_coverage"] == 1.0
    )
    return {
        "baseline_pattern_id": baseline["pattern_id"],
        "candidate_pattern_id": candidate["pattern_id"],
        "drained_controller_cycle_comparison_permitted": cycles_permitted,
        "controller_cycle_ratio": _ratio(
            candidate_run["controller_cycles"], baseline_run["controller_cycles"]
        )
        if cycles_permitted
        else None,
        "controller_cycle_change_percent": 100
        * (
            _ratio(
                candidate_run["controller_cycles"], baseline_run["controller_cycles"]
            )
            - 1
        )
        if cycles_permitted
        else None,
        "average_read_latency_comparison_permitted": latency_permitted,
        "average_read_latency_cycle_ratio": _ratio(
            candidate_run["average_read_latency_cycles"],
            baseline_run["average_read_latency_cycles"],
        )
        if latency_permitted
        else None,
        "row_locality_comparison_permitted": locality_permitted,
        "row_hit_fraction_delta": candidate_run["row_hit_fraction"]
        - baseline_run["row_hit_fraction"]
        if locality_permitted
        else None,
        "boundary": "Native controller cycles include injection and complete callback drain for this exact synthetic trace; they are not GPU latency or wall time.",
    }


def _geometry_analysis(cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_pattern = {case["pattern_id"]: case for case in cases}
    baseline = by_pattern["gather_score_order"]
    sorting = _comparison(by_pattern["gather_address_sorted"], baseline)
    negative_control = _comparison(by_pattern["sequential_stream"], baseline)
    frontier = []
    for target in (2, 4, 8, 16, 32, 64):
        point = _comparison(by_pattern[f"gather_cluster_{target}"], baseline)
        point["target_tokens_per_page"] = target
        frontier.append(point)
    improved = [
        point["target_tokens_per_page"]
        for point in frontier
        if point["controller_cycle_ratio"] is not None
        and point["controller_cycle_ratio"] < 1
    ]
    return {
        "baseline_pattern_id": "gather_score_order",
        "sorting_only_same_selected_set": sorting,
        "sequential_negative_control": negative_control,
        "page_clustering_frontier": {
            "target_1_feasible": False,
            "target_1_reason": "2,048 unique tokens cannot occupy one token each across only ceil(90,000 / 64) = 1,407 pages.",
            "points": frontier,
            "minimum_target_with_lower_native_drained_cycles": min(improved)
            if improved
            else None,
            "candidate_scope": "future page-aware indexer or model architecture change hypothesis, not current GLM behavior",
        },
    }


def _analysis(cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_geometry: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        by_geometry.setdefault(case["geometry_id"], []).append(case)
    return {
        "within_geometry_only": True,
        "cross_geometry_comparison_permitted": False,
        "geometries": {
            geometry_id: _geometry_analysis(geometry_cases)
            for geometry_id, geometry_cases in by_geometry.items()
        },
    }


def _metadata() -> dict[str, Any]:
    return {
        "oracle_scope": "patched Ramulator2 HBM3 synthetic address-order and page-locality sensitivity with complete callback drain",
        "workload": {
            "context_tokens": CONTEXT_TOKENS,
            "selected_token_count": 2048,
            "page_tokens": PAGE_TOKENS,
            "request_bytes": REQUEST_BYTES,
            "geometries": GEOMETRIES,
            "executable_pattern_ids": list(EXECUTABLE_PATTERN_IDS),
            "representative_hbm_transaction_32b": {
                "read_count": 2048,
                "write_count": 0,
                "total_bytes_per_case": 65536,
            },
            "bf16_mla_record_1152b": {
                "read_count": 73728,
                "write_count": 0,
                "total_bytes_per_case": 2359296,
            },
            "address_vector_levels": [
                "Channel",
                "PseudoChannel",
                "Sid",
                "BankGroup",
                "Bank",
                "Row",
                "Column",
            ],
            "mapping": "Each 64-token synthetic page maps across 64 HBM bank domains before advancing row. The representative geometry maps one token to one 32-byte column transaction. The BF16 geometry maps each token to 36 contiguous 32-byte transactions and each page to nine rows in the same bank domain.",
            "logical_address_sort_boundary": "The address-sorted case orders ascending logical token positions. It does not sort the mapped HBM address-vector tuple.",
            "trace_fidelity": "synthetic probes only; the BF16 geometry represents one synthetic one-layer record and neither geometry reproduces full multi-layer GLM DSA, MLA, indexer, cache, scale, GPU traffic, overlap, or execution",
        },
        "hypothesis_source_context": {
            "repository": "https://github.com/vllm-project/vllm",
            "commit": "bec0a4ede621bc9f1ec7be39b79ed2e286da4ca1",
            "observed_boundary": "The pinned sparse top-k output is score-descending rather than address-sorted. Address sorting is a kernel/hardware hypothesis, and page clustering is a model/indexer architecture-change hypothesis.",
            "files": {
                "csrc/libtorch_stable/sampler.cu": "f0adb3a9e260f62a194ec83fd2b2c4ad2b0548c1868d6cf4910004d68d1fef43",
                "vllm/model_executor/layers/sparse_attn_indexer.py": "341662631718eb8315be2287841c201954be9752e9492a7cd04ed5b9ba2ebae4",
                "vllm/model_executor/models/deepseek_v2.py": "a58791119567072d609fa89ec3326a8c3de0a74faee8cb992d9f7ac5f56e7e39",
                "vllm/v1/attention/backends/mla/flashmla_sparse.py": "31316f5d852a06d8e9dd919395f52671732548559486371b06c08a6e2504f723",
                "vllm/v1/kv_cache_interface.py": "8c6d29a19a221062223c2e6a484c050dee5e71c497858cb80b93dbb612d0cbca",
            },
        },
        "dram_configuration": {
            "standard": "HBM3",
            "organization_preset": "HBM3_8Gb_8hi",
            "timing_preset": "HBM3_6400Mbps",
            "controller": "HBM34",
            "scheduler": "FRFCFS",
            "row_policy": "Open",
            "refresh_manager": "NoRefresh",
            "refresh_excluded": True,
            "address_mapper": "PassThroughAddrMapper",
            "channel_mapper": "PassThroughChannelMapper",
            "modeled_channel_count": 1,
            "modeled_controller_count": 1,
            "frontend": "External",
            "frontend_clock_ratio": 1,
            "memory_clock_ratio": 1,
            "drain_contract": "The external runner attempts at most one request per memory tick and continues ticking until all callbacks complete.",
            "scope_boundary": "This is a single-channel DRAM-controller sensitivity probe, not a complete HBM stack, accelerator, or serving system.",
        },
        "seed": SEED,
    }


def run(
    source_root: Path, raw_root: Path, output: Path, repo_root: Path
) -> dict[str, Any]:
    metadata = _metadata()
    source_identity: dict[str, Any] = {
        "name": "Ramulator2",
        "expected_repository": EXPECTED_REPOSITORY,
        "expected_commit": EXPECTED_COMMIT,
        "expected_tag": EXPECTED_TAG,
        "validation_status": "failed",
    }
    build: dict[str, Any] = {"status": "failed", "pristine_source_build": False}
    try:
        source_identity = _source_identity(source_root, repo_root)
        build = _build_identity(source_root, raw_root, repo_root)
        cases = _run_cases(
            source_root,
            raw_root,
            repo_root,
            raw_root / "native/drain_runner",
        )
        report = build_report(source_identity, build, cases, metadata)
        errors = validate_report(report)
        if errors:
            raise ValueError("; ".join(errors))
        report["analysis"] = _analysis(report["cases"])
        report["claims"]["patched_oracle_synthetic_hbm3_sensitivity"] = True
        report["content_identity_sha256"] = content_identity(report)
    except Exception as error:
        blocked_build = {**build, "execution_error": f"{type(error).__name__}: {error}"}
        report = build_report(source_identity, blocked_build, [], metadata)
        report["status"] = "blocked"
        report["claims"]["native_oracle_operability"] = False
        report["claims"]["synthetic_hbm3_sensitivity"] = False
        report["claims"]["patched_oracle_synthetic_hbm3_sensitivity"] = False
        report["content_identity_sha256"] = content_identity(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("artifacts/external/ramulator2-v2.1.0"),
    )
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=Path("artifacts/ramulator2-hbm3-irregular-v1"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "validation/results/qwen3-glm-ramulator2-hbm3-synthetic-irregular-v1.json"
        ),
    )
    args = parser.parse_args()
    repo_root = Path.cwd().resolve()
    report = run(
        args.source_root.resolve(),
        args.raw_root.resolve(),
        args.output.resolve(),
        repo_root,
    )
    print(
        json.dumps(
            {
                "output": _relative(args.output, repo_root),
                "status": report["status"],
                "content_id": report["content_identity_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
