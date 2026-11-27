"""Weight-space interpolation between a fine-tuned export and the base checkpoint (and optional souping).

    python -m gdecide.merge --base CKPT --models EXPORT [EXPORT ...] --weights 0.7 [...] --out DIR

The output is ``sum_i weights[i] * models[i] + (1 - sum(weights)) * base`` for every backbone tensor and the
readout, written as a loadable checkpoint (the first model's non-weight files plus a MODIFICATIONS note).
Tensors are processed one at a time in float32, so memory stays near one shard.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def index(path: Path) -> dict[str, str]:
    return json.loads((path / "model.safetensors.index.json").read_text())["weight_map"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--weights", nargs="+", type=float, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    assert len(args.models) == len(args.weights)
    base, models, out = Path(args.base), [Path(m) for m in args.models], Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for f in models[0].iterdir():
        if f.is_file() and not f.name.startswith("model-") and f.name not in ("model.safetensors.index.json", "readout.safetensors", "done", "SHA256SUMS"):
            shutil.copy2(f, out / f.name)
    rest = 1.0 - sum(args.weights)
    maps = [index(m) for m in models]
    base_map = index(base)
    handles: dict[Path, object] = {}

    def tensor(root: Path, file: str, key: str):
        p = root / file
        if p not in handles:
            handles[p] = safe_open(str(p), framework="pt")
        return handles[p].get_tensor(key)

    def mix(get_base, getters):
        acc = get_base().float() * rest
        for w, g in zip(args.weights, getters, strict=True):
            acc += g().float() * w
        return acc.to(torch.bfloat16)

    weight_map, shard, size, files = {}, {}, 0, []
    total = 0

    def flush():
        nonlocal shard, size
        if shard:
            name = f"model-{len(files) + 1:05d}.safetensors"
            save_file(shard, str(out / name), metadata={"format": "pt"})
            files.append(name)
            weight_map.update({k: name for k in shard})
            shard, size = {}, 0

    for key in sorted(maps[0]):
        shard[key] = mix(lambda: tensor(base, base_map[key], key), [lambda m=m, mp=mp: tensor(m, mp[key], key) for m, mp in zip(models, maps)])
        size += shard[key].numel() * 2
        total += shard[key].numel() * 2
        if size >= 5 * 2**30:
            flush()
    flush()
    (out / "model.safetensors.index.json").write_text(json.dumps({"metadata": {"total_size": total}, "weight_map": weight_map}, indent=1))
    if (base / "readout.safetensors").exists():  # Decider checkpoints; KnowLine reads labels from the tied embedding
        readout = mix(lambda: tensor(base, "readout.safetensors", "weight"), [lambda m=m: tensor(m, "readout.safetensors", "weight") for m in models])
        save_file({"weight": readout}, str(out / "readout.safetensors"))
    (out / "MODIFICATIONS").write_text("Gradiated Decide: weight interpolation " + json.dumps({"base": str(base), "models": [str(m) for m in models], "weights": args.weights}) + "\n")
    (out / "done").write_text("ok\n")
    print(json.dumps({"out": str(out), "tensors": len(weight_map), "files": len(files)}))


if __name__ == "__main__":
    main()
