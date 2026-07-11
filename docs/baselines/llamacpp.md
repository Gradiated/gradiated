# llama.cpp baseline

Baseline throughput numbers for llama.cpp on this machine, for comparison against
sartor and vLLM-CPU.

## Environment

- **Hardware:** Apple M4 Pro, 14-core CPU (10P + 4E), 48 GB unified memory
- **OS:** macOS 15.6.1
- **llama.cpp:** `vendor/llama.cpp` @ `c92e806` (2026-07-11), shallow clone
- **Toolchain:** cmake 4.4.0 + ninja from `/Users/js/dev/vllm-study/.venv/bin` (pip-installed; neither is on the system PATH)
- **Model:** SmolLM2-135M-Instruct, converted to GGUF f16 (256.63 MiB, 134.52 M params)

## Build

```sh
export PATH="/Users/js/dev/vllm-study/.venv/bin:$PATH"   # pip cmake + ninja
cd vendor/llama.cpp
cmake -B build -G Ninja -DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --target llama-server llama-bench llama-cli llama-batched-bench -j 14
```

Binaries land in `vendor/llama.cpp/build/bin/`. Build succeeded cleanly (323 targets).
Note the Metal build also links Accelerate/BLAS, so llama-bench reports the backend
as `MTL,BLAS` even for CPU-only (`-ngl 0`) runs.

## GGUF conversion

`gguf` was missing from the venv (`uv pip install --python /Users/js/dev/vllm-study/.venv/bin/python gguf`); torch, transformers and mistral-common were already present.

```sh
cd vendor/llama.cpp
/Users/js/dev/vllm-study/.venv/bin/python convert_hf_to_gguf.py \
  /Users/js/dev/sartor/models/smollm2-135m-instruct \
  --outfile /Users/js/dev/sartor/models/gguf/smollm2-135m-instruct-f16.gguf --outtype f16

/Users/js/dev/vllm-study/.venv/bin/python convert_hf_to_gguf.py \
  /Users/js/dev/sartor/models/qwen2.5-0.5b-instruct \
  --outfile /Users/js/dev/sartor/models/gguf/qwen2.5-0.5b-instruct-f16.gguf --outtype f16
```

Both converted successfully:

| Output | Size |
|---|---|
| `models/gguf/smollm2-135m-instruct-f16.gguf` | 269 MB |
| `models/gguf/qwen2.5-0.5b-instruct-f16.gguf` | 988 MB |

## Benchmarks (SmolLM2-135M f16)

### Single-stream: llama-bench

```sh
build/bin/llama-bench -m models/gguf/smollm2-135m-instruct-f16.gguf -p 512,2048 -n 128 -o md          # Metal
build/bin/llama-bench -m models/gguf/smollm2-135m-instruct-f16.gguf -ngl 0 -p 512,2048 -n 128 -o md  # CPU-only
```

| Config | Test | tok/s |
|---|---|---:|
| Metal (all layers) | pp512 | 20,823 ± 806 |
| Metal (all layers) | pp2048 | 17,211 ± 179 |
| Metal (all layers) | tg128 | 376.6 ± 5.2 |
| CPU-only (`-ngl 0`, 10 threads) | pp512 | 2,925 ± 81 |
| CPU-only (`-ngl 0`, 10 threads) | pp2048 | 1,882 ± 55 |
| CPU-only (`-ngl 0`, 10 threads) | tg128 | 464.3 ± 37.0 |

### Batched decode: llama-batched-bench

Each row: B parallel sequences, 128 prompt tokens + 128 generated tokens each.
S_TG is aggregate decode throughput across all sequences — the saturation number.

```sh
build/bin/llama-batched-bench -m models/gguf/smollm2-135m-instruct-f16.gguf \
  -c 16384 -b 2048 -ub 512 -npp 128 -ntg 128 -npl 1,2,4,8,16,32,64
# npl 128 rerun with -c 32768; CPU runs add -ngl 0
```

**Metal:**

| B (parallel) | S_PP tok/s | S_TG tok/s (decode) | S total tok/s |
|---:|---:|---:|---:|
| 1 | 10,897 | 371 | 718 |
| 2 | 9,943 | 656 | 1,231 |
| 4 | 14,657 | 925 | 1,740 |
| 8 | 21,292 | 1,156 | 2,193 |
| 16 | 22,620 | 2,505 | 4,510 |
| 32 | 22,871 | 4,630 | 7,702 |
| 64 | 22,957 | 7,186 | 10,945 |
| 128 | 22,933 | **8,530** | 12,435 |

**CPU-only (`-ngl 0`):**

| B (parallel) | S_PP tok/s | S_TG tok/s (decode) | S total tok/s |
|---:|---:|---:|---:|
| 1 | 1,842 | 430 | 697 |
| 2 | 3,036 | 637 | 1,052 |
| 4 | 4,635 | 960 | 1,590 |
| 8 | 4,627 | 1,324 | 2,059 |
| 16 | 4,765 | **1,608** | 2,404 |
| 32 | 4,754 | 551 | 987 |
| 64 | 4,273 | 928 | 1,524 |

### Headline numbers

| Metric | Metal | CPU-only |
|---|---:|---:|
| Prefill (pp512, single stream) | 20,823 tok/s | 2,925 tok/s |
| Decode (single stream, tg128) | 377 tok/s | 464 tok/s |
| Batched decode at saturation | ~8,530 tok/s (B=128) | ~1,608 tok/s (B=16) |

## Server smoke test

```sh
build/bin/llama-server -m models/gguf/smollm2-135m-instruct-f16.gguf --port 8089
curl http://127.0.0.1:8089/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Write one sentence about the ocean."}],"max_tokens":100}'
```

Server started (default 4 slots, 8192 ctx/slot, Metal) and returned a valid completion.
Response `timings`: prompt 308.2 tok/s (37 tokens — overhead-dominated at this size),
generation **369.6 tok/s** (36 tokens), consistent with the tg128 bench number.

## Observations

- **CPU beats Metal for single-stream decode on a 135M model** (464 vs 377 tok/s).
  At this size, decode is latency-bound and per-step Metal dispatch overhead outweighs
  the GPU's bandwidth advantage. Metal only pulls ahead once batching amortizes the
  dispatch cost (crossover around B=8-16).
- **Metal batched decode was still climbing at B=64** (7,186 tok/s), so B=128 was added:
  8,530 tok/s, still rising slowly — 8.5k tok/s is a mild underestimate of true saturation.
- **CPU batched decode degrades sharply past B=16**: 1,608 tok/s at B=16 collapses to
  551 at B=32 (partially recovering to 928 at B=64). Likely attention-over-KV cost growing
  with total KV tokens plus scheduling effects on the 10P+4E core split. Treat B=16 as the
  CPU saturation point.
- Metal prefill saturates around ~23k tok/s regardless of batch; CPU prefill around ~4.7k
  tok/s (batched) but drops to 1,882 tok/s at a single long pp2048.
