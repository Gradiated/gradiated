# vLLM CPU baseline (macOS arm64)

Baseline throughput for vLLM's CPU backend on this machine, for comparison against
barge and llama.cpp. vLLM CPU on macOS is **experimental** — it needed two local
patches to produce a working build (see below).

## Environment

- **Hardware:** Apple M4 Pro, 14-core CPU (10P + 4E), 48 GB unified memory
- **OS:** macOS 15.6.1, Apple Clang
- **vLLM:** `/Users/js/dev/vllm-study` @ `bec0a4e` (2026-07-11) + 2 local patches
- **Python:** 3.12.12 (`.venv`), torch 2.11.0 (CPU)
- **Model:** SmolLM2-135M-Instruct (safetensors, bf16 at runtime)

## Build fixes (local-only patches, not upstreamed)

vLLM has no official macOS CPU support tier; the build "succeeds" but produces a
broken extension without these:

1. **`csrc/cpu/cpu_attn_vec.hpp`** — Apple Clang rejects capturing structured
   bindings in OpenMP-adjacent lambdas ("capturing a structured binding is not yet
   supported in OpenMP"). Unpacked `auto [a, b] = ...` into `.first`/`.second`.

2. **`cmake/cpu_extension.cmake`** — root cause of the
   `Failed to import from vllm._C: ... symbol not found in flat namespace
   '__Z13cpu_fused_moe...'` warning (and the later EngineCore crash).
   `csrc/cpu/cpu_fused_moe.cpp` was only compiled when
   `ASIMD_FOUND AND NOT APPLE_SILICON_FOUND` (or x86 AVX512), but
   `csrc/cpu/torch_bindings.cpp` registers `cpu_fused_moe`/`prepack_moe_weight`
   whenever `ARM_BF16_SUPPORT` is defined — which it is on M-series (FEAT_BF16).
   macOS links Python extensions with `-undefined dynamic_lookup`, so the missing
   object never failed the link; it only failed at `dlopen`. Fix: also add
   `cpu_fused_moe.cpp` to the source list when
   `APPLE_SILICON_FOUND AND ARM_BF16_FOUND`. The file compiles cleanly under
   Apple Clang (`-Xpreprocessor -fopenmp`), so the real MoE kernel is built —
   no stub needed.

```sh
cd /Users/js/dev/vllm-study && . .venv/bin/activate
VLLM_TARGET_DEVICE=cpu MAX_JOBS=10 uv pip install -e . --no-build-isolation
python -c "from vllm import _C"   # must import with no 'Failed to import' warning
```

## Benchmark repro

Full raw output: `experiments/results/vllm-cpu-64-full.log`.

```sh
cd /Users/js/dev/vllm-study && . .venv/bin/activate
VLLM_CPU_KVCACHE_SPACE=2 vllm bench throughput \
  --model /Users/js/dev/sartor/models/smollm2-135m-instruct \
  --dataset-name random --random-input-len 128 --random-output-len 128 \
  --num-prompts 64 --max-model-len 2048 --dtype bfloat16
# and again with --num-prompts 128
```

Two footguns hit along the way (both documented in the raw log):

- **`VLLM_CPU_KVCACHE_SPACE=8` fails on macOS.** vLLM validates the request
  against psutil "available" memory, and macOS reports only ~3 GiB available on a
  48 GB machine (file cache counts against it). 2 GiB is ample for this model
  (93,184 KV tokens, 45.5x concurrency at ctx 2048).
- **`--input-len` is silently ignored for the random dataset.**
  `--random-input-len` defaults to 1024 and takes precedence, so
  `--input-len 128` actually ran 64 x 1024/128 (verified: 65,536 prompt tokens).
  Use `--random-input-len`/`--random-output-len` explicitly.

Thread binding: `VLLM_CPU_OMP_THREADS_BIND` defaults to `auto` (13 worker cores,
1 reserved). No OOM or thread-thrashing observed; both runs were stable.

## Results (SmolLM2-135M, bf16, 128 in / 128 out per request)

| num-prompts | req/s | total tok/s | output tok/s |
|---:|---:|---:|---:|
| 64 | 1.93 | 492.8 | 246.4 |
| 128 | 2.19 | 561.9 | 281.0 |

Engine-side steady state at 64-128 concurrent: prefill ~680 tok/s, decode
~340-450 tok/s aggregate. The accidental 64 x 1024/128 run is a bonus
prefill-heavy datapoint: 0.43 req/s, 490.9 total tok/s, 54.6 output tok/s.

## Comparison (same 64 x 128/128 workload)

| Engine | Device / dtype | req/s | total tok/s | output tok/s | vs vLLM out |
|---|---|---:|---:|---:|---:|
| vLLM CPU | CPU bf16 | 1.93 | 493 | 246 | 1.0x |
| barge | CPU f32 | 4.10 | 1,050 | 525 | 2.1x |
| barge | Metal f16 | 7.37 | 1,888 | 944 | 3.8x |
| llama.cpp (B=64) | CPU f16 | — | 1,524 | 928 (decode) | 3.8x |

Reference points off this exact workload: barge Metal reaches 977 output tok/s at
256 requests; llama.cpp CPU saturates at 1,608 decode tok/s at B=16 (6.5x vLLM).
llama.cpp numbers are from `llama-batched-bench` (S_TG = aggregate decode), which
excludes serving overhead entirely — see `docs/baselines/llamacpp.md`.

## Caveats

- **vLLM CPU on macOS is experimental.** No Triton, so the V1 model runner is
  used; inductor compilation partially disabled; sgl-kernels, oneDNN, and shm
  paths are all off on Apple Silicon. This is not the configuration vLLM CPU is
  tuned for (that's x86 AVX512 Linux).
- **dtypes differ**: vLLM ran bf16 (native on M4), barge CPU is f32, barge Metal
  and llama.cpp are f16. bf16 should not be a handicap on this hardware.
- **Serving overhead included**: vLLM numbers are end-to-end through the Python
  engine + multiprocess executor (EngineCore in a separate process, msgpack IPC);
  llama.cpp's batched-bench measures kernels + scheduler only. barge numbers are
  end-to-end through its engine loop, closer to an apples-to-apples with vLLM.
- At a 135M-parameter model size, per-step framework overhead dominates: vLLM's
  ~246-281 output tok/s vs an engine-side decode rate of ~340-450 tok/s shows a
  meaningful scheduling/IPC tax that a larger model would amortize.
