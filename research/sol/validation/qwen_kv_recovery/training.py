from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn.functional as functional


@dataclass(frozen=True)
class DistillationObjective:
    total: torch.Tensor
    teacher_kl: torch.Tensor
    next_token_cross_entropy: torch.Tensor


def distillation_objective(
    student_logits: torch.Tensor,
    teacher_logits: torch.Tensor,
    targets: torch.Tensor,
    *,
    temperature: float,
    teacher_kl_weight: float,
    next_token_weight: float,
) -> DistillationObjective:
    if student_logits.shape != teacher_logits.shape:
        raise ValueError("student and teacher logits must have identical shapes")
    if student_logits.shape[:-1] != targets.shape:
        raise ValueError("target shape must match the logit positions")
    student = student_logits.to(torch.float32)
    teacher = teacher_logits.detach().to(torch.float32)
    student_log_probabilities = functional.log_softmax(student / temperature, dim=-1)
    teacher_log_probabilities = functional.log_softmax(teacher / temperature, dim=-1)
    teacher_kl = (
        functional.kl_div(
            student_log_probabilities.reshape(-1, student.shape[-1]),
            teacher_log_probabilities.reshape(-1, teacher.shape[-1]),
            reduction="batchmean",
            log_target=True,
        )
        * temperature**2
    )
    next_token = functional.cross_entropy(
        student.reshape(-1, student.shape[-1]),
        targets.reshape(-1),
    )
    total = teacher_kl_weight * teacher_kl + next_token_weight * next_token
    return DistillationObjective(
        total=total,
        teacher_kl=teacher_kl.detach(),
        next_token_cross_entropy=next_token.detach(),
    )


def should_promote(quality_report: dict[str, object]) -> bool:
    return quality_report.get("passed") is True
