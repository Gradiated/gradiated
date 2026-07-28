#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil


PROJECT = pathlib.Path(__file__).resolve().parent
SOURCE = (
    PROJECT.parent
    / "gemma4_h200_device_conditional_decode_graph"
)
SETS = {
    "current_stack": SOURCE / "inputs" / "current_stack",
    "admitted_upstream": SOURCE / "inputs" / "upstream",
}


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    rows: list[dict[str, object]] = []
    for label, source_root in SETS.items():
        destination_root = PROJECT / "inputs" / label
        for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
            relative = source.relative_to(source_root)
            destination = destination_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            os.chmod(destination, 0o444)
            rows.append(
                {
                    "path": str(destination.relative_to(PROJECT)),
                    "source_set": label,
                    "bytes": destination.stat().st_size,
                    "sha256": sha256(destination),
                }
            )
    atomic_json(
        PROJECT / "ADMITTED_INPUT_MANIFEST.json",
        {
            "schema_version": 1,
            "source_project": SOURCE.name,
            "files": rows,
            "pass": bool(rows),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
