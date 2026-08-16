#!/usr/bin/env bash
set -Eeuo pipefail
root=/home/glmrunner/gemma4-h200-v0513-fp8-qkv-residual-profile
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
metrics=sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active,dram__throughput.avg.pct_of_peak_sustained_elapsed,lts__throughput.avg.pct_of_peak_sustained_elapsed,sm__warps_active.avg.pct_of_peak_sustained_active,launch__occupancy_limit_registers,launch__occupancy_limit_shared_mem,launch__registers_per_thread,launch__shared_mem_per_block_dynamic,launch__grid_size,launch__block_size
sudo docker rm -f global-ncu >/dev/null 2>&1 || true
sudo docker run -d --name global-ncu --gpus all --ipc=host --network host --cap-add SYS_ADMIN \
  -v "$root:/work" -e PYTHONPATH=/work/input:/sgl-workspace/sglang/python \
  -e RESIDUAL_ARM=control -e RESIDUAL_CANDIDATE_AUDIT=/work/global-ncu-artifacts/residual.jsonl \
  -e QKV_EPILOGUE_AUDIT=/work/global-ncu-artifacts/qkv.jsonl \
  -e FP8_MODULE_AUDIT=/work/global-ncu-artifacts/modules.jsonl \
  -e FP8_CONSUMER_AUDIT=/work/global-ncu-artifacts/consumers.jsonl \
  -e FP8_RUNTIME_AUDIT=/work/global-ncu-artifacts/runtime.json \
  -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
  "$image" /usr/local/cuda/bin/ncu --target-processes all --profile-from-start off \
  --kernel-name-base function --kernel-name regex:_fwd_kernel --launch-skip 5 --launch-count 1 \
  --metrics "$metrics" --csv --log-file /work/global-ncu-artifacts/ncu.csv \
  --export /work/global-ncu-artifacts/global-fwd \
  python3 /work/input/proven_v0513_endpoint_entrypoint.py \
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint \
  --served-model-name google/gemma-4-31B-it --dtype bfloat16 --quantization fp8 \
  --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000 \
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 \
  --enable-metrics --skip-server-warmup --enable-dynamic-chunking \
  --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 \
  --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 \
  --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8
