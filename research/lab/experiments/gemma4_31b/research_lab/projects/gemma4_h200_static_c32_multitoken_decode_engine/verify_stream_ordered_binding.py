#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

here = Path(__file__).resolve().parent
binding = json.loads((here / "STREAM_ORDERED_CHAIN_BINDING.json").read_text())
actual = hashlib.sha256((here / binding["intervention"]["source_template_path"]).read_bytes()).hexdigest()
if actual != binding["intervention"]["source_template_sha256"]:
    raise SystemExit(f"stream binding mismatch: {actual}")
if "No parent capture" not in binding["intervention"]["topology"]:
    raise SystemExit("stream topology mismatch")
print(json.dumps({"binding": "valid", "topology": "stream_ordered"}))
