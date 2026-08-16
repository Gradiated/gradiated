from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from validation.qwen_int4_quality.schema import (
    EvaluationStrategy,
    QualityThresholds,
    _load_json_object,
    _require_object,
)


@dataclass(frozen=True)
class RunConfig:
    schema_version: str
    suite: str
    seed: int
    dtype: Literal["float32", "bfloat16", "float16"]
    torch_threads: int
    evaluation_strategy: EvaluationStrategy
    transform_scheme: str
    expected_original_kv_heads: int
    expected_unique_kv_heads: int
    maximum_transformed_layers: int
    maximum_pairs_per_transformed_layer: int
    thresholds: QualityThresholds


def load_run_config(path: Path) -> RunConfig:
    document = _load_json_object(path)
    schema_version = str(document.get("schema_version", ""))
    if schema_version != "inference-foundry.kv-dedup-quality-run.v1":
        raise ValueError(f"unsupported KV dedup quality run schema: {schema_version}")
    transform = _require_object(document, "transform")
    scheme = str(transform.get("scheme", ""))
    if scheme != "minimum_joint_kv_weight_distance_pair_mean":
        raise ValueError(f"unsupported KV dedup transform scheme: {scheme}")
    original_heads = int(transform.get("expected_original_kv_heads", 0))
    unique_heads = int(transform.get("expected_unique_kv_heads", 0))
    if original_heads <= 0 or original_heads % 2 != 0:
        raise ValueError("expected original KV heads must be positive and even")
    maximum_transformed_layers = int(transform.get("maximum_transformed_layers", 0))
    if maximum_transformed_layers <= 0:
        raise ValueError("maximum transformed layers must be positive")
    maximum_pairs = int(transform.get("maximum_pairs_per_transformed_layer", 0))
    if maximum_pairs <= 0 or maximum_pairs > original_heads // 2:
        raise ValueError(
            "maximum pairs per transformed layer is outside the KV geometry"
        )
    if unique_heads != original_heads - maximum_pairs:
        raise ValueError("expected unique KV heads must match the selected pair count")
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
    thresholds = _load_thresholds(_require_object(document, "non_inferiority"))
    return RunConfig(
        schema_version=schema_version,
        suite=str(document["suite"]),
        seed=int(document["seed"]),
        dtype=dtype,
        torch_threads=torch_threads,
        evaluation_strategy=evaluation_strategy,
        transform_scheme=scheme,
        expected_original_kv_heads=original_heads,
        expected_unique_kv_heads=unique_heads,
        maximum_transformed_layers=maximum_transformed_layers,
        maximum_pairs_per_transformed_layer=maximum_pairs,
        thresholds=thresholds,
    )


def _load_thresholds(document: dict[str, object]) -> QualityThresholds:
    thresholds = QualityThresholds(
        maximum_nll_increase=float(document["maximum_nll_increase"]),
        maximum_perplexity_ratio=float(document["maximum_perplexity_ratio"]),
        maximum_logit_rmse=float(document["maximum_logit_rmse"]),
        minimum_logit_cosine_similarity=float(
            document["minimum_logit_cosine_similarity"]
        ),
        minimum_top1_agreement=float(document["minimum_top1_agreement"]),
    )
    if thresholds.maximum_nll_increase < 0.0:
        raise ValueError("maximum_nll_increase must be non-negative")
    if thresholds.maximum_perplexity_ratio < 1.0:
        raise ValueError("maximum_perplexity_ratio must be at least one")
    if thresholds.maximum_logit_rmse < 0.0:
        raise ValueError("maximum_logit_rmse must be non-negative")
    if not 0.0 <= thresholds.minimum_logit_cosine_similarity <= 1.0:
        raise ValueError("minimum_logit_cosine_similarity must be between zero and one")
    if not 0.0 <= thresholds.minimum_top1_agreement <= 1.0:
        raise ValueError("minimum_top1_agreement must be between zero and one")
    return thresholds
