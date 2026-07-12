from __future__ import annotations

import gc
import hashlib
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

import torch
import torch.nn.functional as functional
from transformers import AutoModelForCausalLM, AutoTokenizer

from .metrics import EvaluationAggregate, EvaluationSums, aggregate_evaluations
from .provenance import (
    checkpoint_precision_bits,
    model_identity,
    sha256_file,
    software_identity,
    tokenizer_identity,
    validate_model_directory,
)
from .quantization import QuantizationSummary, quantize_linear_weights
from .schema import CorpusEntry, QualityCorpus, RunConfig

TransformResult = TypeVar("TransformResult")


@dataclass(frozen=True)
class TokenizedExample:
    identifier: str
    input_ids: torch.Tensor
    target_start: int
    target_tokens: int


@dataclass(frozen=True)
class BaselineEvaluation:
    identifier: str
    target_logits: torch.Tensor
    nll_sum: float
    target_tokens: int


@dataclass(frozen=True)
class ModelPairEvaluation(Generic[TransformResult]):
    aggregate: EvaluationAggregate
    transform: TransformResult
    weight_files: list[Path]
    runtime_tokenizer_identity: dict[str, object]


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
        lambda model: _quantize_candidate(model, config, model_path),
    )
    aggregate = evaluation.aggregate
    quantization = evaluation.transform

    report = _build_report(
        model_path=model_path,
        config_path=config_path,
        corpus_path=corpus_path,
        config=config,
        corpus=corpus,
        aggregate=aggregate,
        quantization=quantization,
        weight_files=evaluation.weight_files,
        runtime_tokenizer_identity=evaluation.runtime_tokenizer_identity,
    )
    stable_document = {
        "scope": report["scope"],
        "inputs": report["inputs"],
        "quantization": report["quantization"],
        "corpus": report["corpus"],
        "metrics": report["metrics"],
        "quality_report": report["quality_report"],
    }
    report["content_identity_sha256"] = hashlib.sha256(
        json.dumps(stable_document, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return report


def evaluate_model_transform(
    model_path: Path,
    config: Any,
    corpus: QualityCorpus,
    transform: Callable[[torch.nn.Module], TransformResult],
) -> ModelPairEvaluation[TransformResult]:
    weight_files = validate_model_directory(model_path)
    _configure_runtime(config)
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=False,
    )
    runtime_tokenizer_identity = tokenizer_identity(model_path, tokenizer)
    _validate_tokenizer_identity(corpus, runtime_tokenizer_identity)
    tokenized = [_tokenize(tokenizer, entry) for entry in corpus.entries]
    _validate_tokenized_corpus(corpus, tokenized)
    dtype = _torch_dtype(config.dtype)

    if config.evaluation_strategy == "sequential_models":
        baseline_model = _load_model(model_path, dtype)
        _validate_context_lengths(baseline_model, tokenized)
        baseline_evaluations = [
            _evaluate_baseline(baseline_model, example) for example in tokenized
        ]
        del baseline_model
        gc.collect()

        candidate_model = _load_model(model_path, dtype)
        transform_result = transform(candidate_model)
        records = [
            _evaluate_candidate(candidate_model, example, reference)
            for example, reference in zip(tokenized, baseline_evaluations, strict=True)
        ]
        del baseline_evaluations
        del candidate_model
        gc.collect()
    else:
        baseline_model = _load_model(model_path, dtype)
        candidate_model = _load_model(model_path, dtype)
        _validate_context_lengths(baseline_model, tokenized)
        transform_result = transform(candidate_model)
        records = []
        processed_target_tokens = 0
        for index, example in enumerate(tokenized, start=1):
            records.append(
                _evaluate_candidate(
                    candidate_model,
                    example,
                    _evaluate_baseline(baseline_model, example),
                )
            )
            processed_target_tokens += example.target_tokens
            if index % 8 == 0 or index == len(tokenized):
                print(
                    json.dumps(
                        {
                            "evaluation_progress": {
                                "examples": index,
                                "target_tokens": processed_target_tokens,
                                "total_examples": len(tokenized),
                            }
                        },
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                    flush=True,
                )
        del baseline_model
        del candidate_model
        gc.collect()
    return ModelPairEvaluation(
        aggregate=aggregate_evaluations(records),
        transform=transform_result,
        weight_files=weight_files,
        runtime_tokenizer_identity=runtime_tokenizer_identity,
    )


def _configure_runtime(config: RunConfig) -> None:
    random.seed(config.seed)
    torch.manual_seed(config.seed)
    torch.set_num_threads(config.torch_threads)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")


def _torch_dtype(name: str) -> torch.dtype:
    return {
        "float32": torch.float32,
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
    }[name]


def _load_model(model_path: Path, dtype: torch.dtype) -> torch.nn.Module:
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=False,
        dtype=dtype,
        low_cpu_mem_usage=True,
    )
    model.to("cpu")
    model.eval()
    return model


def _quantize_candidate(
    model: torch.nn.Module,
    config: RunConfig,
    model_path: Path,
) -> QuantizationSummary:
    quantization = quantize_linear_weights(
        model,
        granularity=config.granularity,
        group_size=config.group_size,
        excluded_patterns=config.excluded_modules,
        baseline_checkpoint_bits_per_parameter=checkpoint_precision_bits(model_path),
    )
    if quantization.module_count == 0:
        raise RuntimeError("no eligible Linear modules were quantized")
    return quantization


def _tokenize(tokenizer: Any, entry: CorpusEntry) -> TokenizedExample:
    prompt_ids = tokenizer.encode(entry.prompt, add_special_tokens=True)
    completion_ids = tokenizer.encode(entry.completion, add_special_tokens=False)
    if not prompt_ids:
        fallback_token = tokenizer.bos_token_id
        if fallback_token is None:
            fallback_token = tokenizer.eos_token_id
        if fallback_token is None:
            raise ValueError(
                f"tokenizer produced no prompt tokens for {entry.identifier}"
            )
        prompt_ids = [fallback_token]
    if not completion_ids:
        raise ValueError(
            f"tokenizer produced no completion tokens for {entry.identifier}"
        )
    input_ids = torch.tensor([prompt_ids + completion_ids], dtype=torch.long)
    return TokenizedExample(
        identifier=entry.identifier,
        input_ids=input_ids,
        target_start=len(prompt_ids) - 1,
        target_tokens=len(completion_ids),
    )


def _validate_context_lengths(
    model: torch.nn.Module, examples: list[TokenizedExample]
) -> None:
    maximum = int(getattr(model.config, "max_position_embeddings", 0))
    if maximum <= 0:
        return
    oversized = [
        example.identifier
        for example in examples
        if example.input_ids.shape[1] > maximum
    ]
    if oversized:
        raise ValueError(f"corpus exceeds model context for: {', '.join(oversized)}")


def _validate_tokenized_corpus(
    corpus: QualityCorpus,
    examples: list[TokenizedExample],
) -> None:
    if len(examples) != corpus.expected_example_count:
        raise ValueError(
            "tokenized example count does not match the corpus declaration"
        )
    target_tokens = sum(example.target_tokens for example in examples)
    if (
        corpus.expected_target_tokens is not None
        and target_tokens != corpus.expected_target_tokens
    ):
        raise ValueError(
            "tokenized target token count does not match the corpus declaration: "
            f"expected {corpus.expected_target_tokens}, measured {target_tokens}"
        )


def _validate_tokenizer_identity(
    corpus: QualityCorpus,
    actual: dict[str, object],
) -> None:
    expected = corpus.tokenizer
    if not expected:
        return
    for field in ("class", "vocab_size"):
        if field in expected and expected[field] != actual.get(field):
            raise ValueError(
                f"runtime tokenizer identity does not match corpus {field}"
            )
    expected_files = expected.get("files", [])
    actual_files = actual.get("files", [])
    if not isinstance(expected_files, list) or not isinstance(actual_files, list):
        raise ValueError("tokenizer identity files must be arrays")
    actual_hashes = {
        str(value.get("name")): str(value.get("sha256"))
        for value in actual_files
        if isinstance(value, dict)
    }
    for value in expected_files:
        if not isinstance(value, dict):
            raise ValueError("corpus tokenizer identity contains an invalid file")
        name = str(value.get("name", ""))
        expected_hash = str(value.get("sha256", ""))
        if not name or not expected_hash or actual_hashes.get(name) != expected_hash:
            raise ValueError(
                f"runtime tokenizer identity does not match corpus file {name}"
            )


def _target_logits(model: torch.nn.Module, example: TokenizedExample) -> torch.Tensor:
    with torch.inference_mode():
        output = model(input_ids=example.input_ids, use_cache=False)
        end = example.target_start + example.target_tokens
        return output.logits[:, example.target_start : end, :].to(torch.float32).cpu()


def _targets(example: TokenizedExample) -> torch.Tensor:
    start = example.target_start + 1
    return example.input_ids[:, start : start + example.target_tokens]


def _nll_sum(logits: torch.Tensor, targets: torch.Tensor) -> float:
    return float(
        functional.cross_entropy(
            logits.reshape(-1, logits.shape[-1]),
            targets.reshape(-1),
            reduction="sum",
        ).item()
    )


def _evaluate_baseline(
    model: torch.nn.Module,
    example: TokenizedExample,
) -> BaselineEvaluation:
    logits = _target_logits(model, example)
    return BaselineEvaluation(
        identifier=example.identifier,
        target_logits=logits,
        nll_sum=_nll_sum(logits, _targets(example)),
        target_tokens=example.target_tokens,
    )


def _evaluate_candidate(
    model: torch.nn.Module,
    example: TokenizedExample,
    reference: BaselineEvaluation,
) -> EvaluationSums:
    if example.identifier != reference.identifier:
        raise ValueError("baseline and candidate example order differs")
    candidate_logits = _target_logits(model, example)
    baseline_logits = reference.target_logits
    difference = candidate_logits - baseline_logits
    return EvaluationSums(
        target_tokens=example.target_tokens,
        baseline_nll_sum=reference.nll_sum,
        candidate_nll_sum=_nll_sum(candidate_logits, _targets(example)),
        squared_logit_error_sum=float(torch.sum(difference * difference).item()),
        logit_values=difference.numel(),
        logit_dot_product=float(torch.sum(baseline_logits * candidate_logits).item()),
        baseline_logit_squared_sum=float(
            torch.sum(baseline_logits * baseline_logits).item()
        ),
        candidate_logit_squared_sum=float(
            torch.sum(candidate_logits * candidate_logits).item()
        ),
        top1_matches=int(
            torch.sum(
                torch.argmax(baseline_logits, dim=-1)
                == torch.argmax(candidate_logits, dim=-1)
            ).item()
        ),
        compared_positions=example.target_tokens,
    )


def _build_report(
    *,
    model_path: Path,
    config_path: Path,
    corpus_path: Path,
    config: RunConfig,
    corpus: QualityCorpus,
    aggregate: EvaluationAggregate,
    quantization: QuantizationSummary,
    weight_files: list[Path],
    runtime_tokenizer_identity: dict[str, object],
) -> dict[str, object]:
    quality_report = _quality_report(config, aggregate)
    corpus_sha256 = sha256_file(corpus_path)
    return {
        "schema_version": "inference-foundry.quality-validation.v2",
        "scope": {
            "supported_claim": "Measured teacher-forced quality-proxy delta from symmetric weight-only INT4 QDQ on a local Qwen3-0.6B checkpoint on CPU.",
            "unsupported_claims": [
                "task accuracy or end-to-end agent success",
                "Qwen3-8B quality",
                "packed INT4 kernel correctness, memory use, or speed",
                "KV-cache quantization or reduced KV-head quality",
                "FFN architecture changes",
                "serving throughput, latency, energy, or cost",
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
            "model": model_identity(model_path, weight_files),
            "tokenizer": runtime_tokenizer_identity,
            "software": software_identity(),
            "deterministic_algorithms": True,
        },
        "quantization": quantization.to_dict(),
        "corpus": _build_corpus_report(
            corpus,
            actual_target_tokens=aggregate.target_tokens,
            corpus_sha256=corpus_sha256,
        ),
        "metrics": aggregate.to_dict(),
        "quality_report": quality_report,
    }


def _build_corpus_report(
    corpus: QualityCorpus,
    *,
    actual_target_tokens: int,
    corpus_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": corpus.schema_version,
        "kind": corpus.kind,
        "description": corpus.description,
        "task": corpus.task,
        "is_standard_benchmark": corpus.is_standard_benchmark,
        "source": corpus.source,
        "generation": corpus.generation,
        "tokenizer": corpus.tokenizer,
        "generated_corpus_sha256": corpus_sha256,
        "example_count": len(corpus.entries),
        "expected_example_count": corpus.expected_example_count,
        "target_tokens": actual_target_tokens,
        "expected_target_tokens": corpus.expected_target_tokens,
        "example_ids": [entry.identifier for entry in corpus.entries],
    }


def _quality_report(
    config: RunConfig, aggregate: EvaluationAggregate
) -> dict[str, object]:
    thresholds = config.thresholds
    metrics = [
        {
            "name": "mean_nll",
            "baseline": aggregate.baseline_mean_nll,
            "candidate": aggregate.candidate_mean_nll,
            "allowed_regression": thresholds.maximum_nll_increase,
            "higher_is_better": False,
        },
        {
            "name": "perplexity",
            "baseline": aggregate.baseline_perplexity,
            "candidate": aggregate.candidate_perplexity,
            "allowed_regression": aggregate.baseline_perplexity
            * (thresholds.maximum_perplexity_ratio - 1.0),
            "higher_is_better": False,
        },
        {
            "name": "logit_rmse",
            "baseline": 0.0,
            "candidate": aggregate.logit_rmse,
            "allowed_regression": thresholds.maximum_logit_rmse,
            "higher_is_better": False,
        },
        {
            "name": "logit_cosine_similarity",
            "baseline": 1.0,
            "candidate": aggregate.logit_cosine_similarity,
            "allowed_regression": 1.0 - thresholds.minimum_logit_cosine_similarity,
            "higher_is_better": True,
        },
        {
            "name": "top1_agreement",
            "baseline": 1.0,
            "candidate": aggregate.top1_agreement,
            "allowed_regression": 1.0 - thresholds.minimum_top1_agreement,
            "higher_is_better": True,
        },
    ]
    passed = all(_metric_passes(metric) for metric in metrics)
    return {"suite": config.suite, "metrics": metrics, "passed": passed}


def _metric_passes(metric: dict[str, object]) -> bool:
    baseline = float(metric["baseline"])
    candidate = float(metric["candidate"])
    allowed = float(metric["allowed_regression"])
    regression = (
        baseline - candidate if metric["higher_is_better"] else candidate - baseline
    )
    return regression <= allowed
