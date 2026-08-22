#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_local_attention_fusion
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
bench=b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j
image=docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79
: "${OWNER_DEADLINE_UTC:?}" "${OWNER_ARTIFACT_ROOT:?}" "${OWNER_REMOTE_ROOT:?}" "${OWNER_EXECUTION_BINDING:?}"
out=$OWNER_ARTIFACT_ROOT; remote=$OWNER_REMOTE_ROOT; mkdir -p "$out"
phase(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$out/OWNER_PROGRESS.log"; }
atomic(){ python3 - "$1" "$2" <<'PY'
import json,os,pathlib,sys,tempfile
p=pathlib.Path(sys.argv[1]);v=json.loads(sys.argv[2]);p.parent.mkdir(parents=True,exist_ok=True)
with tempfile.NamedTemporaryFile('w',dir=p.parent,delete=False) as f: json.dump(v,f,sort_keys=True,indent=2);f.write('\n');t=f.name
json.loads(pathlib.Path(t).read_text());os.replace(t,p)
PY
}
heartbeat(){ while sleep 20; do PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_b200_fp8_local_attention_fusion --bench "$bench" >>"$out/heartbeat.log" 2>&1 || true; done; }
heartbeat & hb=$!; trap 'kill "$hb" 2>/dev/null || true' EXIT
release(){ PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_b200_fp8_local_attention_fusion --bench "$bench" --condition "$1" --contents "$out/RELEASE_CONTENTS.json" >>"$out/release.log" 2>&1; }
row=$(PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" show --bench "$bench")
eval "$(ROW="$row" python3 - <<'PY'
import json,os,shlex
r=json.loads(os.environ['ROW']);assert r['claim']['project']=='gemma4_b200_fp8_local_attention_fusion'
for k in ('public_ipv4','ssh_user','identity_file','known_hosts_namespace'): print({'public_ipv4':'host','ssh_user':'user','identity_file':'key','known_hosts_namespace':'known'}[k]+'='+shlex.quote(r['resource'][k]))
PY
)"
test -f "$key" && test -f "$known"; sshc=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host"); sshs=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host")
phase binding
python3 - "$OWNER_EXECUTION_BINDING" "$project" "$0" <<'PY'
import hashlib,json,pathlib,sys
b=json.loads(pathlib.Path(sys.argv[1]).read_text());root=pathlib.Path(sys.argv[2]);assert b['execution_authorized'] and b['project']=='gemma4_b200_fp8_local_attention_fusion'
for p in ('candidate/time_split_reducer_b200.py','b200_local_paged_gqa_split_reducer_timing_owner.sh','PRECLAIM_B200_LOCAL_PAGED_GQA_SPLIT_REDUCER_TIMING_TERMINAL.json','candidate/local_paged_gqa_split_reducer_fused.py','candidate/check_split_reducer_correctness_b200.py'):
 assert (root/p).is_file(),p
PY
phase stage; "${sshc[@]}" "mkdir -p '$remote/input' '$remote/output-0'" >"$out/stage.stdout" 2>"$out/stage.stderr"
tar -C "$project" -cf - candidate inputs/pinned/flashinfer-0.6.6 PRECLAIM_B200_LOCAL_PAGED_GQA_SPLIT_REDUCER_TIMING_TERMINAL.json | "${sshs[@]}" "tar -C '$remote/input' -xf -" >>"$out/stage.stdout" 2>>"$out/stage.stderr"
attempt=0
while true; do
  a="$out/attempt-$attempt"; ro="$remote/output-$attempt"; mkdir -p "$a/remote-artifacts"; "${sshc[@]}" "mkdir -p '$ro'"; phase "attempt:$attempt:paired_timing"
  set +e; "${sshc[@]}" "sudo -n docker run --rm --gpus all --ipc=host --entrypoint python3 -v '$remote/input:/work:ro' -v '$ro:/out' '$image' /work/candidate/time_split_reducer_b200.py --project-root /work --artifact-root /out" >"$a/worker.stdout" 2>"$a/worker.stderr"; rc=$?; set -e; echo "$rc" >"$a/worker.exit"
  set +e; "${sshc[@]}" "cat '$ro/TIMING_TERMINAL.json'" >"$a/remote-artifacts/TIMING_TERMINAL.json" 2>"$a/retrieve.stderr"; rr=$?; "${sshc[@]}" "test -e '$ro/timing_science_started' && echo timing_science_started=true || echo timing_science_started=false" >"$a/timing_science_started.txt" 2>>"$a/retrieve.stderr"; set -e
  cls=$(python3 - "$a" "$rr" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]);
try: t=json.loads((p/'remote-artifacts/TIMING_TERMINAL.json').read_text()) if int(sys.argv[2])==0 else {}
except: t={}
print(t.get('terminal','unknown'))
PY
)
  if [[ "$cls" == positive || "$cls" == negative ]]; then cp "$a/remote-artifacts/TIMING_TERMINAL.json" "$out/TIMING_TERMINAL.json"; atomic "$out/OWNER_TERMINAL.json" "{\"schema_version\":1,\"terminal\":\"$cls\",\"interpretable_result\":true,\"scientific_sample_consumed\":true,\"attempt\":$attempt,\"worker_exit_code\":$rc}"; atomic "$out/RELEASE_CONTENTS.json" "{\"schema_version\":1,\"state\":\"split_reducer_timing_$cls\",\"stage\":\"paired_timing_component\",\"science_consumed\":true,\"server_state\":\"GPU unoccupied; image/source/build/checkpoint caches retained\",\"component_terminal\":\"TIMING_TERMINAL.json\"}"; release ready; exit 0; fi
  diag="$a/REPAIR_DIAGNOSTIC.txt"; { echo "classification=$cls rc=$rc retrieval=$rr"; tail -80 "$a/worker.stderr" "$a/retrieve.stderr" 2>/dev/null || true; } >"$diag"; /root/workspace/research/factory/tools/repair-handshake ready --root "$out" --repair-id "timing-repair-$attempt" --deadline "$OWNER_DEADLINE_UTC" --failure-kind "$cls" --diagnostic "$diag" --retry-scope timing_pair >"$a/repair-ready.json"; phase "attempt:$attempt:repair_ready"; /root/workspace/research/factory/tools/repair-handshake wait --root "$out" --repair-id "timing-repair-$attempt" --deadline "$OWNER_DEADLINE_UTC" --poll-seconds 2 >"$a/repair-wait.json" || { atomic "$out/RELEASE_CONTENTS.json" '{"schema_version":1,"state":"split_reducer_timing_repair_deadline","science_consumed":false,"server_state":"GPU unoccupied; caches retained"}'; release maintenance; exit 75; }
  patch=$(python3 - "$a/repair-wait.json" "$project" <<'PY'
import json,pathlib,sys
s=json.loads(pathlib.Path(sys.argv[1]).read_text());p=pathlib.Path(s['request']['patch_artifact']).resolve();root=pathlib.Path(sys.argv[2]).resolve();assert p.is_file() and p.is_relative_to(root);print(p)
PY
); tar -cf - -C "$(dirname "$patch")" "$(basename "$patch")" | "${sshs[@]}" "tar -C '$remote' -xf - && tar -C '$remote/input' -xf '$remote/$(basename "$patch")'"; attempt=$((attempt+1))
done
