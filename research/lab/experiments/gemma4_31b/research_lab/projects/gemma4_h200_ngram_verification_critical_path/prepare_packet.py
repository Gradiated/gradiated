from __future__ import annotations

import hashlib
import json
import os
import pathlib


ROOT = pathlib.Path(__file__).resolve().parent
INPUTS = ROOT / "inputs"
OUTPUT = ROOT / "SOURCE_TRACE_COUNTER_PACKET.json"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> None:
    checkpoint_manifest = json.loads(
        (INPUTS / "evidence/CHECKPOINT_MANIFEST.json").read_text()
    )
    checkpoint = []
    for item in checkpoint_manifest["files"]:
        path = INPUTS / "checkpoint" / item["name"]
        observed = {
            "path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "mode": oct(path.stat().st_mode & 0o777),
        }
        if observed["bytes"] != item["bytes"] or observed["sha256"] != item["sha256"]:
            raise RuntimeError(f"checkpoint_binding_mismatch:{item['name']}")
        if path.stat().st_mode & 0o222:
            raise RuntimeError(f"checkpoint_not_immutable:{item['name']}")
        checkpoint.append(observed)

    bound_files = []
    for path in sorted(INPUTS.rglob("*")):
        if not path.is_file() or "checkpoint" in path.parts:
            continue
        bound_files.append(
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "mode": oct(path.stat().st_mode & 0o777),
            }
        )

    launch = json.loads((INPUTS / "evidence/candidate-full-launch.json").read_text())
    atomic(
        OUTPUT,
        {
            "schema_version": 1,
            "kind": "gemma4_h200_ngram_verification_source_trace_counter_packet",
            "checkpoint": {
                "model": checkpoint_manifest["model"],
                "revision": checkpoint_manifest["revision"],
                "total_bytes": checkpoint_manifest["total_bytes"],
                "files": checkpoint,
                "materialization": (
                    "project-local immutable hard links to the already verified bytes; "
                    "the directory is the only path admitted to staging"
                ),
            },
            "runtime": {
                "image": (
                    "docker.io/lmsysorg/sglang@sha256:"
                    "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
                ),
                "sglang_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
                "launch_args": launch["args"],
                "baseline_intervention": (
                    "decode-equivalent request-major depth-sliced LM head"
                ),
            },
            "workload": {
                "runner": "inputs/bound/exact_runner.py",
                "profile_runner": "profile_runner.py",
                "concurrency": 32,
                "prompt_tokens": 4214,
                "output_tokens": 358,
                "shared_prefix_tokens": 535,
            },
            "profile": {
                "collector": "SGLang /start_profile backed by PyTorch CPU+CUDA profiler",
                "steps": 16,
                "semantic_ranges": [
                    "ngram.cpu_corpus_lookup",
                    "ngram.draft_mask_and_indices",
                    "ngram.cache_slot_prepare",
                    "ngram.target_forward_verify",
                    "ngram.accept_bookkeeping_and_cache",
                    "ngram.cpu_corpus_update",
                ],
                "minimum_counter_followup": (
                    "Only if the timeline cannot distinguish launch/host-gap from "
                    "memory or compute; no counters are preregistered otherwise."
                ),
            },
            "bound_files": bound_files,
        },
    )


if __name__ == "__main__":
    main()
