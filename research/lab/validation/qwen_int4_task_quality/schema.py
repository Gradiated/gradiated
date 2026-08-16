from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .quantization import FROZEN_INCLUDED_PATTERNS


@dataclass(frozen=True)
class ModelConfig:
    model_id: str
    model_revision: str
    local_path: str
    config_sha256: str
    weight_file: str
    weight_bytes: int
    weight_sha256: str
    tokenizer_files: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class DatasetConfig:
    dataset_id: str
    dataset_revision: str
    dataset_version: str
    dataset_script_sha256: str
    source_url: str
    archive_sha256: str
    validation_jsonl_sha256: str
    validation_labels_sha256: str
    expected_validation_rows: int
    expected_validation_rows_sha256: str


@dataclass(frozen=True)
class SelectionConfig:
    method: str
    seed: int
    example_count: int
    expected_selected_indices_sha256: str
    expected_selected_rows_sha256: str


@dataclass(frozen=True)
class PromptConfig:
    template: str
    choice_prefix: str


@dataclass(frozen=True)
class ScoringConfig:
    method: str
    tie_break: str


@dataclass(frozen=True)
class QuantizationConfig:
    scheme: str
    group_size: int
    code_scale: str
    scale_storage: str
    dequantization_scale: str
    included_module_patterns: tuple[str, ...]
    expected_module_count: int
    expected_parameter_count: int


@dataclass(frozen=True)
class GateConfig:
    maximum_accuracy_drop: float


@dataclass(frozen=True)
class UncertaintyConfig:
    paired_bootstrap_samples: int
    confidence_level: float


@dataclass(frozen=True)
class TaskConfig:
    schema_version: str
    suite: str
    seed: int
    dtype: Literal["bfloat16"]
    torch_threads: int
    model: ModelConfig
    dataset: DatasetConfig
    selection: SelectionConfig
    prompt: PromptConfig
    scoring: ScoringConfig
    quantization: QuantizationConfig
    gates: GateConfig
    uncertainty: UncertaintyConfig


def load_task_config(path: Path) -> TaskConfig:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(f"task config does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid task config JSON: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("task config root must be an object")
    if document.get("schema_version") != "inference-foundry.int4-task-quality.v1":
        raise ValueError("unsupported task config schema_version")
    model_document = _section(document, "model")
    tokenizer_files = model_document.pop("tokenizer_files", None)
    if not isinstance(tokenizer_files, list) or not tokenizer_files:
        raise ValueError("model.tokenizer_files must be a non-empty array")
    if any(not isinstance(value, dict) for value in tokenizer_files):
        raise ValueError("model.tokenizer_files must contain objects")
    if any(
        not str(value.get("name", "")).strip()
        or not str(value.get("sha256", "")).strip()
        for value in tokenizer_files
    ):
        raise ValueError("model tokenizer file identity is incomplete")
    model = ModelConfig(
        tokenizer_files=tuple(
            {str(key): str(value) for key, value in tokenizer_file.items()}
            for tokenizer_file in tokenizer_files
        ),
        **model_document,
    )
    dataset = DatasetConfig(**_section(document, "dataset"))
    selection = SelectionConfig(**_section(document, "selection"))
    prompt = PromptConfig(**_section(document, "prompt"))
    scoring = ScoringConfig(**_section(document, "scoring"))
    quantization_document = _section(document, "quantization")
    patterns = quantization_document.pop("included_module_patterns", None)
    if not isinstance(patterns, list) or any(
        not isinstance(value, str) for value in patterns
    ):
        raise ValueError("included_module_patterns must be a string array")
    quantization = QuantizationConfig(
        included_module_patterns=tuple(patterns),
        **quantization_document,
    )
    gates = GateConfig(**_section(document, "gates"))
    uncertainty = UncertaintyConfig(**_section(document, "uncertainty"))
    _validate(
        model, dataset, selection, prompt, scoring, quantization, gates, uncertainty
    )
    dtype = str(document.get("dtype", ""))
    if dtype != "bfloat16":
        raise ValueError("dtype must be bfloat16")
    torch_threads = int(document.get("torch_threads", 0))
    if torch_threads <= 0:
        raise ValueError("torch_threads must be positive")
    return TaskConfig(
        schema_version=str(document["schema_version"]),
        suite=str(document.get("suite", "")),
        seed=int(document.get("seed", 0)),
        dtype="bfloat16",
        torch_threads=torch_threads,
        model=model,
        dataset=dataset,
        selection=selection,
        prompt=prompt,
        scoring=scoring,
        quantization=quantization,
        gates=gates,
        uncertainty=uncertainty,
    )


def _section(document: dict[str, object], key: str) -> dict[str, object]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return dict(value)


def _validate(
    model: ModelConfig,
    dataset: DatasetConfig,
    selection: SelectionConfig,
    prompt: PromptConfig,
    scoring: ScoringConfig,
    quantization: QuantizationConfig,
    gates: GateConfig,
    uncertainty: UncertaintyConfig,
) -> None:
    if model.model_id != "Qwen/Qwen3-0.6B" or len(model.model_revision) != 40:
        raise ValueError("model identity is invalid")
    if model.weight_file != "model.safetensors" or model.weight_bytes <= 0:
        raise ValueError("model weight identity is invalid")
    if not model.tokenizer_files:
        raise ValueError("model tokenizer identity is invalid")
    if dataset.dataset_id != "ybisk/piqa" or len(dataset.dataset_revision) != 40:
        raise ValueError("dataset identity is invalid")
    if dataset.dataset_version != "1.1.0":
        raise ValueError("dataset version is invalid")
    for value in (
        model.config_sha256,
        model.weight_sha256,
        *(file.get("sha256", "") for file in model.tokenizer_files),
        dataset.dataset_script_sha256,
        dataset.archive_sha256,
        dataset.validation_jsonl_sha256,
        dataset.validation_labels_sha256,
        dataset.expected_validation_rows_sha256,
        selection.expected_selected_indices_sha256,
        selection.expected_selected_rows_sha256,
    ):
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError("all content hashes must be lowercase SHA-256")
    if dataset.expected_validation_rows <= 0:
        raise ValueError("expected_validation_rows must be positive")
    if (
        selection.method != "sha256_ranked_seed_colon_index"
        or selection.example_count <= 0
    ):
        raise ValueError("selection contract is invalid")
    if "{goal}" not in prompt.template or prompt.choice_prefix != " ":
        raise ValueError("prompt contract is invalid")
    if scoring.method != "length_normalized_continuation_log_likelihood":
        raise ValueError("scoring method is invalid")
    if scoring.tie_break != "lowest_choice_index":
        raise ValueError("tie_break is invalid")
    if quantization.scheme != "symmetric_signed_int4" or quantization.group_size != 8:
        raise ValueError("quantization scheme is invalid")
    if quantization.code_scale != "float32_max_abs_div_7":
        raise ValueError("code_scale is invalid")
    if quantization.scale_storage != "bfloat16":
        raise ValueError("scale_storage must be bfloat16")
    if quantization.dequantization_scale != "stored_bfloat16_promoted_to_float32":
        raise ValueError("dequantization_scale is invalid")
    if quantization.included_module_patterns != FROZEN_INCLUDED_PATTERNS:
        raise ValueError("included module patterns do not match the runtime transform")
    if (
        quantization.expected_module_count <= 0
        or quantization.expected_parameter_count <= 0
    ):
        raise ValueError("quantization geometry is invalid")
    if not 0.0 <= gates.maximum_accuracy_drop <= 1.0:
        raise ValueError("maximum_accuracy_drop is invalid")
    if uncertainty.paired_bootstrap_samples <= 0:
        raise ValueError("paired_bootstrap_samples must be positive")
    if not 0.0 < uncertainty.confidence_level < 1.0:
        raise ValueError("confidence_level is invalid")
