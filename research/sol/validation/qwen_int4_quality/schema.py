from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .quantization import Granularity

EvaluationStrategy = Literal["sequential_models", "interleaved_models"]


@dataclass(frozen=True)
class CorpusEntry:
    identifier: str
    prompt: str
    completion: str


@dataclass(frozen=True)
class QualityCorpus:
    schema_version: str
    kind: str
    description: str
    task: str
    is_standard_benchmark: bool
    source: dict[str, object]
    generation: dict[str, object]
    tokenizer: dict[str, object]
    expected_example_count: int
    expected_target_tokens: int | None
    entries: tuple[CorpusEntry, ...]


@dataclass(frozen=True)
class QualityThresholds:
    maximum_nll_increase: float
    maximum_perplexity_ratio: float
    maximum_logit_rmse: float
    minimum_logit_cosine_similarity: float
    minimum_top1_agreement: float


@dataclass(frozen=True)
class RunConfig:
    schema_version: str
    suite: str
    seed: int
    dtype: Literal["float32", "bfloat16", "float16"]
    torch_threads: int
    evaluation_strategy: EvaluationStrategy
    granularity: Granularity
    group_size: int | None
    excluded_modules: tuple[str, ...]
    thresholds: QualityThresholds


def load_run_config(path: Path) -> RunConfig:
    document = _load_json_object(path)
    schema_version = str(document.get("schema_version", ""))
    if schema_version != "inference-foundry.quality-run.v1":
        raise ValueError(f"unsupported quality run schema: {schema_version}")
    quantization = _require_object(document, "quantization")
    thresholds = _require_object(document, "non_inferiority")
    scheme = str(quantization.get("scheme", ""))
    if scheme != "symmetric_signed_int4_quantize_dequantize":
        raise ValueError(f"unsupported quantization scheme: {scheme}")
    granularity = str(quantization.get("granularity", ""))
    if granularity not in {"per_channel", "groupwise"}:
        raise ValueError("quantization.granularity must be per_channel or groupwise")
    group_size_value = quantization.get("group_size")
    group_size = int(group_size_value) if group_size_value is not None else None
    if granularity == "groupwise" and (group_size is None or group_size <= 0):
        raise ValueError(
            "quantization.group_size must be positive for groupwise quantization"
        )
    dtype = str(document.get("dtype", ""))
    if dtype not in {"float32", "bfloat16", "float16"}:
        raise ValueError("dtype must be float32, bfloat16, or float16")
    torch_threads = int(document.get("torch_threads", 0))
    if torch_threads <= 0:
        raise ValueError("torch_threads must be positive")
    evaluation_strategy = str(document.get("evaluation_strategy", "sequential_models"))
    if evaluation_strategy not in {"sequential_models", "interleaved_models"}:
        raise ValueError(
            "evaluation_strategy must be sequential_models or interleaved_models"
        )
    excluded = quantization.get("excluded_modules", [])
    if not isinstance(excluded, list) or any(
        not isinstance(value, str) for value in excluded
    ):
        raise ValueError("quantization.excluded_modules must be a string array")

    quality_thresholds = QualityThresholds(
        maximum_nll_increase=float(thresholds["maximum_nll_increase"]),
        maximum_perplexity_ratio=float(thresholds["maximum_perplexity_ratio"]),
        maximum_logit_rmse=float(thresholds["maximum_logit_rmse"]),
        minimum_logit_cosine_similarity=float(
            thresholds["minimum_logit_cosine_similarity"]
        ),
        minimum_top1_agreement=float(thresholds["minimum_top1_agreement"]),
    )
    if quality_thresholds.maximum_nll_increase < 0.0:
        raise ValueError("maximum_nll_increase must be non-negative")
    if quality_thresholds.maximum_perplexity_ratio < 1.0:
        raise ValueError("maximum_perplexity_ratio must be at least one")
    if quality_thresholds.maximum_logit_rmse < 0.0:
        raise ValueError("maximum_logit_rmse must be non-negative")
    if not 0.0 <= quality_thresholds.minimum_logit_cosine_similarity <= 1.0:
        raise ValueError("minimum_logit_cosine_similarity must be between zero and one")
    if not 0.0 <= quality_thresholds.minimum_top1_agreement <= 1.0:
        raise ValueError("minimum_top1_agreement must be between zero and one")

    return RunConfig(
        schema_version=schema_version,
        suite=str(document["suite"]),
        seed=int(document["seed"]),
        dtype=dtype,
        torch_threads=torch_threads,
        evaluation_strategy=evaluation_strategy,
        granularity=granularity,
        group_size=group_size,
        excluded_modules=tuple(excluded),
        thresholds=quality_thresholds,
    )


def load_corpus(path: Path) -> QualityCorpus:
    document = _load_json_object(path)
    schema_version = str(document.get("schema_version", ""))
    entries = _load_corpus_entries(document)
    if schema_version == "inference-foundry.corpus.v1":
        return QualityCorpus(
            schema_version=schema_version,
            kind="hand_authored_agent_style_calibration",
            description=str(document.get("description", "")),
            task="teacher_forced_completion",
            is_standard_benchmark=False,
            source={"type": "hand_authored"},
            generation={},
            tokenizer={},
            expected_example_count=len(entries),
            expected_target_tokens=None,
            entries=tuple(entries),
        )
    if schema_version != "inference-foundry.corpus.v2":
        raise ValueError(f"unsupported corpus schema: {schema_version}")

    kind = str(document.get("kind", "")).strip()
    description = str(document.get("description", "")).strip()
    task = str(document.get("task", "")).strip()
    if not kind or not description or not task:
        raise ValueError("corpus kind, description, and task must be non-empty")
    standard = document.get("is_standard_benchmark")
    if not isinstance(standard, bool):
        raise ValueError("is_standard_benchmark must be a boolean")
    source = _require_object(document, "source")
    generation = _require_object(document, "generation")
    tokenizer = _require_object(document, "tokenizer")
    _require_strings(
        source,
        ("dataset_id", "dataset_config", "split", "dataset_fingerprint"),
        "source",
    )
    _require_strings(
        generation,
        ("generator_version", "selection_method"),
        "generation",
    )
    _require_strings(tokenizer, ("model_id", "class"), "tokenizer")
    if int(tokenizer.get("vocab_size", 0)) <= 0:
        raise ValueError("tokenizer vocab_size must be positive")
    tokenizer_files = tokenizer.get("files")
    if not isinstance(tokenizer_files, list) or not tokenizer_files:
        raise ValueError("tokenizer files must be a non-empty array")
    for value in tokenizer_files:
        if not isinstance(value, dict):
            raise ValueError("tokenizer files must contain objects")
        _require_strings(value, ("name", "sha256"), "tokenizer files")
    expected_example_count = int(document.get("expected_example_count", 0))
    expected_target_tokens = int(document.get("expected_target_tokens", 0))
    if expected_example_count <= 0 or expected_example_count != len(entries):
        raise ValueError("expected_example_count must match the generated examples")
    if expected_target_tokens <= 0:
        raise ValueError("expected_target_tokens must be positive")
    return QualityCorpus(
        schema_version=schema_version,
        kind=kind,
        description=description,
        task=task,
        is_standard_benchmark=standard,
        source=source,
        generation=generation,
        tokenizer=tokenizer,
        expected_example_count=expected_example_count,
        expected_target_tokens=expected_target_tokens,
        entries=tuple(entries),
    )


def _load_corpus_entries(document: dict[str, object]) -> list[CorpusEntry]:
    examples = document.get("examples")
    if not isinstance(examples, list) or not examples:
        raise ValueError("corpus examples must be a non-empty array")
    entries: list[CorpusEntry] = []
    identifiers: set[str] = set()
    for value in examples:
        if not isinstance(value, dict):
            raise ValueError("each corpus example must be an object")
        entry = CorpusEntry(
            identifier=str(value.get("id", "")).strip(),
            prompt=str(value.get("prompt", "")),
            completion=str(value.get("completion", "")),
        )
        if not entry.identifier or not entry.prompt or not entry.completion:
            raise ValueError("corpus id, prompt, and completion must be non-empty")
        if entry.identifier in identifiers:
            raise ValueError(f"duplicate corpus id: {entry.identifier}")
        identifiers.add(entry.identifier)
        entries.append(entry)
    return entries


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(f"input file does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _require_object(document: dict[str, object], key: str) -> dict[str, object]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _require_strings(
    document: dict[str, object],
    keys: tuple[str, ...],
    section: str,
) -> None:
    missing = [key for key in keys if not str(document.get(key, "")).strip()]
    if missing:
        raise ValueError(f"{section} is missing: {', '.join(missing)}")
