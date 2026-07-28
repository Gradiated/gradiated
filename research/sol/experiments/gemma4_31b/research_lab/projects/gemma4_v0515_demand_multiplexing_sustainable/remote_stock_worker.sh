#!/usr/bin/env bash
set -euo pipefail
root=${STOCK_ROOT:?}; out="$root/out"; mkdir -p "$out"
python3 - <<'PY'
import json,os,pathlib
p=pathlib.Path(os.environ['STOCK_ROOT'])/'out'/'INVOCATION_STATE.json'; p.write_text(json.dumps({'science_started':False,'phase':'stock_identity_and_launch'})+'\n')
PY
mapfile -t old < <(sudo docker ps -aq --filter 'name=gemma4-ngram')
if ((${#old[@]})); then sudo docker rm -f "${old[@]}"; fi
args=$(python3 -c "import json; print(' '.join(__import__('shlex').quote(x) for x in json.load(open('$root/stock_packet/STOCK_LAUNCH.json'))['args']))")
sudo docker rm -f gemma4-stock-multiplex >/dev/null 2>&1 || true
sudo docker run -d --name gemma4-stock-multiplex --gpus all --ipc=host --network host -v "$root:/work" docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd python3 -m sglang.launch_server $args > "$out/container_id.txt"
python3 - <<'PY'
import json,os,pathlib
p=pathlib.Path(os.environ['STOCK_ROOT'])/'out'/'INVOCATION_STATE.json'; p.write_text(json.dumps({'science_started':False,'phase':'pre_science_packet_validation'})+'\n')
PY
python3 -c "import sys; sys.path.insert(0, '$root/stock_packet'); import multiplex_runner as r; r.validate_packet(__import__('pathlib').Path('$root/stock_packet'))"
python3 - <<'PY'
import json,os,pathlib
p=pathlib.Path(os.environ['STOCK_ROOT'])/'out'/'INVOCATION_STATE.json'; p.write_text(json.dumps({'science_started':True,'phase':'stock_139_control_and_candidate'})+'\n')
PY
python3 "$root/stock_packet/stock_multiplex_runner.py" --packet-root "$root/stock_packet" --mode control --end 171 --out "$out/control"
python3 "$root/stock_packet/stock_multiplex_runner.py" --packet-root "$root/stock_packet" --mode candidate --end 171 --out "$out/candidate"
python3 - <<'PY'
import json,math,os,pathlib,time
r=pathlib.Path(os.environ['STOCK_ROOT']); out=r/'out'; c=json.loads((out/'control/FINAL_TERMINAL.json').read_text()); x=json.loads((out/'candidate/FINAL_TERMINAL.json').read_text())
def gates(v): return v.get('gates',{})
base=all(gates(c).values()) and all(gates(x).values())
noise=1.96*math.sqrt((c.get('server_seconds_sample_variance') or 0)/max(1,c.get('rows',1))+(x.get('server_seconds_sample_variance') or 0)/max(1,x.get('rows',1)))
delta=(c.get('server_seconds_mean') or 0)-(x.get('server_seconds_mean') or 0)
passed=base and delta>noise
endpoint=False
if passed:
 endpoint=True
 os.system('python3 '+str(r/'stock_packet/stock_multiplex_runner.py')+' --packet-root '+str(r/'stock_packet')+' --mode candidate --end 791 --out '+str(out/'endpoint'))
 e=json.loads((out/'endpoint/FINAL_TERMINAL.json').read_text()); token_count=0
 for line in (out/'endpoint/requests.jsonl').read_text().splitlines(): token_count+=json.loads(line)['semantic']['usage']['total_tokens']
 cost=2.46*e['elapsed_seconds']/3600*1000000/token_count
 endpoint_gate=all(e['gates'].values()) and cost<=.14
else: endpoint_gate=False; cost=None
v={'result':'measured_stock_multiplex_discriminator','candidate_sample_consumed':True,'control':c,'candidate':x,'service_time_delta_seconds':delta,'measured_noise_95_seconds':noise,'discriminator_passed':passed,'endpoint_started':endpoint,'endpoint_gate_passed':endpoint_gate,'endpoint_cost_usd_per_million_total_tokens':cost,'at_utc':time.time()}
(out/'FINAL_TERMINAL.json').write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
PY
