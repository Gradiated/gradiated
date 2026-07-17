#!/usr/bin/env python3
"""Build the V3 holdout offline from the immutable V2 content."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRE = ROOT.parent / "stock_awq_holdout_contract_seal"
OUT = ROOT / "sealed_holdout_v3"
DEV = ROOT.parent / "quality_gate_calibration" / "executable_development_v2"
ADJ = ROOT.parent / "bf16_v2_capture_adjudication"
BRIDGE = ROOT.parent / "bf16_vllm_quality_bridge"
RUNNER = ROOT.parents[2] / "campaign_100" / "nebius" / "vllm_v2_quality_runner.py"
BF16 = Path("/root/.cache/glm47flash-bf16-33faccf4")
AWQ = Path("/root/.cache/glm47flash-awq-ab31d120")
RUNTIME = Path("/root/workspace/.agents/runtime/holdout_tokenizers")
FILES = ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja")

def canon(v): return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
def sha(v): return hashlib.sha256(v).hexdigest()
def fsha(p): return sha(Path(p).read_bytes())
def token_hash(ids): return sha(canon({"serialization":"json_utf8_canonical_array_of_int32_token_ids_v1", "token_ids": ids}))
def row_hash(row): return sha(canon({k:v for k,v in row.items() if k != "content_sha256"}))
def binding(path):
    raw=json.loads((path/"tokenizer.json").read_text()); raw["truncation"]=None
    return {"root":str(path), "files":{x:fsha(path/x) for x in FILES}, "canonical_tokenizer_sha256_truncation_disabled":sha(canon(raw))}

def build():
    rows=[]
    for line in (PRE/"sealed_holdout_v2"/"holdout.jsonl").read_text().splitlines():
        row=json.loads(line); pair=row["token_pair"]
        if row["category"] == "serving_correctness": row["deterministic_repetitions"] = 1
        if pair["bf16_token_ids"] != pair["awq_token_ids"]: raise RuntimeError("QUALITY_POLICY_CLOSE: predecessor token IDs diverge")
        h=token_hash(pair["bf16_token_ids"])
        row["runtime_token_sequence"]={"serialization":"json_utf8_canonical_array_of_int32_token_ids_v1", "hash_algorithm":"sha256", "sha256":h, "returned_ids_must_equal":{"bf16":"token_pair.bf16_token_ids", "awq":"token_pair.awq_token_ids"}, "first_token":"unscored_for_prompt_logprobs_but_included_in_returned_id_list_and_hash"}
        row["token_sequence_sha256"]=h
        row["content_sha256"]=row_hash(row); rows.append(row)
    OUT.mkdir(exist_ok=True)
    holdout=b"".join(canon(r)+b"\n" for r in rows); (OUT/"holdout.jsonl").write_bytes(holdout)
    policy=ROOT/"POST_DEVELOPMENT_QUALITY_POLICY_V2.json"
    manifest={"schema_version":3,"status":"HOLDOUT_CONTRACT_RESEALED","predecessor":{"path":str(PRE/"sealed_holdout_v2"),"holdout_sha256":fsha(PRE/"sealed_holdout_v2"/"holdout.jsonl"),"manifest_sha256":fsha(PRE/"sealed_holdout_v2"/"MANIFEST.json"),"builder_sha256":fsha(PRE/"build_holdout.py"),"policy_sha256":fsha(PRE/"POST_DEVELOPMENT_QUALITY_POLICY.json")},"holdout_sha256":sha(holdout),"builder_sha256":fsha(__file__),"policy_sha256":fsha(policy),"scorer_sha256":fsha(ROOT/"score_resealed_holdout.py"),"validator_sha256":fsha(ROOT/"validate_resealed_holdout.py"),"executable_bridge_sha256":fsha(ROOT/"executable_capture_bridge.py"),"development":{"fixture_sha256":fsha(DEV/"development.jsonl"),"manifest_sha256":fsha(DEV/"MANIFEST.json")},"bf16_archive":{"adjudication_sha256":fsha(ADJ/"BF16_V2_CONTROL_ADJUDICATION.json"),"ceilings_sha256":fsha(ADJ/"BF16_V2_NLL_CEILINGS.json"),"bridge_sha256":fsha(BRIDGE/"BF16_VLLM_BRIDGE_2026-07-15.json")},"checkpoints":{"bf16_revision":"33faccf4c2ba82142214d0d4e16232a4e9ccfe10","awq_revision":"ab31d120fbe79988fe2a0259993cf3c222aa8881","bf16_manifest":binding(BF16),"awq_manifest":binding(AWQ)},"encoding_runtime":{"package":"tokenizers","version":"0.21.0","runtime_root":str(RUNTIME),"canonical_token_sequence":"json_utf8_canonical_array_of_int32_token_ids_v1"},"runner":{"path":str(RUNNER),"sha256":fsha(RUNNER),"model_alias":"glm-4.7-flash-bf16"},"request_contract":{"chat":{"endpoint":"/v1/chat/completions","stream":False,"temperature":0,"top_p":1,"max_tokens":256,"seed":470200,"chat_template_kwargs":{"enable_thinking":False},"timeout_seconds":300,"finish_reason_forbidden":"length"},"loss":{"endpoint":"/v1/completions","stream":False,"temperature":0,"max_tokens":1,"prompt_logprobs":1,"return_token_ids":True,"timeout_seconds":300},"normalization":"only a whole bare response or one language-matched fence; invalid, missing, or truncated evidence rejects"},"case_count":len(rows)}
    (OUT/"MANIFEST.json").write_bytes(canon(manifest)+b"\n")

if __name__ == "__main__": build()
