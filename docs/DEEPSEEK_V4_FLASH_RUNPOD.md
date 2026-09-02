# DeepSeek V4 Flash on RunPod

This runbook records the working single-B300 setup. It also defines the next
checks for a two-B300 deployment.

## Current result

The tested Pod used RunPod Secure Cloud On-Demand with one NVIDIA B300 SXM6.
The measured device capacity was about 275 GiB of VRAM.

The model is served by vLLM 0.27.1 on port `8000`.

| Item | Measured value |
| --- | --- |
| Model directory | `/workspace/models/DeepSeek-V4-Flash-0731` |
| Model download size | About 166.9G on disk |
| Checkpoint size | About 155.43 GiB |
| Model memory after load | 146.46 GiB |
| KV-cache memory | 95.29 GiB |
| Maximum configured context | 262,144 tokens |
| Reported KV-cache capacity | 3,793,467 tokens |
| Reported 262,144-token concurrency | 14.47 requests |

The API returned `HTTP 200` from `/health`. A chat completion test returned the
exact requested text, `DeepSeek is online.`.

These values are measured on this Pod. Do not transfer them to another GPU,
driver, vLLM version, or request mix without a new test.

## Pod preparation

Use a PyTorch image with CUDA 13 support. The tested image reported Python
3.12.3, PyTorch `2.13.0+cu130`, Triton 3.7.1, and FlashInfer
`0.6.16.post3`.

Keep the model and caches on the persistent `/workspace` volume. The 30G
container disk is not large enough for the model.

Check the device and package versions:

```bash
nvidia-smi
python - <<'PY'
import torch, vllm
print("torch", torch.__version__, torch.version.cuda)
print("vllm", vllm.__version__)
print("device", torch.cuda.get_device_name(0))
print("device_count", torch.cuda.device_count())
PY
```

Download the model to the persistent volume. Keep the Hugging Face token in
the shell environment or the provider secret store. Do not put it in this
repository.

```bash
cd /workspace
mkdir -p /workspace/models/DeepSeek-V4-Flash-0731 /workspace/logs
export HF_HOME=/workspace/hf-cache
hf download deepseek-ai/DeepSeek-V4-Flash-0731 \
  --local-dir /workspace/models/DeepSeek-V4-Flash-0731 \
  --max-workers 8 \
  --format human \
  > /workspace/logs/model-download.log 2>&1 &
```

Wait for the download to finish before starting vLLM:

```bash
tail -f /workspace/logs/model-download.log
du -sh /workspace/models/DeepSeek-V4-Flash-0731
```

## B300 compatibility setup

The B300 reports compute capability `sm_103a`. The default CUDA compiler in
the image was too old, so the working process uses the pip-installed CUDA 13.3
toolkit:

```bash
export CUDA_HOME=/usr/local/lib/python3.12/dist-packages/nvidia/cu13
export CUDA_PATH="$CUDA_HOME"
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib:$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export NVCC_PREPEND_FLAGS="-DCCCL_DISABLE_CTK_COMPATIBILITY_CHECK"
```

The image needed two linker path fixes before FlashInfer and DeepGEMM could
compile. Apply them once per Pod image:

```bash
ln -sfn lib /usr/local/lib/python3.12/dist-packages/nvidia/cu13/lib64
ln -sfn libcudart.so.13 \
  /usr/local/lib/python3.12/dist-packages/nvidia/cu13/lib/libcudart.so
```

Clear failed JIT artifacts before the first clean launch after changing the
toolkit or backend:

```bash
rm -rf /root/.cache/vllm/deep_gemm \
  /root/.cache/flashinfer \
  /root/.cache/torch_extensions \
  /tmp/torchinductor_root \
  /root/.cache/torchinductor
```

## Working single-B300 launcher

The tested launcher was `/workspace/start-deepseek.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /workspace
export HF_HOME=/workspace/hf-cache
export CUDA_VISIBLE_DEVICES=0
export CUDA_HOME=/usr/local/lib/python3.12/dist-packages/nvidia/cu13
export CUDA_PATH="$CUDA_HOME"
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib:$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export NVCC_PREPEND_FLAGS="-DCCCL_DISABLE_CTK_COMPATIBILITY_CHECK"
export VLLM_USE_DEEP_GEMM=1
export VLLM_MOE_USE_DEEP_GEMM=1
exec vllm serve /workspace/models/DeepSeek-V4-Flash-0731 \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name deepseek-v4-flash \
  --tensor-parallel-size 1 \
  --pipeline-parallel-size 1 \
  --trust-remote-code \
  --kv-cache-dtype fp8 \
  --block-size 256 \
  --gpu-memory-utilization 0.92 \
  --max-model-len 262144 \
  --max-num-seqs 16 \
  --scheduling-policy priority \
  --max-num-batched-tokens 8192 \
  --tokenizer-mode deepseek_v4 \
  --tool-call-parser deepseek_v4 \
  --enable-auto-tool-choice \
  --reasoning-parser deepseek_v4 \
  --attention_config.use_fp4_indexer_cache True \
  --max-cudagraph-capture-size 128 \
  --moe-backend deep_gemm
```

Start it without tying it to the SSH terminal:

```bash
chmod +x /workspace/start-deepseek.sh
nohup /workspace/start-deepseek.sh \
  > /workspace/logs/deepseek-vllm.log 2>&1 &
```

The first start performs a long DeepGEMM warmup. The tested run loaded the
weights in about three minutes and then tuned 1,670 shapes. The API became
ready after the warmup. Do not kill the process while this step is progressing
unless the log reports an error.

Verify the service:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/v1/models
curl -fsS http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"Reply with exactly: DeepSeek is online."}],"max_tokens":32,"temperature":0}'
```

## Backend decisions and failed paths

The working configuration explicitly selects DeepGEMM for dense FP8 operations
and MXFP4 experts:

```text
VLLM_USE_DEEP_GEMM=1
VLLM_MOE_USE_DEEP_GEMM=1
--moe-backend deep_gemm
```

The following paths were tested and rejected on the B300 image:

- MTP speculative decoding failed with a model weight-name mismatch. The
  working launcher leaves MTP disabled.
- Cutlass FP8 failed in the B300 scaled-matrix-multiply dispatch.
- Triton failed to canonicalise the B300 `float8_e8m0fnu` dtype.
- Humming failed during NVRTC compilation.
- Automatic FlashInfer TRTLLM MXFP4 selected a very large cubin download and
  did not complete in a useful time. Explicit DeepGEMM avoids that download.

Keep the old failures in the log only as diagnosis. A new run should use the
clean cache procedure above and the working launcher.

## Two-B300 deployment result

The tested two-GPU Pod uses the same image family and a persistent
`/workspace` volume. Both devices are NVIDIA B300 SXM6 GPUs with 275,040 MiB
of VRAM each and driver `580.159.03`.

The GPUs are directly connected. `nvidia-smi topo -m` reports `NV18` between
GPU 0 and GPU 1. `nvidia-smi nvlink --status` reports 18 active links per GPU,
at 53.125 GB/s per link.

The process uses `/workspace/start-deepseek-2xb300.sh` and these settings:

Confirm both devices before a future restart:

```bash
nvidia-smi -L
python - <<'PY'
import torch
print(torch.cuda.device_count())
for index in range(torch.cuda.device_count()):
    print(index, torch.cuda.get_device_name(index))
PY
```

Start with tensor parallelism. Change only these launcher settings for the
first two-GPU test:

```bash
export CUDA_VISIBLE_DEVICES=0,1
```

```text
--tensor-parallel-size 2
--pipeline-parallel-size 1
```

The measured two-GPU result is:

| Item | Measured value |
| --- | --- |
| Model memory per GPU | 74.39 GiB |
| Model load time | 51.85 seconds |
| GPU KV-cache capacity | 6,655,824 tokens |
| Reported 262,144-token concurrency | 25.39 requests |
| API warmup completion | 11:40:44 UTC |
| Completion test | Passed |

The API returned `HTTP 200` from `/health`. The completion returned the exact
requested text, `DeepSeek is online.`. The response fingerprint was
`vllm-0.27.1-tp2-572cb1ad`.

The service uses the same DeepGEMM, FP8 KV-cache, tokenizer, parser, and
context settings as the single-GPU baseline. The API became ready after the
one-time 1,664-shape DeepGEMM warmup.

The two-GPU acceptance test is now complete:

1. Both B300 devices are visible to PyTorch and NCCL. **Passed.**
2. The model loads without a rank or collective error. **Passed.**
3. `/health`, `/v1/models`, and a deterministic completion all pass.
   **Passed.**
4. Startup, model memory, and KV-cache capacity are recorded above.
5. Prompt throughput, decode throughput, time to first token, and maximum
   stable concurrency still need a representative load test.

The next safe action is a matched single-GPU versus two-GPU load test. Record
prompt and output token counts, time to first token, inter-token latency,
throughput, queue time, GPU utilization, NVLink traffic, and tail latency.
Do not claim that two GPUs double throughput until this test is complete.

### Quick same-session comparison

This descriptive comparison used the two running Pods, the same vLLM version,
the same 23-token prompt, `max_tokens=128`, temperature `0`, loopback HTTP,
one warmup request, and five sequential samples or three concurrent rounds.
It is not a production SLO benchmark.

| Workload | 1×B300 | 2×B300 | Change |
| --- | ---: | ---: | ---: |
| Sequential median decode | 131.93 tok/s | 133.73 tok/s | +1.4% |
| Four-way median aggregate | 414.80 tok/s | 451.75 tok/s | +8.9% |

An eight-way run reached 614.84 tok/s on the single B300 and 704.44 tok/s on
the two-B300 Pod in the final measured round, about +14.6%. Earlier rounds
triggered additional CUDA graph work and were much slower. Repeat this test
with the production prompt and output distribution before making a capacity or
cost claim.

### Concurrency ramp

The capacity ramp used the same short prompt and 128-token output limit. It
sent three rounds at each level from 1 through 24, then two rounds at 32, 48,
and 64. Every request returned successfully on both Pods.

| Submitted at once | 1×B300 tok/s | 1× p95 (s) | 2×B300 tok/s | 2× p95 (s) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 132 | 0.97 | 133 | 0.96 |
| 2 | 237 | 1.07 | 251 | 1.02 |
| 4 | 422 | 1.21 | 455 | 1.12 |
| 8 | 639 | 1.60 | 717 | 1.42 |
| 12 | 722 | 2.13 | 871 | 1.75 |
| 16 | 1,000 | 2.04 | 1,164 | 1.75 |
| 20 | 793 | 3.22 | 932 | 2.72 |
| 24 | 852 | 3.60 | 966 | 3.14 |
| 32 | 848 | 4.98 | 928 | 4.89 |
| 48 | 661 | 12.74 | 761 | 12.18 |
| 64 | 1,013 | 8.06 | 1,242 | 6.49 |

Additional one-round probes at 96 and 128 submitted requests also completed
with zero errors. They showed 31.15s and 16.15s wall time on 1×B300, and
30.39s and 13.06s on 2×B300. These batches triggered shape-dependent CUDA
graph work, so their order was not monotonic.

The configured `--max-num-seqs 16` is the active execution limit. Requests
above 16 can be accepted and queued, but they are not 20, 48, or 128 active
model sequences. For this short-request test, 24 submitted requests remained
below about 4s p95 on both Pods. Use the production prompt and output mix to
choose an SLO-based limit. Long-context capacity is governed by the KV-cache
figures above, not this short-request ramp.

## Operations and limits

- The current endpoint is local to the Pod on port `8000`. It is not an
  authenticated public service.
- Use an SSH tunnel for testing. Add authentication and a reverse proxy before
  exposing the endpoint to users.
- `nohup` protects the process from an SSH disconnect. It does not restart the
  service after a Pod restart.
- Keep `/workspace/models`, `/workspace/hf-cache`, and `/workspace/logs` on the
  persistent volume.
- The API accepts OpenAI-compatible chat-completion requests with the model
  name `deepseek-v4-flash`.
