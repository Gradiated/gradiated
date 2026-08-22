#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_residual_hotpath
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
bench=${B200_M32_BENCH:?set B200_M32_BENCH}; out=${B200_M32_OUTPUT:?set B200_M32_OUTPUT}; release_by=${B200_M32_RELEASE_BY_UTC:?set B200_M32_RELEASE_BY_UTC}
host=${B200_M32_HOST:?set B200_M32_HOST}; user=${B200_M32_USER:?set B200_M32_USER}; key=${B200_M32_KEY:?set B200_M32_KEY}; known=${B200_M32_KNOWN_HOSTS:?set B200_M32_KNOWN_HOSTS}
preclaim=$project/PRECLAIM_TERMINAL.json; runner=$project/b200_m32_dispatch_component.py; patch=$project/M32_DISPATCH.patch
remote=/home/$user/b200-m32-dispatch-20260728t1606z; image=docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79
mkdir -p "$out"; phase(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$out/OWNER_PROGRESS.log"; }
heartbeat(){ while sleep 45; do python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_b200_fp8_residual_hotpath --bench "$bench" >>"$out/heartbeat.log" 2>&1 || true; done; }
heartbeat & heartbeat_pid=$!; trap 'kill "$heartbeat_pid" 2>/dev/null || true' EXIT
ssh_cmd=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host")
scp_cmd=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known")
phase binding_validation
python3 - "$preclaim" "$runner" "$patch" "$0" <<'PY'
import hashlib,json,pathlib,sys
preclaim,runner,patch,owner=map(pathlib.Path,sys.argv[1:]); b=json.loads(preclaim.read_text()); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert b['runner_sha256']==sha(runner); assert b['patch_sha256']==sha(patch); assert b['owner_sha256']==sha(owner); assert b['bench_gate']['claim_allowed'] is True
PY
phase inventory_reconcile
row=$(python3 -m grad_research.gpu_pool --lab "$lab" show --bench "$bench")
python3 - "$row" "$bench" <<'PY'
import json,sys
r=json.loads(sys.argv[1]); assert r['id']==sys.argv[2]; assert (r.get('claim') or {}).get('project')=='gemma4_b200_fp8_residual_hotpath'
PY
phase remote_identity
"${ssh_cmd[@]}" "hostname; nvidia-smi --query-gpu=name,compute_cap --format=csv,noheader; sudo -n docker image inspect '$image' --format '{{index .RepoDigests 0}}'" >"$out/remote-identity.log" 2>"$out/remote-identity.stderr"
phase preserve_and_stop_resident_server
"${ssh_cmd[@]}" "sudo -n docker logs --tail 400 gemma4-b200-dynamic_fp8_candidate" >"$out/resident-server.log" 2>"$out/resident-server.stderr" || true
sha256sum "$out/resident-server.log" >"$out/resident-server.sha256"
"${ssh_cmd[@]}" "sudo -n docker stop --time 30 gemma4-b200-dynamic_fp8_candidate" >"$out/server-stop.stdout" 2>"$out/server-stop.stderr"
phase stage_packet
"${ssh_cmd[@]}" "mkdir -p '$remote/input' '$remote/output'"
"${scp_cmd[@]}" "$runner" "$patch" "$preclaim" "$user@$host:$remote/input/" >"$out/stage.stdout" 2>"$out/stage.stderr"
phase source_build
"${ssh_cmd[@]}" "cd '$remote' && if [ ! -d vllm/.git ]; then git clone --filter=blob:none --no-checkout https://github.com/vllm-project/vllm.git vllm; fi && cd vllm && git fetch --filter=blob:none origin 6d4a8e6d204a9b2827544003b26321fff62923da && git checkout --detach 6d4a8e6d204a9b2827544003b26321fff62923da && git restore --source=HEAD -- csrc/quantization/w8a8/cutlass/c3x/scaled_mm_sm100_fp8_dispatch.cuh && cp '$remote/input/M32_DISPATCH.patch' M32_DISPATCH.patch && git apply --check M32_DISPATCH.patch && git apply M32_DISPATCH.patch && sudo -n docker run --rm --gpus all --ipc=host --network=host --user 0:0 --entrypoint bash -e SETUPTOOLS_SCM_PRETEND_VERSION=0.19.1.dev6+g6d4a8e6d2 -e SETUPTOOLS_SCM_PRETEND_VERSION_FOR_VLLM=0.19.1.dev6+g6d4a8e6d2 -v '$remote/vllm:/work/vllm' '$image' -lc 'apt-get update -qq && apt-get install -y -qq git && git config --global --add safe.directory /work/vllm && pip install cmake ninja --no-cache-dir && cd /work/vllm && pip install -e . --no-build-isolation --no-deps'" >"$out/source-build.stdout" 2>"$out/source-build.stderr"
phase stock_component
"${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --ipc=host --network=host --user 0:0 --entrypoint python3 -v '$remote/input:/work/input:ro' -v '$remote/output/stock:/work/output' '$image' /work/input/b200_m32_dispatch_component.py --arm stock --output /work/output" >"$out/stock.stdout" 2>"$out/stock.stderr"
phase patched_component
"${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --ipc=host --network=host --user 0:0 --entrypoint python3 -v '$remote/input:/work/input:ro' -v '$remote/vllm:/work/vllm:ro' -v '$remote/output/patched:/work/output' -e PYTHONPATH=/work/vllm '$image' /work/input/b200_m32_dispatch_component.py --arm patched --output /work/output" >"$out/patched.stdout" 2>"$out/patched.stderr"
phase retrieve_terminals
mkdir -p "$out/stock" "$out/patched"
"${scp_cmd[@]}" -r "$user@$host:$remote/output/stock/." "$out/stock/" >"$out/retrieve-stock.stdout" 2>"$out/retrieve-stock.stderr"
"${scp_cmd[@]}" -r "$user@$host:$remote/output/patched/." "$out/patched/" >"$out/retrieve-patched.stdout" 2>"$out/retrieve-patched.stderr"
phase finalize_component
python3 - "$out" "$preclaim" <<'PY'
import hashlib, json, pathlib, sys
out, preclaim = map(pathlib.Path, sys.argv[1:])
b = json.loads(preclaim.read_text())
stock = json.loads((out / 'stock/TERMINAL.json').read_text())
patched = json.loads((out / 'patched/TERMINAL.json').read_text())
assert stock['custom_extension_sha256'] != patched['custom_extension_sha256']
assert stock['candidate_science_started'] and patched['candidate_science_started']
srows = {row['name']: row for row in stock['rows']}
prows = {row['name']: row for row in patched['rows']}
rows = []
for name in srows:
    a, c = srows[name], prows[name]
    rows.append({'name': name, 'stock_p50_ms': a['quant_and_gemm_p50_ms'], 'patched_p50_ms': c['quant_and_gemm_p50_ms'], 'multiplicity_per_decode_step': a['multiplicity_per_decode_step'], 'regression_fraction': c['quant_and_gemm_p50_ms'] / a['quant_and_gemm_p50_ms'] - 1, 'correctness': c['numeric']})
stock_ms = sum(row['multiplicity_per_decode_step'] * row['stock_p50_ms'] for row in rows)
patched_ms = sum(row['multiplicity_per_decode_step'] * row['patched_p50_ms'] for row in rows)
gain = 1 - patched_ms / stock_ms
saving = 358 * (stock_ms - patched_ms) / 1000 / 32
correct = all(row['correctness']['finite'] and row['correctness']['cosine'] >= 0.99999 and row['correctness']['normalized_rmse'] <= 0.005 and row['correctness']['max_abs'] <= 0.01 for row in rows)
shape_ok = all(row['regression_fraction'] <= 0.05 for row in rows)
classification = 'component_positive_endpoint_conditional' if correct and shape_ok and gain >= 0.10 and saving >= 0.005 else 'component_negative_stop'
terminal = {'schema_version': 1, 'classification': classification, 'science_consumed': True, 'stock_terminal_sha256': hashlib.sha256((out / 'stock/TERMINAL.json').read_bytes()).hexdigest(), 'patched_terminal_sha256': hashlib.sha256((out / 'patched/TERMINAL.json').read_bytes()).hexdigest(), 'preclaim_sha256': hashlib.sha256(preclaim.read_bytes()).hexdigest(), 'rows': rows, 'weighted_stock_quant_and_gemm_p50_ms': stock_ms, 'weighted_patched_quant_and_gemm_p50_ms': patched_ms, 'weighted_gain_fraction': gain, 'projected_endpoint_saving_seconds_per_request': saving, 'gates': {'correctness': correct, 'shape_regression': shape_ok, 'weighted_gain': gain >= 0.10, 'endpoint_projection': saving >= 0.005}, 'stop_conditions': b['stop_conditions'], 'next_action': 'retain claim for endpoint-promotion handoff' if classification == 'component_positive_endpoint_conditional' else 'release maintenance without endpoint replay'}
tmp = out / 'PRECLAIM_FINAL.json.part'
tmp.write_text(json.dumps(terminal, indent=2, sort_keys=True) + '\n')
tmp.replace(out / 'PRECLAIM_FINAL.json')
PY
phase scientific_terminal
classification=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["classification"])' "$out/PRECLAIM_FINAL.json")
if [[ "$classification" == component_negative_stop ]]; then
  python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_b200_fp8_residual_hotpath --bench "$bench" --condition maintenance --contents "M32 component negative; retained checkpoint/image/source; resident endpoint stopped; artifacts at $out" >"$out/release.log" 2>&1
else
  phase retain_for_endpoint_promotion
fi
