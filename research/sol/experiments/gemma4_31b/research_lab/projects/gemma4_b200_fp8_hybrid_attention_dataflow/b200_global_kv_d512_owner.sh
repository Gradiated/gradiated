#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_hybrid_attention_dataflow
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
bench=b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j; out=$project/artifacts/b200-global-kv-d512-20260728t1832z; deadline=2026-07-28T18:59:00Z
image=docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79
mkdir -p "$out"; phase(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$out/OWNER_PROGRESS.log"; }
heartbeat(){ while sleep 20; do PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_b200_fp8_hybrid_attention_dataflow --bench "$bench" >>"$out/heartbeat.log" 2>&1 || true; done; }; heartbeat & hb=$!; trap 'kill "$hb" 2>/dev/null || true' EXIT
repair(){ phase "repair:$1"; printf '%s\n' "$2" >"$out/REPAIR_DIAGNOSTIC.txt"; /root/workspace/research/factory/tools/repair-handshake ready --root "$out" --repair-id "d512-$(date -u +%Y%m%dT%H%M%SZ)" --failure-kind "$1" --diagnostic "$out/REPAIR_DIAGNOSTIC.txt" --retry-scope "$3" --deadline "$deadline" >>"$out/repair.log" 2>&1 || true; while [ "$(date -u +%s)" -lt "$(date -u -d "$deadline" +%s)" ]; do sleep 15; done; exit 75; }
row=$(PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" show --bench "$bench") || repair pool show
eval "$(ROW="$row" python3 - <<'PY'
import json,os,shlex
r=json.loads(os.environ['ROW']); assert r['claim']['project']=='gemma4_b200_fp8_hybrid_attention_dataflow'
for k,v in {'host':r['resource']['public_ipv4'],'user':r['resource']['ssh_user'],'key':r['resource']['identity_file'],'known':r['resource']['known_hosts_namespace']}.items(): print(f'{k}={shlex.quote(v)}')
PY
)"
remote=/home/$user/b200-global-kv-d512-20260728t1832z; capture=/home/$user/b200-global-kv-20260728t1807z/m32_hidden.pt; checkpoint=/home/$user/b200-nvfp4-gemma4-endpoint-v2-20260728t1323z/bf16-source
ssh_cmd=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host"); scp_cmd=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known")
phase stage; "${ssh_cmd[@]}" "test -f '$capture'; test -f '$checkpoint/model.safetensors.index.json'; mkdir -p '$remote'" >"$out/stage.stdout" 2>"$out/stage.stderr" || repair input "$(tail -60 "$out/stage.stderr")" consumer
"${scp_cmd[@]}" "$project/b200_k_eq_v_component.py" "$project/PRECLAIM_B200_GLOBAL_KV_D512_TERMINAL.json" "$user@$host:$remote/" >>"$out/stage.stdout" 2>>"$out/stage.stderr" || repair copy "$(tail -60 "$out/stage.stderr")" consumer
sha=$(${ssh_cmd[@]} "sha256sum '$capture' | awk '{print \$1}'"); test "$sha" = cd84ccd1dab17b32b5028d81e0d4f3bd7599a00759b9ead4a6a56fda09e776a3 || repair capture_digest "$sha" consumer
phase component; "${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --ipc=host --entrypoint python3 -v '$checkpoint:/checkpoint:ro' -v '$capture:/work/m32_hidden.pt:ro' -v '$remote:/work' '$image' /work/b200_k_eq_v_component.py --checkpoint /checkpoint --hidden /work/m32_hidden.pt --hidden-sha256 '$sha' --output /work/COMPONENT_TERMINAL.json" >"$out/worker.stdout" 2>"$out/worker.stderr" || repair component "$(tail -120 "$out/worker.stderr")" consumer
phase retrieve; mkdir -p "$out/remote-artifacts"; "${scp_cmd[@]}" "$user@$host:$remote/COMPONENT_TERMINAL.json" "$out/remote-artifacts/COMPONENT_TERMINAL.json" >>"$out/retrieve.stdout" 2>>"$out/retrieve.stderr" || repair retrieve "$(tail -80 "$out/retrieve.stderr")" retrieval
phase terminal
