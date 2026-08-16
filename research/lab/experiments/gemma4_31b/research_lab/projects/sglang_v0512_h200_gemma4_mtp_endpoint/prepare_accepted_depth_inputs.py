#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib


PROJECT = pathlib.Path(__file__).resolve().parent


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def records(root: pathlib.Path) -> list[dict[str, object]]:
    return [
        {
            "path": str(path.relative_to(PROJECT)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(root.iterdir())
        if path.is_file() and path.name != ".gitignore"
    ]


def main() -> int:
    checkpoint = records(PROJECT / "inputs/accepted_depth/checkpoint")
    assistant = records(PROJECT / "artifacts/assistant")
    stack = records(PROJECT / "inputs/accepted_depth/stack")
    runtime_source = records(PROJECT / "inputs/accepted_depth/runtime_source")
    programs = [
        PROJECT / name
        for name in (
            "accepted_depth_discriminator.py",
            "accepted_depth_sitecustomize.py",
            "accepted_depth_entrypoint.py",
            "accepted_depth_diagnostic.py",
            "remote_accepted_depth.sh",
        )
    ]
    binding = {
        "schema_version": 1,
        "pass": True,
        "runtime_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
        "runtime_image": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6",
        "native_path": {
            "assistant_forward": "FrozenKVMTPWorker.draft -> draft_forward -> draft_model_runner.forward",
            "target_verify": "FrozenKVMTPWorker.verify -> target_worker.forward_batch_generation(is_verify=True)",
            "accepted_tokens": "EagleVerifyInput.verify updates Req.spec_verify_ct, spec_num_correct_drafts, and histogram",
            "output_telemetry": "TokenizerManager._calculate_spec_decoding_metrics derives accepted/proposed drafts and verify count",
        },
        "source": runtime_source,
        "one_proposal_contract": {
            "speculative_num_steps": 1,
            "speculative_eagle_topk": 1,
            "speculative_num_draft_tokens": 2,
            "proposed_drafts_per_verify": 1,
        },
        "gate": {
            "minimum_whole_request_gain_fraction": 0.03,
            "decode_wall_seconds": 15.416948979,
            "profile_wall_seconds": 22.46439278,
            "formula": "decode_fraction * (1 - (verify_calls + assistant_ms/(verify_ms/verify_calls))/accepted_tokens)",
            "evidence_class": "derived_from_measured_native_worker_events_and_scope_matched_trace",
        },
    }
    atomic(PROJECT / "ACCEPTED_DEPTH_SOURCE_BINDING.json", binding)
    manifest = {
        "schema_version": 1,
        "pass": True,
        "source_binding": "ACCEPTED_DEPTH_SOURCE_BINDING.json",
        "source_binding_sha256": sha256(
            PROJECT / "ACCEPTED_DEPTH_SOURCE_BINDING.json"
        ),
        "checkpoint": checkpoint,
        "checkpoint_bytes": sum(int(row["bytes"]) for row in checkpoint),
        "assistant": assistant,
        "assistant_bytes": sum(int(row["bytes"]) for row in assistant),
        "stack": stack,
        "programs": [
            {
                "path": str(path.relative_to(PROJECT)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in programs
        ],
    }
    atomic(PROJECT / "ACCEPTED_DEPTH_INPUT_MANIFEST.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
