#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/gemma4_h200_dflash_endpoint
lab=/root/workspace/research/lab/experiments/gemma4_31b/research_lab
out="$1"
key=/root/.config/nebius/glm-campaign/ssh_ed25519
known=/root/.config/nebius/glm-campaign/known_hosts
remote=/home/glmrunner/gemma4-dflash/work/dflash-cycle-oracle
mkdir -p "$out"; exec > >(tee -a "$out/owner.log") 2>&1
export PYTHONPATH=/root/workspace/research/factory/src
pool=(python3 -m grad_research.gpu_pool --lab "$lab")
ssh=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" -o ConnectTimeout=20 glmrunner@89.169.109.132)
scp=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" -o ConnectTimeout=20)
heartbeat() { while sleep 45; do "${pool[@]}" heartbeat --project gemma4_h200_dflash_endpoint >> "$out/heartbeat.log" 2>&1 || true; done; }
heartbeat & hb=$!; trap 'kill "$hb" 2>/dev/null || true; wait "$hb" 2>/dev/null || true' EXIT
"${ssh[@]}" "test -f '$remote/container-id'; sudo docker ps --filter name=gemma4-dflash --format '{{.Names}}' | grep -qx gemma4-dflash; test ! -e '$remote/request/request-00.json'; test -d '$remote/request'; mv '$remote/request' '$remote/request-pre-metrics-404'"
"${scp[@]}" "$project/dflash_endpoint_runner.py" "glmrunner@89.169.109.132:$remote/dflash_endpoint_runner.repair.py"
"${ssh[@]}" "sudo docker cp '$remote/dflash_endpoint_runner.repair.py' gemma4-dflash:/work/dflash_endpoint_runner.repair.py; sudo docker exec gemma4-dflash python3 /work/dflash_endpoint_runner.repair.py --arm cycle-oracle-repair --concurrency 1 --output /work/request-repair1"
"${ssh[@]}" "test -s '$remote/oracle-cycles.jsonl'; test ! -e '$remote/oracle-cycles.observer-error'; python3 - '/home/glmrunner/gemma4-dflash/cycle-project/dflash_cycle_oracle.py' '$remote/oracle-cycles.jsonl' '$remote/DFLASH_CYCLE_ORACLE_TERMINAL.json' <<'PY'
import importlib.util,json,pathlib,sys
spec=importlib.util.spec_from_file_location('oracle',sys.argv[1]); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
rows=[]
for i,line in enumerate(pathlib.Path(sys.argv[2]).read_text().splitlines()):
 row=json.loads(line); row['cycle_index']=i; rows.append({'cycle':row,'result':m.evaluate_cycle(row)})
bad=next((x for x in rows if not x['result']['pass']),None)
pathlib.Path(sys.argv[3]).write_text(json.dumps({'schema_version':1,'classification':'cycle_oracle','pass':bad is None,'cycles':rows,'first_divergent_field':None if bad is None else bad['result']['issues'][0]},indent=2,sort_keys=True)+'\\n')
raise SystemExit(0 if bad is None else 1)
PY"
rc=$?
set +e
mkdir -p "$out/retrieved"
"${scp[@]}" "glmrunner@89.169.109.132:$remote/DFLASH_CYCLE_ORACLE_TERMINAL.json" "$out/retrieved/"
"${scp[@]}" "glmrunner@89.169.109.132:$remote/REMOTE_TERMINAL.json" "$out/retrieved/"
set -e
cp "$out/retrieved/DFLASH_CYCLE_ORACLE_TERMINAL.json" "$project/DFLASH_CYCLE_ORACLE_TERMINAL.json"
if python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1]))["pass"] is False else 1)' "$project/DFLASH_CYCLE_ORACLE_TERMINAL.json"; then
  "${ssh[@]}" "sudo docker rm -f gemma4-dflash >/dev/null"
  "${pool[@]}" release --project gemma4_h200_dflash_endpoint --condition ready --contents "$out/retrieved/REMOTE_TERMINAL.json"
fi
exit "$rc"
