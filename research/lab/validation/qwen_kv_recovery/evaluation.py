from __future__ import annotations

import gc
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch

from validation.qwen_int4_quality.metrics import aggregate_evaluations
from validation.qwen_int4_quality.provenance import sha256_file
from validation.qwen_int4_quality.runner import (
    _build_corpus_report,
    _evaluate_baseline,
    _evaluate_candidate,
    _quality_report,
    _tokenize,
    _validate_context_lengths,
    _validate_tokenized_corpus,
    _validate_tokenizer_identity,
)
from validation.qwen_int4_quality.schema import QualityCorpus

from .schema import RecoveryConfig


@dataclass(frozen=True)
class PreparedHoldout:
    path: Path
    corpus: QualityCorpus
    examples: tuple[Any, ...]


def prepare_holdout(
    path: Path,
    corpus: QualityCorpus,
    tokenizer: Any,
    model: torch.nn.Module,
    tokenizer_identity: dict[str, object],
) -> PreparedHoldout:
    _validate_tokenizer_identity(corpus, tokenizer_identity)
    examples = tuple(_tokenize(tokenizer, entry) for entry in corpus.entries)
    _validate_tokenized_corpus(corpus, list(examples))
    _validate_context_lengths(model, list(examples))
    return PreparedHoldout(path=path, corpus=corpus, examples=examples)


def evaluate_holdout(
    teacher: torch.nn.Module,
    student: torch.nn.Module,
    holdout: PreparedHoldout,
    config: RecoveryConfig,
    *,
    training_target_tokens: int,
) -> dict[str, object]:
    started = time.perf_counter()
    teacher.eval()
    student.eval()
    records = []
    for example in holdout.examples:
        baseline = _evaluate_baseline(teacher, example)
        records.append(_evaluate_candidate(student, example, baseline))
        del baseline
    aggregate = aggregate_evaluations(records)
    quality = _quality_report(config, aggregate)
    gc.collect()
    return {
        "training_target_tokens": training_target_tokens,
        "wall_seconds": time.perf_counter() - started,
        "corpus": _build_corpus_report(
            holdout.corpus,
            actual_target_tokens=aggregate.target_tokens,
            corpus_sha256=sha256_file(holdout.path),
        ),
        "metrics": aggregate.to_dict(),
        "quality_report": quality,
    }
