#!/usr/bin/env bash
set -Eeuo pipefail
P=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_dynamic_fp8_c64_saturation; L=/root/workspace/research/sol/experiments/gemma4_31b/research_lab; B=b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j; O=$P/artifacts/${C96_RUN_ID:?}; D=${C96_DEADLINE_UTC:?}; PRE=$P/PRECLAIM_C96_TERMINAL.json; C64=$P/artifacts/b200-fp8-c64-20260728t1546z-repair2/FINAL_TERMINAL.json
mkdir -p "$O"; phase(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$O/OWNER_PROGRESS.log"; }; hb(){ PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$L" heartbeat --project gemma4_b200_dynamic_fp8_c64_saturation --bench "$B" >>"$O/heartbeat.log" 2>&1; }; while true;do hb;sleep 45;done & H=$!; trap 'kill "$H" 2>/dev/null||true' EXIT
repair(){ phase "repair:$1"; printf '%s\n' "$2">"$O/REPAIR_DIAGNOSTIC.txt"; /root/workspace/research/factory/tools/repair-handshake ready --root "$O" --repair-id "c96-$(date -u +%Y%m%dT%H%M%SZ)" --failure-kind "$1" --diagnostic "$O/REPAIR_DIAGNOSTIC.txt" --retry-scope endpoint_consumer --deadline "$D" >>"$O/repair.log" 2>&1||true; while [ "$(date -u +%s)" -lt "$(date -u -d "$D" +%s)" ];do find "$O/.repair-handshakes" -name REPAIR_REQUEST.json -type f -print -quit|grep -q .&&exit 75;sleep 30;done;exit 75; }
python3 - "$PRE" "$0" "$P/b200_fp8_c96_driver.py" "$C64" <<'PY' || repair binding local_binding_failed
import hashlib,json,pathlib,sys
pre,owner,driver,c64=map(pathlib.Path,sys.argv[1:]); x=json.loads(pre.read_text()); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); assert x['owner_sha256']==sha(owner) and x['driver_sha256']==sha(driver) and x['c64_terminal_sha256']==sha(c64)
PY
row=$(PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$L" show --bench "$B")||repair inventory no_bench; eval "$(ROW="$row" python3 - <<'PY'
import json,os,shlex
r=json.loads(os.environ['ROW'])['resource'];[print(f'{k}={shlex.quote(v)}')for k,v in {'HOST':r['public_ipv4'],'USER':r['ssh_user'],'KEY':r['identity_file'],'KNOWN':r['known_hosts_namespace']}.items()]
PY
)"; S=(ssh -n -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$USER@$HOST"); R=/home/$USER/$C96_RUN_ID
phase executor_fence; "${S[@]}" "ps -eo pid=,args=" >"$O/remote-processes.txt" 2>"$O/remote-processes.stderr"||repair census remote_census_failed
python3 - "$O/remote-processes.txt" <<'PY' >"$O/remote-census.json" || repair census competing_executor
import pathlib,re,sys
x=pathlib.Path(sys.argv[1]).read_text(); raise SystemExit(bool(re.search(r'run_endpoint_pair\.sh|dynamic_fp8_endpoint_driver\.py|b200_fp8_c64_driver\.py|b200_fp8_c96_driver\.py|/v1/completions',x)))
PY
phase health; "${S[@]}" "sudo -n docker ps --format '{{.Names}} {{.Status}}'|awk '\$1==\"gemma4-b200-dynamic_fp8_candidate\"&&\$2==\"Up\"{f=1}END{exit !f}'&&curl -fsS --max-time 10 http://127.0.0.1:30001/health" >"$O/health.out" 2>"$O/health.err"||repair server resident_server_unhealthy; "${S[@]}" "sudo -n docker logs --tail 400 gemma4-b200-dynamic_fp8_candidate" >"$O/server.log" 2>"$O/server.err"||repair fp8 logs_unavailable; grep -F CutlassFP8ScaledMMLinearKernel "$O/server.log">/dev/null||repair fp8 kernel_evidence_missing
phase stage; "${S[@]}" "mkdir -p '$R'"||repair stage remote_root; scp -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$P/b200_fp8_c96_driver.py" "$PRE" "$C64" "$USER@$HOST:$R/" >>"$O/stage.out" 2>>"$O/stage.err"||repair stage copy_failed
phase endpoint_execution; "${S[@]}" "cd '$R'&&python3 b200_fp8_c96_driver.py --host 127.0.0.1 --port 30001 --output '$R/artifacts' --binding PRECLAIM_C96_TERMINAL.json --c64 FINAL_TERMINAL.json" >"$O/worker.out" 2>"$O/worker.err"||repair consumer c96_consumer_failed
phase retrieve; mkdir -p "$O/remote-artifacts"; scp -r -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$USER@$HOST:$R/artifacts/." "$O/remote-artifacts/" >>"$O/retrieve.out" 2>>"$O/retrieve.err"||repair retrieval terminal_unretrieved
python3 - "$O" "$PRE" <<'PY' || repair terminal invalid_terminal
import hashlib,json,os,pathlib,sys
o,p=map(pathlib.Path,sys.argv[1:]); t=json.loads((o/'remote-artifacts/TERMINAL.json').read_text()); s=json.loads((o/'remote-artifacts/SCIENCE_STARTED.json').read_text()); b=json.loads(p.read_text());assert t['classification']=='endpoint_measurement' and t['complete_requests']==96 and s['arm']==t['arm']; v={'schema_version':1,'classification':'c96_endpoint_measurement','science_consumed':True,'candidate':t,'preclaim_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'c96_vs_c64_fraction':t['service_seconds_per_request']/b['c64_service_seconds_per_request']-1,'c96_vs_target_fraction':t['service_seconds_per_request']/b['campaign_target_seconds_per_request']-1};q=o/'FINAL_TERMINAL.json.part';q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n');os.replace(q,o/'FINAL_TERMINAL.json')
PY
phase terminal; PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$L" release --project gemma4_b200_dynamic_fp8_c64_saturation --bench "$B" --condition maintenance >>"$O/release.log" 2>&1
