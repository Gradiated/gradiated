#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_residual_hotpath
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
bench=${B200_M32_BENCH:?set B200_M32_BENCH}; out=${B200_M32_OUTPUT:?set B200_M32_OUTPUT}; release_by=${B200_M32_RELEASE_BY_UTC:?set B200_M32_RELEASE_BY_UTC}
host=${B200_M32_HOST:?set B200_M32_HOST}; user=${B200_M32_USER:?set B200_M32_USER}; key=${B200_M32_KEY:?set B200_M32_KEY}; known=${B200_M32_KNOWN_HOSTS:?set B200_M32_KNOWN_HOSTS}
preclaim=$project/PRECLAIM_RECOVERY5_TERMINAL.json; runner=$project/b200_m32_dispatch_component.py; patch=$project/M32_DISPATCH.patch; dockerfile=$project/recovery5.Dockerfile
remote=/home/$user/b200-m32-dispatch-20260728t1623z; source_remote=$remote/vllm-recovery5; output_remote=$remote/output-recovery5
image=docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79; derived=b200-m32-recovery5:20260728t1623z
mkdir -p "$out"; phase(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$out/OWNER_PROGRESS.log"; }
heartbeat(){ while sleep 45; do python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_b200_fp8_residual_hotpath --bench "$bench" >>"$out/heartbeat.log" 2>&1 || true; done; }
heartbeat & heartbeat_pid=$!; trap 'kill "$heartbeat_pid" 2>/dev/null || true' EXIT
ssh_cmd=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host")
scp_cmd=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known")
deadline_epoch=$(date -u -d "$release_by" +%s)
repair_wait(){
  stage=$1; code=$2; diagnostic="$out/REPAIR_${stage}.json"
  python3 - "$diagnostic" "$stage" "$code" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); value={'schema_version':1,'classification':'invalid_pre_science_integration_attempt','science_consumed':False,'candidate_science_started':False,'stage':sys.argv[2],'exit_code':int(sys.argv[3])}; t=p.with_suffix('.part'); t.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); t.replace(p)
PY
  /root/workspace/research/factory/tools/repair-handshake ready --root "$out" --repair-id "recovery5-$stage" --deadline "$release_by" --failure-kind integration --diagnostic "$diagnostic" --retry-scope "$stage" >"$out/repair-$stage.log" 2>&1 || true
  while (( $(date -u +%s) < deadline_epoch )); do sleep 30; done
  exit 75
}
phase binding_validation
python3 - "$preclaim" "$runner" "$patch" "$dockerfile" "$0" <<'PY'
import hashlib,json,pathlib,sys
preclaim,runner,patch,dockerfile,owner=map(pathlib.Path,sys.argv[1:]); b=json.loads(preclaim.read_text()); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); assert b['runner_sha256']==sha(runner); assert b['patch_sha256']==sha(patch); assert b['dockerfile_sha256']==sha(dockerfile); assert b['owner_sha256']==sha(owner); assert b['bench_gate']['claim_allowed'] is True
PY
phase claim_reconcile
row=$(python3 -m grad_research.gpu_pool --lab "$lab" show --bench "$bench") || repair_wait claim_reconcile 1
python3 - "$row" "$bench" <<'PY' || repair_wait claim_identity 1
import json,sys
r=json.loads(sys.argv[1]); assert r['id']==sys.argv[2]; assert (r.get('claim') or {}).get('project')=='gemma4_b200_fp8_residual_hotpath'
PY
phase predecessor_fence
python3 - <<'PY' >"$out/predecessor-fence.json" || repair_wait predecessor_fence 1
import json,os,pathlib
needles=('3323854','3325090','3325334','3327444','3329225','b200_m32_dispatch_owner.sh'); matches=[]
for p in pathlib.Path('/proc').iterdir():
    if not p.name.isdigit() or int(p.name)==os.getpid(): continue
    try: cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
    except OSError: continue
    if any(x in cmd for x in needles): matches.append({'pid':int(p.name),'cmd':cmd})
print(json.dumps({'matches':matches},sort_keys=True)); raise SystemExit(bool(matches))
PY
phase remote_stage
"${ssh_cmd[@]}" "rm -rf '$source_remote' '$output_remote' && mkdir -p '$source_remote' '$output_remote/stock' '$output_remote/patched' '$remote/build'" || repair_wait remote_stage 1
"${scp_cmd[@]}" "$runner" "$patch" "$preclaim" "$dockerfile" "$user@$host:$remote/" || repair_wait packet_stage 1
phase derived_image
"${scp_cmd[@]}" "$dockerfile" "$user@$host:$remote/recovery5.Dockerfile" >"$out/dockerfile-stage.stdout" 2>"$out/dockerfile-stage.stderr" || repair_wait dockerfile_stage 1
"${ssh_cmd[@]}" "sudo -n docker build --pull=false --tag '$derived' -f '$remote/recovery5.Dockerfile' '$remote'" >"$out/derived-build.stdout" 2>"$out/derived-build.stderr" || repair_wait derived_image 1
"${ssh_cmd[@]}" "sudo -n docker image inspect '$derived' --format '{{json .}}'" >"$out/derived-image.json" 2>"$out/derived-image.stderr" || repair_wait derived_identity 1
"${ssh_cmd[@]}" "sudo -n docker run --rm --entrypoint bash '$derived' -lc 'git --version; cmake --version | head -1; ninja --version'" >"$out/build-tool-versions.log" 2>"$out/build-tool-versions.stderr" || repair_wait derived_tools 1
phase fresh_source
"${ssh_cmd[@]}" "git clone --filter=blob:none --no-checkout https://github.com/vllm-project/vllm.git '$source_remote' && cd '$source_remote' && git fetch --filter=blob:none origin 6d4a8e6d204a9b2827544003b26321fff62923da && git checkout --detach 6d4a8e6d204a9b2827544003b26321fff62923da && sha256sum csrc/quantization/w8a8/cutlass/c3x/scaled_mm_sm100_fp8_dispatch.cuh" >"$out/source-pre.stdout" 2>"$out/source-pre.stderr" || repair_wait fresh_source 1
grep -F '492ab8232db9f04605e5cd50417ee00902b4476181540f3c223f470d1ced14cf' "$out/source-pre.stdout" >/dev/null || repair_wait source_pre_hash 1
phase apply_patch_build
"${ssh_cmd[@]}" "cp '$remote/M32_DISPATCH.patch' '$source_remote/M32_DISPATCH.patch' && cd '$source_remote' && git apply --check M32_DISPATCH.patch && git apply M32_DISPATCH.patch && sha256sum csrc/quantization/w8a8/cutlass/c3x/scaled_mm_sm100_fp8_dispatch.cuh && sudo -n docker run --rm --gpus all --ipc=host --network=host --user 0:0 --entrypoint bash -e SETUPTOOLS_SCM_PRETEND_VERSION=0.19.1.dev6+g6d4a8e6d2 -e SETUPTOOLS_SCM_PRETEND_VERSION_FOR_VLLM=0.19.1.dev6+g6d4a8e6d2 -v '$source_remote:/work/vllm' '$derived' -lc 'git config --global --add safe.directory /work/vllm && cd /work/vllm && pip install -e . --no-build-isolation --no-deps'" >"$out/patched-build.stdout" 2>"$out/patched-build.stderr" || repair_wait patched_build 1
grep -F '2662238503d1a233fe7c6b85c209076ef5657c789b2ae21b52b708aed9f15cef' "$out/patched-build.stdout" >/dev/null || repair_wait patched_post_hash 1
phase stock_arm
"${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --ipc=host --network=host --user 0:0 --entrypoint python3 -v '$remote/b200_m32_dispatch_component.py:/work/runner.py:ro' -v '$output_remote/stock:/work/output' '$image' /work/runner.py --arm stock --output /work/output" >"$out/stock.stdout" 2>"$out/stock.stderr" || repair_wait stock_arm 1
phase patched_arm
"${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --ipc=host --network=host --user 0:0 --entrypoint python3 -e PYTHONPATH=/work/vllm -v '$remote/b200_m32_dispatch_component.py:/work/runner.py:ro' -v '$source_remote:/work/vllm:ro' -v '$output_remote/patched:/work/output' '$derived' /work/runner.py --arm patched --output /work/output" >"$out/patched.stdout" 2>"$out/patched.stderr" || repair_wait patched_arm 1
phase retrieve
mkdir -p "$out/stock" "$out/patched"
"${scp_cmd[@]}" -r "$user@$host:$output_remote/stock/." "$out/stock/" || repair_wait retrieve_stock 1
"${scp_cmd[@]}" -r "$user@$host:$output_remote/patched/." "$out/patched/" || repair_wait retrieve_patched 1
phase component_finalize
python3 - "$out" "$preclaim" <<'PY'
import hashlib,json,pathlib,sys
out,preclaim=map(pathlib.Path,sys.argv[1:]); b=json.loads(preclaim.read_text()); stock=json.loads((out/'stock/TERMINAL.json').read_text()); patched=json.loads((out/'patched/TERMINAL.json').read_text())
assert stock['custom_extension_sha256'] != patched['custom_extension_sha256']; assert stock['candidate_science_started'] and patched['candidate_science_started']
s={r['name']:r for r in stock['rows']}; p={r['name']:r for r in patched['rows']}; rows=[]
for name in s:
    a,c=s[name],p[name]; rows.append({'name':name,'stock_p50_ms':a['quant_and_gemm_p50_ms'],'patched_p50_ms':c['quant_and_gemm_p50_ms'],'multiplicity_per_decode_step':a['multiplicity_per_decode_step'],'regression_fraction':c['quant_and_gemm_p50_ms']/a['quant_and_gemm_p50_ms']-1,'correctness':c['numeric']})
ws=sum(r['multiplicity_per_decode_step']*r['stock_p50_ms'] for r in rows); wp=sum(r['multiplicity_per_decode_step']*r['patched_p50_ms'] for r in rows); gain=1-wp/ws; saving=358*(ws-wp)/1000/32
correct=all(r['correctness']['finite'] and r['correctness']['cosine']>=0.99999 and r['correctness']['normalized_rmse']<=0.005 and r['correctness']['max_abs']<=0.01 for r in rows); shape_ok=all(r['regression_fraction']<=0.05 for r in rows); classification='component_positive_endpoint_conditional' if correct and shape_ok and gain>=0.10 and saving>=0.005 else 'component_negative_stop'
value={'schema_version':1,'classification':classification,'science_consumed':True,'stock_terminal_sha256':hashlib.sha256((out/'stock/TERMINAL.json').read_bytes()).hexdigest(),'patched_terminal_sha256':hashlib.sha256((out/'patched/TERMINAL.json').read_bytes()).hexdigest(),'preclaim_sha256':hashlib.sha256(preclaim.read_bytes()).hexdigest(),'rows':rows,'weighted_stock_quant_and_gemm_p50_ms':ws,'weighted_patched_quant_and_gemm_p50_ms':wp,'weighted_gain_fraction':gain,'projected_endpoint_saving_seconds_per_request':saving,'gates':{'correctness':correct,'shape_regression':shape_ok,'weighted_gain':gain>=0.10,'endpoint_projection':saving>=0.005},'stop_conditions':b['stop_conditions'],'next_action':'retain claim for endpoint-promotion handoff' if classification=='component_positive_endpoint_conditional' else 'release maintenance without endpoint replay'}
t=out/'RECOVERY5_TERMINAL.json.part'; t.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); t.replace(out/'RECOVERY5_TERMINAL.json')
PY
classification=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["classification"])' "$out/RECOVERY5_TERMINAL.json")
if [[ "$classification" == component_negative_stop ]]; then
  python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_b200_fp8_residual_hotpath --bench "$bench" --condition maintenance --contents "Recovery5 M32 component negative; fresh source and derived image retained at $remote; resident endpoint remains stopped; artifacts at $out" >"$out/release.log" 2>&1
else
  phase retain_for_endpoint_promotion
fi
