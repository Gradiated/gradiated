#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_cross_operator_executor
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
bench=b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j
out=$project/artifacts/b200-cross-operator-component-20260728t2016z
binding=$project/DIRECTOR_B200_CROSS_OPERATOR_EXECUTION_20260728T2016Z.json
preclaim=$project/PRECLAIM_B200_CROSS_OPERATOR_TERMINAL.json
runner=$project/b200_cross_operator_consumer.py
release_by=2026-07-28T20:58:00Z
image=docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79
mkdir -p "$out"
phase(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$out/OWNER_PROGRESS.log"; }
heartbeat(){ while sleep 30; do PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_b200_fp8_cross_operator_executor --bench "$bench" >>"$out/heartbeat.log" 2>&1 || true; done; }
heartbeat & hb=$!
trap 'kill "$hb" 2>/dev/null || true' EXIT
repair(){
  local stage=$1
  local code=$2
  local diagnostic="$out/REPAIR_${stage}.json"
  local repair_id="cross-operator-${stage}-$(date -u +%Y%m%dT%H%M%SZ)"
  python3 - "$diagnostic" "$stage" "$code" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); x={'schema_version':1,'classification':'invalid_uninterpretable_integration_attempt','stage':sys.argv[2],'exit_code':int(sys.argv[3]),'science_consumed':False}
t=p.with_suffix('.part'); t.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); t.replace(p)
PY
  /root/workspace/research/factory/tools/repair-handshake ready --root "$out" --repair-id "$repair_id" --deadline "$release_by" --failure-kind integration --diagnostic "$diagnostic" --retry-scope "$stage" >>"$out/repair.log" 2>&1 || true
  phase "repair_ready:$stage"
  /root/workspace/research/factory/tools/repair-handshake wait --root "$out" --repair-id "$repair_id" --deadline "$release_by" >>"$out/repair.log" 2>&1 || true
  exit 75
}
phase binding_validation
python3 - "$binding" "$preclaim" "$runner" "$0" <<'PY' || repair binding_validation $?
import hashlib,json,pathlib,sys
b,pre,runner,owner=map(pathlib.Path,sys.argv[1:]); x=json.loads(pre.read_text()); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert x['binding_sha256']==sha(b)
assert x['runner_sha256']==sha(runner)
assert x['owner_sha256']==sha(owner)
assert x['finite_negative_timing_amendment'] is True
PY
row=$(PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" show --bench "$bench") || repair pool_show $?
eval "$(ROW="$row" python3 - <<'PY'
import json,os,shlex
r=json.loads(os.environ['ROW']); assert r['claim']['project']=='gemma4_b200_fp8_cross_operator_executor'
for k,v in {'host':r['resource']['public_ipv4'],'user':r['resource']['ssh_user'],'key':r['resource']['identity_file'],'known':r['resource']['known_hosts_namespace']}.items(): print(f'{k}={shlex.quote(v)}')
PY
)" || repair claim_identity $?
test -f "$key" || repair identity 1
remote=/home/$user/b200-cross-operator-20260728t2016z
remote_out=$remote/output-5
ssh_cmd=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host")
scp_cmd=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known")
phase packet_stage
"${ssh_cmd[@]}" "mkdir -p '$remote'; test ! -e '$remote_out'" >"$out/stage.stdout" 2>"$out/stage.stderr" || repair remote_stage $?
"${scp_cmd[@]}" "$runner" "$preclaim" "$user@$host:$remote/" >>"$out/stage.stdout" 2>>"$out/stage.stderr" || repair packet_copy $?
phase component_execution
"${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --ipc=host --entrypoint python3 -v '$remote:/work' '$image' /work/b200_cross_operator_consumer.py --output /work/output-5 --warmup 8 --repeats 40 && sudo -n chown -R \$(id -u):\$(id -g) '$remote_out'" >"$out/worker.stdout" 2>"$out/worker.stderr" || repair component_execution $?
phase retrieve
mkdir -p "$out/remote-artifacts"
"${scp_cmd[@]}" -r "$user@$host:$remote_out/." "$out/remote-artifacts/" >"$out/retrieve.stdout" 2>"$out/retrieve.stderr" || repair retrieve $?
python3 - "$out/remote-artifacts/TERMINAL.json" "$preclaim" "$out" <<'PY' || repair terminal_validation $?
import hashlib,json,pathlib,sys
t,pre,out=map(pathlib.Path,sys.argv[1:]); x=json.loads(t.read_text()); p=json.loads(pre.read_text())
assert x['scope']['dispatcher_modified'] is False and x['scope']['endpoint_requests_submitted'] is False
assert x['identities']['runner_sha256']==p['runner_sha256']
assert x['classification'] in ('exact_consumer_component_measurement','exact_consumer_component_incorrect_nonfinite_or_structural')
v={'schema_version':1,'classification':'component_positive_director_promotion' if x.get('decision',{}).get('reopen_integration') else 'component_decision_bearing_negative','science_consumed':True,'component_terminal_sha256':hashlib.sha256(t.read_bytes()).hexdigest(),'preclaim_sha256':hashlib.sha256(pre.read_bytes()).hexdigest(),'terminal':x,'actual_spend_usd':3.7782}
q=out/'FINAL_TERMINAL.json.part'; q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); q.replace(out/'FINAL_TERMINAL.json')
PY
classification=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["classification"])' "$out/FINAL_TERMINAL.json")
if [[ "$classification" == component_decision_bearing_negative ]]; then
  printf '{"state":"cross_operator_component_complete_negative","artifacts":"%s","component_terminal":"%s"}\n' "$out" "$out/FINAL_TERMINAL.json" >"$out/resident_contents.json"
  PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_b200_fp8_cross_operator_executor --bench "$bench" --condition ready --contents "$out/resident_contents.json" >"$out/release.log" 2>&1
else
  phase retain_positive_for_director
fi
