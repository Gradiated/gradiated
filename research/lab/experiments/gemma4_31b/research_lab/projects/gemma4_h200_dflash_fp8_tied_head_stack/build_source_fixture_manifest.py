#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def record(root: pathlib.Path, path: pathlib.Path) -> dict[str, object]:
    return {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sglang-root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    project = pathlib.Path(__file__).resolve().parent
    dflash = project.parent / "gemma4_h200_dflash_endpoint"
    fp8_project = project.parent / "gemma4_h200_fp8_tied_head_endpoint"
    source_paths = [
        project / "overlay/dflash_fp8_tied_head_stack.py",
        project / "overlay/sitecustomize.py",
        project / "conditional_fp8_stack_launcher.sh",
        project / "run_stack_fixtures.py",
        project / "verify_director_binding.py",
        project / "build_source_fixture_manifest.py",
        project / "fixtures/DFLASH_DIAGNOSTIC_GATE_PASS.json",
    ]
    fixture_paths = [
        project / "DIRECTOR_BINDING_VERIFICATION.json",
        project / "DFLASH_FP8_TIED_HEAD_STACK_FIXTURES.json",
        project / "CONDITIONAL_LAUNCH_FIXTURE.json",
    ]
    terminal_paths = [
        project / "DFLASH_FP8_TIED_HEAD_STACK_RESULT.json",
        project / "DFLASH_FP8_TIED_HEAD_STACK_DECISION.md",
        project / "RESEARCH_LOG.md",
        project / "STATUS.json",
    ]

    source_records = [record(project, path) for path in source_paths]
    fixture_records = [record(project, path) for path in fixture_paths]
    terminal_records = [record(project, path) for path in terminal_paths]
    tree_hasher = hashlib.sha256()
    for row in sorted(
        source_records + fixture_records + terminal_records,
        key=lambda value: value["path"],
    ):
        tree_hasher.update(
            f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n".encode()
        )

    bound_paths = [
        project / "DIRECTOR_BINDING.json",
        dflash / "DIRECTOR_TIED_HEAD_ADAPTER_FRESH_H200_BINDING.json",
        dflash / "artifacts/tied-head-adapter-inputs-20260725.tar",
        dflash / "TIED_HEAD_ADAPTER_INPUTS.json",
        dflash / "remote_tied_head_adapter.sh",
        project.parent
        / "gemma4_h200_fp8_tied_head_endpoint"
        / "iterations/c32-topology-settled-resume-20260723t2110z"
        / "resident-consumer-repair-artifacts/FINAL_TERMINAL.json",
        project.parent
        / "gemma4_h200_fp8_tied_head_endpoint"
        / "iterations/c32-topology-settled-resume-20260723t2110z"
        / "resident-consumer-repair-artifacts/attempt1/fp8-graph-endpoint-compact.tar.gz",
        project.parent
        / "gemma4_h200_fp8_tied_head_endpoint"
        / "iterations/c32-topology-settled-resume-20260723t2110z"
        / "resident-consumer-repair-artifacts/attempt1/retrieved/GRAPH_TOPOLOGY_DECISION.json",
    ]
    bound_inputs = [
        {
            "path": str(path.resolve()),
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        }
        for path in bound_paths
    ]

    pinned_runtime = {}
    for relative in (
        "python/sglang/srt/models/gemma4_mm.py",
        "python/sglang/srt/speculative/dflash_worker.py",
        "python/sglang/srt/speculative/dflash_info.py",
        "python/sglang/srt/speculative/dflash_utils.py",
        "python/sglang/srt/speculative/triton_ops/dflash_accept_bonus.py",
        "python/sglang/srt/layers/logits_processor.py",
        "python/sglang/srt/layers/vocab_parallel_embedding.py",
        "python/sglang/srt/layers/sampler.py",
        "python/sglang/srt/model_executor/model_runner.py",
        "python/sglang/srt/model_executor/runner/decode_cuda_graph_runner.py",
        "python/sglang/srt/model_executor/runner/base_cuda_graph_runner.py",
    ):
        path = args.sglang_root / relative
        pinned_runtime[relative] = digest(path)

    prior_patch = (
        fp8_project
        / "iterations/graph-bound-endpoint-20260723t1930z"
        / "inputs/stack/fp8_tied_head_patch.py"
    )
    manifest = {
        "schema_version": 1,
        "status": "complete",
        "project": project.name,
        "runtime_commit": "588d1f7bc9424201f89957e145f9d5af633a3eb8",
        "source_files": source_records,
        "fixture_artifacts": fixture_records,
        "terminal_artifacts": terminal_records,
        "content_tree_sha256": tree_hasher.hexdigest(),
        "bound_inputs": bound_inputs,
        "pinned_runtime_source_sha256": pinned_runtime,
        "prior_mechanism_source": {
            "path": str(prior_patch.resolve()),
            "sha256": digest(prior_patch),
            "provenance": "The same digest appears in the prior captured endpoint input-sha256.txt; only its separate-storage E4M3 target-head mechanism was ported.",
        },
        "binding_disposition": {
            "verification": "DIRECTOR_BINDING_VERIFICATION.json",
            "passes": 48,
            "failures": 1,
            "nominatable": False,
        },
        "claims": {
            "source_complete": True,
            "fixtures_reproducible": True,
            "gpu_measured": False,
            "performance_claim": False,
            "quality_claim": False,
        },
    }
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
