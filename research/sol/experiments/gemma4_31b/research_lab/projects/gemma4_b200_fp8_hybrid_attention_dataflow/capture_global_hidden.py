from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--layer", type=int, default=5)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.checkpoint, revision="b9ea41a2887d8607f594846523f94c6cc75ac8a4")
    token = tokenizer.eos_token_id or 1
    rows, tokens = (32, 1) if args.smoke else (1, 4214)
    ids = torch.full((rows, tokens), token, dtype=torch.long, device="cuda")
    model = AutoModelForCausalLM.from_pretrained(
        args.checkpoint, torch_dtype=torch.bfloat16, device_map="cuda", local_files_only=True
    ).eval()
    captured: list[torch.Tensor] = []
    module = model.model.language_model.layers[args.layer].self_attn
    class Captured(Exception):
        pass
    def capture(_module, _args, kwargs):
        captured.append(kwargs["hidden_states"].detach().cpu())
        raise Captured
    hook = module.register_forward_pre_hook(capture, with_kwargs=True)
    with torch.inference_mode():
        if args.smoke:
            try:
                model(input_ids=ids, use_cache=False)
            except Captured:
                pass
        else:
            for _ in range(32):
                try:
                    model(input_ids=ids, use_cache=False)
                except Captured:
                    pass
    hook.remove()
    expected = (rows, tokens, 5376)
    if len(captured) != (1 if args.smoke else 32) or any(tuple(value.shape) != expected for value in captured):
        raise RuntimeError(f"unexpected exact-model layer input {[tuple(x.shape) for x in captured]}")
    hidden = torch.cat(captured, dim=0)[:, -1, :].contiguous()
    if args.smoke:
        print(json.dumps({"capture_smoke": True, "shape": list(hidden.shape), "dtype": str(hidden.dtype)}))
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    torch.save({"hidden": hidden, "source": "exact_gemma4_layer5_attention_pre_hook", "prompt_tokens": 4214}, temp)
    temp.replace(args.output)
    manifest = {"hidden": str(args.output), "sha256": digest(args.output), "shape": list(hidden.shape), "dtype": str(hidden.dtype), "layer": args.layer, "production_geometry": "M32 decode, prompt 4214, completion 358, TP=1"}
    manifest_path = args.output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
