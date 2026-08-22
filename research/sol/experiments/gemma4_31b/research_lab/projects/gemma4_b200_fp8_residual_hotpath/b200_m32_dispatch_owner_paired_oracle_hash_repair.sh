#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_residual_hotpath
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
bench=${B200_M32_BENCH:?}; out=${B200_M32_OUTPUT:?}; host=${B200_M32_HOST:?}; user=${B200_M32_USER:?}; key=${B200_M32_KEY:?}; known=${B200_M32_KNOWN_HOSTS:?}
preclaim=$project/PRECLAIM_M32_PAIRED_ORACLE_HASH_REPAIR_TERMINAL.json; runner=$project/b200_m32_dispatch_component_paired_oracle.py; patch=$project/M32_DISPATCH.patch
remote=/home/$user/b200-m32-dispatch-20260728t1623z; source_remote=$remote/vllm-recovery5; install_remote=$remote/sm100-install-20260728t1734z-repair2; output_remote=$remote/output-sm100-paired-oracle-hash-repair-20260728t1906z
image=b200-m32-recovery5:20260728t1623z; expected=66fb9013b67832d6939c59f21395aeafc59a8e1b52abc3636132819e38cc5be2
mkdir -p "$out"; phase(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$out/OWNER_PROGRESS.log"; }; heartbeat(){ while sleep 30; do python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_b200_fp8_residual_hotpath --bench "$bench" >>"$out/heartbeat.log" 2>&1 || true; done; }; heartbeat & hb=$!; trap 'kill "$hb" 2>/dev/null || true' EXIT
ssh_cmd=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host"); scp_cmd=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known")
incomplete(){ stage=$1; code=$2; python3 - "$out/INCOMPLETE_TERMINAL.json" "$stage" "$code" <<'PY'
import json,os,pathlib,sys,tempfile,time
p=pathlib.Path(sys.argv[1]); v={'schema_version':1,'classification':'component_incomplete_repairable','stage':sys.argv[2],'exit_code':int(sys.argv[3]),'science_consumed':False,'candidate_science_started':False,'repair_deadline_utc':'2026-07-28T19:18:00Z'}; fd,t=tempfile.mkstemp(prefix='.incomplete.',dir=p.parent); os.close(fd); pathlib.Path(t).write_text(json.dumps(v,sort_keys=True,indent=2)+'\n'); os.replace(t,p); (p.parent/'REPAIR_READY.json').write_text(json.dumps({'repair_scope':sys.argv[2],'deadline_utc':'2026-07-28T19:18:00Z','resume':'invalidated operation only; do not replay completed arms'},indent=2)+'\n')
PY
  while [[ "$(date -u +%s)" -lt 1785266280 ]]; do sleep 30; python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_b200_fp8_residual_hotpath --bench "$bench" >/dev/null 2>&1 || true; done; exit "$code"; }
phase binding_validation
python3 - "$preclaim" "$runner" "$patch" "$0" <<'PY' || incomplete binding_validation 2
import hashlib,json,pathlib,sys
b,r,p,o=map(pathlib.Path,sys.argv[1:]); x=json.loads(b.read_text()); h=lambda q:hashlib.sha256(q.read_bytes()).hexdigest(); assert x['owner_sha256']==h(o) and x['runner_sha256']==h(r) and x['patch_sha256']==h(p) and x['bench_gate']['claim_allowed']
PY
phase predecessor_wait
pre_pid=3530991; pre_ticks=138143588; deadline=1785266280
while [[ "$(date -u +%s)" -lt "$deadline" ]]; do
  if [[ ! -r "/proc/$pre_pid/stat" ]]; then break; fi
  cur_ticks=$(awk "{print \$22}" "/proc/$pre_pid/stat" 2>/dev/null || true)
  if [[ "$cur_ticks" != "$pre_ticks" ]]; then break; fi
  sleep 2
done
if [[ -r "/proc/$pre_pid/stat" ]]; then cur_ticks=$(awk "{print \$22}" "/proc/$pre_pid/stat" 2>/dev/null || true); if [[ "$cur_ticks" == "$pre_ticks" ]]; then kill "$pre_pid"; fi; fi
phase claim_reconcile; row=$(python3 -m grad_research.gpu_pool --lab "$lab" show --bench "$bench") || incomplete claim_reconcile 3
python3 - "$row" "$bench" <<'PY' || incomplete claim_identity 3
import json,sys
r=json.loads(sys.argv[1]); assert r['id']==sys.argv[2] and r.get('claim',{}).get('project')=='gemma4_b200_fp8_residual_hotpath'
PY
phase extension_adoption
"${ssh_cmd[@]}" "set -Eeuo pipefail; ext='$install_remote/vllm/_C.abi3.so'; test -f \"\$ext\"; got=\$(sha256sum \"\$ext\" | awk '{print \$1}'); test \"\$got\" = '$expected'; cp \"\$ext\" '$source_remote/vllm/_C.abi3.so'; test \"\$(sha256sum '$source_remote/vllm/_C.abi3.so' | awk '{print \$1}')\" = '$expected'" >"$out/adoption.stdout" 2>"$out/adoption.stderr" || incomplete extension_adoption 5
phase packet_stage; "${scp_cmd[@]}" "$runner" "$patch" "$preclaim" "$user@$host:$remote/" || incomplete packet_stage 6
phase stock_arm; "${ssh_cmd[@]}" "sudo -n mkdir -p '$output_remote'; sudo -n rm -rf '$output_remote/stock' '$output_remote/patched'; sudo -n docker run --rm --gpus all --ipc=host --network=host --user 0:0 --entrypoint python3 -v '$remote/b200_m32_dispatch_component_paired_oracle.py:/work/runner.py:ro' -v '$output_remote:/work/output-root' 'docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79' /work/runner.py --arm stock --output /work/output-root/stock; sudo -n chmod -R a+rX '$output_remote/stock'" >"$out/stock.stdout" 2>"$out/stock.stderr" || incomplete stock_arm 10
phase patched_arm; "${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --ipc=host --network=host --user 0:0 --entrypoint python3 -e PYTHONPATH=/work/vllm -v '$remote/b200_m32_dispatch_component_paired_oracle.py:/work/runner.py:ro' -v '$source_remote:/work/vllm:ro' -v '$output_remote:/work/output-root' -v '$output_remote/stock:/work/oracle:ro' '$image' /work/runner.py --arm patched --oracle /work/oracle --output /work/output-root/patched; sudo -n chmod -R a+rX '$output_remote/patched'" >"$out/patched.stdout" 2>"$out/patched.stderr" || incomplete patched_arm 11
phase retrieve; mkdir -p "$out/stock" "$out/patched"; "${scp_cmd[@]}" -r "$user@$host:$output_remote/stock/." "$out/stock/" || incomplete retrieve_stock 12; "${scp_cmd[@]}" -r "$user@$host:$output_remote/patched/." "$out/patched/" || incomplete retrieve_patched 13
phase component_finalize; python3 "$project/sm100_component_finalize.py" "$out" "$preclaim" || incomplete component_finalize 14
classification=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["classification"])' "$out/SM100_TERMINAL.json")
if [[ "$classification" == component_negative_stop ]]; then python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_b200_fp8_residual_hotpath --bench "$bench" --condition maintenance --contents '{"state":"m32_paired_oracle_negative"}' >"$out/release.log" 2>&1; else phase retain_for_promotion; fi
