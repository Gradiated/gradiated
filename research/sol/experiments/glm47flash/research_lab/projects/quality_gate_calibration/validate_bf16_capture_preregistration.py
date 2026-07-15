#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
 p=json.loads((ROOT/"BF16_DEVELOPMENT_CAPTURE_PREREGISTRATION.json").read_text())
 checks={"not_admitted":p["authorization"]=={"provider_mutation":False,"model_launch":False,"holdout_access":False,"director_admission_required":True},"three_captures":p["captures"]["count"]==3,"no_spend":p["economics"]["authorized_spend_usd"]==0.0,"feasible_conditional_cap":p["economics"]["conditional_spend_cap_usd"]>=4.27,"holdout_sealed":p["suite"]["holdout_status"]=="not_generated_not_inspected","controller_not_started":p["controller"]["not_started"] is True,"cleanup_bound":p["cleanup"]["watchdog_seconds"]>p["captures"]["absolute_session_timeout_seconds"]}
 out={"schema_version":1,"classification":"zero_cost_preregistration_validation","checks":checks,"pass":all(checks.values())}
 (ROOT/"BF16_DEVELOPMENT_CAPTURE_PREREGISTRATION_AUDIT.json").write_bytes(json.dumps(out,sort_keys=True,indent=2).encode()+b"\n")
 print(json.dumps(out,sort_keys=True));
 if not out["pass"]: raise SystemExit("validation failed")
if __name__=="__main__": main()
