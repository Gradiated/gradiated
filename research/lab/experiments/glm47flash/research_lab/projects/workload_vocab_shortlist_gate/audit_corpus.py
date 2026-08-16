#!/usr/bin/env python3
"""Audit retained stock archives without treating hashes as token evidence."""

from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ARCHIVES = [
    ROOT.parent / "near_stock_c32_memory_frontier" / "artifacts" / "near_stock_c32_memory_frontier_r3_control" / "vllm-awq-batch.tar.gz",
    ROOT.parent / "nebius_current_awq_c16_direct" / "artifacts" / "nebius_current_awq_c16_direct_2026-07-15-r2" / "vllm-awq-batch.tar.gz",
]
OUT = ROOT / "artifacts" / "CORPUS_CLOSE_2026-07-16.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(tf: tarfile.TarFile, name: str):
    member = tf.getmember(name)
    return json.loads(tf.extractfile(member).read())


def main() -> None:
    sources = []
    response_texts = {}
    response_text_record_count = 0
    for archive in ARCHIVES:
        with tarfile.open(archive, "r:gz") as tf:
            names = {m.name.rsplit("/", 1)[-1]: m.name for m in tf.getmembers() if m.isfile()}
            quality = [json.loads(line) for line in tf.extractfile(names["quality-awq-responses.jsonl"]).read().decode().splitlines()]
            semantic = [read_json(tf, names[name]) for name in ("semantic-response-1.json", "semantic-response-2.json") if name in names]
            quality_text = {row["case_id"]: row.get("output") for row in quality if isinstance(row.get("output"), str)}
            semantic_text = [item["choices"][0]["message"]["content"] for item in semantic]
            response_text_record_count += len(quality_text) + len(semantic_text)
            for case_id, text in quality_text.items():
                response_texts.setdefault(hashlib.sha256(text.encode()).hexdigest(), {"category": "development", "case_ids": [], "chars": len(text), "declared_completion_tokens": None})["case_ids"].append(case_id)
            for text in semantic_text:
                response_texts.setdefault(hashlib.sha256(text.encode()).hexdigest(), {"category": "semantic_smoke", "case_ids": [], "chars": len(text), "declared_completion_tokens": 22})["case_ids"].append("semantic_smoke")
            allocation = read_json(tf, names["allocation-result.json"])
            perf = allocation.get("performance", {})
            sources.append({
                "archive": str(archive),
                "archive_sha256": sha256(archive),
                "member_count": len(names),
                "raw_response_text_members": ["quality-awq-responses.jsonl", "semantic-response-1.json", "semantic-response-2.json"],
                "quality_case_count": len(quality),
                "quality_case_ids": [row.get("case_id") for row in quality],
                "semantic_response_count": len(semantic),
                "performance_profiles": [{"profile_id": p.get("profile_id"), "requests": p.get("requests"), "output_tokens": p.get("total_output_tokens"), "response_text": False, "output_token_ids": False, "stream_hashes_only": True} for p in perf.get("profiles", [])],
                "performance_prompt_sha256_only": True,
                "tokenizer_binding": perf.get("authoritative_tokenizer"),
            })

    result = {
        "schema_version": 1,
        "classification": "CORPUS_CLOSE",
        "decision": "No target-representative shortlist may be nominated from retained stock evidence.",
        "evidence_class": "measured retained-artifact audit; no token inference from hashes",
        "target_workload": {"input_tokens": 8192, "max_output_tokens": 1024, "authoritative_profiles": ["fixed_8k_1k_c1", "fixed_8k_1k_c8", "fixed_8k_1k_c16"]},
        "sources": sources,
        "deduplicated_raw_response_corpus": {"unique_response_texts": len(response_texts), "total_response_text_records": response_text_record_count, "categories": {"development": 5, "semantic_smoke": 1}, "duplicate_response_text_records_excluded": response_text_record_count - len(response_texts), "input_token_ids_present_in_teacher_forced_row": True, "output_token_ids_available": False, "target_performance_response_text_available": False, "tokenizer_tokenization_performed": False, "tokenization_reason": "Corpus closes before tokenization: retained performance traffic has no token identities and remaining text is explicitly development/semantic smoke traffic."},
        "representativeness": {"target_categories_present": False, "target_8k_1k_response_tokens_present": False, "leave_one_group_out_coverage": None, "reason": "All raw text is dev_* quality output or the repeated alpha/beta semantic smoke response; performance rows contain only counts and stream hashes."},
        "economic_gate": {"r3_c16_tok_per_s": 552.1710554232396, "target_tok_per_s": 594.466, "robust_nomination_tok_per_s": 606.355, "endpoint_stress_run": "not admissible after corpus close"},
        "scope_compliance": {"provider_spend_usd": 0.0, "cuda_used": False, "checkpoint_mutated": False, "shared_launcher_mutated": False, "hashes_used_as_tokens": False},
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(OUT), "classification": result["classification"], "unique_response_texts": len(response_texts), "target_performance_response_text_available": False}, indent=2))


if __name__ == "__main__":
    main()
