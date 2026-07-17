#!/usr/bin/env python3
"""Materialize and audit the two exact selective-W4 serving roots."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path


HERE = Path(__file__).parent
SOURCE = Path("/root/.cache/glm47flash-awq-ab31d120")
IMAGE = "glm-vllm:0.15.0-transformers-1618d44"
OUT = HERE / "artifacts" / "local_admission_r3"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def header(path: Path) -> tuple[int, dict]:
    with path.open("rb") as f:
        size = struct.unpack("<Q", f.read(8))[0]
        return 8 + size, json.loads(f.read(size))


def tensor_hashes(root: Path, index: dict) -> dict[str, str]:
    result = {}
    cache = {}
    for name, shard in index["weight_map"].items():
        if shard not in cache:
            cache[shard] = header(root / shard)
        offset, items = cache[shard]
        start, end = items[name]["data_offsets"]
        h = hashlib.sha256()
        with (root / shard).open("rb") as f:
            f.seek(offset + start)
            remaining = end - start
            while remaining:
                block = f.read(min(1 << 20, remaining)); h.update(block); remaining -= len(block)
        result[name] = h.hexdigest()
    return result


def selected(name: str, include_head: bool) -> bool:
    return (include_head and name == "lm_head.weight") or (".mlp.shared_experts." in name and ".layers.47." not in name and name.endswith(".weight"))


def materialize(label: str, include_head: bool) -> dict:
    temp = Path(tempfile.mkdtemp(prefix=f"glm47-{label}-", dir="/root/.cache"))
    try:
        for path in SOURCE.iterdir():
            if path.is_file(): shutil.copy2(path, temp / path.name)
        evidence = temp / "binding.json"
        command = ["docker", "run", "--rm", "-v", f"{temp}:/model", "-v", f"{HERE}:/project:ro", "-e", "GLM_HEAD_SHARED_ROOT=/model", "-e", f"GLM_HEAD_SHARED_OUT=/model/binding.json", "-e", f"GLM_HEAD_SHARED_INCLUDE_HEAD={int(include_head)}", "--entrypoint", "python3", IMAGE, "/project/head_shared_w4_bind.py"]
        completed = subprocess.run(command, text=True, capture_output=True, timeout=3600)
        if completed.returncode:
            raise RuntimeError(f"binder failed for {label}: {completed.stderr[-2000:]}")
        index = json.loads((temp / "model.safetensors.index.json").read_text())
        source_index = json.loads((SOURCE / "model.safetensors.index.json").read_text())
        before, after = tensor_hashes(SOURCE, source_index), tensor_hashes(temp, index)
        changed = [name for name in source_index["weight_map"] if selected(name, include_head)]
        expected_new = {name.removesuffix(".weight") + suffix for name in changed for suffix in (".weight_packed", ".weight_scale", ".weight_shape")}
        unrelated = set(source_index["weight_map"]) - set(changed)
        identity = all(before[name] == after.get(name) for name in unrelated)
        closure = len(changed) == (139 if include_head else 138) and expected_new <= set(index["weight_map"]) and not (set(changed) & set(index["weight_map"]))
        manifest_sha = sha(temp / "model-files-manifest.json")
        root = Path(f"/root/.cache/glm47flash-awq-{label}-{manifest_sha[:12]}")
        os.replace(temp, root)
        return {"label": label, "root": str(root), "manifest_sha256": manifest_sha, "weight_bytes": json.loads((root / "model-files-manifest.json").read_text())["weight_bytes"], "changed_bf16_tensors": len(changed), "derived_w4_tensors": len(expected_new), "closure_pass": closure, "unrelated_tensor_count": len(unrelated), "unrelated_byte_identity_pass": identity, "binding_sha256": sha(root / "binding.json"), "source_config_sha256": sha(SOURCE / "config.json"), "source_index_sha256": sha(SOURCE / "model.safetensors.index.json")}
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    result = {"schema_version": 1, "source": str(SOURCE), "combined": materialize("full47-head-shared-w4", True), "shared_w4_bf16_head": materialize("full47-shared-w4-bf16-head", False)}
    result["pass"] = all(x["closure_pass"] and x["unrelated_byte_identity_pass"] for x in (result["combined"], result["shared_w4_bf16_head"]))
    path = OUT / "LOCAL_ADMISSION.json"; path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"artifact": str(path), "pass": result["pass"]}, sort_keys=True))


if __name__ == "__main__": main()
