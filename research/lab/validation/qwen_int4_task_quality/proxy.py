from __future__ import annotations

import hashlib
import json
from pathlib import Path

from validation.qwen_int4_quality.provenance import (
    model_identity,
    sha256_file,
    software_identity,
)
from validation.qwen_int4_quality.runner import (
    _build_corpus_report,
    _quality_report,
    evaluate_model_transform,
)
from validation.qwen_int4_quality.schema import load_corpus, load_run_config

from .quantization import FROZEN_INCLUDED_PATTERNS, quantize_frozen_selective_mask


def validate_proxy_contract(document: dict[str, object]) -> None:
    if document.get("dtype") != "bfloat16":
        raise ValueError("proxy dtype must be bfloat16")
    if document.get("evaluation_strategy") != "interleaved_models":
        raise ValueError("proxy evaluation must interleave baseline and candidate")
    quantization = document.get("quantization")
    if not isinstance(quantization, dict):
        raise ValueError("proxy quantization must be an object")
    if (
        quantization.get("granularity") != "groupwise"
        or quantization.get("group_size") != 8
    ):
        raise ValueError("proxy quantization must use group size 8")
    if quantization.get("code_scale") != "float32_max_abs_div_7":
        raise ValueError("proxy code scale does not match the packed kernel")
    if quantization.get("scale_storage") != "bfloat16":
        raise ValueError("proxy scale storage does not match the packed kernel")
    if (
        quantization.get("dequantization_scale")
        != "stored_bfloat16_promoted_to_float32"
    ):
        raise ValueError("proxy dequantization scale does not match the packed kernel")
    if (
        tuple(quantization.get("included_module_patterns", []))
        != FROZEN_INCLUDED_PATTERNS
    ):
        raise ValueError("proxy included module patterns do not match the frozen mask")
    if quantization.get("expected_module_count") != 84:
        raise ValueError("proxy expected module count does not match the frozen mask")
    if quantization.get("expected_parameter_count") != 234881024:
        raise ValueError(
            "proxy expected parameter count does not match the frozen mask"
        )


def run_proxy_validation(
    *,
    model_path: Path,
    config_path: Path,
    corpus_path: Path,
) -> dict[str, object]:
    config_document = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config_document, dict):
        raise ValueError("proxy config root must be an object")
    validate_proxy_contract(config_document)
    config = load_run_config(config_path)
    corpus = load_corpus(corpus_path)
    quantization_document = config_document["quantization"]
    if not isinstance(quantization_document, dict):
        raise ValueError("proxy quantization must be an object")
    expected_module_count = int(quantization_document["expected_module_count"])
    expected_parameter_count = int(quantization_document["expected_parameter_count"])
    evaluation = evaluate_model_transform(
        model_path,
        config,
        corpus,
        lambda model: quantize_frozen_selective_mask(
            model,
            expected_module_count=expected_module_count,
            expected_parameter_count=expected_parameter_count,
        ),
    )
    aggregate = evaluation.aggregate
    quantization = evaluation.transform
    packed_code_bytes = (quantization.parameter_count * 4 + 7) // 8
    scale_bytes = quantization.scale_count * 2
    report = {
        "schema_version": "inference-foundry.int4-bf16-scale-proxy.v1",
        "suite": config.suite,
        "scope": {
            "supported_claim": (
                "Measured teacher-forced quality-proxy delta for the frozen selective "
                "group-8 INT4 candidate whose float32-derived scales are rounded to "
                "BF16 before dequantization."
            ),
            "unsupported_claims": [
                "full standard benchmark accuracy",
                "packed INT4 kernel execution or equivalence",
                "unseen-task or agentic-workload generalization",
                "model safety",
                "serving throughput, latency, energy, or cost",
            ],
        },
        "inputs": {
            "model_path": str(model_path),
            "config_path": str(config_path),
            "config_sha256": sha256_file(config_path),
            "corpus_path": str(corpus_path),
            "corpus_sha256": sha256_file(corpus_path),
            "seed": config.seed,
            "dtype": config.dtype,
            "torch_threads": config.torch_threads,
            "evaluation_strategy": config.evaluation_strategy,
        },
        "provenance": {
            "model": model_identity(model_path, evaluation.weight_files),
            "tokenizer": evaluation.runtime_tokenizer_identity,
            "software": software_identity(),
            "deterministic_algorithms": True,
            "candidate_contract_frozen_before_run": True,
        },
        "quantization": quantization.to_dict(),
        "logical_selected_weight_storage": {
            "packed_code_bytes": packed_code_bytes,
            "bfloat16_scale_bytes": scale_bytes,
            "total_bytes": packed_code_bytes + scale_bytes,
            "runtime_storage_compressed": False,
        },
        "corpus": _build_corpus_report(
            corpus,
            actual_target_tokens=aggregate.target_tokens,
            corpus_sha256=sha256_file(corpus_path),
        ),
        "metrics": aggregate.to_dict(),
        "quality_report": _quality_report(config, aggregate),
        "claims": {
            "measured_teacher_forced_proxy": True,
            "runtime_representation_bridge_materialized": True,
            "full_standard_benchmark": False,
            "packed_kernel_executed": False,
            "packed_kernel_equivalence": False,
            "safety": False,
            "serving_performance": False,
            "energy": False,
            "cost_per_token": False,
        },
    }
    report["content_identity_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return report
