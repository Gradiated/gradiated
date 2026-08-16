#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-h200-v0513-fp8-qkv-residual-profile
input="$root/input"
artifacts="$root/global-ncu-artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
mkdir -p "$artifacts"
sudo docker rm -f global-ncu residual-profile residual-control residual-candidate >/dev/null 2>&1 || true
rm -f "$artifacts/ncu.csv" "$artifacts/global-fwd.ncu-rep" "$artifacts/exact-request.json" "$artifacts/exact-request.stderr"

terminal() {
  python3 - "$artifacts/TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
v={'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}
q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

compact() {
  set +e
  sudo docker logs global-ncu >"$artifacts/server-final.log" 2>&1 || true
  sudo docker inspect global-ncu >"$artifacts/server-inspect.json" 2>&1 || true
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/global-ncu-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/global-ncu-compact.tar.gz" >"$root/global-ncu-compact.tar.gz.sha256"
}
trap compact EXIT
trap 'test -f "$artifacts/TERMINAL.json" || terminal integration_failure "$BASH_COMMAND"' ERR
rm -f "$artifacts/TERMINAL.json"

ncu_path=$(sudo docker run --rm "$image" sh -lc 'command -v ncu || find /opt/nvidia -type f -name ncu 2>/dev/null | head -n1' | tail -n1)
test -n "$ncu_path" || { terminal ncu_unavailable ncu_binary_missing; exit 1; }
printf '%s\n' "$ncu_path" >"$artifacts/ncu-path.txt"

metrics=sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active,dram__throughput.avg.pct_of_peak_sustained_elapsed,lts__throughput.avg.pct_of_peak_sustained_elapsed,sm__warps_active.avg.pct_of_peak_sustained_active,launch__occupancy_limit_registers,launch__occupancy_limit_shared_mem,launch__registers_per_thread,launch__shared_mem_per_block_dynamic,launch__grid_size,launch__block_size
base_args=(
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint
  --served-model-name google/gemma-4-31B-it --dtype bfloat16 --quantization fp8
  --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85
  --enable-metrics --skip-server-warmup --enable-dynamic-chunking
  --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32
  --prefill-attention-backend triton --decode-attention-backend triton --page-size 1
  --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8
)

sudo docker run -d --name global-ncu --gpus all --ipc=host --network host --cap-add SYS_ADMIN \
  -v "$root:/work" -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
  -e RESIDUAL_ARM=control -e RESIDUAL_CANDIDATE_AUDIT=/work/global-ncu-artifacts/residual.jsonl \
  -e QKV_EPILOGUE_AUDIT=/work/global-ncu-artifacts/qkv.jsonl \
  -e FP8_MODULE_AUDIT=/work/global-ncu-artifacts/modules.jsonl \
  -e FP8_CONSUMER_AUDIT=/work/global-ncu-artifacts/consumers.jsonl \
  -e FP8_RUNTIME_AUDIT=/work/global-ncu-artifacts/runtime.json \
  -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
  "$image" "$ncu_path" --target-processes all --profile-from-start on \
  --kernel-name-base function --kernel-name 'regex:^_fwd_kernel$' --launch-skip 5 --launch-count 1 \
  --metrics "$metrics" --csv --log-file /work/global-ncu-artifacts/ncu.csv \
  --export /work/global-ncu-artifacts/global-fwd \
  python3 /work/input/proven_v0513_endpoint_entrypoint.py "${base_args[@]}" >"$artifacts/container-id"

ready=0
for _ in $(seq 1 180); do
  if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/models.json" 2>"$artifacts/models.stderr"; then ready=1; break; fi
  sleep 5
done
sudo docker logs global-ncu >"$artifacts/server-start.log" 2>&1 || true
test "$ready" -eq 1 || { terminal integration_failure server_not_ready; exit 1; }

python3 "$input/ncu_exact_request.py" >"$artifacts/exact-request.json" 2>"$artifacts/exact-request.stderr"
sleep 2
sudo docker stop -t 30 global-ncu >/dev/null || true
sudo docker run --rm -v "$root:/work" "$image" /usr/local/cuda/bin/ncu \
  --import /work/global-ncu-artifacts/global-fwd.ncu-rep --csv --page raw \
  >"$artifacts/ncu.csv" 2>"$artifacts/ncu-export.stderr"
test -s "$artifacts/ncu.csv" || { terminal ncu_counter_unavailable ncu_csv_missing; exit 1; }
grep -q '"_fwd_kernel"' "$artifacts/ncu.csv" || { terminal ncu_counter_unavailable exact_kernel_missing; exit 1; }
terminal ncu_complete exact_global_launch_6_captured
