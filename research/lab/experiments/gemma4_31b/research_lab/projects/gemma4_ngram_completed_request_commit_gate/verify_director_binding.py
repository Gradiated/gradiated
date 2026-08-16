#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
WORKSPACE = PROJECT.parents[6]
PINNED = WORKSPACE / ".agents/runtime/sglang-v0.5.13-source"
PYTHON_ROOT = PINNED / "python/sglang/srt"
BOUND_DIR = PROJECT / "inputs/bound"
LIFECYCLE_DIR = PROJECT / "inputs/lifecycle"
EXPECTED_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
TRACE_PACKET_SHA256 = (
    "ccc559094ee612d5da11e771c2ebf8ac14046ad03b8ec7bd6ae165be25725d68"
)

LIFECYCLE_SOURCES = {
    "ngram_info.py": PYTHON_ROOT / "speculative/ngram_info.py",
    "schedule_batch.py": PYTHON_ROOT / "managers/schedule_batch.py",
    "scheduler.py": PYTHON_ROOT / "managers/scheduler.py",
    "batch_result_processor.py": (
        PYTHON_ROOT / "managers/scheduler_components/batch_result_processor.py"
    ),
    "ngram_corpus/param.h": (
        PINNED / "python/sglang/jit_kernel/csrc/ngram_corpus/param.h"
    ),
    "ngram_corpus/result.cpp": (
        PINNED / "python/sglang/jit_kernel/csrc/ngram_corpus/result.cpp"
    ),
    "ngram_corpus/result.h": (
        PINNED / "python/sglang/jit_kernel/csrc/ngram_corpus/result.h"
    ),
    "ngram_corpus/trie.cpp": (
        PINNED / "python/sglang/jit_kernel/csrc/ngram_corpus/trie.cpp"
    ),
    "ngram_corpus/trie.h": (
        PINNED / "python/sglang/jit_kernel/csrc/ngram_corpus/trie.h"
    ),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    part.replace(path)


def main() -> None:
    binding = json.loads((PROJECT / "DIRECTOR_BINDING.json").read_text())
    BOUND_DIR.mkdir(parents=True, exist_ok=True)
    observed_bound = {}
    for name, spec in binding.items():
        if not isinstance(spec, dict) or "path" not in spec:
            continue
        source = (PROJECT / spec["path"]).resolve()
        if digest(source) != spec["sha256"]:
            raise RuntimeError(f"director binding mismatch: {name}")
        destination = BOUND_DIR / source.name
        if destination.exists() and digest(destination) != spec["sha256"]:
            raise RuntimeError(f"project-local binding mismatch: {destination}")
        if not destination.exists():
            part = destination.with_suffix(destination.suffix + ".part")
            shutil.copyfile(source, part)
            part.replace(destination)
        observed_bound[name] = {
            "path": str(destination.relative_to(PROJECT)),
            "sha256": digest(destination),
        }

    trace_source = (
        PROJECT.parent
        / "gemma4_ngram_distinct_request_promotion_gate/inputs/bound/TRACE_PACKET.json"
    )
    if digest(trace_source) != TRACE_PACKET_SHA256:
        raise RuntimeError("supporting request template binding mismatch")
    trace_destination = BOUND_DIR / "TRACE_PACKET.json"
    if trace_destination.exists() and digest(trace_destination) != TRACE_PACKET_SHA256:
        raise RuntimeError("project-local request template mismatch")
    if not trace_destination.exists():
        part = trace_destination.with_suffix(".json.part")
        shutil.copyfile(trace_source, part)
        part.replace(trace_destination)
    observed_bound["request_template_packet"] = {
        "path": str(trace_destination.relative_to(PROJECT)),
        "sha256": digest(trace_destination),
        "binding": "source-project SHA256SUMS.json supporting launch input",
    }

    commit = subprocess.run(
        ["git", "-C", str(PINNED), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(PINNED), "status", "--porcelain"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    if commit != EXPECTED_COMMIT or dirty:
        raise RuntimeError({"commit": commit, "dirty": dirty})
    if digest(PYTHON_ROOT / "speculative/ngram_worker.py") != binding[
        "ngram_worker_source"
    ]["sha256"]:
        raise RuntimeError("pinned checkout worker differs from director binding")

    causal = json.loads((BOUND_DIR / "causal_result.json").read_text())
    expected_lifecycle = causal["source_identity"]["sha256"]
    if digest(LIFECYCLE_SOURCES["ngram_info.py"]) != expected_lifecycle[
        "ngram_info.py"
    ]:
        raise RuntimeError("pinned ngram_info.py differs from causal binding")

    observed_lifecycle = {}
    for name, source in LIFECYCLE_SOURCES.items():
        destination = LIFECYCLE_DIR / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_sha = digest(source)
        if destination.exists() and digest(destination) != source_sha:
            raise RuntimeError(f"project-local lifecycle mismatch: {destination}")
        if not destination.exists():
            part = destination.with_suffix(destination.suffix + ".part")
            shutil.copyfile(source, part)
            part.replace(destination)
        observed_lifecycle[name] = {
            "path": str(destination.relative_to(PROJECT)),
            "sha256": digest(destination),
        }

    result = {
        "schema_version": 1,
        "result": "director_binding_verified_and_materialized",
        "model": binding["model"],
        "runtime_image": binding["runtime_image"],
        "sglang_commit": commit,
        "bound_inputs": observed_bound,
        "lifecycle_sources": observed_lifecycle,
    }
    atomic_json(
        BOUND_DIR / "SHA256SUMS.json",
        {
            Path(row["path"]).name: row["sha256"]
            for row in observed_bound.values()
        },
    )
    atomic_json(PROJECT / "DIRECTOR_BINDING_VERIFIED.json", result)
    print(json.dumps({"result": result["result"], "sglang_commit": commit}))


if __name__ == "__main__":
    main()
