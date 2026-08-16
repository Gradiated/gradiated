#!/usr/bin/env python3
import hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SUITE=ROOT/"executable_development_v2"
REFERENCE=ROOT.parents[2]/"campaign_100/allocations/nebius_h100_complete_stock_v13/preregistration.json"
OUT=ROOT/"BF16_DEVELOPMENT_CAPTURE_PREREGISTRATION.json"
def digest(b): return hashlib.sha256(b).hexdigest()
def main():
    manifest=json.loads((SUITE/"MANIFEST.json").read_text()); reference=json.loads(REFERENCE.read_text())
    if manifest["case_count"]!=36 or manifest["holdout_status"]!="not_generated_not_inspected": raise SystemExit("invalid suite")
    identities=reference["identities"]
    result={
      "schema_version":1,"classification":"prepared_not_admitted_bf16_development_capture","authorization":{"provider_mutation":False,"model_launch":False,"holdout_access":False,"director_admission_required":True},
      "question":"Three intended-BF16 captures calibrate per-sequence NLL ceilings and test the executable development-only screen.",
      "suite":{"manifest_sha256":digest((SUITE/"MANIFEST.json").read_bytes()),"fixture_sha256":manifest["fixture_sha256"],"case_count":36,"holdout_status":manifest["holdout_status"]},
      "runtime_identity":{"model_revision":reference["model"]["revision"],"container":identities["container"],"runtime_source_revision":identities["runtime_source_revision"],"tokenizer_bindings_sha256":identities["tokenizer_bindings_sha256"],"request_policy":{"enable_thinking":False,"temperature":0.0,"top_p":1.0,"max_output_tokens":256,"chat_endpoint":"/v1/chat/completions","logprob_endpoint":"/generate"},"minimum_context_length":32768},
      "captures":{"count":3,"control":"intended BF16 only","candidate":"not_admitted","sequence":"one_fresh_vm_then_three_fresh_server_process_captures_with_identity_bound_resident_checkpoint","capture_timeout_seconds":900,"absolute_session_timeout_seconds":3600,"phases":{"provision_load_verify_seconds":900,"capture_1_seconds":900,"capture_2_seconds":900,"capture_3_seconds":900},"checkpoint_reuse":"only while storage identity, checkpoint revision, tokenizer binding, and verified 48-shard marker remain identical; otherwise stop"},
      "nll_calibration":{"rule":"For each of six sequences, freeze ceiling to maximum of the three runtime-derived control mean NLL values times 1.05.","required_raw_fields":["input_token_logprobs","token_sequence_sha256","raw_response_sha256"],"failure":"missing or malformed runtime logprobs fails capture"},
      "development_gate":{"category_minimum":"at least 5 of 6 point score in every category","failure":"do not generate holdout, do not admit AWQ, preserve raw artifacts and classify failure"},
      "artifacts":{"per_capture":["raw-response-bytes","normalized-output-bytes","transform-decisions","responses.jsonl","runtime-evidence.json","identity-manifest.json","capture-result.json"],"session":["preregistration.json","content-hashes.json","retrieval-log","cleanup-verification.json"]},
      "economics":{"authorized_spend_usd":0.0,"conditional_spend_cap_usd":4.27,"measured_v13_cost_reconciliation":"BF16_CAPTURE_COST_RECONCILIATION.json","provider_admission_required_before_spend":True},
      "controller":{"required":"durable external controller with one owner, absolute watchdog, terminal result artifact, and verified cleanup","not_started":True},
      "cleanup":{"on_any_exit":["retrieve and hash artifacts","delete compute and named disks","verify instance not found","verify zero named resources"],"watchdog_seconds":3900},
      "stop_rules":["Any identity mismatch, missing raw evidence, transport mutation failure, timeout, or cleanup failure stops the lineage.","No performance workload, candidate representation, or holdout operation is in scope."]}
    OUT.write_bytes(json.dumps(result,sort_keys=True,indent=2).encode()+b"\n")
    print(json.dumps({"preregistration_sha256":digest(OUT.read_bytes()),"admitted":False,"conditional_spend_cap_usd":result["economics"]["conditional_spend_cap_usd"]},sort_keys=True))
if __name__=="__main__": main()
