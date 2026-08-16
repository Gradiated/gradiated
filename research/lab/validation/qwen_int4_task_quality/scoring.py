from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch


@dataclass(frozen=True)
class ChoiceEncoding:
    input_ids: torch.Tensor
    target_start: int
    target_tokens: int


def build_choice_encoding(
    tokenizer: Any,
    *,
    prompt: str,
    choice: str,
    choice_prefix: str = " ",
) -> ChoiceEncoding:
    prompt_ids = tokenizer.encode(prompt, add_special_tokens=True)
    full_ids = tokenizer.encode(
        f"{prompt}{choice_prefix}{choice}", add_special_tokens=True
    )
    if not prompt_ids:
        raise ValueError("tokenizer produced an empty prompt")
    if full_ids[: len(prompt_ids)] != prompt_ids:
        raise ValueError("joint tokenization does not preserve the prompt token prefix")
    target_tokens = len(full_ids) - len(prompt_ids)
    if target_tokens <= 0:
        raise ValueError("tokenizer produced an empty continuation")
    return ChoiceEncoding(
        input_ids=torch.tensor([full_ids], dtype=torch.long),
        target_start=len(prompt_ids) - 1,
        target_tokens=target_tokens,
    )


def length_normalized_continuation_log_likelihood(
    logits: torch.Tensor,
    input_ids: torch.Tensor,
    *,
    target_start: int,
    target_tokens: int,
) -> float:
    if target_tokens <= 0:
        raise ValueError("target_tokens must be positive")
    end = target_start + target_tokens
    target_logits = logits[:, target_start:end, :].to(torch.float32)
    targets = input_ids[:, target_start + 1 : end + 1]
    if target_logits.shape[:2] != targets.shape:
        raise ValueError("logits do not cover the declared continuation")
    log_probabilities = torch.log_softmax(target_logits, dim=-1)
    selected = torch.gather(log_probabilities, -1, targets.unsqueeze(-1)).squeeze(-1)
    return float(selected.mean().item())
