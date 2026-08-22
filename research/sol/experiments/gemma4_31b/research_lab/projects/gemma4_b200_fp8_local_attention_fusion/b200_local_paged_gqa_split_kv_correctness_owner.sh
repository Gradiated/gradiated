#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_local_attention_fusion
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
bench=b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j
out=$project/artifacts/b200-local-paged-gqa-split-kv-20260728t1948z
remote=/home/glmrunner/b200-local-paged-gqa-split-kv-20260728t1948z
deadline=2026-07-28T20:17:00Z
image=docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79
preclaim=$project/PRECLAIM_B200_LOCAL_PAGED_GQA_SPLIT_KV_TERMINAL.json

mkdir -p "$out"
phase() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$out/OWNER_PROGRESS.log"; }
atomic_json() { python3 - "$1" "$2" <<'PY'
import json, os, pathlib, sys, tempfile
p=pathlib.Path(sys.argv[1]); v=json.loads(sys.argv[2]); p.parent.mkdir(parents=True,exist_ok=True)
with tempfile.NamedTemporaryFile('w',dir=p.parent,delete=False) as f:
 json.dump(v,f,indent=2,sort_keys=True); f.write('\n'); n=f.name
os.replace(n,p)
PY
}
heartbeat() { while sleep 20; do PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_b200_fp8_local_attention_fusion --bench "$bench" >>"$out/heartbeat.log" 2>&1 || true; done; }
heartbeat & hb=$!
trap 'kill "$hb" 2>/dev/null || true' EXIT

release() {
  local condition=$1
  phase "release:$condition"
  PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_b200_fp8_local_attention_fusion --bench "$bench" --condition "$condition" --contents "$out/RELEASE_CONTENTS.json" >>"$out/release.log" 2>&1
}
repair() {
  local kind=$1 message=$2 scope=$3
  phase "repair:$kind"
  printf '%s\n' "$message" >"$out/REPAIR_DIAGNOSTIC.txt"
  /root/workspace/research/factory/tools/repair-handshake ready --root "$out" --repair-id "local-paged-gqa-split-kv-$(date -u +%Y%m%dT%H%M%SZ)" --failure-kind "$kind" --diagnostic "$out/REPAIR_DIAGNOSTIC.txt" --retry-scope "$scope" --deadline "$deadline" >>"$out/repair.log" 2>&1 || true
  atomic_json "$out/OWNER_TERMINAL.json" "{\"schema_version\":1,\"terminal\":\"incomplete_repair_ready\",\"scientific_sample_consumed\":false,\"repair_scope\":\"$scope\"}"
  # A live controller retains the claim for the bounded explicit repair handoff.
  while [ "$(date -u +%s)" -lt "$(date -u -d "$deadline" +%s)" ]; do sleep 15; done
  printf '%s\n' '{"schema_version":1,"state":"repair_deadline_expired","server_state":"GPU unoccupied; source/cache/image retained","stage":"correctness_component"}' >"$out/RELEASE_CONTENTS.json"
  release maintenance
  exit 75
}

phase binding
python3 - "$preclaim" "$0" "$project/candidate/check_split_kv_correctness_b200.py" "$project/candidate/local_paged_gqa_split_kv_fused.py" <<'PY' || repair packet_binding "preclaim binding validation failed" packet
import hashlib,json,pathlib,sys
p,owner,runner,candidate=map(pathlib.Path,sys.argv[1:])
x=json.loads(p.read_text())
def sha(q): return hashlib.sha256(q.read_bytes()).hexdigest()
assert x['owner_sha256']==sha(owner.resolve())
assert x['candidate_runner_sha256']==sha(runner)
assert x['candidate_source_sha256']==sha(candidate)
assert x['source_bundle_manifest_sha256']=='377b2e7226cbdb99271783cbeb2df547084d804a756374f8d6f02dcd9aa08144'
PY
row=$(PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" show --bench "$bench") || repair pool_show "could not read claimed pool row" packet
eval "$(ROW="$row" python3 - <<'PY'
import json,os,shlex
r=json.loads(os.environ['ROW']); assert r['claim']['project']=='gemma4_b200_fp8_local_attention_fusion'
for k,v in {'host':r['resource']['public_ipv4'],'user':r['resource']['ssh_user'],'key':r['resource']['identity_file'],'known':r['resource']['known_hosts_namespace']}.items(): print(f'{k}={shlex.quote(v)}')
PY
)"
test -f "$key" && test -f "$known" || repair local_identity "inventory identity path absent" packet
ssh_cmd=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host")
ssh_stream_cmd=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host")

phase stage
"${ssh_cmd[@]}" "mkdir -p '$remote/input' '$remote/output'" >"$out/stage.stdout" 2>"$out/stage.stderr" || repair remote_prepare "$(tail -60 "$out/stage.stderr")" packet
tar -C "$project" -cf - candidate inputs/pinned "$(basename "$preclaim")" | "${ssh_stream_cmd[@]}" "tar -C '$remote/input' -xf -" >>"$out/stage.stdout" 2>>"$out/stage.stderr" || repair packet_copy "$(tail -60 "$out/stage.stderr")" packet
"${ssh_cmd[@]}" "cd '$remote/input' && sha256sum candidate/check_split_kv_correctness_b200.py candidate/local_paged_gqa_split_kv_fused.py inputs/pinned/flashinfer-0.6.6/trtllm-gen-artifact/fmhaSm100fKernel_QkvBfloat16OBfloat16H256PagedKvSlidingOrChunkedCausalP16MultiCtasKvVarSeqQ8Kv128StaticSwapsAbForGen.cubin" >"$out/remote-packet.sha256" 2>>"$out/stage.stderr" || repair packet_verify "$(tail -60 "$out/stage.stderr")" packet

phase scientific_pair
set +e
"${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --ipc=host --entrypoint python3 -v '$remote/input:/work:ro' -v '$remote/output:/out' '$image' /work/candidate/check_split_kv_correctness_b200.py --project-root /work --artifact-root /out" >"$out/worker.stdout" 2>"$out/worker.stderr"
worker_rc=$?
set -e
mkdir -p "$out/remote-artifacts"
"${ssh_cmd[@]}" "test -r '$remote/output/CORRECTNESS_TERMINAL.json' && cat '$remote/output/CORRECTNESS_TERMINAL.json'" >"$out/remote-artifacts/CORRECTNESS_TERMINAL.json" 2>>"$out/retrieve.stderr" || repair retrieval "$(tail -60 "$out/retrieve.stderr")" retrieval
"${ssh_cmd[@]}" "test -e '$remote/output/candidate_science_started' && echo candidate_science_started=true || echo candidate_science_started=false" >"$out/candidate_science_started.txt" 2>>"$out/retrieve.stderr" || repair retrieval_marker "$(tail -60 "$out/retrieve.stderr")" retrieval

phase classify
python3 - "$out" "$worker_rc" <<'PY' || repair terminal_classify "terminal classification failed" terminal
import hashlib,json,pathlib,sys
out=pathlib.Path(sys.argv[1]); rc=int(sys.argv[2]); t=json.loads((out/'remote-artifacts/CORRECTNESS_TERMINAL.json').read_text())
terminal=t.get('terminal'); interpreted=bool(t.get('interpretable_result')); consumed=bool(t.get('scientific_sample_consumed'))
record={'schema_version':1,'worker_exit_code':rc,'terminal':terminal,'interpretable_result':interpreted,'scientific_sample_consumed':consumed,'correctness_terminal_sha256':hashlib.sha256((out/'remote-artifacts/CORRECTNESS_TERMINAL.json').read_bytes()).hexdigest(),'candidate_science_marker':(out/'candidate_science_started.txt').read_text().strip()}
(out/'OWNER_TERMINAL.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
if not interpreted: raise SystemExit(2)
PY
if jq -e '.terminal == "incorrect" and .interpretable_result == true' "$out/remote-artifacts/CORRECTNESS_TERMINAL.json" >/dev/null; then
  printf '%s\n' '{"schema_version":1,"state":"decision_bearing_incorrect_local_paged_gqa","stage":"correctness_component","science_consumed":true,"server_state":"GPU unoccupied; image/cache/source retained","component_terminal":"local project artifact retrieved"}' >"$out/RELEASE_CONTENTS.json"
  release ready
  exit 0
fi
if jq -e '.terminal == "correct" and .interpretable_result == true' "$out/remote-artifacts/CORRECTNESS_TERMINAL.json" >/dev/null; then
  # Positive evidence is retained for director promotion; do not time here.
  atomic_json "$out/RELEASE_CONTENTS.json" '{"schema_version":1,"state":"correct_local_paged_gqa_retained_for_director","stage":"correctness_component","science_consumed":true,"server_state":"GPU unoccupied; image/cache/source retained"}'
  exit 0
fi
repair invalid_attempt "$(jq -r '.error // .terminal' "$out/remote-artifacts/CORRECTNESS_TERMINAL.json")" scientific_pair
