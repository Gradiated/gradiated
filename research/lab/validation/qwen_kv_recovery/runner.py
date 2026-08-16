from __future__ import annotations

import gc
import hashlib
import json
import os
import random
import resource
import sys
import time
from pathlib import Path
from typing import Any

import torch
from datasets import load_dataset
from safetensors.torch import save_file
from transformers import AutoModelForCausalLM, AutoTokenizer

from validation.qwen_int4_quality.provenance import (
    checkpoint_precision_bits,
    model_identity,
    sha256_file,
    software_identity,
    tokenizer_identity,
    validate_model_directory,
)
from validation.qwen_int4_quality.schema import QualityCorpus

from .data import TrainingCorpus, build_training_windows
from .evaluation import evaluate_holdout, prepare_holdout
from .schema import RecoveryConfig
from .training import distillation_objective, should_promote
from .transform import (
    RecoveryStructureSummary,
    adapter_state_dict,
    apply_recovery_structure,
    assert_exact_kv_sharing,
)


def run_recovery(
    *,
    model_path: Path,
    config_path: Path,
    first_holdout_path: Path,
    first_holdout: QualityCorpus,
    confirmation_holdout_path: Path,
    confirmation_holdout: QualityCorpus,
    output_path: Path,
    config: RecoveryConfig,
    maximum_training_target_tokens: int,
) -> dict[str, object]:
    started = time.perf_counter()
    checkpoints = tuple(
        value
        for value in config.checkpoint_tokens
        if value <= maximum_training_target_tokens
    )
    _validate_effective_budget(config, maximum_training_target_tokens, checkpoints)
    _configure_runtime(config)
    weight_files = validate_model_directory(model_path)
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=False,
    )
    runtime_tokenizer_identity = tokenizer_identity(model_path, tokenizer)
    dataset, training_corpus, dataset_identity = _load_training_corpus(
        config, tokenizer
    )
    del dataset
    gc.collect()
    teacher = _load_model(model_path)
    student = _load_model(model_path)
    structure = apply_recovery_structure(
        student,
        original_kv_heads=config.transform.original_kv_heads,
        unique_kv_heads=config.transform.unique_kv_heads,
        adapter_rank=config.adapter.rank,
        adapter_alpha=config.adapter.alpha,
    )
    _validate_structure(structure)
    _enforce_memory_bound(config, "model initialization")
    first_prepared = prepare_holdout(
        first_holdout_path,
        first_holdout,
        tokenizer,
        teacher,
        runtime_tokenizer_identity,
    )
    confirmation_prepared = prepare_holdout(
        confirmation_holdout_path,
        confirmation_holdout,
        tokenizer,
        teacher,
        runtime_tokenizer_identity,
    )
    optimizer = torch.optim.AdamW(
        (value for value in student.parameters() if value.requires_grad),
        lr=config.optimization.learning_rate,
        weight_decay=config.optimization.weight_decay,
    )
    report = _initial_report(
        model_path=model_path,
        config_path=config_path,
        first_holdout_path=first_holdout_path,
        confirmation_holdout_path=confirmation_holdout_path,
        output_path=output_path,
        config=config,
        maximum_training_target_tokens=maximum_training_target_tokens,
        checkpoints=checkpoints,
        weight_files=weight_files,
        tokenizer_identity_value=runtime_tokenizer_identity,
        dataset_identity=dataset_identity,
        training_corpus=training_corpus,
        structure=structure,
    )
    loss_trajectory: list[dict[str, object]] = []
    checkpoint_evaluations: list[dict[str, object]] = []
    checkpoint_artifacts: list[dict[str, object]] = []
    training_started = time.perf_counter()
    prior_checkpoint_time = training_started
    prior_checkpoint_step = 0
    effective_windows = training_corpus.windows[
        : maximum_training_target_tokens // training_corpus.target_tokens_per_step
    ]
    for window in effective_windows:
        step_started = time.perf_counter()
        input_ids = torch.tensor([window.input_ids], dtype=torch.long)
        targets = torch.tensor([window.target_ids], dtype=torch.long)
        with torch.inference_mode():
            teacher_logits = teacher(input_ids=input_ids, use_cache=False).logits[
                :, :-1, :
            ]
        optimizer.zero_grad(set_to_none=True)
        student_logits = student(input_ids=input_ids, use_cache=False).logits[:, :-1, :]
        objective = distillation_objective(
            student_logits,
            teacher_logits,
            targets,
            temperature=config.optimization.temperature,
            teacher_kl_weight=config.optimization.teacher_kl_weight,
            next_token_weight=config.optimization.next_token_weight,
        )
        if not torch.isfinite(objective.total):
            raise RuntimeError(f"non-finite loss at optimizer step {window.step}")
        objective.total.backward()
        gradient_norm = _gradient_norm(student)
        optimizer.step()
        if not assert_exact_kv_sharing(student, structure.layer_pairings):
            raise RuntimeError(
                f"KV pair equality failed after optimizer step {window.step}"
            )
        target_tokens = window.step * training_corpus.target_tokens_per_step
        record = {
            "step": window.step,
            "cumulative_target_tokens": target_tokens,
            "total_loss": float(objective.total.detach()),
            "teacher_kl": float(objective.teacher_kl),
            "next_token_cross_entropy": float(objective.next_token_cross_entropy),
            "gradient_l2_norm": gradient_norm,
            "wall_seconds": time.perf_counter() - step_started,
            "peak_rss_bytes": _peak_rss_bytes(),
        }
        loss_trajectory.append(record)
        del objective, student_logits, teacher_logits, input_ids, targets
        gc.collect()
        _enforce_memory_bound(config, f"optimizer step {window.step}")
        print(
            json.dumps({"recovery_training_progress": record}, sort_keys=True),
            flush=True,
        )
        if target_tokens not in checkpoints:
            continue
        checkpoint_path = output_path.with_name(
            f"{output_path.stem}-adapter-{target_tokens}.safetensors"
        )
        checkpoint_state = adapter_state_dict(student)
        save_file(checkpoint_state, checkpoint_path)
        checkpoint_artifacts.append(
            {
                "training_target_tokens": target_tokens,
                "path": str(checkpoint_path),
                "bytes": checkpoint_path.stat().st_size,
                "sha256": sha256_file(checkpoint_path),
                "exact_kv_pair_sharing": assert_exact_kv_sharing(
                    student, structure.layer_pairings
                ),
                "adapter_state": _adapter_state_summary(checkpoint_state),
            }
        )
        training_segment_finished = time.perf_counter()
        segment_steps = window.step - prior_checkpoint_step
        segment_seconds = training_segment_finished - prior_checkpoint_time
        first_evaluation = evaluate_holdout(
            teacher,
            student,
            first_prepared,
            config,
            training_target_tokens=target_tokens,
        )
        first_evaluation["training_segment"] = {
            "optimizer_steps": segment_steps,
            "wall_seconds": segment_seconds,
            "seconds_per_step": segment_seconds / segment_steps,
        }
        first_evaluation["peak_rss_bytes_after_evaluation"] = _peak_rss_bytes()
        checkpoint_evaluations.append(first_evaluation)
        prior_checkpoint_time = time.perf_counter()
        prior_checkpoint_step = window.step
        _enforce_memory_bound(config, f"{target_tokens}-token holdout")
        report["training"]["loss_trajectory"] = loss_trajectory
        report["training"]["checkpoint_artifacts"] = checkpoint_artifacts
        report["evaluation"]["first_holdout_checkpoints"] = checkpoint_evaluations
        report["resources"] = _resource_report(config, started, training_started)
        _write_report(output_path, report)
        print(
            json.dumps(
                {
                    "recovery_checkpoint": {
                        "training_target_tokens": target_tokens,
                        "seconds_per_step": first_evaluation["training_segment"][
                            "seconds_per_step"
                        ],
                        "peak_rss_bytes": _peak_rss_bytes(),
                        "first_holdout_passed": first_evaluation["quality_report"][
                            "passed"
                        ],
                    }
                },
                sort_keys=True,
            ),
            flush=True,
        )
    confirmation: dict[str, object] | None = None
    reached_full_budget = (
        maximum_training_target_tokens == config.data.training_target_tokens
    )
    final_first = checkpoint_evaluations[-1]
    if reached_full_budget and should_promote(final_first["quality_report"]):
        confirmation = evaluate_holdout(
            teacher,
            student,
            confirmation_prepared,
            config,
            training_target_tokens=maximum_training_target_tokens,
        )
        _enforce_memory_bound(config, "confirmation holdout")
    report["training"]["loss_trajectory"] = loss_trajectory
    report["training"]["checkpoint_artifacts"] = checkpoint_artifacts
    report["training"]["completed_optimizer_steps"] = len(effective_windows)
    report["training"]["completed_target_tokens"] = maximum_training_target_tokens
    report["training"]["exact_kv_pair_sharing_after_training"] = (
        assert_exact_kv_sharing(
            student,
            structure.layer_pairings,
        )
    )
    report["evaluation"]["first_holdout_checkpoints"] = checkpoint_evaluations
    report["evaluation"]["confirmation_holdout"] = confirmation or {
        "ran": False,
        "reason": _confirmation_skip_reason(reached_full_budget, final_first),
    }
    report["decision"] = _decision(report, config, reached_full_budget)
    report["resources"] = _resource_report(config, started, training_started)
    _write_report(output_path, report)
    del optimizer, student, teacher
    gc.collect()
    return report


def _configure_runtime(config: RecoveryConfig) -> None:
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
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


def _load_training_corpus(
    config: RecoveryConfig,
    tokenizer: Any,
) -> tuple[Any, TrainingCorpus, dict[str, object]]:
    dataset = load_dataset(
        config.data.dataset_id,
        config.data.dataset_config,
        split=config.data.training_split,
    )
    fingerprint = str(getattr(dataset, "_fingerprint", ""))
    if fingerprint != config.data.training_dataset_fingerprint:
        raise ValueError(
            "cached training dataset fingerprint differs from the pinned recovery config"
        )
    corpus = build_training_windows(
        dataset["text"],
        tokenizer,
        reserved_calibration_tokens=config.data.reserved_calibration_tokens,
        training_target_tokens=config.data.training_target_tokens,
        target_tokens_per_step=config.data.target_tokens_per_step,
    )
    cache_files = []
    for value in getattr(dataset, "cache_files", []):
        path = Path(str(value["filename"]))
        cache_files.append(
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return (
        dataset,
        corpus,
        {
            "dataset_id": config.data.dataset_id,
            "dataset_config": config.data.dataset_config,
            "cached_builder_revision": config.data.dataset_revision,
            "split": config.data.training_split,
            "dataset_fingerprint": fingerprint,
            "dataset_row_count": len(dataset),
            "cache_files": cache_files,
            "local_files_only": True,
        },
    )


def _initial_report(
    *,
    model_path: Path,
    config_path: Path,
    first_holdout_path: Path,
    confirmation_holdout_path: Path,
    output_path: Path,
    config: RecoveryConfig,
    maximum_training_target_tokens: int,
    checkpoints: tuple[int, ...],
    weight_files: list[Path],
    tokenizer_identity_value: dict[str, object],
    dataset_identity: dict[str, object],
    training_corpus: TrainingCorpus,
    structure: RecoveryStructureSummary,
) -> dict[str, object]:
    baseline_bits = checkpoint_precision_bits(model_path)
    checkpoint_file_bytes = sum(value.stat().st_size for value in weight_files)
    current_model_identity = model_identity(model_path, weight_files)
    zero_token_control = _load_and_validate_zero_token_control(
        config,
        structure,
        current_model_identity,
        first_holdout_path,
    )
    baseline_weight_bytes = (
        (
            structure.total_parameter_count_after_adapters
            - structure.trainable_parameter_count
        )
        * baseline_bits
        // 8
    )
    semantic_cache_baseline = (
        structure.layer_count
        * 2
        * structure.original_kv_heads
        * structure.head_dim
        * baseline_bits
        // 8
    )
    semantic_cache_candidate = (
        semantic_cache_baseline
        * structure.unique_kv_heads
        // structure.original_kv_heads
    )
    merged_specialized_weight_bytes = baseline_weight_bytes - (
        structure.deduplicated_projection_parameter_count * baseline_bits // 8
    )
    unmerged_adapter_bytes = structure.trainable_parameter_count * 4
    return {
        "schema_version": "inference-foundry.qwen-kv-recovery-result.v1",
        "scope": {
            "supported_claim": "A deterministic local CPU teacher-distillation screen for whether rank-8 Q/O adapters can recover a Qwen3-0.6B checkpoint whose 8 logical KV heads remain exactly paired into 4 semantic unique heads in all 28 layers.",
            "unsupported_claims": [
                "task accuracy, chat quality, reasoning, safety, or end-to-end agent success",
                "canonical WikiText perplexity or broad language-model quality",
                "runtime storage deduplication or alias-attention kernel correctness",
                "serving throughput, latency, memory, energy, or dollars per token",
                "quality or performance transfer to GLM-5.2 or another model",
                "recovery at larger literature-scale training budgets",
                "production readiness or a provider advantage",
            ],
        },
        "inputs": {
            "suite": config.suite,
            "seed": config.seed,
            "device": config.device,
            "dtype": config.dtype,
            "torch_threads": config.torch_threads,
            "config_path": str(config_path),
            "config_sha256": sha256_file(config_path),
            "first_holdout_path": str(first_holdout_path),
            "first_holdout_sha256": sha256_file(first_holdout_path),
            "confirmation_holdout_path": str(confirmation_holdout_path),
            "confirmation_holdout_sha256": sha256_file(confirmation_holdout_path),
            "output_path": str(output_path),
        },
        "provenance": {
            "model": current_model_identity,
            "tokenizer": tokenizer_identity_value,
            "training_dataset": dataset_identity,
            "software": software_identity(),
            "deterministic_algorithms": True,
        },
        "training_data": training_corpus.to_dict(),
        "zero_token_control": zero_token_control,
        "structure": structure.to_dict(),
        "opportunity": {
            "logical_kv_heads_executed_by_stock_model": structure.original_kv_heads,
            "semantic_unique_kv_heads": structure.unique_kv_heads,
            "baseline_semantic_bf16_kv_bytes_per_token": semantic_cache_baseline,
            "specialized_semantic_bf16_kv_bytes_per_token": semantic_cache_candidate,
            "semantic_kv_byte_reduction_percent": 50.0,
            "local_checkpoint_file_bytes": checkpoint_file_bytes,
            "baseline_unique_model_weight_bytes": baseline_weight_bytes,
            "estimated_merged_specialized_unique_weight_bytes": merged_specialized_weight_bytes,
            "estimated_merged_weight_reduction_percent": 100.0
            * (baseline_weight_bytes - merged_specialized_weight_bytes)
            / baseline_weight_bytes,
            "unmerged_fp32_adapter_bytes": unmerged_adapter_bytes,
            "stock_runtime_physically_stores_four_heads": False,
            "stock_runtime_physically_deduplicates_weights": False,
        },
        "training": {
            "optimizer": config.optimization.optimizer,
            "learning_rate": config.optimization.learning_rate,
            "weight_decay": config.optimization.weight_decay,
            "teacher_kl_weight": config.optimization.teacher_kl_weight,
            "next_token_weight": config.optimization.next_token_weight,
            "temperature": config.optimization.temperature,
            "configured_target_tokens": config.data.training_target_tokens,
            "maximum_target_tokens_for_this_run": maximum_training_target_tokens,
            "checkpoints_after_target_tokens": list(checkpoints),
            "loss_trajectory": [],
            "checkpoint_artifacts": [],
        },
        "evaluation": {
            "first_holdout_checkpoints": [],
            "confirmation_holdout": None,
        },
        "claim_flags": {
            "small_budget_recoverability_signal": False,
            "runtime_alias_kernel_validated": False,
            "runtime_kv_reduction_measured": False,
            "serving_performance_measured": False,
            "cost_reduction_measured": False,
            "task_or_agent_quality_validated": False,
            "glm_5_2_transfer_validated": False,
        },
    }


def _validate_effective_budget(
    config: RecoveryConfig,
    maximum_training_target_tokens: int,
    checkpoints: tuple[int, ...],
) -> None:
    if maximum_training_target_tokens <= 0:
        raise ValueError("maximum training target tokens must be positive")
    if maximum_training_target_tokens > config.data.training_target_tokens:
        raise ValueError("maximum training target tokens exceed the configured budget")
    if maximum_training_target_tokens % config.data.target_tokens_per_step:
        raise ValueError("maximum training target tokens must align to a complete step")
    if not checkpoints or checkpoints[-1] != maximum_training_target_tokens:
        raise ValueError(
            "maximum training target tokens must be a configured checkpoint"
        )


def _load_and_validate_zero_token_control(
    config: RecoveryConfig,
    structure: RecoveryStructureSummary,
    current_model_identity: dict[str, object],
    first_holdout_path: Path,
) -> dict[str, object]:
    path = Path(config.zero_token_control.path)
    if sha256_file(path) != config.zero_token_control.sha256:
        raise ValueError("zero-token control file hash differs from the pinned config")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("zero-token control must be a JSON object")
    source_pairings = document.get("transform", {}).get("layer_pairings")
    expected_pairings = [
        [[left, right] for left, right in layer] for layer in structure.layer_pairings
    ]
    source_weights = (
        document.get("provenance", {}).get("model", {}).get("weight_files", [])
    )
    current_weights = current_model_identity.get("weight_files", [])
    assertions = {
        "content_identity_matches": document.get("content_identity_sha256")
        == config.zero_token_control.content_identity_sha256,
        "raw_artifact_sha256_matches": sha256_file(path)
        == config.zero_token_control.sha256,
        "model_weight_identity_matches": source_weights == current_weights,
        "first_holdout_identity_matches": document.get("inputs", {}).get(
            "corpus_sha256"
        )
        == sha256_file(first_holdout_path),
        "dtype_matches": document.get("inputs", {}).get("dtype") == config.dtype,
        "layer_pairings_match": source_pairings == expected_pairings,
        "all_28_layers_are_transformed": document.get("transform", {}).get(
            "transformed_layer_indices"
        )
        == list(range(28)),
        "four_pairs_per_layer_are_transformed": all(
            len(value) == 4 for value in source_pairings or []
        ),
        "adapter_delta_is_exactly_zero": structure.adapter_b_zero_at_initialization,
    }
    if not all(assertions.values()):
        failed = [name for name, passed in assertions.items() if not passed]
        raise ValueError(
            "zero-token control is not exactly equivalent to recovery initialization: "
            + ", ".join(failed)
        )
    return {
        "path": str(path),
        "sha256": config.zero_token_control.sha256,
        "content_identity_sha256": config.zero_token_control.content_identity_sha256,
        "equivalence_assertions": assertions,
        "exactly_equivalent_to_recovery_initialization": True,
        "metrics": document["metrics"],
        "quality_report": document["quality_report"],
    }


def _validate_structure(structure: RecoveryStructureSummary) -> None:
    if structure.layer_count != 28:
        raise ValueError("recovery screen requires exactly 28 Qwen layers")
    if structure.original_kv_heads != 8 or structure.unique_kv_heads != 4:
        raise ValueError("recovery screen requires exact 8-to-4 KV sharing")
    if not structure.exact_pair_sharing_at_initialization:
        raise RuntimeError("KV heads are not exactly shared after initialization")
    if structure.trainable_parameter_count != 1_376_256:
        raise ValueError(
            f"unexpected trainable parameter count: {structure.trainable_parameter_count}"
        )


def _gradient_norm(model: torch.nn.Module) -> float:
    squared = 0.0
    for parameter in model.parameters():
        if parameter.grad is not None:
            gradient = parameter.grad.detach().to(torch.float32)
            squared += float(torch.sum(gradient * gradient).item())
    return squared**0.5


def _adapter_state_summary(
    state: dict[str, torch.Tensor],
) -> dict[str, object]:
    total_squared = 0.0
    b_squared = 0.0
    b_nonzero = 0
    for name, value in state.items():
        squared = float(torch.sum(value * value).item())
        total_squared += squared
        if name.endswith("adapter_b"):
            b_squared += squared
            b_nonzero += int(torch.count_nonzero(value).item())
    return {
        "tensor_count": len(state),
        "parameter_count": sum(value.numel() for value in state.values()),
        "l2_norm": total_squared**0.5,
        "adapter_b_l2_norm": b_squared**0.5,
        "adapter_b_nonzero_values": b_nonzero,
    }


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _enforce_memory_bound(config: RecoveryConfig, stage: str) -> None:
    peak = _peak_rss_bytes()
    if peak > config.maximum_rss_bytes:
        raise MemoryError(
            f"peak RSS {peak} exceeded limit {config.maximum_rss_bytes} after {stage}"
        )


def _resource_report(
    config: RecoveryConfig,
    started: float,
    training_started: float,
) -> dict[str, object]:
    return {
        "maximum_allowed_rss_bytes": config.maximum_rss_bytes,
        "peak_rss_bytes": _peak_rss_bytes(),
        "within_memory_bound": _peak_rss_bytes() <= config.maximum_rss_bytes,
        "total_wall_seconds": time.perf_counter() - started,
        "training_and_evaluation_wall_seconds": time.perf_counter() - training_started,
    }


def _confirmation_skip_reason(
    reached_full_budget: bool,
    final_first: dict[str, object],
) -> str:
    if not reached_full_budget:
        return (
            "This timing run did not reach the configured 8,192-token recovery budget."
        )
    return "The 8,192-token candidate failed at least one 512-target promotion gate."


def _decision(
    report: dict[str, object],
    config: RecoveryConfig,
    reached_full_budget: bool,
) -> dict[str, object]:
    checkpoints = report["evaluation"]["first_holdout_checkpoints"]
    nll_values = [value["metrics"]["candidate_mean_nll"] for value in checkpoints]
    monotonic = all(right <= left for left, right in zip(nll_values, nll_values[1:]))
    final_first_passed = checkpoints[-1]["quality_report"]["passed"] is True
    confirmation = report["evaluation"]["confirmation_holdout"]
    confirmation_passed = (
        isinstance(confirmation, dict)
        and confirmation.get("quality_report", {}).get("passed") is True
    )
    positive = (
        reached_full_budget and monotonic and final_first_passed and confirmation_passed
    )
    report["claim_flags"]["small_budget_recoverability_signal"] = positive
    if not reached_full_budget:
        outcome = "incomplete_timing_screen"
    elif positive:
        outcome = "positive_small_budget_recoverability_signal"
    else:
        outcome = "negative_at_tested_8192_token_budget"
    return {
        "outcome": outcome,
        "heldout_candidate_nll_nonincreasing_across_checkpoints": monotonic,
        "final_512_target_quality_gate_passed": final_first_passed,
        "confirmation_4096_target_quality_gate_passed": confirmation_passed,
        "interpretation_if_negative": "This exact hard-shared K/V plus rank-8 Q/O adapter recipe is not promising at the tested budget; it does not disprove recovery with different initialization, trainable K/V parameters, data, or literature-scale budgets.",
        "configured_full_training_target_tokens": config.data.training_target_tokens,
    }


def _write_report(path: Path, report: dict[str, object]) -> None:
    stable = {key: report[key] for key in report if key != "content_identity_sha256"}
    report["content_identity_sha256"] = hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
