#!/usr/bin/env python3
"""Build the immutable post-development V2 holdout without contacting a model."""
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "sealed_holdout_v2"
DEV = ROOT.parent / "quality_gate_calibration" / "executable_development_v2"
ADJ = ROOT.parent / "bf16_v2_capture_adjudication"
BF16 = Path("/root/.cache/glm47flash-bf16-33faccf4")
AWQ = Path("/root/.cache/glm47flash-awq-ab31d120")
RUNTIME = Path("/root/workspace/.agents/runtime/holdout_tokenizers")
BF16_REVISION = "33faccf4c2ba82142214d0d4e16232a4e9ccfe10"
AWQ_REVISION = "ab31d120fbe79988fe2a0259993cf3c222aa8881"
TOKENIZERS_VERSION = "0.21.0"
CATEGORIES = ("tool_call", "coding", "long_context_retrieval", "multi_turn_continuation", "teacher_forced_loss", "serving_correctness")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def file_sha(path):
    return sha(path.read_bytes())


def content_hash(row):
    return sha(canonical({key: value for key, value in row.items() if key != "content_sha256"}))


def tokenizer_hashes(root):
    raw = json.loads((root / "tokenizer.json").read_text())
    raw["truncation"] = None
    return {
        "root": str(root),
        "tokenizer_json_sha256": file_sha(root / "tokenizer.json"),
        "tokenizer_config_json_sha256": file_sha(root / "tokenizer_config.json"),
        "chat_template_jinja_sha256": file_sha(root / "chat_template.jinja"),
        "canonical_tokenizer_sha256_truncation_disabled": sha(canonical(raw)),
        "request_policy": {"truncation": False, "add_special_tokens": False},
    }


def tokenizer_pair():
    if not RUNTIME.is_dir():
        raise RuntimeError("QUALITY_POLICY_CLOSE: pinned tokenizer runtime is absent")
    sys.path.insert(0, str(RUNTIME))
    import tokenizers
    from tokenizers import Tokenizer
    if tokenizers.__version__ != TOKENIZERS_VERSION:
        raise RuntimeError("QUALITY_POLICY_CLOSE: tokenizer runtime version drift")
    bf16 = Tokenizer.from_file(str(BF16 / "tokenizer.json"))
    awq = Tokenizer.from_file(str(AWQ / "tokenizer.json"))
    bf16.no_truncation()
    awq.no_truncation()
    return bf16, awq


def long_context(index, value):
    left = " ".join(f"H{index:02d}L{n:04x}" for n in range(4096))
    right = " ".join(f"H{index:02d}R{n:04x}" for n in range(4096))
    return f"{left}\nHOLDOUT-KEY-{index:02d}: {value}\n{right}"


def case_fields(category, index):
    if category == "tool_call":
        path = f"src/holdout_{index}_sealed.py"
        return {"prompt": f'Return exactly this JSON object and no prose: {{"arguments":{{"path":"{path}"}},"name":"read_file"}}', "scorer": {"kind": "json_exact", "expected": {"name": "read_file", "arguments": {"path": path}}}}
    if category == "coding":
        fn = f"holdout_add_{index}"
        return {"prompt": f"Return only Python, or one complete python fenced block, defining {fn}(a, b) that returns a * b + {index}.", "scorer": {"kind": "python_tests", "tests": [f"assert {fn}(2, 3) == {6 + index}", f"assert {fn}(-1, 4) == {-4 + index}"]}, "transport": {"accepted": ["bare_python", "single_python_fence"], "reject": ["prose", "multiple_blocks", "wrong_fence"]}}
    if category == "long_context_retrieval":
        value = f"holdout-aurora-{index:02d}"
        return {"prompt": f"In the supplied context, return only the value paired with HOLDOUT-KEY-{index:02d}.", "synthetic_context": long_context(index, value), "tokenizer_binding": {"model": "zai-org/GLM-4.7-Flash", "checkpoint_revision": BF16_REVISION, "minimum_raw_context_characters": 40000}, "scorer": {"kind": "normalized_exact", "expected": value}}
    if category == "multi_turn_continuation":
        params = f"delta{index}, epsilon{index}, zeta{index}"
        return {"history": [{"role": "user", "content": f"Inspect holdout_blend_{index}."}, {"role": "assistant", "content": f"holdout_blend_{index}({params}) was found."}], "prompt": "Return only the ordered parameter names from the prior assistant message.", "scorer": {"kind": "normalized_exact", "expected": params}}
    if category == "teacher_forced_loss":
        return {"prompt": "Teacher-force the supplied frozen holdout sequence through the runtime logprob endpoint.", "scorer": {"kind": "teacher_forced_logprobs_holdout", "minimum_scored_tokens": 3, "ceiling_status": "unfrozen_requires_three_holdout_bf16_captures", "ceiling_rule": "1.05_times_max_of_three_bf16_capture_mean_nll"}}
    if category == "serving_correctness":
        expected = {"case": f"holdout-{index:02d}", "status": "sealed", "truncated": False}
        return {"deterministic_repetitions": 2, "prompt": f"Return exactly this JSON object and no prose: {json.dumps(expected, separators=(',', ':'))}", "scorer": {"kind": "json_exact", "expected": expected}}
    raise ValueError(category)


def build_rows():
    bf16, awq = tokenizer_pair()
    rows = []
    serial = 0
    for category in CATEGORIES:
        for index in range(1, 7):
            serial += 1
            sentinel = f"V2 holdout sentinel {serial:02d}: aurora ledger {category} variant {index}; frozen after development."
            bf16_ids = bf16.encode(sentinel, add_special_tokens=False).ids
            awq_ids = awq.encode(sentinel, add_special_tokens=False).ids
            if bf16_ids != awq_ids:
                raise RuntimeError(f"PAIR_NLL_CLOSE: token IDs differ for holdout_{category}_{index:02d}")
            row = {"case_id": f"holdout_{category}_{index:02d}", "split": "post_development_holdout", "category": category, "critical": True, **case_fields(category, index), "teacher_forced_text": sentinel, "token_pair": {"bf16_token_ids": bf16_ids, "awq_token_ids": awq_ids, "bf16_token_ids_sha256": sha(canonical(bf16_ids)), "awq_token_ids_sha256": sha(canonical(awq_ids)), "equal": True, "truncation_disabled": True}}
            row["content_sha256"] = content_hash(row)
            rows.append(row)
    return rows


def manifest(rows):
    return {"schema_version": 1, "status": "HOLDOUT_CONTRACT_SEALED", "split": "post_development_holdout", "case_count": len(rows), "categories": list(CATEGORIES), "cases_per_category": 6, "builder_sha256": file_sha(Path(__file__)), "policy_sha256": file_sha(ROOT / "POST_DEVELOPMENT_QUALITY_POLICY.json"), "holdout_sha256": sha(OUT.joinpath("holdout.jsonl").read_bytes()), "development_fixture": {"path": str(DEV / "development.jsonl"), "sha256": file_sha(DEV / "development.jsonl"), "manifest_sha256": file_sha(DEV / "MANIFEST.json")}, "bf16_adjudication": {"path": str(ADJ / "BF16_V2_CONTROL_ADJUDICATION.json"), "sha256": file_sha(ADJ / "BF16_V2_CONTROL_ADJUDICATION.json"), "nll_ceilings_sha256": file_sha(ADJ / "BF16_V2_NLL_CEILINGS.json")}, "behavioral_reference_pair": {"classification": "frozen_behavioral_reference_eligibility_pair_not_causal_quantization_only", "bf16_revision": BF16_REVISION, "awq_revision": AWQ_REVISION, "causal_quantization_derivation": "not_retained_not_asserted"}, "tokenizers": {"encoding_runtime": {"package": "tokenizers", "version": TOKENIZERS_VERSION}, "bf16": tokenizer_hashes(BF16), "awq": tokenizer_hashes(AWQ), "observed_json_difference": "AWQ tokenizer.json embeds only a 1024-token truncation preset; canonical hashes below normalize truncation to disabled", "all_36_token_id_pairs_equal": True}, "transport_policy": {"raw_normalized_transform_runtime_logprob_and_token_sequence_hash_required": True, "normalization": "single language-matched fenced block or bare output only", "missing_or_invalid_evidence": "reject"}, "scorer_policy": {"bf16_controls": 3, "awq_candidates": 3, "bf16_category_minimum": "5/6 each category", "critical_category_maximum_regression": "1/6", "paired_bootstrap": {"seed":470236, "resamples":10000, "strata":"category", "statistic":"equal-weight mean of per-category paired score deltas", "lower_confidence_bound_quantile":0.025, "reject_below":-0.05}, "nll_ceiling_rule":"per sequence: 1.05 * max(mean BF16 NLL across three captures)"}}


def main():
    rows = build_rows()
    OUT.mkdir(exist_ok=True)
    OUT.joinpath("holdout.jsonl").write_bytes(b"".join(canonical(row) + b"\n" for row in rows))
    OUT.joinpath("MANIFEST.json").write_bytes(canonical(manifest(rows)) + b"\n")
    print(json.dumps({"status": "HOLDOUT_CONTRACT_SEALED", "cases": len(rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
