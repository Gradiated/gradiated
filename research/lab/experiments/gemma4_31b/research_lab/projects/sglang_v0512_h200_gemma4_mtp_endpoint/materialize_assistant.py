#!/usr/bin/env python3
"""Materialize the small immutable Gemma 4 assistant without touching target weights."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BINDINGS = json.loads((ROOT / "BINDINGS.json").read_text())
MODEL = BINDINGS["assistant"]["model"]
REVISION = BINDINGS["assistant"]["revision"]
OUTPUT = ROOT / "artifacts" / "assistant"
TERMINAL = ROOT / "artifacts" / "ASSISTANT_TERMINAL.json"
FILES = ("config.json", "generation_config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    started = time.time()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in FILES:
        target = OUTPUT / name
        partial = target.with_suffix(target.suffix + ".part")
        if not target.is_file():
            partial.unlink(missing_ok=True)
            url = f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}"
            result = subprocess.run(
                ["curl", "--fail", "--location", "--retry", "3", "--retry-delay", "2", "--silent", "--show-error", url, "--output", str(partial)],
                text=True,
                capture_output=True,
                timeout=5400,
            )
            if result.returncode:
                partial.unlink(missing_ok=True)
                raise RuntimeError(f"download {name} failed: {result.stderr[-1000:]}")
            partial.replace(target)
        rows.append({"name": name, "bytes": target.stat().st_size, "sha256": digest(target)})
    terminal = {
        "classification": "gemma4_assistant_materialized",
        "pass": all(row["bytes"] > 0 for row in rows),
        "model": MODEL,
        "revision": REVISION,
        "root": str(OUTPUT),
        "files": rows,
        "total_bytes": sum(row["bytes"] for row in rows),
        "elapsed_seconds": round(time.time() - started, 3),
    }
    temporary = TERMINAL.with_suffix(".json.part")
    temporary.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    temporary.replace(TERMINAL)
    return 0 if terminal["pass"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        TERMINAL.parent.mkdir(parents=True, exist_ok=True)
        TERMINAL.write_text(json.dumps({"classification": "assistant_materialization_failure", "pass": False, "error_type": type(error).__name__, "message": str(error)[:2000]}, indent=2) + "\n")
        raise
