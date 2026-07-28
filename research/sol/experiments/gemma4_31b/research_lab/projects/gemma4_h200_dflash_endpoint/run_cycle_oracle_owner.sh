#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_dflash_endpoint
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
out="$1"
remote=/home/glmrunner/gemma4-dflash/cycle-project
key=/root/.config/nebius/glm-campaign/ssh_ed25519
known=/root/.config/nebius/glm-campaign/known_hosts
mkdir -p "$out"; exec > >(tee -a "$out/owner.log") 2>&1
export PYTHONPATH=/root/workspace/research/factory/src
pool=(python3 -m grad_research.gpu_pool --lab "$lab")
ssh=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" -o ConnectTimeout=20 glmrunner@89.169.109.132)
scp=(scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" -o ConnectTimeout=20)
heartbeat() { while sleep 45; do "${pool[@]}" heartbeat --project gemma4_h200_dflash_endpoint >> "$out/heartbeat.log" 2>&1 || true; done; }
heartbeat & hb=$!; trap 'kill "$hb" 2>/dev/null || true; wait "$hb" 2>/dev/null || true' EXIT
mkdir -p "$out/packet"
cp "$project"/{DFLASH_REQUEST_INDEXED_RELAY_REPAIR.patch,dflash_cycle_oracle.py,dflash_endpoint_runner.py,cycle_oracle_sitecustomize.py,remote_cycle_oracle.sh} "$out/packet/"
(cd "$out/packet" && sha256sum DFLASH_REQUEST_INDEXED_RELAY_REPAIR.patch dflash_cycle_oracle.py dflash_endpoint_runner.py cycle_oracle_sitecustomize.py remote_cycle_oracle.sh > BOUND.sha256)
"${ssh[@]}" "rm -rf '$remote' && mkdir -p '$remote'"
"${scp[@]}" "$out/packet"/* "glmrunner@89.169.109.132:$remote/"
set +e
"${ssh[@]}" "chmod 700 '$remote/remote_cycle_oracle.sh'; bash '$remote/remote_cycle_oracle.sh'"
rc=$?
set -e
set +e
mkdir -p "$out/retrieved"
"${scp[@]}" -r "glmrunner@89.169.109.132:/home/glmrunner/gemma4-dflash/work/dflash-cycle-oracle/"'*' "$out/retrieved/"
set -e
test -f "$out/retrieved/DFLASH_CYCLE_ORACLE_TERMINAL.json"
cp "$out/retrieved/DFLASH_CYCLE_ORACLE_TERMINAL.json" "$project/DFLASH_CYCLE_ORACLE_TERMINAL.json"
python3 - "$project/STATUS.json" "$out/retrieved/DFLASH_CYCLE_ORACLE_TERMINAL.json" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); s=json.loads(p.read_text()); t=json.loads(pathlib.Path(sys.argv[2]).read_text()); s['active_session']=None; s['oracle_result']=t; p.write_text(json.dumps(s,indent=2,sort_keys=True)+'\n')
PY
if ! python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1]))["pass"] is False else 1)' "$out/retrieved/DFLASH_CYCLE_ORACLE_TERMINAL.json"; then
  echo "oracle pass requires the still-unimplemented conditional depth consumer" >&2
  exit 73
fi
"${pool[@]}" update --project gemma4_h200_dflash_endpoint --contents "$out/retrieved/REMOTE_TERMINAL.json"
"${pool[@]}" release --project gemma4_h200_dflash_endpoint --condition ready --contents "$out/retrieved/REMOTE_TERMINAL.json"
exit "$rc"
