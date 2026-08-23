#!/usr/bin/env python3
"""Capture Gemma target features and domain-tune its frozen-KV MTP drafter.

The capture split and the tuning split are the same file by design. Selection
must happen on a separate validation workload and final reporting on holdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer


TARGET_MODEL = "google/gemma-4-31B-it"
TARGET_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
ASSISTANT_MODEL = "google/gemma-4-31B-it-assistant"
ASSISTANT_REVISION = "627c5ec1458b9086b841a91e0512fd31fd2fbbf1"


def load_sessions(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def training_turn(session: dict[str, object]) -> tuple[list[dict[str, object]], dict[str, object]]:
    messages = session["messages"]
    if not isinstance(messages, list):
        raise ValueError(f"session {session['session_id']} has invalid messages")
    for index in range(len(messages) - 1, 0, -1):
        message = messages[index]
        if isinstance(message, dict) and message.get("role") == "assistant":
            return messages[:index], message
    raise ValueError(f"session {session['session_id']} has no assistant turn")


def encode_chat(
    tokenizer, messages: list[dict[str, object]], add_generation_prompt: bool
) -> torch.Tensor:
    # Transformers 5's tokenizer backend returns tokenizers.Encoding from
    # apply_chat_template(..., tokenize=True) for some Gemma tokenizers. Render
    # first so the tensor contract remains stable across backends.
    rendered = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=add_generation_prompt,
    )
    return tokenizer(rendered, return_tensors="pt", add_special_tokens=False).input_ids[0]


def select_anchors(start: int, stop: int, count: int) -> list[int]:
    if stop < start:
        return []
    available = stop - start + 1
    if available <= count:
        return list(range(start, stop + 1))
    return sorted({round(start + index * (available - 1) / (count - 1)) for index in range(count)})


def capture(args: argparse.Namespace) -> int:
    args.features.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(TARGET_MODEL, revision=TARGET_REVISION)
    target = AutoModelForCausalLM.from_pretrained(
        TARGET_MODEL,
        revision=TARGET_REVISION,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        low_cpu_mem_usage=True,
        device_map={"": "cuda:0"},
    ).eval()
    target.requires_grad_(False)
    embedding = target.get_input_embeddings()
    output_head = target.get_output_embeddings()
    if embedding is None or output_head is None:
        raise RuntimeError("target model did not expose input/output embeddings")

    sessions = load_sessions(args.workload)
    if args.max_sessions:
        sessions = sessions[: args.max_sessions]
    captured: list[dict[str, object]] = []
    for session_index, session in enumerate(sessions):
        prompt, answer = training_turn(session)
        prompt_ids = encode_chat(tokenizer, prompt, add_generation_prompt=True)
        # Recorded assistants may use another model's channel syntax. Preserve
        # Gemma's exact generation prefix and append only the recorded content;
        # Gemma itself supplies every supervision target below.
        answer_ids = tokenizer(
            str(answer.get("content") or ""),
            return_tensors="pt",
            add_special_tokens=False,
        ).input_ids[0]
        full_ids = torch.cat([prompt_ids, answer_ids])
        prefix_length = prompt_ids.numel()
        if full_ids.numel() > args.max_length:
            # Keep the newest context while preserving the assistant response.
            trim = full_ids.numel() - args.max_length
            full_ids = full_ids[trim:]
            prefix_length -= trim
        if prefix_length < 1:
            continue

        # Position t predicts token t+1. Reserve `draft_depth` true future
        # tokens and focus on the response region seen in production decoding.
        anchor_start = max(0, prefix_length - 1)
        anchor_stop = min(
            full_ids.numel() - args.draft_depth - 1,
            anchor_start + args.response_tokens - 1,
        )
        anchors = select_anchors(anchor_start, anchor_stop, args.anchors_per_session)
        if not anchors:
            continue
        needed_positions = sorted(
            {position + depth for position in anchors for depth in range(args.draft_depth)}
        )

        input_ids = full_ids.unsqueeze(0).cuda()
        attention_mask = torch.ones_like(input_ids)
        with torch.inference_mode():
            outputs = target(
                input_ids=input_ids,
                attention_mask=attention_mask,
                output_hidden_states=True,
                return_shared_kv_states=True,
                use_cache=False,
            )
            hidden_states = outputs.hidden_states[-1]
            selected = torch.tensor(needed_positions, device=input_ids.device)
            teacher_logits = output_head(hidden_states[:, selected])
            teacher_tokens = teacher_logits.argmax(dim=-1)
            token_embeddings = embedding(input_ids[:, selected])

        shared_kv_states = outputs.shared_kv_states
        if not shared_kv_states:
            raise RuntimeError("target did not return shared_kv_states")
        max_kv_length = max(anchors) + 1
        feature = {
            "session_id": session["session_id"],
            "anchors": anchors,
            "needed_positions": needed_positions,
            "token_embeddings": token_embeddings[0].cpu(),
            "target_hidden_states": hidden_states[0, selected].cpu(),
            "teacher_tokens": teacher_tokens[0].cpu(),
            "shared_kv_states": {
                name: (
                    key[:, :, :max_kv_length].cpu(),
                    value[:, :, :max_kv_length].cpu(),
                )
                for name, (key, value) in shared_kv_states.items()
            },
        }
        feature_path = args.features / f"{session_index:04d}.pt"
        torch.save(feature, feature_path)
        captured.append(
            {
                "session_id": session["session_id"],
                "path": feature_path.name,
                "anchors": len(anchors),
                "max_kv_length": max_kv_length,
            }
        )
        del outputs, hidden_states, shared_kv_states, teacher_logits, token_embeddings
        torch.cuda.empty_cache()
        print(
            json.dumps(
                {
                    "capture": session_index + 1,
                    "total": len(sessions),
                    "session_id": session["session_id"],
                    "anchors": len(anchors),
                }
            ),
            flush=True,
        )

    manifest = {
        "target_model": TARGET_MODEL,
        "target_revision": TARGET_REVISION,
        "assistant_model": ASSISTANT_MODEL,
        "assistant_revision": ASSISTANT_REVISION,
        "source_workload": str(args.workload),
        "source_sha256": hashlib.sha256(args.workload.read_bytes()).hexdigest(),
        "draft_depth": args.draft_depth,
        "anchors_per_session": args.anchors_per_session,
        "response_tokens": args.response_tokens,
        "features": captured,
    }
    (args.features / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return 0


def train(args: argparse.Namespace) -> int:
    manifest = json.loads((args.features / "manifest.json").read_text())
    if manifest["target_revision"] != TARGET_REVISION:
        raise ValueError("feature target revision does not match the training contract")
    feature_paths = [args.features / item["path"] for item in manifest["features"]]
    assistant = AutoModelForCausalLM.from_pretrained(
        ASSISTANT_MODEL,
        revision=ASSISTANT_REVISION,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
    ).cuda().train()
    optimizer = torch.optim.AdamW(
        assistant.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay
    )
    checkpoints = sorted(set(args.checkpoint_steps))
    max_steps = checkpoints[-1]
    rng = random.Random(args.seed)
    step = 0
    running_losses: list[float] = []
    args.output.mkdir(parents=True, exist_ok=True)

    while step < max_steps:
        epoch_paths = feature_paths.copy()
        rng.shuffle(epoch_paths)
        for feature_path in epoch_paths:
            feature = torch.load(feature_path, map_location="cpu", weights_only=True)
            position_to_index = {
                int(position): index
                for index, position in enumerate(feature["needed_positions"])
            }
            token_embeddings = feature["token_embeddings"].cuda(non_blocking=True)
            target_hidden = feature["target_hidden_states"].cuda(non_blocking=True)
            teacher_tokens = feature["teacher_tokens"].cuda(non_blocking=True)
            shared = {
                name: (key.cuda(non_blocking=True), value.cuda(non_blocking=True))
                for name, (key, value) in feature["shared_kv_states"].items()
            }
            optimizer.zero_grad(set_to_none=True)
            sample_loss = 0.0
            anchors = [int(anchor) for anchor in feature["anchors"]]
            for anchor in anchors:
                previous_hidden = target_hidden[position_to_index[anchor]].view(1, 1, -1)
                depth_losses = []
                frozen_kv = {
                    name: (key[:, :, : anchor + 1], value[:, :, : anchor + 1])
                    for name, (key, value) in shared.items()
                }
                attention_mask = torch.ones(
                    (1, anchor + 1), dtype=torch.long, device="cuda"
                )
                for depth in range(manifest["draft_depth"]):
                    position = anchor + depth
                    index = position_to_index[position]
                    model_input = torch.cat(
                        [token_embeddings[index].view(1, 1, -1), previous_hidden], dim=-1
                    )
                    outputs = assistant(
                        inputs_embeds=model_input,
                        attention_mask=attention_mask,
                        position_ids=torch.tensor([[position]], device="cuda"),
                        shared_kv_states=frozen_kv,
                        use_cache=False,
                    )
                    depth_losses.append(
                        F.cross_entropy(
                            outputs.logits[:, -1].float(),
                            teacher_tokens[index].view(1),
                        )
                    )
                    previous_hidden = outputs.last_hidden_state
                anchor_loss = torch.stack(depth_losses).mean() / len(anchors)
                anchor_loss.backward()
                sample_loss += float(anchor_loss.detach())
            torch.nn.utils.clip_grad_norm_(assistant.parameters(), args.max_grad_norm)
            optimizer.step()
            step += 1
            running_losses.append(sample_loss)
            print(
                json.dumps(
                    {
                        "step": step,
                        "loss": round(sample_loss, 6),
                        "loss_mean_20": round(
                            sum(running_losses[-20:]) / min(20, len(running_losses)), 6
                        ),
                        "session_id": feature["session_id"],
                    }
                ),
                flush=True,
            )
            if step in checkpoints:
                checkpoint = args.output / f"checkpoint-{step}"
                assistant.save_pretrained(checkpoint, safe_serialization=True)
                state = {
                    "step": step,
                    "learning_rate": args.learning_rate,
                    "weight_decay": args.weight_decay,
                    "max_grad_norm": args.max_grad_norm,
                    "seed": args.seed,
                    "feature_manifest": str(args.features / "manifest.json"),
                    "base_assistant_revision": ASSISTANT_REVISION,
                }
                (checkpoint / "gradiated_training.json").write_text(
                    json.dumps(state, indent=2) + "\n", encoding="utf-8"
                )
            del token_embeddings, target_hidden, teacher_tokens, shared
            if step >= max_steps:
                break
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--workload", type=Path, required=True)
    capture_parser.add_argument("--features", type=Path, required=True)
    capture_parser.add_argument("--max-length", type=int, default=7000)
    capture_parser.add_argument("--response-tokens", type=int, default=128)
    capture_parser.add_argument("--anchors-per-session", type=int, default=4)
    capture_parser.add_argument("--draft-depth", type=int, default=4)
    capture_parser.add_argument("--max-sessions", type=int, default=0)

    train_parser = subparsers.add_parser("train")
    train_parser.add_argument("--features", type=Path, required=True)
    train_parser.add_argument("--output", type=Path, required=True)
    train_parser.add_argument("--learning-rate", type=float, default=2e-6)
    train_parser.add_argument("--weight-decay", type=float, default=0.01)
    train_parser.add_argument("--max-grad-norm", type=float, default=1.0)
    train_parser.add_argument("--checkpoint-steps", default="50,150,400")
    train_parser.add_argument("--seed", type=int, default=20260822)
    args = parser.parse_args()
    if args.command == "train":
        args.checkpoint_steps = [int(value) for value in args.checkpoint_steps.split(",")]
        if not args.checkpoint_steps or min(args.checkpoint_steps) <= 0:
            parser.error("--checkpoint-steps must contain positive integers")
    return args


def main() -> int:
    args = parse_args()
    torch.manual_seed(getattr(args, "seed", 20260822))
    return capture(args) if args.command == "capture" else train(args)


if __name__ == "__main__":
    raise SystemExit(main())
