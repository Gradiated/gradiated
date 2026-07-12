from __future__ import annotations

import hashlib
import json
from pathlib import Path

from validation.qwen_int4_quality.provenance import (
    checkpoint_precision_bits,
    model_identity,
    sha256_file,
    software_identity,
)
from validation.qwen_int4_quality.runner import (
    _build_corpus_report,
    _quality_report,
    evaluate_model_transform,
)
from validation.qwen_int4_quality.schema import QualityCorpus

from .schema import RunConfig
from .transform import KvHeadDedupSummary, apply_kv_head_deduplication


def run_validation(
    model_path: Path,
    config_path: Path,
    corpus_path: Path,
    config: RunConfig,
    corpus: QualityCorpus,
) -> dict[str, object]:
    evaluation = evaluate_model_transform(
        model_path,
        config,
        corpus,
        lambda model: apply_kv_head_deduplication(
            model,
            baseline_checkpoint_bits_per_parameter=checkpoint_precision_bits(
                model_path
            ),
            maximum_transformed_layers=config.maximum_transformed_layers,
            maximum_pairs_per_transformed_layer=config.maximum_pairs_per_transformed_layer,
        ),
    )
    _validate_transform_config(config, evaluation.transform)
    aggregate = evaluation.aggregate
    corpus_sha256 = sha256_file(corpus_path)
    quality_report = _quality_report(config, aggregate)
    report: dict[str, object] = {
        "schema_version": "inference-foundry.kv-dedup-quality-validation.v1",
        "scope": {
            "supported_claim": "Measured teacher-forced quality-proxy delta after independently pairing each layer's Qwen3-0.6B KV heads by minimum joint K/V weight distance and replacing every pair with its mean on CPU.",
            "unsupported_claims": [
                "task accuracy or end-to-end agent success",
                "quality transfer to GLM-5.2 or another model",
                "runtime KV-cache or checkpoint storage reduction",
                "custom attention alias-kernel correctness or performance",
                "serving throughput, latency, energy, or cost",
                "fine-tuned recovery after the one-shot model change",
                "custom hardware performance",
            ],
        },
        "inputs": {
            "suite": config.suite,
            "seed": config.seed,
            "dtype": config.dtype,
            "torch_threads": config.torch_threads,
            "evaluation_strategy": config.evaluation_strategy,
            "config_path": str(config_path),
            "config_sha256": sha256_file(config_path),
            "corpus_path": str(corpus_path),
            "corpus_sha256": corpus_sha256,
        },
        "provenance": {
            "model": model_identity(model_path, evaluation.weight_files),
            "tokenizer": evaluation.runtime_tokenizer_identity,
            "software": software_identity(),
            "deterministic_algorithms": True,
        },
        "transform": evaluation.transform.to_dict(),
        "corpus": _build_corpus_report(
            corpus,
            actual_target_tokens=aggregate.target_tokens,
            corpus_sha256=corpus_sha256,
        ),
        "metrics": aggregate.to_dict(),
        "quality_report": quality_report,
    }
    stable_document = {
        key: report[key]
        for key in (
            "scope",
            "inputs",
            "transform",
            "corpus",
            "metrics",
            "quality_report",
        )
    }
    report["content_identity_sha256"] = hashlib.sha256(
        json.dumps(stable_document, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return report


def _validate_transform_config(
    config: RunConfig,
    summary: KvHeadDedupSummary,
) -> None:
    if summary.scheme != config.transform_scheme:
        raise ValueError("runtime transform scheme does not match the pinned config")
    if summary.original_kv_heads != config.expected_original_kv_heads:
        raise ValueError(
            "runtime original KV head count does not match the pinned config"
        )
    if summary.unique_kv_heads != config.expected_unique_kv_heads:
        raise ValueError(
            "runtime unique KV head count does not match the pinned config"
        )
    if len(summary.transformed_layer_indices) != config.maximum_transformed_layers:
        raise ValueError(
            "runtime transformed layer count does not match the pinned config"
        )
