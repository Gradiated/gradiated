#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_hybrid_attention_dataflow
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
bench=b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j
out=$project/artifacts/b200-global-kv-20260728t1807z
deadline=2026-07-28T18:32:00Z
image=docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79
mkdir -p "$out"
phase(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$out/OWNER_PROGRESS.log"; }
heartbeat(){ while sleep 20; do PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_b200_fp8_hybrid_attention_dataflow --bench "$bench" >>"$out/heartbeat.log" 2>&1 || true; done; }
heartbeat & hb=$!; trap 'kill "$hb" 2>/dev/null || true' EXIT
repair(){ phase "repair:$1"; printf '%s\n' "$2" >"$out/REPAIR_DIAGNOSTIC.txt"; /root/workspace/research/factory/tools/repair-handshake ready --root "$out" --repair-id "global-kv-$(date -u +%Y%m%dT%H%M%SZ)" --failure-kind "$1" --diagnostic "$out/REPAIR_DIAGNOSTIC.txt" --retry-scope "$3" --deadline "$deadline" >>"$out/repair.log" 2>&1 || true; while [ "$(date -u +%s)" -lt "$(date -u -d "$deadline" +%s)" ]; do find "$out/.repair-handshakes" -name REPAIR_REQUEST.json -type f -print -quit 2>/dev/null | grep -q . && exit 75; sleep 15; done; exit 75; }
row=$(PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" show --bench "$bench") || repair pool_show failed retrieval
eval "$(ROW="$row" python3 - <<'PY'
import json,os,shlex
r=json.loads(os.environ['ROW']); assert r['claim']['project']=='gemma4_b200_fp8_hybrid_attention_dataflow'
for k,v in {'host':r['resource']['public_ipv4'],'user':r['resource']['ssh_user'],'key':r['resource']['identity_file'],'known':r['resource']['known_hosts_namespace']}.items(): print(f'{k}={shlex.quote(v)}')
PY
)"
test -f "$key" || repair identity "missing identity" retrieval
remote=/home/$user/b200-global-kv-20260728t1807z; checkpoint=/home/$user/b200-nvfp4-gemma4-endpoint-v2-20260728t1323z/bf16-source
ssh_cmd=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host")
scp_cmd=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known")
phase packet_stage
"${ssh_cmd[@]}" "test -f '$checkpoint/model.safetensors.index.json'; mkdir -p '$remote'" >"$out/stage.stdout" 2>"$out/stage.stderr" || repair checkpoint "$(tail -80 "$out/stage.stderr")" capture
"${scp_cmd[@]}" "$project/b200_k_eq_v_component.py" "$project/capture_global_hidden.py" "$project/PRECLAIM_B200_GLOBAL_KV_TERMINAL.json" "$user@$host:$remote/" >>"$out/stage.stdout" 2>>"$out/stage.stderr" || repair packet_copy "$(tail -80 "$out/stage.stderr")" capture
phase production_hidden_capture
"${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --ipc=host --entrypoint python3 -v '$checkpoint:/checkpoint:ro' -v '$remote:/work' '$image' /work/capture_global_hidden.py --checkpoint /checkpoint --output /work/m32_hidden.pt --layer 5" >"$out/capture.stdout" 2>"$out/capture.stderr" || repair capture "$(tail -120 "$out/capture.stderr")" capture
phase component_execution
hidden_sha=$(${ssh_cmd[@]} "sha256sum '$remote/m32_hidden.pt' | awk '{print \$1}'")
"${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --ipc=host --entrypoint python3 -v '$checkpoint:/checkpoint:ro' -v '$remote:/work' '$image' /work/b200_k_eq_v_component.py --checkpoint /checkpoint --hidden /work/m32_hidden.pt --hidden-sha256 '$hidden_sha' --output /work/COMPONENT_TERMINAL.json" >"$out/worker.stdout" 2>"$out/worker.stderr" || repair component "$(tail -120 "$out/worker.stderr")" component
phase retrieve
mkdir -p "$out/remote-artifacts"; "${scp_cmd[@]}" "$user@$host:$remote/COMPONENT_TERMINAL.json" "$user@$host:$remote/m32_hidden.manifest.json" "$out/remote-artifacts/" >>"$out/retrieve.stdout" 2>>"$out/retrieve.stderr" || repair retrieve "$(tail -120 "$out/retrieve.stderr")" retrieval
python3 - "$out/remote-artifacts/COMPONENT_TERMINAL.json" <<'PY' || repair terminal_validation invalid_component_terminal retrieval
import json,sys
x=json.load(open(sys.argv[1])); assert x['classification']=='b200_exact_global_k_eq_v_component' and x['science_started']
PY
phase scientific_terminal
PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_b200_fp8_hybrid_attention_dataflow --bench "$bench" --condition maintenance --contents "{\"state\":\"global_k_eq_v_component_complete\",\"artifacts\":\"$out\"}" >"$out/release.log" 2>&1
