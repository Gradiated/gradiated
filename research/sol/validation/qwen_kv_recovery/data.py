from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class TrainingWindow:
    step: int
    target_start_token: int
    input_ids: tuple[int, ...]
    target_ids: tuple[int, ...]
    token_ids_sha256: str


@dataclass(frozen=True)
class TrainingCorpus:
    stream_text_sha256: str
    stream_token_ids_sha256: str
    stream_token_count: int
    calibration_token_range: tuple[int, int]
    training_target_token_range: tuple[int, int]
    training_target_tokens: int
    target_tokens_per_step: int
    windows: tuple[TrainingWindow, ...]

    def to_dict(self) -> dict[str, object]:
        document = asdict(self)
        document["window_count"] = len(self.windows)
        document["windows"] = [
            {
                "step": value.step,
                "target_start_token": value.target_start_token,
                "target_tokens": len(value.target_ids),
                "token_ids_sha256": value.token_ids_sha256,
            }
            for value in self.windows
        ]
        return document


def build_training_windows(
    rows: Iterable[str],
    tokenizer: Any,
    *,
    reserved_calibration_tokens: int,
    training_target_tokens: int,
    target_tokens_per_step: int,
) -> TrainingCorpus:
    if (
        min(reserved_calibration_tokens, training_target_tokens, target_tokens_per_step)
        <= 0
    ):
        raise ValueError("token counts must be positive")
    if training_target_tokens % target_tokens_per_step:
        raise ValueError(
            "training target tokens must be divisible by target tokens per step"
        )
    stream = "\n\n".join(rows)
    token_ids = tokenizer.encode(stream, add_special_tokens=False)
    target_end = reserved_calibration_tokens + training_target_tokens
    if len(token_ids) < target_end:
        raise ValueError(
            f"training stream has {len(token_ids)} tokens; {target_end} required"
        )
    windows: list[TrainingWindow] = []
    for step, target_start in enumerate(
        range(reserved_calibration_tokens, target_end, target_tokens_per_step),
        start=1,
    ):
        input_ids = tuple(
            token_ids[target_start - 1 : target_start + target_tokens_per_step]
        )
        target_ids = tuple(
            token_ids[target_start : target_start + target_tokens_per_step]
        )
        encoded = ",".join(str(value) for value in input_ids).encode("utf-8")
        windows.append(
            TrainingWindow(
                step=step,
                target_start_token=target_start,
                input_ids=input_ids,
                target_ids=target_ids,
                token_ids_sha256=hashlib.sha256(encoded).hexdigest(),
            )
        )
    token_stream = ",".join(str(value) for value in token_ids).encode("utf-8")
    return TrainingCorpus(
        stream_text_sha256=hashlib.sha256(stream.encode("utf-8")).hexdigest(),
        stream_token_ids_sha256=hashlib.sha256(token_stream).hexdigest(),
        stream_token_count=len(token_ids),
        calibration_token_range=(0, reserved_calibration_tokens),
        training_target_token_range=(reserved_calibration_tokens, target_end),
        training_target_tokens=training_target_tokens,
        target_tokens_per_step=target_tokens_per_step,
        windows=tuple(windows),
    )
