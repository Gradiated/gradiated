#!/usr/bin/env python3
import hashlib
import json
import pathlib


root = pathlib.Path(__file__).resolve().parent
rows = []
for path in sorted((root / "wheels").glob("*.whl")):
    rows.append(
        {
            "path": str(path.relative_to(root)),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    )
(root / "WHEEL_LOCK.json").write_text(
    json.dumps(
        {
            "python": "3.12",
            "roots": ["llmcompressor==0.12.0", "torchvision==0.27.0"],
            "wheels": rows,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
