#!/usr/bin/env bash
set -Eeuo pipefail
stage="${STAGE:?}"; base="${ARTIFACT_BASENAME:?}"
out="/workspace/h100-direct-fp8-${stage}"; public=/workspace/public-mla-microbench; telemetry=
rm -rf "$out" "$public"; mkdir -p "$out" "$public"
finish() {
  rc=$?; set +e
  if [ -n "$telemetry" ]; then kill -TERM "$telemetry" 2>/dev/null; wait "$telemetry" 2>/dev/null; fi
  nvidia-smi -q > "$out/nvidia-smi-final.txt" 2>&1
  python3 - "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]); rows=[]
for p in sorted(r.rglob('*')):
 if p.is_file() and p.name != 'manifest.json': rows.append({'path':str(p.relative_to(r)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(r/'manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf "$public/$base.tar.gz" "$(basename "$out")"
  sha256sum "$public/$base.tar.gz" > "$public/$base.tar.gz.sha256"; exit "$rc"
}
trap finish EXIT
python3 - /input/STAGED_MANIFEST.json /input "$0" > "$out/input-verification.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
m=json.load(open(sys.argv[1])); root=Path(sys.argv[2]); wrapper=Path(sys.argv[3]); observed={}
for name,expected in m['remote_files'].items():
 p=root/name; actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None; observed[name]={'expected':expected,'actual':actual,'pass':actual==expected}
value={'schema_version':1,'packet_observed':observed,'corrected_wrapper_sha256':hashlib.sha256(wrapper.read_bytes()).hexdigest(),'pass':bool(observed) and all(x['pass'] for x in observed.values())}
print(json.dumps(value,sort_keys=True)); raise SystemExit(0 if value['pass'] else 1)
PY
nvidia-smi -q > "$out/nvidia-smi-initial.txt" 2>&1
( while [ "$(date +%s)" -lt "$CAMPAIGN_DEADLINE_EPOCH" ]; do
 TZ=UTC nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits; sleep 0.15
done ) > "$out/telemetry.csv" 2> "$out/telemetry.stderr.log" & telemetry=$!
set +e
python3 "$MICROBENCH_PATH" --stage "$stage" --output "$out/result.json" --seed 20260717 > "$out/stdout.log" 2> "$out/stderr.log"; rc=$?
if [ "$rc" -eq 0 ] && [ "$stage" = primary ]; then
 python3 - "$out/liveness.json" <<'PY'
import json,math,sys,time,torch
from vllm import _custom_ops as ops
from h100_contract import CASES
_,k,n,_=CASES[0]; torch.manual_seed(20260717); x=torch.randn((8,k),device='cuda',dtype=torch.bfloat16)/math.sqrt(k); w=torch.randn((n,k),device='cuda',dtype=torch.bfloat16)/math.sqrt(k)
xq,xs=ops.scaled_fp8_quant(x,scale=None); wq,ws=ops.scaled_fp8_quant(w,scale=None); b=wq.t(); start=time.perf_counter(); calls=0; maximum=0.0
while time.perf_counter()-start < 2.0:
 out=ops.cutlass_scaled_mm(xq,b,scale_a=xs,scale_b=ws,out_dtype=torch.bfloat16); torch.cuda.synchronize(); calls+=1; maximum=max(maximum,float(out.float().abs().max()))
elapsed=time.perf_counter()-start
value={'type':'separate_unscored_synchronized_candidate_liveness','duration_seconds':elapsed,'calls':calls,'output_max_abs':maximum,'positive_finite_cuda_work':bool(calls>0 and math.isfinite(maximum) and maximum>0),'pass':bool(1.5<=elapsed<=3.5 and calls>0 and math.isfinite(maximum) and maximum>0)}
json.dump(value,open(sys.argv[1],'w'),indent=2,sort_keys=True);open(sys.argv[1],'a').write('\n');raise SystemExit(0 if value['pass'] else 1)
PY
 rc=$?
fi
set -e
kill -TERM "$telemetry" 2>/dev/null || true; wait "$telemetry" 2>/dev/null || true; telemetry=
python3 - "$out/result.json" "$out/telemetry.csv" "$out/liveness.json" "$out/stage-terminal.json" "$stage" "$rc" <<'PY'
import csv,json,math,sys
from pathlib import Path
rp,tp,lp,op,stage,rc=sys.argv[1:]
try: result=json.load(open(rp))
except Exception as e: result={'error':{'type':type(e).__name__,'message':str(e)}}
try: live=json.load(open(lp)) if Path(lp).is_file() else {'pass':stage!='primary','missing':stage=='primary'}
except Exception as e: live={'pass':False,'error':str(e)}
rows=list(csv.reader(open(tp))) if Path(tp).is_file() else []
def num(x):
 try:return float(x.strip())
 except:return math.nan
valid=[r for r in rows if len(r)>=9]; mem=[num(r[5]) for r in valid if math.isfinite(num(r[5]))]; total=[num(r[6]) for r in valid if math.isfinite(num(r[6]))]; power=[num(r[7]) for r in valid if math.isfinite(num(r[7]))]; util=[num(r[3]) for r in valid if math.isfinite(num(r[3]))]
idle_power=power[0] if power else math.nan
telemetry={'sample_period_seconds_max':0.2,'row_count':len(valid),'gpu_names':sorted({r[2].strip() for r in valid}),'memory_used_mib':mem,'memory_total_mib':total,'power_w':power,'gpu_util_percent':util}
telemetry['liveness_pass']=bool(max(util,default=0)>0 or (max(mem,default=0)-min(mem,default=0)>=256 and max(power,default=0)-idle_power>=20))
telemetry['pass']=bool(len(valid)>=2 and telemetry['gpu_names']==['NVIDIA H100 80GB HBM3'] and min(total,default=0)>=80000 and telemetry['liveness_pass'])
terminal={'schema_version':1,'stage':stage,'pass':bool(rc=='0' and result.get('pass') is True and live.get('pass') is True and telemetry['pass']),'telemetry':telemetry,'liveness':live,'result':result}
json.dump(terminal,open(op,'w'),indent=2,sort_keys=True);open(op,'a').write('\n');raise SystemExit(0 if terminal['pass'] else 1)
PY
