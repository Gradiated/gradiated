#!/usr/bin/env bash
set -Eeuo pipefail
p=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_local_attention_fusion; lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab; bench=b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j; image=docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79
: "${OWNER_DEADLINE_UTC:?}" "${OWNER_ARTIFACT_ROOT:?}" "${OWNER_REMOTE_ROOT:?}" "${OWNER_EXECUTION_BINDING:?}"; out=$OWNER_ARTIFACT_ROOT; remote=$OWNER_REMOTE_ROOT; mkdir -p "$out"
phase(){ echo "$(date -u +%FT%TZ) $1" >>"$out/OWNER_PROGRESS.log"; }; hb(){ while sleep 20;do PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_b200_fp8_local_attention_fusion --bench "$bench" >>"$out/heartbeat.log" 2>&1||true;done;};hb& h=$!;trap 'kill $h 2>/dev/null||true' EXIT
row=$(PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" show --bench "$bench");eval "$(ROW="$row" python3 - <<'PY'
import json,os,shlex
r=json.loads(os.environ['ROW']);assert r['claim']['project']=='gemma4_b200_fp8_local_attention_fusion'
for a,b in [('host','public_ipv4'),('user','ssh_user'),('key','identity_file'),('known','known_hosts_namespace')]:print(a+'='+shlex.quote(r['resource'][b]))
PY
)";sc=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host");ss=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host")
phase binding;python3 - "$OWNER_EXECUTION_BINDING" "$p" <<'PY'
import json,pathlib,sys
b=json.loads(pathlib.Path(sys.argv[1]).read_text());r=pathlib.Path(sys.argv[2]);assert b['execution_authorized'];assert (r/'candidate/time_stock_append_consumer_b200.py').is_file();assert (r/'PRECLAIM_B200_LOCAL_PAGED_GQA_STOCK_DECOMPOSITION_TERMINAL.json').is_file()
PY
phase stage;"${sc[@]}" "mkdir -p '$remote/input' '$remote/output-0'";tar -C "$p" -cf - candidate/time_stock_append_consumer_b200.py PRECLAIM_B200_LOCAL_PAGED_GQA_STOCK_DECOMPOSITION_TERMINAL.json inputs/pinned/flashinfer-0.6.6 | "${ss[@]}" "tar -C '$remote/input' -xf -"
i=0;while :;do a="$out/attempt-$i";ro="$remote/output-$i";mkdir -p "$a/remote-artifacts";"${sc[@]}" "mkdir -p '$ro'";phase "attempt:$i:stock_decomposition";set +e;"${sc[@]}" "sudo -n docker run --rm --gpus all --ipc=host --entrypoint python3 -v '$remote/input:/work:ro' -v '$ro:/out' '$image' /work/candidate/time_stock_append_consumer_b200.py --project-root /work --artifact-root /out" >"$a/worker.stdout" 2>"$a/worker.stderr";rc=$?;set -e;echo $rc >"$a/worker.exit";set +e;"${sc[@]}" "cat '$ro/STOCK_DECOMPOSITION_TERMINAL.json'" >"$a/remote-artifacts/STOCK_DECOMPOSITION_TERMINAL.json" 2>"$a/retrieve.stderr";rr=$?;set -e
 cls=$(python3 - "$a" "$rr" <<'PY'
import json,pathlib,sys
try:t=json.loads((pathlib.Path(sys.argv[1])/'remote-artifacts/STOCK_DECOMPOSITION_TERMINAL.json').read_text()) if int(sys.argv[2])==0 else {}
except:t={}
print(t.get('terminal','unknown'))
PY
);if [[ "$cls" == interpretable ]];then cp "$a/remote-artifacts/STOCK_DECOMPOSITION_TERMINAL.json" "$out/STOCK_DECOMPOSITION_TERMINAL.json";printf '{"schema_version":1,"terminal":"interpretable","interpretable_result":true,"scientific_sample_consumed":true}\n' >"$out/OWNER_TERMINAL.json";printf '{"schema_version":1,"state":"stock_decomposition_complete","science_consumed":true,"server_state":"GPU unoccupied; caches retained","component_terminal":"STOCK_DECOMPOSITION_TERMINAL.json"}\n' >"$out/RELEASE_CONTENTS.json";PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_b200_fp8_local_attention_fusion --bench "$bench" --condition ready --contents "$out/RELEASE_CONTENTS.json" >>"$out/release.log" 2>&1;exit 0;fi
 diag="$a/REPAIR_DIAGNOSTIC.txt";{ echo "cls=$cls rc=$rc rr=$rr";tail -80 "$a/worker.stderr" "$a/retrieve.stderr" 2>/dev/null||true;}>"$diag";/root/workspace/research/factory/tools/repair-handshake ready --root "$out" --repair-id "stock-decomp-repair-$i" --deadline "$OWNER_DEADLINE_UTC" --failure-kind "$cls" --diagnostic "$diag" --retry-scope stock_decomposition >"$a/repair-ready.json";phase "attempt:$i:repair_ready";/root/workspace/research/factory/tools/repair-handshake wait --root "$out" --repair-id "stock-decomp-repair-$i" --deadline "$OWNER_DEADLINE_UTC" --poll-seconds 2 >"$a/repair-wait.json"||exit 75;patch=$(python3 - "$a/repair-wait.json" <<'PY'
import json,pathlib,sys
print(pathlib.Path(json.loads(pathlib.Path(sys.argv[1]).read_text())['request']['patch_artifact']).resolve())
PY
);tar -cf - -C "$(dirname "$patch")" "$(basename "$patch")"|"${ss[@]}" "tar -C '$remote/input' -xf -";i=$((i+1));done
