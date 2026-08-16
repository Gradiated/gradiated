#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import pathlib
import random
import re
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


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_language_model(model: torch.nn.Module) -> torch.nn.Module:
    candidates = [model]
    for _ in range(5):
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


def request_ids(bodies: pathlib.Path, request_index: int, selected_tokens: int) -> torch.Tensor:
    body = json.loads((bodies / f"request-{request_index:02d}.json").read_text())
    prompt = body["prompt"]
    if len(prompt) != 4214:
        raise RuntimeError(f"request {request_index} prompt geometry drifted: {len(prompt)}")
    return torch.tensor(prompt[-selected_tokens:], dtype=torch.long).unsqueeze(0)


def register_local_attention_hooks(
    language_model: torch.nn.Module,
    layer_ids: list[int],
    destination: dict[int, torch.Tensor],
) -> list[torch.utils.hooks.RemovableHandle]:
    handles = []
    for layer_id in layer_ids:
        attention = language_model.layers[layer_id].self_attn

        def hook(module, args, kwargs, output, layer_id=layer_id):
            hidden = output[0] if isinstance(output, tuple) else output
            destination[layer_id] = hidden[:, -1, :]

        handles.append(attention.register_forward_hook(hook, with_kwargs=True))
    return handles


def forward_targets(
    language_model: torch.nn.Module,
    input_ids: torch.Tensor,
    layer_ids: list[int],
) -> tuple[dict[int, torch.Tensor], torch.Tensor]:
    captured: dict[int, torch.Tensor] = {}
    handles = register_local_attention_hooks(language_model, layer_ids, captured)
    try:
        output = language_model(
            input_ids=input_ids,
            use_cache=False,
            output_hidden_states=False,
            return_dict=True,
        )
    finally:
        for handle in handles:
            handle.remove()
    if set(captured) != set(layer_ids):
        raise RuntimeError(
            f"local attention capture incomplete: missing={sorted(set(layer_ids) - set(captured))}"
        )
    final_hidden = output.last_hidden_state[:, -1, :]
    return captured, final_hidden


def capture_teacher(
    checkpoint: pathlib.Path,
    bodies: pathlib.Path,
    output_root: pathlib.Path,
    contract: dict,
) -> dict:
    terminal_path = output_root / "CAPTURE_TERMINAL.json"
    if terminal_path.exists():
        return json.loads(terminal_path.read_text())
    from transformers import Gemma4ForConditionalGeneration

    started = time.time()
    model = Gemma4ForConditionalGeneration.from_pretrained(
        checkpoint,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        low_cpu_mem_usage=True,
        local_files_only=True,
    )
    model.to("cuda")
    model.eval()
    language_model = resolve_language_model(model)
    layer_ids = contract["local_layer_ids"]
    selected_tokens = contract["token_sampling"]["selected_tokens"]
    output_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for request_index in range(32):
        target_path = output_root / f"teacher-{request_index:02d}.pt"
        if target_path.exists():
            rows.append(
                {
                    "request_index": request_index,
                    "bytes": target_path.stat().st_size,
                    "sha256": sha256(target_path),
                    "resumed": True,
                }
            )
            continue
        input_ids = request_ids(bodies, request_index, selected_tokens).to("cuda")
        with torch.inference_mode():
            blocks, final_hidden = forward_targets(language_model, input_ids, layer_ids)
        value = {
            "request_index": request_index,
            "request_sha256": sha256(bodies / f"request-{request_index:02d}.json"),
            "selected_tokens": selected_tokens,
            "block_targets": {
                layer_id: tensor[0].detach().to("cpu", dtype=torch.bfloat16)
                for layer_id, tensor in blocks.items()
            },
            "final_hidden_target": final_hidden[0].detach().to("cpu", dtype=torch.bfloat16),
        }
        temporary = target_path.with_suffix(".pt.part")
        torch.save(value, temporary)
        temporary.replace(target_path)
        rows.append(
            {
                "request_index": request_index,
                "bytes": target_path.stat().st_size,
                "sha256": sha256(target_path),
                "resumed": False,
            }
        )
        atomic_json(output_root / "CAPTURE_PROGRESS.json", {"completed": len(rows), "rows": rows})
    result = {
        "schema_version": 1,
        "status": "captured",
        "requests": 32,
        "local_layers": layer_ids,
        "selected_tokens": selected_tokens,
        "bytes": sum(row["bytes"] for row in rows),
        "seconds": time.time() - started,
        "rows": rows,
    }
    atomic_json(terminal_path, result)
    del model, language_model
    gc.collect()
    torch.cuda.empty_cache()
    return result


def checkpoint_tensor(
    checkpoint: pathlib.Path,
    index: dict[str, str],
    full_name: str,
) -> torch.Tensor:
    shard_name = index[full_name]
    with safe_open(checkpoint / shard_name, framework="pt", device="cpu") as handle:
        return handle.get_tensor(full_name)


def pair_mean(weight: torch.Tensor) -> torch.Tensor:
    expected = [16 * 256, 5376]
    if list(weight.shape) != expected:
        raise RuntimeError(f"pair-mean input shape mismatch: {list(weight.shape)}")
    return (
        weight.reshape(8, 2, 256, 5376)
        .float()
        .mean(dim=1)
        .to(dtype=weight.dtype)
        .reshape(8 * 256, 5376)
        .contiguous()
    )


def mismatch_identity(row: object) -> str:
    if isinstance(row, (tuple, list)) and row:
        return str(row[0])
    return str(row)


def load_student(
    checkpoint: pathlib.Path,
    contract: dict,
    output_root: pathlib.Path,
) -> tuple[torch.nn.Module, torch.nn.Module, list[torch.nn.Parameter]]:
    from transformers import AutoConfig, Gemma4ForConditionalGeneration

    config = AutoConfig.from_pretrained(checkpoint, local_files_only=True)
    if config.text_config.num_key_value_heads != 16 or config.text_config.num_global_key_value_heads != 4:
        raise RuntimeError("bound teacher KV geometry drifted")
    config.text_config.num_key_value_heads = 8
    model, loading_info = Gemma4ForConditionalGeneration.from_pretrained(
        checkpoint,
        config=config,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        low_cpu_mem_usage=True,
        local_files_only=True,
        ignore_mismatched_sizes=True,
        output_loading_info=True,
    )
    layer_ids = contract["local_layer_ids"]
    mismatch_names = [mismatch_identity(row) for row in loading_info.get("mismatched_keys", [])]
    mismatch_pairs = set()
    for name in mismatch_names:
        match = re.search(r"language_model\.layers\.(\d+)\.self_attn\.(k_proj|v_proj)\.weight$", name)
        if match is None:
            raise RuntimeError(f"unexpected student mismatch: {name}")
        mismatch_pairs.add((int(match.group(1)), match.group(2)))
    expected_pairs = {(layer_id, projection) for layer_id in layer_ids for projection in ("k_proj", "v_proj")}
    if mismatch_pairs != expected_pairs:
        raise RuntimeError(
            "student mismatch set is not the declared local K/V tensors: "
            f"missing={sorted(expected_pairs - mismatch_pairs)}, unexpected={sorted(mismatch_pairs - expected_pairs)}"
        )
    if loading_info.get("error_msgs"):
        raise RuntimeError(f"student loading errors: {loading_info['error_msgs']}")
    language_model = resolve_language_model(model)
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    index = json.loads((checkpoint / "model.safetensors.index.json").read_text())["weight_map"]
    initialization_rows = []
    trainable = []
    trainable_names = []
    for layer_id in layer_ids:
        for projection in ("k_proj", "v_proj"):
            full_name = f"model.language_model.layers.{layer_id}.self_attn.{projection}.weight"
            original = checkpoint_tensor(checkpoint, index, full_name)
            initialized = pair_mean(original)
            parameter = getattr(language_model.layers[layer_id].self_attn, projection).weight
            if list(parameter.shape) != [2048, 5376]:
                raise RuntimeError(f"student parameter shape drifted: {full_name} {list(parameter.shape)}")
            parameter.data.copy_(initialized)
            parameter.requires_grad_(True)
            trainable.append(parameter)
            overlay_name = f"language_model.layers.{layer_id}.self_attn.{projection}.weight"
            trainable_names.append(overlay_name)
            initialization_rows.append(
                {
                    "name": overlay_name,
                    "source_shape": list(original.shape),
                    "student_shape": list(initialized.shape),
                    "source_dtype": str(original.dtype),
                    "initial_abs_sum": float(initialized.float().abs().sum()),
                }
            )
    observed_requires_grad = [
        name.removeprefix("model.")
        for name, parameter in model.named_parameters()
        if parameter.requires_grad
    ]
    if set(observed_requires_grad) != set(trainable_names) or len(trainable) != 100:
        raise RuntimeError("trainable manifest does not contain exactly the declared 100 local K/V tensors")
    atomic_json(
        output_root / "TRAINABLE_MANIFEST.json",
        {
            "schema_version": 1,
            "tensor_count": len(trainable),
            "names": trainable_names,
            "initialization": initialization_rows,
            "all_other_parameters_frozen": True,
            "loading_mismatch_names": mismatch_names,
        },
    )
    model.to("cuda")
    return model, language_model, trainable


def accumulator() -> dict[str, float]:
    return {
        "squared_error": 0.0,
        "target_squared": 0.0,
        "dot": 0.0,
        "candidate_squared": 0.0,
        "count": 0.0,
    }


def add_metrics(state: dict[str, float], candidate: torch.Tensor, target: torch.Tensor) -> None:
    candidate = candidate.detach().float().reshape(-1)
    target = target.detach().float().reshape(-1)
    state["squared_error"] += float((candidate - target).pow(2).sum())
    state["target_squared"] += float(target.pow(2).sum())
    state["dot"] += float((candidate * target).sum())
    state["candidate_squared"] += float(candidate.pow(2).sum())
    state["count"] += float(target.numel())


def finalize_metrics(state: dict[str, float]) -> dict[str, float]:
    return {
        **state,
        "nrmse": math.sqrt(state["squared_error"] / max(state["target_squared"], 1e-30)),
        "cosine": state["dot"]
        / math.sqrt(max(state["candidate_squared"] * state["target_squared"], 1e-30)),
    }


def load_teacher_target(capture_root: pathlib.Path, request_index: int) -> dict:
    return torch.load(
        capture_root / f"teacher-{request_index:02d}.pt",
        map_location="cpu",
        weights_only=True,
    )


def evaluate(
    language_model: torch.nn.Module,
    bodies: pathlib.Path,
    capture_root: pathlib.Path,
    request_indices: list[int],
    contract: dict,
) -> dict:
    language_model.eval()
    block_state = accumulator()
    final_state = accumulator()
    rows = []
    selected_tokens = contract["token_sampling"]["selected_tokens"]
    layer_ids = contract["local_layer_ids"]
    with torch.inference_mode():
        for request_index in request_indices:
            target = load_teacher_target(capture_root, request_index)
            input_ids = request_ids(bodies, request_index, selected_tokens).to("cuda")
            blocks, final_hidden = forward_targets(language_model, input_ids, layer_ids)
            row_block = accumulator()
            for layer_id in layer_ids:
                teacher = target["block_targets"][layer_id].to("cuda")
                add_metrics(row_block, blocks[layer_id][0], teacher)
                add_metrics(block_state, blocks[layer_id][0], teacher)
            teacher_final = target["final_hidden_target"].to("cuda")
            add_metrics(final_state, final_hidden[0], teacher_final)
            row_final = accumulator()
            add_metrics(row_final, final_hidden[0], teacher_final)
            rows.append(
                {
                    "request_index": request_index,
                    "block": finalize_metrics(row_block),
                    "final_hidden": finalize_metrics(row_final),
                }
            )
    return {
        "block": finalize_metrics(block_state),
        "final_hidden": finalize_metrics(final_state),
        "rows": rows,
    }


def training_loss(
    blocks: dict[int, torch.Tensor],
    final_hidden: torch.Tensor,
    target: dict,
    layer_ids: list[int],
    loss_contract: dict,
) -> tuple[torch.Tensor, dict[str, float]]:
    block_nmse = []
    block_cosine_loss = []
    for layer_id in layer_ids:
        candidate = blocks[layer_id].float()
        teacher = target["block_targets"][layer_id].to("cuda").float().unsqueeze(0)
        block_nmse.append((candidate - teacher).pow(2).mean() / teacher.pow(2).mean().clamp_min(1e-12))
        block_cosine_loss.append(
            1.0 - F.cosine_similarity(candidate.reshape(1, -1), teacher.reshape(1, -1)).mean()
        )
    aggregate_block_nmse = torch.stack(block_nmse).mean()
    aggregate_block_cosine_loss = torch.stack(block_cosine_loss).mean()
    teacher_final = target["final_hidden_target"].to("cuda").float().unsqueeze(0)
    candidate_final = final_hidden.float()
    final_nmse = (candidate_final - teacher_final).pow(2).mean() / teacher_final.pow(2).mean().clamp_min(1e-12)
    final_cosine_loss = 1.0 - F.cosine_similarity(
        candidate_final.reshape(1, -1), teacher_final.reshape(1, -1)
    ).mean()
    loss = (
        loss_contract["aggregate_local_attention_normalized_mse_weight"] * aggregate_block_nmse
        + loss_contract["aggregate_local_attention_cosine_weight"] * aggregate_block_cosine_loss
        + loss_contract["end_to_end_final_hidden_normalized_mse_weight"] * final_nmse
        + loss_contract["end_to_end_final_hidden_cosine_weight"] * final_cosine_loss
    )
    return loss, {
        "loss": float(loss.detach()),
        "block_nmse": float(aggregate_block_nmse.detach()),
        "block_cosine_loss": float(aggregate_block_cosine_loss.detach()),
        "final_hidden_nmse": float(final_nmse.detach()),
        "final_hidden_cosine_loss": float(final_cosine_loss.detach()),
    }


def train_student(
    model: torch.nn.Module,
    language_model: torch.nn.Module,
    trainable: list[torch.nn.Parameter],
    checkpoint: pathlib.Path,
    bodies: pathlib.Path,
    capture_root: pathlib.Path,
    output_root: pathlib.Path,
    contract: dict,
) -> dict:
    baseline = evaluate(
        language_model,
        bodies,
        capture_root,
        contract["split"]["holdout_request_indices"],
        contract,
    )
    atomic_json(output_root / "PAIR_MEAN_BASELINE.json", baseline)
    (output_root / "SCIENTIFIC_STARTED").write_text(str(time.time()) + "\n")
    optimizer_contract = contract["optimizer"]
    optimizer = torch.optim.AdamW(
        trainable,
        lr=optimizer_contract["learning_rate"],
        betas=tuple(optimizer_contract["betas"]),
        eps=optimizer_contract["eps"],
        weight_decay=optimizer_contract["weight_decay"],
        foreach=False,
    )
    torch.manual_seed(contract["seed"])
    random.seed(contract["seed"])
    language_model.train()
    progress = []
    selected_tokens = contract["token_sampling"]["selected_tokens"]
    for update_index, request_index in enumerate(contract["split"]["train_request_indices"]):
        target = load_teacher_target(capture_root, request_index)
        input_ids = request_ids(bodies, request_index, selected_tokens).to("cuda")
        blocks, final_hidden = forward_targets(language_model, input_ids, contract["local_layer_ids"])
        loss, row = training_loss(
            blocks,
            final_hidden,
            target,
            contract["local_layer_ids"],
            contract["loss"],
        )
        if not torch.isfinite(loss):
            raise RuntimeError(f"non-finite training loss at update {update_index}")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        gradient_norm = torch.nn.utils.clip_grad_norm_(
            trainable,
            optimizer_contract["gradient_clip_norm"],
        )
        if not torch.isfinite(gradient_norm):
            raise RuntimeError(f"non-finite gradient norm at update {update_index}")
        optimizer.step()
        row.update(
            {
                "update_index": update_index,
                "request_index": request_index,
                "gradient_norm_before_clip": float(gradient_norm),
            }
        )
        progress.append(row)
        atomic_json(output_root / "TRAIN_PROGRESS.json", {"completed_updates": len(progress), "rows": progress})
    trained = evaluate(
        language_model,
        bodies,
        capture_root,
        contract["split"]["holdout_request_indices"],
        contract,
    )
    overlay = {}
    for layer_id in contract["local_layer_ids"]:
        for projection in ("k_proj", "v_proj"):
            overlay[f"language_model.layers.{layer_id}.self_attn.{projection}.weight"] = (
                getattr(language_model.layers[layer_id].self_attn, projection)
                .weight.detach()
                .to("cpu", dtype=torch.bfloat16)
                .contiguous()
            )
    overlay_path = output_root / "overlay.safetensors"
    save_file(overlay, overlay_path)
    block_improved = (
        trained["block"]["nrmse"] < baseline["block"]["nrmse"]
        and trained["block"]["cosine"] > baseline["block"]["cosine"]
    )
    final_improved = (
        trained["final_hidden"]["nrmse"] < baseline["final_hidden"]["nrmse"]
        and trained["final_hidden"]["cosine"] > baseline["final_hidden"]["cosine"]
    )
    result = {
        "schema_version": 1,
        "pair_mean_baseline": baseline,
        "trained": trained,
        "heldout_block_fidelity_improved": block_improved,
        "heldout_final_hidden_fidelity_improved": final_improved,
        "all_values_finite": all(
            math.isfinite(value)
            for section in (baseline["block"], baseline["final_hidden"], trained["block"], trained["final_hidden"])
            for key, value in section.items()
            if key in {"nrmse", "cosine"}
        ),
        "optimizer_updates": len(progress),
        "overlay_tensor_count": len(overlay),
        "overlay_bytes": overlay_path.stat().st_size,
        "overlay_sha256": sha256(overlay_path),
        "peak_cuda_memory_bytes": torch.cuda.max_memory_allocated(),
    }
    result["fidelity_gate_pass"] = bool(
        result["heldout_block_fidelity_improved"]
        and result["heldout_final_hidden_fidelity_improved"]
        and result["all_values_finite"]
        and result["optimizer_updates"] == 24
        and result["overlay_tensor_count"] == 100
    )
    atomic_json(output_root / "FIDELITY.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=pathlib.Path, required=True)
    parser.add_argument("--bodies", type=pathlib.Path, required=True)
    parser.add_argument("--contract", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    contract = json.loads(args.contract.read_text())
    atomic_json(
        args.output / "IDENTITY.json",
        {
            "contract_sha256": sha256(args.contract),
            "implementation_sha256": sha256(pathlib.Path(__file__)),
            "checkpoint_files": len(list(args.checkpoint.iterdir())),
            "checkpoint_total_bytes": sum(path.stat().st_size for path in args.checkpoint.iterdir() if path.is_file()),
        },
    )
    capture = capture_teacher(
        args.checkpoint,
        args.bodies,
        args.output / "teacher_capture",
        contract,
    )
    model, language_model, trainable = load_student(args.checkpoint, contract, args.output)
    fidelity = train_student(
        model,
        language_model,
        trainable,
        args.checkpoint,
        args.bodies,
        args.output / "teacher_capture",
        args.output,
        contract,
    )
    atomic_json(
        args.output / "DISTILL_TERMINAL.json",
        {
            "schema_version": 1,
            "status": "terminal",
            "candidate_invocations": 1,
            "capture": capture,
            "fidelity": fidelity,
        },
    )
    return 0 if fidelity["fidelity_gate_pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
