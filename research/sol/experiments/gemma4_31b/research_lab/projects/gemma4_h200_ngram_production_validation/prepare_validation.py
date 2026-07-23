#!/usr/bin/env python3
"""Freeze the admitted n-gram inputs and normalize persisted SSE evidence."""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil


ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT.parent / "gemma4_h200_ngram_speculative_endpoint"
PAIR = SOURCE / "artifacts/ngram-diagnostic-20260723t0815z/pair"
SNAPSHOT = ROOT / "inputs/bound"
ARTIFACT = ROOT / "artifacts/persisted-pair-normalization"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def events(path: pathlib.Path) -> tuple[list[dict], int, bool]:
    parsed: list[dict] = []
    malformed = 0
    done = False
    for line in path.read_text(errors="replace").splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            done = True
            continue
        try:
            parsed.append(json.loads(payload))
        except json.JSONDecodeError:
            malformed += 1
    return parsed, malformed, done


def normalize(path: pathlib.Path) -> dict:
    parsed, malformed, done = events(path)
    chunks: list[str] = []
    usage_events = 0
    finish_reasons: list[str] = []
    for event in parsed:
        choices = event.get("choices") or []
        if not choices:
            if event.get("usage") is not None:
                usage_events += 1
            continue
        choice = choices[0]
        text = choice.get("text")
        if isinstance(text, str):
            chunks.append(text)
        if choice.get("finish_reason") is not None:
            finish_reasons.append(choice["finish_reason"])
    nonempty = [text for text in chunks if text]
    incremental = "".join(chunks)
    terminal = nonempty[-1] if nonempty else ""
    emitted = ""
    representation_conflicts = 0
    for text in nonempty:
        if text.startswith(emitted):
            emitted = text
        elif emitted.startswith(text):
            continue
        else:
            representation_conflicts += 1
            emitted += text
    return {
        "raw_sha256": sha256(path),
        "data_events": len(parsed),
        "malformed_data_events": malformed,
        "done": done,
        "usage_only_events": usage_events,
        "text_events": len(chunks),
        "nonempty_text_events": len(nonempty),
        "finish_reasons": finish_reasons,
        "strategies": {
            "incremental_concat": {"sha256": hashlib.sha256(incremental.encode()).hexdigest(), "bytes": len(incremental)},
            "terminal_nonempty_chunk": {"sha256": hashlib.sha256(terminal.encode()).hexdigest(), "bytes": len(terminal)},
            "prefix_aware_reducer": {"sha256": hashlib.sha256(emitted.encode()).hexdigest(), "bytes": len(emitted), "representation_conflicts": representation_conflicts},
        },
    }


def main() -> None:
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    files = [
        SOURCE / "EVIDENCE_BINDING.json",
        SOURCE / "NGRAM_CONTRACT.json",
        SOURCE / "inputs/bound/exact_runner.py",
        SOURCE / "inputs/bound/endpoint_entrypoint.py",
        SOURCE / "inputs/bound/sitecustomize.py",
        SOURCE / "inputs/bound/install_endpoint_patch.py",
        SOURCE / "inputs/bound/qkv_epilogue_discriminator.py",
        ROOT / "EVIDENCE_BINDING.json",
        ROOT / "DIRECTOR_RESPONSE_EQUIVALENCE_SCREEN.json",
    ]
    manifest = []
    for source in files:
        target = SNAPSHOT / source.name
        if not target.exists() or sha256(target) != sha256(source):
            shutil.copy2(source, target)
        manifest.append({"source": str(source), "snapshot": str(target), "sha256": sha256(target)})
    rows = []
    for index in range(32):
        control = normalize(PAIR / "control" / f"response-{index:02d}.sse")
        candidate = normalize(PAIR / "candidate" / f"response-{index:02d}.sse")
        comparisons = {
            name: control["strategies"][name]["sha256"] == candidate["strategies"][name]["sha256"]
            for name in control["strategies"]
        }
        rows.append({"index": index, "control": control, "candidate": candidate, "equal_by_strategy": comparisons})
    summary = {
        "schema_version": 1,
        "classification": "persisted_sse_normalization_not_quality_terminal",
        "source_pair": str(PAIR),
        "bound_inputs": manifest,
        "request_count": len(rows),
        "equal_counts": {name: sum(row["equal_by_strategy"][name] for row in rows) for name in rows[0]["equal_by_strategy"]},
        "rows": rows,
    }
    (ARTIFACT / "NORMALIZED_PERSISTED_PAIR.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary["equal_counts"], sort_keys=True))


if __name__ == "__main__":
    main()
