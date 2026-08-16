#!/usr/bin/env python3
"""Fail-closed validation for the sealed holdout and its policy."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "sealed_holdout_v2"
DEV = ROOT.parent / "quality_gate_calibration" / "executable_development_v2" / "development.jsonl"
RUNTIME = Path("/root/workspace/.agents/runtime/holdout_tokenizers")
BF16 = Path("/root/.cache/glm47flash-bf16-33faccf4/tokenizer.json")
AWQ = Path("/root/.cache/glm47flash-awq-ab31d120/tokenizer.json")
CATEGORIES = {"tool_call", "coding", "long_context_retrieval", "multi_turn_continuation", "teacher_forced_loss", "serving_correctness"}

def canonical(v): return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
def sha(v): return hashlib.sha256(v).hexdigest()
def fail(message): raise ValueError(message)

def validate(root=ROOT):
    out = root / "sealed_holdout_v2"
    policy = json.loads((root / "POST_DEVELOPMENT_QUALITY_POLICY.json").read_text())
    manifest = json.loads((out / "MANIFEST.json").read_text())
    rows = [json.loads(line) for line in (out / "holdout.jsonl").read_text().splitlines()]
    if policy["status"] != "HOLDOUT_CONTRACT_SEALED" or manifest["status"] != "HOLDOUT_CONTRACT_SEALED": fail("status")
    if manifest.get("policy_sha256") != sha((root / "POST_DEVELOPMENT_QUALITY_POLICY.json").read_bytes()): fail("policy_hash")
    if policy["future_capture_order"] != ["three_fresh_process_bf16_holdout_controls", "freeze_sequence_specific_holdout_nll_ceilings", "three_current_awq_holdout_candidates"]: fail("capture_order")
    if len(rows) != 36 or {r["category"] for r in rows} != CATEGORIES: fail("geometry")
    if any(sum(r["category"] == c for r in rows) != 6 for c in CATEGORIES): fail("category_count")
    if len({r["case_id"] for r in rows}) != 36: fail("case_ids")
    if not RUNTIME.is_dir(): fail("tokenizer_runtime")
    sys.path.insert(0, str(RUNTIME))
    import tokenizers
    from tokenizers import Tokenizer
    if tokenizers.__version__ != manifest["tokenizers"]["encoding_runtime"]["version"]: fail("tokenizer_runtime_version")
    bf16, awq = Tokenizer.from_file(str(BF16)), Tokenizer.from_file(str(AWQ))
    bf16.no_truncation(); awq.no_truncation()
    for row in rows:
        body = {k:v for k,v in row.items() if k != "content_sha256"}
        if row.get("content_sha256") != sha(canonical(body)): fail("row_integrity")
        pair = row.get("token_pair", {})
        if not pair.get("equal") or pair.get("bf16_token_ids") != pair.get("awq_token_ids") or not pair.get("truncation_disabled"): fail("token_pair")
        if pair.get("bf16_token_ids_sha256") != sha(canonical(pair["bf16_token_ids"])): fail("bf16_token_hash")
        if pair.get("awq_token_ids_sha256") != sha(canonical(pair["awq_token_ids"])): fail("awq_token_hash")
        if bf16.encode(row["teacher_forced_text"], add_special_tokens=False).ids != pair["bf16_token_ids"]: fail("bf16_reencode")
        if awq.encode(row["teacher_forced_text"], add_special_tokens=False).ids != pair["awq_token_ids"]: fail("awq_reencode")
    if manifest["holdout_sha256"] != sha((out / "holdout.jsonl").read_bytes()): fail("manifest_holdout_hash")
    dev_rows = [json.loads(line) for line in DEV.read_text().splitlines()]
    dev_texts = {json.dumps({k:v for k,v in r.items() if k != "content_sha256"}, sort_keys=True, ensure_ascii=False) for r in dev_rows}
    holdout_texts = {json.dumps({k:v for k,v in r.items() if k != "content_sha256"}, sort_keys=True, ensure_ascii=False) for r in rows}
    if dev_texts & holdout_texts: fail("development_holdout_overlap")
    if any("calibration sentinel" in r["teacher_forced_text"].lower() for r in rows): fail("development_nll_overlap")
    return {"pass": True, "cases": len(rows), "token_pairs": len(rows)}

def main():
    print(json.dumps(validate(), sort_keys=True))

if __name__ == "__main__": main()
