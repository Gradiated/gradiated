#!/usr/bin/env python3
"""CPU-only reconciliation of overflow economics with the measured endpoint rate."""
import hashlib, json, math
from pathlib import Path

P = Path(__file__).resolve().parent
B = P / "DIRECTOR_ENDPOINT_OVERFLOW_RECONCILIATION_20260725.json"
CAPS = (0.0, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, float("inf"))
PERIODS, PLAN, ACTUAL = 64, 2.8, 2.95

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def q(xs, p):
    xs=sorted(xs); x=(len(xs)-1)*p; lo,hi=math.floor(x),math.ceil(x)
    return xs[lo] if lo==hi else xs[lo]*(hi-x)+xs[hi]*(x-lo)
def resolve(row):
    x=Path(row["path"]); return x if x.is_absolute() else (P/x).resolve()
def run(rows, service, cap=float("inf"), periods=1):
    period=rows[-1]["scheduled_s"]; free=0.; waits=[]; spill=[]
    for cycle in range(periods):
      for row in rows:
        arrival=row["scheduled_s"]+cycle*period; wait=max(0.,free-arrival)
        if wait>cap: spill.append((cycle,row["usage"]["total_tokens"])); continue
        free=max(free,arrival)+service; waits.append(wait)
    return {"periods":periods,"wait_cap_seconds":None if math.isinf(cap) else cap,
      "local_requests":len(waits),"spill_requests":len(spill),"spill_tokens":sum(x[1] for x in spill),
      "last_period_spill_requests":sum(c==periods-1 for c,_ in spill),
      "last_period_spill_tokens":sum(t for c,t in spill if c==periods-1),
      "drain_extension_seconds":max(0.,free-periods*period),
      "wait_seconds":{"p50":q(waits,.5),"p95":q(waits,.95),"p99":q(waits,.99),"max":max(waits)}}
def cost(hourly, period, total, spill, retail): return (hourly*period/3600+spill*retail/1e6)*1e6/total
def pareto(points,tier):
    out=[]
    for x in points:
      w=x["periodic"]["wait_seconds"]["max"]; c=x["planning_cost_usd_per_million"][tier]
      if not any(y is not x and y["periodic"]["wait_seconds"]["max"]<=w and y["planning_cost_usd_per_million"][tier]<=c and (y["periodic"]["wait_seconds"]["max"]<w or y["planning_cost_usd_per_million"][tier]<c) for y in points):
       out.append({"wait_cap_seconds":x["wait_cap_seconds"],"max_wait_seconds":w,"planning_cost_usd_per_million":c,"steady_spill_requests":x["periodic"]["last_period_spill_requests"]})
    return out
def scenario(name, rows, service, tiers):
    period=rows[-1]["scheduled_s"]; total=sum(r["usage"]["total_tokens"] for r in rows); points=[]
    for cap in CAPS:
      finite=run(rows,service,cap); periodic=run(rows,service,cap,PERIODS); spill=periodic["last_period_spill_tokens"]
      points.append({"wait_cap_seconds":None if math.isinf(cap) else cap,"finite":finite,"periodic":periodic,
        "planning_cost_usd_per_million":{k:cost(PLAN,period,total,spill,v) for k,v in tiers.items()},
        "actual_cost_usd_per_million":{k:cost(ACTUAL,period,total,spill,v) for k,v in tiers.items()}})
    return {"evidence_label":"measured_endpoint_prefix" if name=="observed_791_prefix" else "analytical_extrapolation_beyond_measured_endpoint",
      "requests":len(rows),"total_tokens":total,"period_seconds":period,"finite_h100_only":run(rows,service),"periodic_h100_only":run(rows,service,periods=PERIODS),
      "points":points,"non_dominated_planning_points_by_tier":{k:pareto(points,k) for k in tiers},
      "retail_only_usd_per_million":tiers,
      "continuous_90pct_h100_usd_per_million":PLAN*service/(.9*3600*(total/len(rows)))*1e6,
      "two_h100_finite_usd_per_million":2*PLAN*run(rows,service,periods=1)["drain_extension_seconds"]*0 # overwritten below
    }
def main():
 b=json.loads(B.read_text()); assert digest(B)=="c4750511b0cc80afbfa1c08c2bbb9b6f9a58146a1582544fc7b86f81b36a1d13"
 verified={}
 for k,row in b["bound_inputs"].items():
  if "path" not in row: continue
  p=resolve(row); assert digest(p)==row["sha256"], k; verified[k]={"path":str(p),"sha256":row["sha256"]}
 rows=[json.loads(x) for x in resolve(b["bound_inputs"]["request_trace"]).read_text().splitlines() if x]
 assert len(rows)==1036 and [r["i"] for r in rows]==list(range(1036))
 prior=json.loads(resolve(b["bound_inputs"]["prior_result"]).read_text()); old=run(rows,.7073339939181298,periods=1)
 assert abs(old["drain_extension_seconds"]-prior["one_replica_finite_trace"]["queue"]["drain_extension_seconds"])<1e-9
 endpoint=json.loads(resolve(b["bound_inputs"]["measured_endpoint"]).read_text()); service=b["bound_inputs"]["measured_endpoint"]["service_seconds_per_request"]
 assert endpoint["requests"]==791 and endpoint["decision"]["normalized_semantics_exact"] is False
 tiers={k.removesuffix("_usd_per_million_total_tokens"):v for k,v in b["bound_inputs"]["market_tiers"].items()}
 prefix,full=rows[:791],rows
 observed=scenario("observed_791_prefix",prefix,service,tiers); extrap=scenario("full_trace_extrapolation",full,service,tiers)
 for x,rs in ((observed,prefix),(extrap,full)):
  period=rs[-1]["scheduled_s"]; total=sum(r["usage"]["total_tokens"] for r in rs); two=run(rs,service,periods=1) # two uniform workers calculated below
  # At two replicas no queue under this trace; bill their finite drain span from an explicit two-worker replay.
  free=[0.,0.]
  for r in rs:
   i=min(range(2),key=lambda z:free[z]); free[i]=max(free[i],r["scheduled_s"])+service
  x["two_h100_finite_usd_per_million"]=2*PLAN*max(free)/3600/total*1e6
 result={"schema_version":1,"classification":"analytical_endpoint_overflow_reconciliation_semantic_blocked","binding_sha256":digest(B),"verified_inputs":verified,
  "measured_endpoint":{"service_seconds_per_request":service,"requests":791,"normalized_semantics_exact":False,"deployment_eligibility":"ineligible_pending_semantic_repair"},
  "prior_control":{"reproduced":True,"old_service_seconds_per_request":.7073339939181298,"one_h100_finite_drain_extension_seconds":old["drain_extension_seconds"]},
  "retail_tiers_usd_per_million":tiers,"observed_791_prefix":observed,"full_1036_extrapolation":extrap,
  "actual_spend_usd":0.,"provider_mutation":"none","scope_boundary":"No GPU, provider, SSH, or endpoint replay."}
 (P/"ENDPOINT_OVERFLOW_RESULT_20260725.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
 print(json.dumps({"prefix_max_wait":observed["finite_h100_only"]["wait_seconds"]["max"],"full_max_wait":extrap["finite_h100_only"]["wait_seconds"]["max"]}))
if __name__=="__main__": main()
