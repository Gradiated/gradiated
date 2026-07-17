#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path


EXPECTED = {
    "glm4_moe.py": "2a1a1e0a56009cc98b3c0fc5ec106ee7a3c4f219469df2f3a21e40eb9401d2f8",
    "glm4_moe_lite.py": "6a984f701d46dfa05389a45d7aedde6a10ef45a6f59e73d3bbfa1e82f556b4a9",
}


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"expected one occurrence: {old!r}")
    return text.replace(old, new)


def patch(path: Path, name: str) -> dict[str, str]:
    before = path.read_bytes()
    digest = hashlib.sha256(before).hexdigest()
    if digest != EXPECTED[name]:
        raise RuntimeError(f"unexpected {name} sha256 {digest}")
    text = before.decode()
    text = replace_once(text, "import typing\n", "import os\nimport typing\n")
    if name == "glm4_moe.py":
        text = replace_once(
            text,
            "if config.n_shared_experts is not None:\n",
            "if config.n_shared_experts is not None and os.environ.get(\"GLM_MOE_TOP2_NO_SHARED\") != \"1\":\n",
        )
        text = replace_once(
            text,
            "top_k=config.num_experts_per_tok,\n",
            "top_k=2 if os.environ.get(\"GLM_MOE_TOP2_NO_SHARED\") == \"1\" else config.num_experts_per_tok,\n",
        )
    else:
        text = replace_once(
            text,
            "        for name, loaded_weight in weights:\n",
            "        for name, loaded_weight in weights:\n            if os.environ.get(\"GLM_MOE_TOP2_NO_SHARED\") == \"1\" and \"mlp.shared_experts.\" in name:\n                continue\n",
        )
    after = text.encode()
    path.write_bytes(after)
    return {"before": digest, "after": hashlib.sha256(after).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root
    rows = {name: patch(root / name, name) for name in EXPECTED}
    args.evidence.write_text(json.dumps({"switch": "GLM_MOE_TOP2_NO_SHARED=1", "files": rows}, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
