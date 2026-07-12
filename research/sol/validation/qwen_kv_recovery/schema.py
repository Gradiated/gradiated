from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from validation.qwen_int4_quality.schema import (
    QualityThresholds,
    _load_json_object,
    _require_object,
)


@dataclass(frozen=True)
class DataConfig:
    dataset_id: str
    dataset_config: str
    dataset_revision: str
    training_split: str
    training_dataset_fingerprint: str
    heldout_split: str
    reserved_calibration_tokens: int
    training_target_tokens: int
    target_tokens_per_step: int


@dataclass(frozen=True)
class TransformConfig:
    scheme: str
    original_kv_heads: int
    unique_kv_heads: int


@dataclass(frozen=True)
class AdapterConfig:
    rank: int
    alpha: float
    targets: tuple[str, ...]


@dataclass(frozen=True)
class OptimizationConfig:
    optimizer: str
    learning_rate: float
    weight_decay: float
    teacher_kl_weight: float
    next_token_weight: float
    temperature: float


@dataclass(frozen=True)
class ZeroTokenControlConfig:
    path: str
    sha256: str
    content_identity_sha256: str


@dataclass(frozen=True)
class RecoveryConfig:
    schema_version: str
    suite: str
    seed: int
    device: Literal["cpu"]
    dtype: Literal["bfloat16"]
    torch_threads: int
    maximum_rss_bytes: int
    data: DataConfig
    transform: TransformConfig
    adapter: AdapterConfig
    optimization: OptimizationConfig
    zero_token_control: ZeroTokenControlConfig
    checkpoint_tokens: tuple[int, ...]
    thresholds: QualityThresholds


def load_config(path: Path) -> RecoveryConfig:
    document = _load_json_object(path)
    schema_version = str(document.get("schema_version", ""))
    if schema_version != "inference-foundry.qwen-kv-recovery-run.v1":
        raise ValueError(f"unsupported recovery run schema: {schema_version}")
    data = _load_data(_require_object(document, "data"))
    transform = _load_transform(_require_object(document, "transform"))
    adapter = _load_adapter(_require_object(document, "adapter"))
    optimization = _load_optimization(_require_object(document, "optimization"))
    zero_token_control = _load_zero_token_control(
        _require_object(document, "zero_token_control")
    )
    checkpoints = tuple(
        int(value) for value in document.get("checkpoints_after_target_tokens", [])
    )
    if not checkpoints or tuple(sorted(set(checkpoints))) != checkpoints:
        raise ValueError("checkpoints must be unique, positive, and increasing")
    if checkpoints[0] <= 0 or checkpoints[-1] > data.training_target_tokens:
        raise ValueError("checkpoint is outside the training-token budget")
    if any(value % data.target_tokens_per_step for value in checkpoints):
        raise ValueError("each checkpoint must align with a complete optimizer step")
    thresholds = _load_thresholds(_require_object(document, "non_inferiority"))
    device = str(document.get("device", ""))
    if device != "cpu":
        raise ValueError("this recovery screen is CPU-only")
    dtype = str(document.get("dtype", ""))
    if dtype != "bfloat16":
        raise ValueError("this recovery screen requires bfloat16 base weights")
    torch_threads = int(document.get("torch_threads", 0))
    maximum_rss_bytes = int(document.get("maximum_rss_bytes", 0))
    if torch_threads <= 0 or maximum_rss_bytes <= 0:
        raise ValueError("torch_threads and maximum_rss_bytes must be positive")
    return RecoveryConfig(
        schema_version=schema_version,
        suite=str(document.get("suite", "")),
        seed=int(document.get("seed", 0)),
        device="cpu",
        dtype="bfloat16",
        torch_threads=torch_threads,
        maximum_rss_bytes=maximum_rss_bytes,
        data=data,
        transform=transform,
        adapter=adapter,
        optimization=optimization,
        zero_token_control=zero_token_control,
        checkpoint_tokens=checkpoints,
        thresholds=thresholds,
    )


def _load_data(document: dict[str, object]) -> DataConfig:
    data = DataConfig(
        dataset_id=str(document.get("dataset_id", "")),
        dataset_config=str(document.get("dataset_config", "")),
        dataset_revision=str(document.get("dataset_revision", "")),
        training_split=str(document.get("training_split", "")),
        training_dataset_fingerprint=str(
            document.get("training_dataset_fingerprint", "")
        ),
        heldout_split=str(document.get("heldout_split", "")),
        reserved_calibration_tokens=int(document.get("reserved_calibration_tokens", 0)),
        training_target_tokens=int(document.get("training_target_tokens", 0)),
        target_tokens_per_step=int(document.get("target_tokens_per_step", 0)),
    )
    strings = (
        data.dataset_id,
        data.dataset_config,
        data.dataset_revision,
        data.training_split,
        data.training_dataset_fingerprint,
        data.heldout_split,
    )
    if any(not value for value in strings):
        raise ValueError("data provenance fields must be non-empty")
    if data.training_split == data.heldout_split:
        raise ValueError("training and held-out splits must differ")
    if (
        min(
            data.reserved_calibration_tokens,
            data.training_target_tokens,
            data.target_tokens_per_step,
        )
        <= 0
    ):
        raise ValueError("data token counts must be positive")
    if data.training_target_tokens % data.target_tokens_per_step:
        raise ValueError("training target tokens must be divisible by tokens per step")
    return data


def _load_transform(document: dict[str, object]) -> TransformConfig:
    transform = TransformConfig(
        scheme=str(document.get("scheme", "")),
        original_kv_heads=int(document.get("original_kv_heads", 0)),
        unique_kv_heads=int(document.get("unique_kv_heads", 0)),
    )
    if transform.scheme != "minimum_joint_kv_weight_distance_pair_mean":
        raise ValueError(f"unsupported recovery transform: {transform.scheme}")
    if (
        transform.original_kv_heads <= 0
        or transform.unique_kv_heads * 2 != transform.original_kv_heads
    ):
        raise ValueError("the recovery transform must halve an even KV-head count")
    return transform


def _load_adapter(document: dict[str, object]) -> AdapterConfig:
    targets = document.get("targets", [])
    if not isinstance(targets, list) or tuple(targets) != ("q_proj", "o_proj"):
        raise ValueError("adapter targets must be q_proj and o_proj")
    adapter = AdapterConfig(
        rank=int(document.get("rank", 0)),
        alpha=float(document.get("alpha", 0.0)),
        targets=("q_proj", "o_proj"),
    )
    if adapter.rank <= 0 or adapter.alpha <= 0.0:
        raise ValueError("adapter rank and alpha must be positive")
    return adapter


def _load_optimization(document: dict[str, object]) -> OptimizationConfig:
    optimization = OptimizationConfig(
        optimizer=str(document.get("optimizer", "")),
        learning_rate=float(document.get("learning_rate", 0.0)),
        weight_decay=float(document.get("weight_decay", 0.0)),
        teacher_kl_weight=float(document.get("teacher_kl_weight", -1.0)),
        next_token_weight=float(document.get("next_token_weight", -1.0)),
        temperature=float(document.get("temperature", 0.0)),
    )
    if optimization.optimizer != "AdamW":
        raise ValueError("only AdamW is supported")
    if optimization.learning_rate <= 0.0 or optimization.weight_decay < 0.0:
        raise ValueError("optimizer hyperparameters are outside their valid range")
    if (
        abs(optimization.teacher_kl_weight + optimization.next_token_weight - 1.0)
        > 1e-12
    ):
        raise ValueError("loss weights must sum to one")
    if min(optimization.teacher_kl_weight, optimization.next_token_weight) < 0.0:
        raise ValueError("loss weights must be non-negative")
    if optimization.temperature <= 0.0:
        raise ValueError("temperature must be positive")
    return optimization


def _load_zero_token_control(
    document: dict[str, object],
) -> ZeroTokenControlConfig:
    control = ZeroTokenControlConfig(
        path=str(document.get("path", "")),
        sha256=str(document.get("sha256", "")),
        content_identity_sha256=str(document.get("content_identity_sha256", "")),
    )
    if not control.path:
        raise ValueError("zero-token control path must be non-empty")
    for digest in (control.sha256, control.content_identity_sha256):
        if len(digest) != 64 or any(
            value not in "0123456789abcdef" for value in digest
        ):
            raise ValueError(
                "zero-token control hashes must be lowercase SHA-256 digests"
            )
    return control


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
        raise ValueError("maximum NLL increase must be non-negative")
    if thresholds.maximum_perplexity_ratio < 1.0:
        raise ValueError("maximum perplexity ratio must be at least one")
    if thresholds.maximum_logit_rmse < 0.0:
        raise ValueError("maximum logit RMSE must be non-negative")
    if not 0.0 <= thresholds.minimum_logit_cosine_similarity <= 1.0:
        raise ValueError("minimum logit cosine must be between zero and one")
    if not 0.0 <= thresholds.minimum_top1_agreement <= 1.0:
        raise ValueError("minimum top-1 agreement must be between zero and one")
    return thresholds
