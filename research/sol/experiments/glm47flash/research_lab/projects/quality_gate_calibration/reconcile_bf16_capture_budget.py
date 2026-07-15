#!/usr/bin/env python3
import hashlib,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
V13=ROOT.parents[2]/"campaign_100/allocations/nebius_h100_complete_stock_v13/summary.json"
OUT=ROOT/"BF16_CAPTURE_COST_RECONCILIATION.json"
def main():
 v=json.loads(V13.read_text()); seconds=v["allocation_seconds"]; cost=v["cost_usd_derived"]
 rate=cost/seconds; session=3600; reserve=1.10
 cap=math.ceil(rate*session*reserve*100)/100
 result={"schema_version":1,"classification":"derived_measured_phase_cost_reconciliation","source":{"summary":str(V13.relative_to(ROOT.parents[2])),"allocation_seconds":seconds,"cost_usd_derived":cost,"effective_all_in_rate_usd_per_second":rate},"phase_model":{"allocation":"one fresh VM and one verified resident checkpoint","checkpoint_reuse":"Allowed only across the three fresh server-process captures while storage identity, model revision, tokenizer binding, and 48-shard verification marker remain identical; otherwise stop.","phases":[{"name":"provision_load_verify","cap_seconds":900},{"name":"capture_1_fresh_server","cap_seconds":900},{"name":"capture_2_fresh_server","cap_seconds":900},{"name":"capture_3_fresh_server","cap_seconds":900}],"session_cap_seconds":session},"costs":{"current_conditional_cap_usd":1.5,"current_cap_seconds_at_measured_rate":1.5/rate,"measured_v13_session_cost_usd":cost,"session_cap_cost_usd":rate*session,"recommended_conditional_all_in_cap_usd":cap,"reserve_fraction":0.10},"decision":"Current $1.50 cap is infeasible: it buys less than the measured V13 session duration. Preserve three captures and 3600-second session; require at least the rounded-up $4.27 conditional all-in authority after director admission.","authorization":{"provider_mutation":False,"spend_authorized_usd":0.0}}
 OUT.write_bytes(json.dumps(result,sort_keys=True,indent=2).encode()+b"\n")
 print(json.dumps({"recommended_cap_usd":result["costs"]["recommended_conditional_all_in_cap_usd"],"session_cost_usd":result["costs"]["session_cap_cost_usd"]},sort_keys=True))
if __name__=="__main__": main()
