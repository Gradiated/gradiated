from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from validation.qwen_int4_quality.provenance import sha256_file


def build_frontier(paths: list[Path]) -> dict[str, object]:
    if not paths:
        raise ValueError("at least one KV dedup quality report is required")
    documents = [_load_report(path) for path in paths]
    _validate_common_identity(documents)
    records = sorted(
        (
            _record(path, document)
            for path, document in zip(paths, documents, strict=True)
        ),
        key=lambda record: (
            float(record["kv_cache_reduction_percent"]),
            str(record["source_content_id"]),
        ),
    )
    passing = [record for record in records if bool(record["quality_gate_passed"])]
    maximum_passing = max(
        passing,
        key=lambda record: float(record["kv_cache_reduction_percent"]),
        default=None,
    )
    maximum_passing_reduction = (
        float(maximum_passing["kv_cache_reduction_percent"])
        if maximum_passing is not None
        else 0.0
    )
    later_failures = [
        record
        for record in records
        if not bool(record["quality_gate_passed"])
        and float(record["kv_cache_reduction_percent"]) > maximum_passing_reduction
    ]
    first_failure = min(
        later_failures,
        key=lambda record: float(record["kv_cache_reduction_percent"]),
        default=None,
    )
    cache_fraction = maximum_passing_reduction / 100.0
    speedup_bound = 1.0 / (1.0 - cache_fraction) if cache_fraction < 1.0 else None
    report: dict[str, object] = {
        "schema_version": "inference-foundry.kv-dedup-quality-frontier.v1",
        "scope": {
            "supported_claim": "A deterministic 512-target teacher-forced quality frontier for one-shot, tensor-selected Qwen3-0.6B KV-head pair averaging.",
            "unsupported_claims": [
                "task accuracy or end-to-end agent success",
                "quality after uptraining or architecture-aware pretraining",
                "runtime KV-cache, checkpoint, latency, energy, or cost reduction",
                "custom attention alias-kernel correctness or speed",
                "transfer to GLM-5.2 or another model",
            ],
        },
        "identity": {
            "model_weight_files": documents[0]["provenance"]["model"]["weight_files"],
            "corpus_sha256": documents[0]["corpus"]["generated_corpus_sha256"],
            "target_tokens": documents[0]["metrics"]["target_tokens"],
            "transform_scheme": documents[0]["transform"]["scheme"],
        },
        "frontier": records,
        "summary": {
            "candidate_count": len(records),
            "passing_candidate_count": len(passing),
            "maximum_passing_cache_reduction_percent": maximum_passing_reduction,
            "maximum_passing_weight_storage_reduction_percent": (
                float(maximum_passing["weight_storage_reduction_percent"])
                if maximum_passing is not None
                else 0.0
            ),
            "maximum_passing_source_content_id": (
                maximum_passing["source_content_id"]
                if maximum_passing is not None
                else None
            ),
            "first_failing_cache_reduction_percent": (
                float(first_failure["kv_cache_reduction_percent"])
                if first_failure is not None
                else None
            ),
            "first_failing_source_content_id": (
                first_failure["source_content_id"]
                if first_failure is not None
                else None
            ),
            "ideal_cache_only_decode_speedup_upper_bound": speedup_bound,
            "speedup_bound_assumption": "All decode time is proportional to KV-cache bytes and the custom alias kernel has zero overhead.",
        },
        "claims": {
            "quality_proxy_frontier_claim_permitted": True,
            "runtime_cost_reduction_claim_permitted": False,
            "business_viability_claim_permitted": False,
            "blockers": [
                "held_out_target_count_is_512",
                "teacher_forced_proxy_only",
                "alias_kernel_not_implemented",
                "cache_traffic_share_unmeasured",
                "serving_and_cost_unmeasured",
            ],
        },
    }
    stable = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    report["content_identity_sha256"] = hashlib.sha256(stable).hexdigest()
    return report


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize a Qwen KV-head quality frontier."
    )
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    try:
        report = build_frontier(args.input)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(args.output)
    except (FileNotFoundError, OSError, ValueError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "output": str(args.output),
                "content_id": report["content_identity_sha256"],
            }
        )
    )
    return 0


def _load_report(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"quality report must be a JSON object: {path}")
    if (
        document.get("schema_version")
        != "inference-foundry.kv-dedup-quality-validation.v1"
    ):
        raise ValueError(f"unsupported KV dedup quality report: {path}")
    return document


def _validate_common_identity(documents: list[dict[str, object]]) -> None:
    first = documents[0]
    expected_model = json.dumps(
        first["provenance"]["model"]["weight_files"],
        sort_keys=True,
    )
    expected_corpus = first["corpus"]["generated_corpus_sha256"]
    expected_tokens = first["metrics"]["target_tokens"]
    expected_scheme = first["transform"]["scheme"]
    for document in documents[1:]:
        model = json.dumps(
            document["provenance"]["model"]["weight_files"],
            sort_keys=True,
        )
        if model != expected_model:
            raise ValueError("frontier reports do not share a model checkpoint")
        if document["corpus"]["generated_corpus_sha256"] != expected_corpus:
            raise ValueError("frontier reports do not share a corpus")
        if document["metrics"]["target_tokens"] != expected_tokens:
            raise ValueError("frontier reports do not share a target-token count")
        if document["transform"]["scheme"] != expected_scheme:
            raise ValueError("frontier reports do not share a transform scheme")


def _record(path: Path, document: dict[str, object]) -> dict[str, object]:
    transform = document["transform"]
    metrics = document["metrics"]
    return {
        "source_path": str(path),
        "source_sha256": sha256_file(path),
        "source_content_id": document["content_identity_sha256"],
        "transformed_layer_count": len(transform["transformed_layer_indices"]),
        "transformed_pair_count": sum(
            len(value) for value in transform["layer_pairings"]
        ),
        "kv_cache_reduction_percent": transform["kv_cache_reduction_percent"],
        "weight_storage_reduction_percent": transform[
            "estimated_weight_storage_reduction_percent"
        ],
        "nll_delta": metrics["nll_delta"],
        "perplexity_ratio": metrics["perplexity_ratio"],
        "logit_rmse": metrics["logit_rmse"],
        "logit_cosine_similarity": metrics["logit_cosine_similarity"],
        "top1_agreement": metrics["top1_agreement"],
        "quality_gate_passed": document["quality_report"]["passed"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
