from __future__ import annotations

import gc
import hashlib
import json
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from validation.qwen_int4_quality.provenance import sha256_file, software_identity

from .dataset import (
    PiqaExample,
    canonical_rows_sha256,
    hash_ranked_indices,
    load_piqa_validation,
    selected_indices_sha256,
)
from .quantization import FrozenMaskSummary, quantize_frozen_selective_mask
from .schema import GateConfig, TaskConfig, UncertaintyConfig, load_task_config
from .scoring import (
    ChoiceEncoding,
    build_choice_encoding,
    length_normalized_continuation_log_likelihood,
)
from .statistics import (
    exact_two_sided_mcnemar_p,
    paired_bootstrap_accuracy_delta_interval,
    paired_outcomes,
)


@dataclass(frozen=True)
class ExampleScore:
    identifier: str
    label: int
    choice_scores: tuple[float, float]

    @property
    def prediction(self) -> int:
        return 0 if self.choice_scores[0] >= self.choice_scores[1] else 1

    @property
    def correct(self) -> bool:
        return self.prediction == self.label

    @property
    def correct_choice_score(self) -> float:
        return self.choice_scores[self.label]

    @property
    def incorrect_choice_score(self) -> float:
        return self.choice_scores[1 - self.label]

    @property
    def correct_choice_margin(self) -> float:
        return self.correct_choice_score - self.incorrect_choice_score

    def to_dict(self) -> dict[str, object]:
        return {
            "identifier": self.identifier,
            "label": self.label,
            "choice_scores": list(self.choice_scores),
            "prediction": self.prediction,
            "correct": self.correct,
            "correct_choice_score": self.correct_choice_score,
            "incorrect_choice_score": self.incorrect_choice_score,
            "correct_choice_margin": self.correct_choice_margin,
        }


@dataclass(frozen=True)
class EncodedTaskExample:
    source: PiqaExample
    choices: tuple[ChoiceEncoding, ChoiceEncoding]


def aggregate_task_scores(
    baseline: list[ExampleScore],
    candidate: list[ExampleScore],
    gates: GateConfig,
    uncertainty: UncertaintyConfig,
    *,
    seed: int,
) -> dict[str, object]:
    if not baseline or len(baseline) != len(candidate):
        raise ValueError(
            "baseline and candidate scores must have equal non-zero length"
        )
    for reference, measured in zip(baseline, candidate, strict=True):
        if (
            reference.identifier != measured.identifier
            or reference.label != measured.label
        ):
            raise ValueError("baseline and candidate example order differs")
    baseline_correct = [score.correct for score in baseline]
    candidate_correct = [score.correct for score in candidate]
    outcomes = paired_outcomes(baseline_correct, candidate_correct)
    count = len(baseline)
    baseline_accuracy = sum(baseline_correct) / count
    candidate_accuracy = sum(candidate_correct) / count
    accuracy_delta = candidate_accuracy - baseline_accuracy
    bootstrap = paired_bootstrap_accuracy_delta_interval(
        baseline_correct,
        candidate_correct,
        samples=uncertainty.paired_bootstrap_samples,
        confidence_level=uncertainty.confidence_level,
        seed=seed,
    )
    prediction_changes = sum(
        reference.prediction != measured.prediction
        for reference, measured in zip(baseline, candidate, strict=True)
    )
    return {
        "example_count": count,
        "baseline": _score_aggregate(baseline),
        "candidate": _score_aggregate(candidate),
        "accuracy_delta": accuracy_delta,
        "paired_outcomes": outcomes.to_dict(),
        "prediction_change_count": prediction_changes,
        "prediction_change_rate": prediction_changes / count,
        "exact_two_sided_mcnemar_p": exact_two_sided_mcnemar_p(
            outcomes.candidate_only_correct,
            outcomes.baseline_only_correct,
        ),
        "paired_bootstrap_accuracy_delta": {
            "method": "paired_percentile_bootstrap",
            "seed": seed,
            "samples": uncertainty.paired_bootstrap_samples,
            "confidence_level": uncertainty.confidence_level,
            "lower": bootstrap[0],
            "upper": bootstrap[1],
        },
        "uncertainty_interpretation": {
            "bootstrap_interval_excludes_accuracy_drop_beyond_margin": bootstrap[0]
            >= -gates.maximum_accuracy_drop,
            "confirmatory_non_inferiority_established": bootstrap[0]
            >= -gates.maximum_accuracy_drop,
            "basis": (
                "The predeclared point-estimate gate is distinct from this descriptive "
                "paired-bootstrap interval diagnostic."
            ),
        },
        "gate": {
            "name": "task_accuracy_non_inferiority",
            "maximum_accuracy_drop": gates.maximum_accuracy_drop,
            "measured_accuracy_drop": baseline_accuracy - candidate_accuracy,
            "passed": baseline_accuracy - candidate_accuracy
            <= gates.maximum_accuracy_drop + 1e-12,
        },
    }


def run_task_validation(
    *,
    config_path: Path,
    dataset_script_path: Path,
    archive_path: Path,
    validation_jsonl_path: Path,
    validation_labels_path: Path,
    raw_output_path: Path,
) -> dict[str, object]:
    config = load_task_config(config_path)
    _configure_runtime(config)
    model_path = Path(config.model.local_path)
    _validate_inputs(
        config,
        model_path,
        dataset_script_path,
        archive_path,
        validation_jsonl_path,
        validation_labels_path,
    )
    all_rows = load_piqa_validation(validation_jsonl_path, validation_labels_path)
    if len(all_rows) != config.dataset.expected_validation_rows:
        raise ValueError("PIQA validation row count does not match the frozen contract")
    if (
        canonical_rows_sha256(all_rows)
        != config.dataset.expected_validation_rows_sha256
    ):
        raise ValueError(
            "PIQA validation row identity does not match the frozen contract"
        )
    selected_indices = hash_ranked_indices(
        len(all_rows),
        config.selection.example_count,
        config.selection.seed,
    )
    selected = [all_rows[index] for index in selected_indices]
    if (
        selected_indices_sha256(selected_indices)
        != config.selection.expected_selected_indices_sha256
    ):
        raise ValueError(
            "selected PIQA index identity does not match the frozen contract"
        )
    if (
        canonical_rows_sha256(selected)
        != config.selection.expected_selected_rows_sha256
    ):
        raise ValueError(
            "selected PIQA row identity does not match the frozen contract"
        )
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=False,
    )
    encoded = [_encode_example(tokenizer, config, example) for example in selected]
    maximum_sequence_tokens = max(
        choice.input_ids.shape[1] for example in encoded for choice in example.choices
    )
    total_continuation_tokens = sum(
        choice.target_tokens for example in encoded for choice in example.choices
    )
    pad_token_id = tokenizer.pad_token_id
    if pad_token_id is None:
        pad_token_id = tokenizer.eos_token_id
    if pad_token_id is None:
        raise ValueError("tokenizer has no pad or EOS token")

    baseline_model = _load_model(model_path)
    _validate_model_context(baseline_model, maximum_sequence_tokens)
    baseline_scores = _score_model(
        baseline_model,
        encoded,
        int(pad_token_id),
        phase="baseline",
    )
    del baseline_model
    gc.collect()

    candidate_model = _load_model(model_path)
    quantization = quantize_frozen_selective_mask(
        candidate_model,
        expected_module_count=config.quantization.expected_module_count,
        expected_parameter_count=config.quantization.expected_parameter_count,
    )
    candidate_scores = _score_model(
        candidate_model,
        encoded,
        int(pad_token_id),
        phase="candidate",
    )
    unique_parameter_count = sum(
        parameter.numel() for parameter in candidate_model.parameters()
    )
    del candidate_model
    gc.collect()

    metrics = aggregate_task_scores(
        baseline_scores,
        candidate_scores,
        config.gates,
        config.uncertainty,
        seed=config.seed,
    )
    storage = _storage_estimate(quantization, unique_parameter_count)
    raw_report = _raw_report(
        config=config,
        config_path=config_path,
        dataset_script_path=dataset_script_path,
        archive_path=archive_path,
        validation_jsonl_path=validation_jsonl_path,
        validation_labels_path=validation_labels_path,
        selected_indices=selected_indices,
        selected=selected,
        baseline=baseline_scores,
        candidate=candidate_scores,
        quantization=quantization,
        storage=storage,
        metrics=metrics,
        tokenizer=tokenizer,
        maximum_sequence_tokens=maximum_sequence_tokens,
        total_continuation_tokens=total_continuation_tokens,
    )
    raw_report["content_identity_sha256"] = _content_identity(raw_report)
    raw_output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_output_path.write_text(
        json.dumps(raw_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return _summary_report(
        raw_report,
        raw_output_path=raw_output_path,
        raw_output_sha256=sha256_file(raw_output_path),
    )


def _score_aggregate(scores: list[ExampleScore]) -> dict[str, float | int]:
    count = len(scores)
    correct = sum(score.correct for score in scores)
    return {
        "correct": correct,
        "accuracy": correct / count,
        "mean_correct_choice_log_likelihood_per_token": sum(
            score.correct_choice_score for score in scores
        )
        / count,
        "mean_incorrect_choice_log_likelihood_per_token": sum(
            score.incorrect_choice_score for score in scores
        )
        / count,
        "mean_correct_choice_margin_per_token": sum(
            score.correct_choice_margin for score in scores
        )
        / count,
    }


def _configure_runtime(config: TaskConfig) -> None:
    random.seed(config.seed)
    torch.manual_seed(config.seed)
    torch.set_num_threads(config.torch_threads)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")


def _load_model(model_path: Path) -> torch.nn.Module:
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
    )
    model.to("cpu")
    model.eval()
    return model


def _encode_example(
    tokenizer: Any,
    config: TaskConfig,
    example: PiqaExample,
) -> EncodedTaskExample:
    prompt = config.prompt.template.format(goal=example.goal)
    choices = tuple(
        build_choice_encoding(
            tokenizer,
            prompt=prompt,
            choice=choice,
            choice_prefix=config.prompt.choice_prefix,
        )
        for choice in example.choices
    )
    return EncodedTaskExample(example, (choices[0], choices[1]))


def _score_model(
    model: torch.nn.Module,
    examples: list[EncodedTaskExample],
    pad_token_id: int,
    *,
    phase: str,
) -> list[ExampleScore]:
    results: list[ExampleScore] = []
    with torch.inference_mode():
        for position, example in enumerate(examples, start=1):
            lengths = [choice.input_ids.shape[1] for choice in example.choices]
            maximum = max(lengths)
            input_ids = torch.full((2, maximum), pad_token_id, dtype=torch.long)
            attention_mask = torch.zeros((2, maximum), dtype=torch.long)
            for choice_index, choice in enumerate(example.choices):
                length = lengths[choice_index]
                input_ids[choice_index, :length] = choice.input_ids[0]
                attention_mask[choice_index, :length] = 1
            logits = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                use_cache=False,
            ).logits
            choice_scores = tuple(
                length_normalized_continuation_log_likelihood(
                    logits[choice_index : choice_index + 1],
                    choice.input_ids,
                    target_start=choice.target_start,
                    target_tokens=choice.target_tokens,
                )
                for choice_index, choice in enumerate(example.choices)
            )
            results.append(
                ExampleScore(
                    identifier=example.source.identifier,
                    label=example.source.label,
                    choice_scores=(choice_scores[0], choice_scores[1]),
                )
            )
            if position % 16 == 0 or position == len(examples):
                print(
                    json.dumps(
                        {
                            "task_quality_progress": {
                                "phase": phase,
                                "examples": position,
                                "total_examples": len(examples),
                            }
                        },
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                    flush=True,
                )
    return results


def _validate_model_context(model: torch.nn.Module, maximum_tokens: int) -> None:
    maximum = int(getattr(model.config, "max_position_embeddings", 0))
    if maximum > 0 and maximum_tokens > maximum:
        raise ValueError("PIQA continuation exceeds the model context length")


def _validate_inputs(
    config: TaskConfig,
    model_path: Path,
    dataset_script_path: Path,
    archive_path: Path,
    validation_jsonl_path: Path,
    validation_labels_path: Path,
) -> None:
    _require_sha(model_path / "config.json", config.model.config_sha256)
    weight_path = model_path / config.model.weight_file
    _require_sha(weight_path, config.model.weight_sha256)
    if weight_path.stat().st_size != config.model.weight_bytes:
        raise ValueError("model weight byte count does not match the frozen contract")
    for tokenizer_file in config.model.tokenizer_files:
        _require_sha(
            model_path / tokenizer_file["name"],
            tokenizer_file["sha256"],
        )
    _require_sha(dataset_script_path, config.dataset.dataset_script_sha256)
    _require_sha(archive_path, config.dataset.archive_sha256)
    _require_sha(validation_jsonl_path, config.dataset.validation_jsonl_sha256)
    _require_sha(validation_labels_path, config.dataset.validation_labels_sha256)


def _require_sha(path: Path, expected: str) -> None:
    if sha256_file(path) != expected:
        raise ValueError(f"SHA-256 does not match the frozen contract: {path}")


def _storage_estimate(
    quantization: FrozenMaskSummary,
    unique_parameter_count: int,
) -> dict[str, object]:
    packed_code_bytes = (quantization.parameter_count * 4 + 7) // 8
    scale_bytes = quantization.scale_count * 2
    retained_parameters = unique_parameter_count - quantization.parameter_count
    retained_bytes = retained_parameters * 2
    baseline_bytes = unique_parameter_count * 2
    deployed_bytes = packed_code_bytes + scale_bytes + retained_bytes
    return {
        "kind": "logical_packed_mixed_precision_weight_estimate",
        "unique_parameter_count": unique_parameter_count,
        "baseline_bfloat16_bytes": baseline_bytes,
        "quantized_parameter_count": quantization.parameter_count,
        "packed_code_bytes": packed_code_bytes,
        "bfloat16_scale_bytes": scale_bytes,
        "retained_bfloat16_parameter_count": retained_parameters,
        "retained_bfloat16_bytes": retained_bytes,
        "estimated_deployed_weight_bytes": deployed_bytes,
        "estimated_whole_model_bits_per_parameter": deployed_bytes
        * 8
        / unique_parameter_count,
        "estimated_weight_storage_reduction_percent": 100
        * (baseline_bytes - deployed_bytes)
        / baseline_bytes,
        "runtime_storage_compressed": False,
    }


def _raw_report(
    *,
    config: TaskConfig,
    config_path: Path,
    dataset_script_path: Path,
    archive_path: Path,
    validation_jsonl_path: Path,
    validation_labels_path: Path,
    selected_indices: list[int],
    selected: list[PiqaExample],
    baseline: list[ExampleScore],
    candidate: list[ExampleScore],
    quantization: FrozenMaskSummary,
    storage: dict[str, object],
    metrics: dict[str, object],
    tokenizer: Any,
    maximum_sequence_tokens: int,
    total_continuation_tokens: int,
) -> dict[str, object]:
    return {
        "schema_version": "inference-foundry.int4-task-quality-report.v1",
        "suite": config.suite,
        "scope": {
            "supported_claim": (
                "Measured paired accuracy and token-length-normalized continuation scores "
                "on a frozen PIQA validation subset for the pinned Qwen3-0.6B selective "
                "group-8 INT4 candidate with BF16-stored scales materialized into BF16 "
                "weights on CPU."
            ),
            "unsupported_claims": [
                "full standard PIQA benchmark accuracy",
                "benchmark decontamination",
                "packed INT4 kernel execution or numerical equivalence",
                "unseen-task or agentic-workload generalization",
                "model safety",
                "serving throughput or latency",
                "energy or dollars per token",
                "Qwen3 models other than the pinned 0.6B checkpoint",
            ],
        },
        "contract": {
            "config_path": str(config_path),
            "config_sha256": sha256_file(config_path),
            "frozen_before_model_scoring": True,
            "seed": config.seed,
            "dtype": config.dtype,
            "torch_threads": config.torch_threads,
            "prompt": asdict(config.prompt),
            "scoring": asdict(config.scoring),
            "gates": asdict(config.gates),
            "uncertainty": asdict(config.uncertainty),
        },
        "provenance": {
            "model": {
                **asdict(config.model),
                "local_files_only": True,
            },
            "tokenizer": {
                "class": type(tokenizer).__name__,
                "vocab_size": int(tokenizer.vocab_size),
                "files": list(config.model.tokenizer_files),
            },
            "dataset": {
                **asdict(config.dataset),
                "dataset_script_path": str(dataset_script_path),
                "archive_path": str(archive_path),
                "validation_jsonl_path": str(validation_jsonl_path),
                "validation_labels_path": str(validation_labels_path),
            },
            "software": software_identity(),
            "deterministic_algorithms": True,
        },
        "selection": {
            **asdict(config.selection),
            "selected_indices": selected_indices,
            "selected_example_ids": [example.identifier for example in selected],
            "measured_selected_indices_sha256": selected_indices_sha256(
                selected_indices
            ),
            "measured_selected_rows_sha256": canonical_rows_sha256(selected),
            "is_full_standard_benchmark": False,
        },
        "tokenization": {
            "joint_prompt_plus_continuation": True,
            "prompt_prefix_must_be_token_prefix": True,
            "choice_count": len(selected) * 2,
            "total_continuation_tokens_across_both_choices": total_continuation_tokens,
            "maximum_sequence_tokens": maximum_sequence_tokens,
        },
        "quantization": quantization.to_dict(),
        "storage": storage,
        "metrics": metrics,
        "examples": [
            {
                "identifier": reference.identifier,
                "label": reference.label,
                "baseline": reference.to_dict(),
                "candidate": measured.to_dict(),
            }
            for reference, measured in zip(baseline, candidate, strict=True)
        ],
        "claims": {
            "measured_frozen_piqa_subset_task_quality": True,
            "runtime_representation_bridge_materialized": True,
            "full_standard_benchmark": False,
            "packed_kernel_executed": False,
            "packed_kernel_equivalence": False,
            "safety": False,
            "serving_performance": False,
            "energy": False,
            "cost_per_token": False,
            "decontamination_checked": False,
        },
    }


def _summary_report(
    raw_report: dict[str, object],
    *,
    raw_output_path: Path,
    raw_output_sha256: str,
) -> dict[str, object]:
    metrics = raw_report["metrics"]
    if not isinstance(metrics, dict):
        raise ValueError("raw report metrics must be an object")
    gate = metrics["gate"]
    if not isinstance(gate, dict):
        raise ValueError("raw report gate must be an object")
    passed = bool(gate["passed"])
    uncertainty_interpretation = metrics["uncertainty_interpretation"]
    if not isinstance(uncertainty_interpretation, dict):
        raise ValueError("raw report uncertainty interpretation must be an object")
    confirmatory = bool(
        uncertainty_interpretation["confirmatory_non_inferiority_established"]
    )
    if passed and confirmatory:
        conclusion = (
            "The frozen selective INT4 candidate passed the predeclared 2-percentage-point "
            "point-estimate gate and its descriptive paired-bootstrap interval excluded a "
            "larger accuracy drop on the deterministic 256-example PIQA validation subset. "
            "This remains subset-level evidence, not a full benchmark, packed-kernel "
            "equivalence, serving, safety, energy, or cost result."
        )
    elif passed:
        conclusion = (
            "The frozen selective INT4 candidate passed the predeclared 2-percentage-point "
            "point-estimate gate on the deterministic 256-example PIQA validation subset, "
            "but the paired-bootstrap interval crossed the non-inferiority margin, so "
            "confirmatory non-inferiority remains inconclusive. This is not a full benchmark, "
            "packed-kernel equivalence, serving, safety, energy, or cost result."
        )
    else:
        conclusion = (
            "The frozen selective INT4 candidate failed the predeclared 2-percentage-point "
            "accuracy non-inferiority gate on a deterministic 256-example PIQA validation "
            "subset. The selective quantization direction is not promoted despite any "
            "storage estimate or proxy result."
        )
    summary = {
        "schema_version": "inference-foundry.int4-task-quality-summary.v1",
        "suite": raw_report["suite"],
        "scope": raw_report["scope"],
        "contract": raw_report["contract"],
        "provenance": raw_report["provenance"],
        "selection": raw_report["selection"],
        "tokenization": raw_report["tokenization"],
        "quantization": raw_report["quantization"],
        "storage": raw_report["storage"],
        "metrics": metrics,
        "claims": raw_report["claims"],
        "raw_artifact": {
            "path": str(raw_output_path),
            "sha256": raw_output_sha256,
            "bytes": raw_output_path.stat().st_size,
            "content_identity_sha256": raw_report["content_identity_sha256"],
            "checked_in": False,
        },
        "conclusion": conclusion,
    }
    summary["content_identity_sha256"] = _content_identity(summary)
    return summary


def _content_identity(document: dict[str, object]) -> str:
    stable = {
        key: value
        for key, value in document.items()
        if key != "content_identity_sha256"
    }
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
