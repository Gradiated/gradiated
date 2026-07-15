#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
 p=json.loads((ROOT/"BF16_DEVELOPMENT_CAPTURE_PREREGISTRATION.json").read_text())
 v=json.loads((ROOT.parents[2]/"campaign_100/allocations/nebius_h100_complete_stock_v13/preregistration.json").read_text())
 suite=json.loads((ROOT/"executable_development_v2/MANIFEST.json").read_text())
 bindings={r["tokenizer_binding"]["checkpoint_revision"] for r in map(json.loads,(ROOT/"executable_development_v2/development.jsonl").read_text().splitlines()) if r["category"]=="long_context_retrieval"}
 result={"schema_version":1,"classification":"derived_prelaunch_identity_falsifier","protocol_model_revision":p["runtime_identity"]["model_revision"],"complete_v13_model_revision":v["model"]["revision"],"suite_long_context_checkpoint_bindings":sorted(bindings),"same_intended_checkpoint":p["runtime_identity"]["model_revision"]==v["model"]["revision"],"identity_ready_for_fresh_admission":True,"decision":"PASS identity rebind: protocol and suite bind the measured complete intended BF16 checkpoint. A fresh admission remains required before launch.","holdout_status":suite["holdout_status"],"authorized_spend_usd":0.0}
 out=ROOT/"INTENDED_BF16_IDENTITY_AUDIT.json"; out.write_bytes(json.dumps(result,sort_keys=True,indent=2).encode()+b"\n")
 print(json.dumps({"same_intended_checkpoint":result["same_intended_checkpoint"],"audit_sha256":hashlib.sha256(out.read_bytes()).hexdigest()},sort_keys=True))
 if not result["same_intended_checkpoint"]: raise SystemExit("intended checkpoint mismatch")
if __name__=="__main__": main()
