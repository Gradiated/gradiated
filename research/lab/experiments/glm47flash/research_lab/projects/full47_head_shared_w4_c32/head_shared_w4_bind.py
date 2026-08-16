#!/usr/bin/env python3
"""Bind the selective full-47 head/shared-expert W4 payload in the pinned image."""
import hashlib
import json
import os
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file


ROOT = Path(os.environ.get("GLM_HEAD_SHARED_ROOT", "/workspace/model-awq"))
VLLM = Path("/usr/local/lib/python3.12/dist-packages/vllm/model_executor/layers/quantization/compressed_tensors/compressed_tensors.py")
OUT = Path(os.environ.get("GLM_HEAD_SHARED_OUT", "/workspace/campaign-100-vllm-awq-batch/head-shared-w4-binding.json"))


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def selected(name: str) -> bool:
    return (os.environ.get("GLM_HEAD_SHARED_INCLUDE_HEAD", "1") == "1" and name == "lm_head.weight") or (".mlp.shared_experts." in name and ".layers.47." not in name and name.endswith(".weight"))


def packed(weight: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    rows, cols = weight.shape
    grouped = weight.float().reshape(rows, cols // 32, 32)
    scale = grouped.abs().amax(dim=-1).div(7).clamp_min(torch.finfo(torch.float32).tiny).to(torch.bfloat16)
    q = torch.round(grouped / scale.float().unsqueeze(-1)).clamp(-8, 7).to(torch.int16)
    nibbles = (q & 15).reshape(rows, cols // 8, 8)
    value = sum(nibbles[..., i] << (4 * i) for i in range(8)).to(torch.int32)
    return value.contiguous(), scale.contiguous(), torch.tensor([rows, cols], dtype=torch.int64)


def patch_runtime() -> dict:
    before = VLLM.read_text()
    needle = "from vllm.model_executor.layers.linear import (\n    LinearBase,"
    condition = "if isinstance(layer, LinearBase):"
    if before.count(needle) != 1 or before.count(condition) != 1:
        raise RuntimeError("unexpected compressed-tensors source layout")
    text = before.replace(needle, "from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead\n" + needle)
    text = text.replace(condition, "if isinstance(layer, (LinearBase, ParallelLMHead)):")
    VLLM.write_text(text)
    return {"source_sha256_before": hashlib.sha256(before.encode()).hexdigest(), "source_sha256_after": hashlib.sha256(text.encode()).hexdigest(), "changed_occurrences": 1}


def main() -> None:
    config_path, index_path = ROOT / "config.json", ROOT / "model.safetensors.index.json"
    config, index = json.loads(config_path.read_text()), json.loads(index_path.read_text())
    group = config["quantization_config"]["config_groups"]["group_0"]
    config["quantization_config"]["config_groups"]["parallel_lm_head_w4"] = {
        **group, "targets": ["ParallelLMHead"]
    }
    names = [name for name in index["weight_map"] if selected(name)]
    expected = 139 if os.environ.get("GLM_HEAD_SHARED_INCLUDE_HEAD", "1") == "1" else 138
    if len(names) != expected:
        raise RuntimeError(f"unexpected selective scope count: {len(names)}")
    grouped = {}
    for name in names:
        grouped.setdefault(index["weight_map"][name], []).append(name)
    converted = []
    for shard, targets in grouped.items():
        path, temporary = ROOT / shard, ROOT / (shard + ".head-shared.tmp")
        tensors = {}
        with safe_open(str(path), framework="pt", device="cpu") as source:
            for name in source.keys():
                if name in targets:
                    p, s, shape = packed(source.get_tensor(name))
                    prefix = name.removesuffix(".weight")
                    tensors[prefix + ".weight_packed"] = p
                    tensors[prefix + ".weight_scale"] = s
                    tensors[prefix + ".weight_shape"] = shape
                    converted.append({"source": name, "packed_shape": list(p.shape), "scale_shape": list(s.shape)})
                else:
                    tensors[name] = source.get_tensor(name)
        save_file(tensors, str(temporary), metadata={"format": "pt"})
        temporary.replace(path)
    for name in names:
        del index["weight_map"][name]
        prefix = name.removesuffix(".weight")
        for suffix in (".weight_packed", ".weight_scale", ".weight_shape"):
            index["weight_map"][prefix + suffix] = index["weight_map"].get(prefix + suffix, next(shard for shard, targets in grouped.items() if name in targets))
    index["metadata"]["total_size"] = sum((ROOT / p).stat().st_size for p in sorted(set(index["weight_map"].values())))
    config["quantization_config"]["ignore"] = [x for x in config["quantization_config"].get("ignore", []) if x not in {n.removesuffix(".weight") for n in names}]
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    rows = []
    for path in sorted(p for p in ROOT.iterdir() if p.is_file() and p.name not in {"model-files.sha256", "model-files-manifest.json", ".campaign-integrity-v1"}):
        rows.append({"path": path.name, "bytes": path.stat().st_size, "sha256": digest(path)})
    manifest = {"schema_version": 2, "repository": "local-derived/glm47flash-full47-head-shared-w4", "revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881", "shard_count": 4, "weight_bytes": sum(r["bytes"] for r in rows if r["path"].endswith(".safetensors")), "files": rows}
    (ROOT / "model-files-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (ROOT / "model-files.sha256").write_text("".join(f'{r["sha256"]}  {r["path"]}\n' for r in rows))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"scope_tensor_count": len(converted), "converted": converted, "runtime_patch": patch_runtime(), "manifest_sha256": digest(ROOT / "model-files-manifest.json"), "weight_bytes": manifest["weight_bytes"]}, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
