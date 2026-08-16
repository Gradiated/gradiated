#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import pathlib
import random
import time
from contextlib import ExitStack

import torch
import torch.nn.functional as F
from safetensors import safe_open
from safetensors.torch import save_file


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def resolve_language_model(model: torch.nn.Module) -> torch.nn.Module:
    candidates = [model]
    for _ in range(4):
        next_candidates = []
        for candidate in candidates:
            if hasattr(candidate, "language_model"):
                language_model = candidate.language_model
                if hasattr(language_model, "layers"):
                    return language_model
            if hasattr(candidate, "model"):
                next_candidates.append(candidate.model)
        candidates = next_candidates
    raise RuntimeError("could not resolve Gemma4 language_model.layers")


def capture_teacher(
    checkpoint: pathlib.Path,
    bodies: pathlib.Path,
    capture_root: pathlib.Path,
    layer_ids: list[int],
    positions: list[int],
) -> dict:
    from transformers import Gemma4ForConditionalGeneration

    started = time.time()
    model = Gemma4ForConditionalGeneration.from_pretrained(
        checkpoint,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        low_cpu_mem_usage=True,
    )
    model.to("cuda")
    model.eval()
    language_model = resolve_language_model(model)
    capture_root.mkdir(parents=True, exist_ok=False)
    rows = []
    for request_index in range(32):
        body = json.loads((bodies / f"request-{request_index:02d}.json").read_text())
        input_ids = torch.tensor(body["prompt"], dtype=torch.long, device="cuda").unsqueeze(0)
        captured_inputs: dict[int, torch.Tensor] = {}
        captured_targets: dict[int, torch.Tensor] = {}
        captured_rotary: dict[str, torch.Tensor] = {}
        handles = []
        for layer_id in layer_ids:
            attention = language_model.layers[layer_id].self_attn

            def pre_hook(module, args, kwargs, layer_id=layer_id):
                hidden = kwargs.get("hidden_states") if kwargs else None
                if hidden is None:
                    hidden = args[0]
                captured_inputs[layer_id] = hidden[0].detach().to("cpu", dtype=torch.bfloat16)
                if not captured_rotary:
                    cosine, sine = kwargs["position_embeddings"]
                    captured_rotary["cosine"] = cosine[0, :, :128].detach().to("cpu", dtype=torch.bfloat16)
                    captured_rotary["sine"] = sine[0, :, :128].detach().to("cpu", dtype=torch.bfloat16)

            def post_hook(module, args, kwargs, output, layer_id=layer_id):
                hidden = output[0] if isinstance(output, tuple) else output
                captured_targets[layer_id] = hidden[0, positions].detach().to("cpu", dtype=torch.bfloat16)

            handles.append(attention.register_forward_pre_hook(pre_hook, with_kwargs=True))
            handles.append(attention.register_forward_hook(post_hook, with_kwargs=True))
        with torch.inference_mode():
            model(input_ids=input_ids, use_cache=False, return_dict=True)
        for handle in handles:
            handle.remove()
        if set(captured_inputs) != set(layer_ids) or set(captured_targets) != set(layer_ids):
            raise RuntimeError(f"incomplete capture for request {request_index}")
        output_path = capture_root / f"request-{request_index:02d}.pt"
        torch.save(
            {
                "request_index": request_index,
                "input_sha256": hashlib.sha256((bodies / f"request-{request_index:02d}.json").read_bytes()).hexdigest(),
                "inputs": captured_inputs,
                "targets": captured_targets,
                "rotary": captured_rotary,
            },
            output_path,
        )
        rows.append({"request_index": request_index, "bytes": output_path.stat().st_size})
        atomic_json(capture_root / "PROGRESS.json", {"completed": request_index + 1, "rows": rows})
    del model, language_model
    gc.collect()
    torch.cuda.empty_cache()
    result = {"status": "captured", "requests": 32, "layers": layer_ids, "bytes": sum(x["bytes"] for x in rows), "seconds": time.time() - started}
    atomic_json(capture_root / "CAPTURE.json", result)
    return result


def checkpoint_tensors(checkpoint: pathlib.Path, layer_id: int) -> dict[str, torch.Tensor]:
    index = json.loads((checkpoint / "model.safetensors.index.json").read_text())["weight_map"]
    prefix = f"model.language_model.layers.{layer_id}.self_attn."
    suffixes = ["q_proj.weight", "k_proj.weight", "o_proj.weight", "q_norm.weight", "k_norm.weight"]
    result = {}
    with ExitStack() as stack:
        shards = {}
        for suffix in suffixes:
            full_name = prefix + suffix
            shard_name = index[full_name]
            if shard_name not in shards:
                shards[shard_name] = stack.enter_context(safe_open(checkpoint / shard_name, framework="pt", device="cpu"))
            result[suffix] = shards[shard_name].get_tensor(full_name)
    return result


def sliced_student(original: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    return {
        "q_proj.weight": original["q_proj.weight"].reshape(32, 512, 5376)[:, :256].reshape(8192, 5376).contiguous(),
        "k_proj.weight": original["k_proj.weight"].reshape(4, 512, 5376)[:, :256].reshape(1024, 5376).contiguous(),
        "o_proj.weight": original["o_proj.weight"].reshape(5376, 32, 512)[:, :, :256].reshape(5376, 8192).contiguous(),
        "q_norm.weight": original["q_norm.weight"][:256].contiguous(),
        "k_norm.weight": original["k_norm.weight"][:256].contiguous(),
    }


def rms_norm(value: torch.Tensor, weight: torch.Tensor | None) -> torch.Tensor:
    normalized = value.float() * torch.rsqrt(value.float().pow(2).mean(dim=-1, keepdim=True) + 1e-6)
    if weight is not None:
        normalized = normalized * weight.float()
    return normalized.to(dtype=value.dtype)


def apply_rope(value: torch.Tensor, cosine: torch.Tensor, sine: torch.Tensor) -> torch.Tensor:
    rotary = value[..., :128].float()
    untouched = value[..., 128:]
    cosine = cosine.float().unsqueeze(1)
    sine = sine.float().unsqueeze(1)
    first, second = rotary.chunk(2, dim=-1)
    rotated = torch.cat((-second, first), dim=-1)
    encoded = rotary * cosine + rotated * sine
    return torch.cat((encoded.to(dtype=value.dtype), untouched), dim=-1)


def candidate_attention(hidden: torch.Tensor, rotary: dict[str, torch.Tensor], weights: dict[str, torch.Tensor], query_positions: torch.Tensor) -> torch.Tensor:
    hidden = hidden.to("cuda", dtype=torch.bfloat16)
    selected = hidden.index_select(0, query_positions)
    q = F.linear(selected, weights["q_proj.weight"]).reshape(-1, 32, 256)
    k = F.linear(hidden, weights["k_proj.weight"]).reshape(-1, 4, 256)
    v = k
    q = rms_norm(q, weights["q_norm.weight"])
    k = rms_norm(k, weights["k_norm.weight"])
    v = rms_norm(v, None)
    all_positions = torch.arange(hidden.shape[0], device=hidden.device)
    cosine = rotary["cosine"].to("cuda")
    sine = rotary["sine"].to("cuda")
    q = apply_rope(q, cosine.index_select(0, query_positions), sine.index_select(0, query_positions))
    k = apply_rope(k, cosine, sine)
    k = k.repeat_interleave(8, dim=1)
    v = v.repeat_interleave(8, dim=1)
    scores = torch.einsum("qhd,khd->qhk", q.float(), k.float())
    causal = all_positions.unsqueeze(0) <= query_positions.unsqueeze(1)
    scores = scores.masked_fill(~causal.unsqueeze(1), -torch.inf)
    probability = torch.softmax(scores, dim=-1).to(dtype=torch.bfloat16)
    attended = torch.einsum("qhk,khd->qhd", probability, v).reshape(-1, 8192)
    return F.linear(attended, weights["o_proj.weight"])


def metric_accumulator() -> dict[str, float]:
    return {"squared_error": 0.0, "target_squared": 0.0, "dot": 0.0, "candidate_squared": 0.0, "count": 0.0}


def add_metrics(accumulator: dict[str, float], candidate: torch.Tensor, target: torch.Tensor) -> None:
    candidate = candidate.float().reshape(-1)
    target = target.float().reshape(-1)
    accumulator["squared_error"] += float((candidate - target).pow(2).sum())
    accumulator["target_squared"] += float(target.pow(2).sum())
    accumulator["dot"] += float((candidate * target).sum())
    accumulator["candidate_squared"] += float(candidate.pow(2).sum())
    accumulator["count"] += target.numel()


def finalize_metrics(accumulator: dict[str, float]) -> dict[str, float]:
    return {
        "nrmse": math.sqrt(accumulator["squared_error"] / accumulator["target_squared"]),
        "cosine": accumulator["dot"] / math.sqrt(accumulator["candidate_squared"] * accumulator["target_squared"]),
        **accumulator,
    }


def evaluate(capture_root: pathlib.Path, request_indices: list[int], layer_id: int, weights: dict[str, torch.Tensor], positions: torch.Tensor) -> dict[str, float]:
    metrics = metric_accumulator()
    with torch.inference_mode():
        for request_index in request_indices:
            capture = torch.load(capture_root / f"request-{request_index:02d}.pt", map_location="cpu", weights_only=True)
            candidate = candidate_attention(capture["inputs"][layer_id], capture["rotary"], weights, positions)
            add_metrics(metrics, candidate, capture["targets"][layer_id].to("cuda"))
    return finalize_metrics(metrics)


def train(contract: dict, checkpoint: pathlib.Path, capture_root: pathlib.Path, output_root: pathlib.Path) -> dict:
    torch.manual_seed(contract["seed"])
    random.seed(contract["seed"])
    positions = torch.tensor(contract["sampled_query_positions"], device="cuda", dtype=torch.long)
    overlay: dict[str, torch.Tensor] = {}
    layer_rows = []
    for layer_id in contract["global_layer_ids"]:
        initial = sliced_student(checkpoint_tensors(checkpoint, layer_id))
        weights = {name: torch.nn.Parameter(value.to("cuda", dtype=torch.bfloat16)) for name, value in initial.items()}
        baseline = evaluate(capture_root, contract["split"]["holdout_request_indices"], layer_id, weights, positions)
        optimizer_contract = contract["optimizer"]
        optimizer = torch.optim.AdamW(
            list(weights.values()),
            lr=optimizer_contract["learning_rate"],
            betas=tuple(optimizer_contract["betas"]),
            eps=optimizer_contract["eps"],
            weight_decay=optimizer_contract["weight_decay"],
        )
        losses = []
        for request_index in contract["split"]["train_request_indices"]:
            capture = torch.load(capture_root / f"request-{request_index:02d}.pt", map_location="cpu", weights_only=True)
            target = capture["targets"][layer_id].to("cuda", dtype=torch.bfloat16)
            candidate = candidate_attention(capture["inputs"][layer_id], capture["rotary"], weights, positions)
            normalized_mse = (candidate.float() - target.float()).pow(2).mean() / target.float().pow(2).mean().clamp_min(1e-12)
            cosine_loss = 1.0 - F.cosine_similarity(candidate.float().reshape(1, -1), target.float().reshape(1, -1)).mean()
            loss = normalized_mse + 0.05 * cosine_loss
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(list(weights.values()), optimizer_contract["gradient_clip_norm"])
            optimizer.step()
            losses.append(float(loss.detach()))
        trained = evaluate(capture_root, contract["split"]["holdout_request_indices"], layer_id, weights, positions)
        row = {"layer_id": layer_id, "baseline": baseline, "trained": trained, "train_loss_first": losses[0], "train_loss_last": losses[-1], "updates": len(losses)}
        layer_rows.append(row)
        for suffix, value in weights.items():
            overlay[f"language_model.layers.{layer_id}.self_attn.{suffix}"] = value.detach().to("cpu", dtype=torch.bfloat16).contiguous()
        del optimizer, weights
        gc.collect()
        torch.cuda.empty_cache()
        atomic_json(output_root / "TRAIN_PROGRESS.json", {"layers": layer_rows})
    overlay_path = output_root / "overlay.safetensors"
    save_file(overlay, overlay_path)
    aggregate_baseline = metric_accumulator()
    aggregate_trained = metric_accumulator()
    for row in layer_rows:
        for key in aggregate_baseline:
            aggregate_baseline[key] += row["baseline"][key]
            aggregate_trained[key] += row["trained"][key]
    result = {
        "schema_version": 1,
        "layers": layer_rows,
        "baseline": finalize_metrics(aggregate_baseline),
        "trained": finalize_metrics(aggregate_trained),
        "heldout_nrmse_improved": finalize_metrics(aggregate_trained)["nrmse"] < finalize_metrics(aggregate_baseline)["nrmse"],
        "heldout_cosine_improved": finalize_metrics(aggregate_trained)["cosine"] > finalize_metrics(aggregate_baseline)["cosine"],
        "overlay_tensor_count": len(overlay),
        "overlay_bytes": overlay_path.stat().st_size,
        "overlay_sha256": hashlib.sha256(overlay_path.read_bytes()).hexdigest(),
    }
    result["fidelity_gate_pass"] = result["heldout_nrmse_improved"] and result["heldout_cosine_improved"] and result["overlay_tensor_count"] == 50
    atomic_json(output_root / "FIDELITY.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=pathlib.Path, required=True)
    parser.add_argument("--bodies", type=pathlib.Path, required=True)
    parser.add_argument("--contract", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    contract = json.loads(args.contract.read_text())
    atomic_json(args.output / "IDENTITY.json", {"contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest(), "implementation_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()})
    capture = capture_teacher(args.checkpoint, args.bodies, args.output / "capture", contract["global_layer_ids"], contract["sampled_query_positions"])
    fidelity = train(contract, args.checkpoint, args.output / "capture", args.output)
    atomic_json(args.output / "DISTILL_TERMINAL.json", {"status": "terminal", "capture": capture, "fidelity": fidelity})
    return 0 if fidelity["fidelity_gate_pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
