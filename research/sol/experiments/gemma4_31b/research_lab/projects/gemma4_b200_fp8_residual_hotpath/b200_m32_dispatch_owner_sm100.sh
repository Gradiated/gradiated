#!/usr/bin/env bash
set -Eeuo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_fp8_residual_hotpath
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
bench=${B200_M32_BENCH:?}; out=${B200_M32_OUTPUT:?}; release_by=${B200_M32_RELEASE_BY_UTC:?}
host=${B200_M32_HOST:?}; user=${B200_M32_USER:?}; key=${B200_M32_KEY:?}; known=${B200_M32_KNOWN_HOSTS:?}
preclaim=$project/PRECLAIM_SM100_TERMINAL.json; runner=$project/b200_m32_dispatch_component.py; patch=$project/M32_DISPATCH.patch
remote=/home/$user/b200-m32-dispatch-20260728t1623z; source_remote=$remote/vllm-recovery5
build_remote=$remote/sm100-build-20260728t1719z-repair1; install_remote=$remote/sm100-install-20260728t1719z-repair1; output_remote=$remote/output-sm100-20260728t1719z-repair1
image=b200-m32-recovery5:20260728t1623z
mkdir -p "$out"
phase(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$out/OWNER_PROGRESS.log"; }
heartbeat(){ while sleep 45; do python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_b200_fp8_residual_hotpath --bench "$bench" >>"$out/heartbeat.log" 2>&1 || true; done; }
heartbeat & heartbeat_pid=$!; trap 'kill "$heartbeat_pid" 2>/dev/null || true' EXIT
ssh_cmd=(ssh -n -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "$user@$host")
scp_cmd=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known")
incomplete(){ stage=$1; code=$2; python3 - "$out/INCOMPLETE_TERMINAL.json" "$stage" "$code" <<'PY'
import json,os,pathlib,sys,tempfile
p=pathlib.Path(sys.argv[1]); v={'schema_version':1,'classification':'component_incomplete_pre_science_or_partial','stage':sys.argv[2],'exit_code':int(sys.argv[3]),'science_consumed':False,'candidate_science_started':False}
fd,t=tempfile.mkstemp(prefix='.INCOMPLETE.',dir=p.parent); os.close(fd); pathlib.Path(t).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(t,p)
PY
python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_b200_fp8_residual_hotpath --bench "$bench" --condition maintenance --contents "{\"state\":\"sm100_continuation_incomplete\",\"stage\":\"$stage\",\"remote\":\"$remote\",\"artifacts\":\"$out\"}" >"$out/release.log" 2>&1 || true; exit "$code"; }
phase binding_validation
python3 - "$preclaim" "$runner" "$patch" "$0" <<'PY' || incomplete binding_validation 2
import hashlib,json,pathlib,sys
b,r,p,o=map(pathlib.Path,sys.argv[1:]); x=json.loads(b.read_text()); sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
assert x['runner_sha256']==sha(r) and x['patch_sha256']==sha(p) and x['owner_sha256']==sha(o) and x['bench_gate']['claim_allowed'] and x['build']['cuda_architectures']==['sm_100']
PY
phase claim_reconcile
row=$(python3 -m grad_research.gpu_pool --lab "$lab" show --bench "$bench") || incomplete claim_reconcile 3
python3 - "$row" "$bench" <<'PY' || incomplete claim_identity 3
import json,sys
r=json.loads(sys.argv[1]); assert r['id']==sys.argv[2] and (r.get('claim') or {}).get('project')=='gemma4_b200_fp8_residual_hotpath'
PY
phase predecessor_fence
python3 - <<'PY' >"$out/predecessor-fence.json" || incomplete predecessor_fence 4
import json,os,pathlib
n=('3337978','3329225','b200_m32_dispatch_owner_recovery5.sh','b200_m32_dispatch_owner.sh'); m=[]
for p in pathlib.Path('/proc').iterdir():
 if p.name.isdigit() and int(p.name)!=os.getpid():
  try: c=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
  except OSError: continue
  if any(x in c for x in n): m.append({'pid':int(p.name),'cmd':c})
print(json.dumps({'matches':m},sort_keys=True)); raise SystemExit(bool(m))
PY
phase retained_state
"${ssh_cmd[@]}" "test -d '$source_remote/.deps/cutlass-src' && test -d '$source_remote/.deps/vllm-flash-attn-src' && sha256sum '$source_remote/csrc/quantization/w8a8/cutlass/c3x/scaled_mm_sm100_fp8_dispatch.cuh'" >"$out/source-state.stdout" 2>"$out/source-state.stderr" || incomplete retained_state 5
grep -F '2662238503d1a233fe7c6b85c209076ef5657c789b2ae21b52b708aed9f15cef' "$out/source-state.stdout" >/dev/null || incomplete source_hash 5
"${scp_cmd[@]}" "$runner" "$patch" "$preclaim" "$user@$host:$remote/" || incomplete packet_stage 6
phase sm100_minimum_build
"${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --ipc=host --network=host --user 0:0 --entrypoint bash -e TORCH_CUDA_ARCH_LIST=10.0 -e CUDA_HOME=/usr/local/cuda -e CUDA_PATH=/usr/local/cuda -e LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/cuda/targets/x86_64-linux/lib -v /usr/local/cuda:/usr/local/cuda:ro -v '$source_remote:/work/vllm:rw' -v '$build_remote:/work/build' -v '$install_remote:/work/install' '$image' -lc 'set -Eeuo pipefail; find /work/build -mindepth 1 -delete 2>/dev/null || true; find /work/install -mindepth 1 -delete 2>/dev/null || true; mkdir -p /work/build /work/install; cmake -S /work/vllm -B /work/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DVLLM_TARGET_DEVICE=cuda -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc -DCMAKE_CUDA_FLAGS=\"-gencode arch=compute_100,code=sm_100\" -DCMAKE_CUDA_ARCHITECTURES=100 -DFETCHCONTENT_BASE_DIR=/work/vllm/.deps -DVLLM_CUTLASS_SRC_DIR=/work/vllm/.deps/cutlass-src -DVLLM_FLASH_ATTN_SRC_DIR=/work/vllm/.deps/vllm-flash-attn-src -DCUDA_nvrtc_LIBRARY=/usr/local/cuda/lib64/libnvrtc.so -DCMAKE_INSTALL_PREFIX=/work/install; cmake --build /work/build --target _C --parallel 20 --verbose; cmake --install /work/build --prefix /work/install --component _C; find /work/install -name \"_C*.so\" -type f -exec sha256sum {} \\;'" >"$out/sm100-build.stdout" 2>"$out/sm100-build.stderr" || incomplete sm100_minimum_build 7
phase compiler_audit
grep -E -- '-gencode(=| )arch=compute_100,code=sm_100' "$out/sm100-build.stdout" >/dev/null || incomplete compiler_audit_missing 8
if grep -E -- '-gencode(=| )arch=(compute_)?(7|8|9|1[12])' "$out/sm100-build.stdout" >/dev/null; then incomplete compiler_arch_fanout 8; fi
phase sm100_install_rebind
"${ssh_cmd[@]}" "set -Eeuo pipefail; ext=\$(find '$install_remote' -name '_C*.so' -type f | head -1); test -n \"\$ext\"; if test -f '$source_remote/vllm/_C.abi3.so'; then mv '$source_remote/vllm/_C.abi3.so' '$source_remote/vllm/_C.broad_invalid_pre_science.abi3.so'; fi; cp \"\$ext\" '$source_remote/vllm/_C.abi3.so'; sha256sum '$source_remote/vllm/_C.abi3.so' '$source_remote/vllm/_C.broad_invalid_pre_science.abi3.so' 2>/dev/null || true" >"$out/extension-rebind.stdout" 2>"$out/extension-rebind.stderr" || incomplete sm100_install_rebind 9
phase stock_arm
"${ssh_cmd[@]}" "rm -rf '$output_remote/stock' '$output_remote/patched'; mkdir -p '$output_remote/stock' '$output_remote/patched'; sudo -n docker run --rm --gpus all --ipc=host --network=host --user 0:0 --entrypoint python3 -v '$remote/b200_m32_dispatch_component.py:/work/runner.py:ro' -v '$output_remote/stock:/work/output' 'docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79' /work/runner.py --arm stock --output /work/output" >"$out/stock.stdout" 2>"$out/stock.stderr" || incomplete stock_arm 10
phase patched_arm
"${ssh_cmd[@]}" "sudo -n docker run --rm --gpus all --ipc=host --network=host --user 0:0 --entrypoint python3 -e PYTHONPATH=/work/vllm -v '$remote/b200_m32_dispatch_component.py:/work/runner.py:ro' -v '$source_remote:/work/vllm:ro' -v '$output_remote/patched:/work/output' '$image' /work/runner.py --arm patched --output /work/output" >"$out/patched.stdout" 2>"$out/patched.stderr" || incomplete patched_arm 11
phase retrieve
mkdir -p "$out/stock" "$out/patched"
"${scp_cmd[@]}" -r "$user@$host:$output_remote/stock/." "$out/stock/" || incomplete retrieve_stock 12
"${scp_cmd[@]}" -r "$user@$host:$output_remote/patched/." "$out/patched/" || incomplete retrieve_patched 13
phase component_finalize
python3 "$project/sm100_component_finalize.py" "$out" "$preclaim" || incomplete component_finalize 14
classification=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["classification"])' "$out/SM100_TERMINAL.json")
if [[ "$classification" == component_negative_stop ]]; then python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_b200_fp8_residual_hotpath --bench "$bench" --condition maintenance --contents "SM100 component negative; retained image/source/dependencies at $remote; artifacts at $out" >"$out/release.log" 2>&1; else phase retain_for_promotion; fi
