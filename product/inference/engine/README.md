# Gradiated native inference engine

This directory owns the native C++/CUDA inference path for the pinned `google/gemma-4-31B-it`
release on one NVIDIA H200. [DESIGN.md](DESIGN.md) is the performance contract and holds the
measured results.

## Runtime interface

`gradiated-engine-runtime MODEL_DIRECTORY` serves token IDs, not text. The gateway does the
tokenization and the OpenAI-compatible translation.

| Route                        | Purpose                                                                                                                            |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `POST /v1/token-completions` | Greedy completion. The body has `input_ids`, and optionally `max_tokens` (default 128), `stop_token_ids`, `stream` and `priority`. |
| `GET /health`                | Returns `ready` after the weights load and the warmup completes.                                                                   |
| `GET /metrics`               | Prometheus counters and gauges named `gradiated_native_*`.                                                                         |

The runtime stops on the model EOS ids from `config.json` unless `GRADIATED_IGNORE_MODEL_EOS` is
set. Every token ID in `input_ids` and `stop_token_ids` must be less than the vocabulary size. The prompt must
be shorter than the 8,192-token context, and `max_tokens` must fit in the remaining context.

A stream sends one event per token with cumulative usage, then a terminal event with
`finish_reason`, then `data: [DONE]`. A closed socket cancels the request and frees its slot.

| Status | Body `error`        | Cause                                                                                          |
| ------ | ------------------- | ---------------------------------------------------------------------------------------------- |
| 400    | `invalid_request`   | The body is not valid. `message` gives the reason.                                             |
| 401    | `unauthorized`      | The bearer token does not match the configured API key.                                        |
| 404    | `not_found`         | The route does not exist.                                                                      |
| 503    | `inference_failure` | Inference failed before the response started. The body has no `message`; stderr has the cause. |

When inference fails after a stream starts, the runtime closes the stream without a terminal event
and without `data: [DONE]`. The gateway uses the missing terminal event to detect the failure.
Each failed inference writes one stderr line with its request id, the failure site and the cause.
`gradiated_native_failures_total` counts failed inferences. `gradiated_native_invalid_requests_total`
counts 400 responses.

## Configuration

The runtime reads these variables at startup. When a value is invalid, it names the variable and
exits. An empty value counts as unset. `GRADIATED_ASSISTANT_FP8_MODE` is the exception: the CUDA
library also reads it, so the runtime rejects an empty value.

| Variable                                        | Default                   | Accepted values                                                                                                 |
| ----------------------------------------------- | ------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `GRADIATED_RUNTIME_HOST`                        | `0.0.0.0`                 | Bind address                                                                                                    |
| `GRADIATED_RUNTIME_PORT`                        | `30000`                   | 1 to 65535                                                                                                      |
| `GRADIATED_RUNTIME_API_KEY`                     | `DESMOND_RUNTIME_API_KEY` | Bearer token. When both are empty, the runtime does not check authorization.                                    |
| `DESMOND_TRACE_PATH`                            | unset                     | Desmond shared trace ring. The runtime logs a ring it cannot open and continues.                                |
| `GRADIATED_FP8_DECODE`                          | `off`                     | `off` or `tensor`                                                                                               |
| `GRADIATED_FP8_WEIGHT_SCALE_MULTIPLIER`         | `1.0`                     | (0, 1]. Read only with FP8 decode. Research only.                                                               |
| `GRADIATED_INT4_LM_HEAD_ORACLE`                 | unset                     | `0` or `1`. Read only with FP8 decode. Research only.                                                           |
| `GRADIATED_INT4_LM_HEAD_ORACLE_BLOCK`           | `128`                     | 32, 64, 128 or 256                                                                                              |
| `GRADIATED_ASSISTANT_MODEL_PATH`                | unset                     | Gemma 4 assistant directory. Requires FP8 decode and a target with hidden size 5376 and vocabulary size 262144. |
| `GRADIATED_ASSISTANT_FP8_MODE`                  | `off`                     | `off`, `lm_head` or `all`                                                                                       |
| `GRADIATED_PREFILL_QUANTUM_TOKENS`              | `1024`                    | 1 to 8192                                                                                                       |
| `GRADIATED_IDLE_PREFILL_QUANTUM_TOKENS`         | `1024`                    | 1 to 8192                                                                                                       |
| `GRADIATED_SHORT_PREFILL_BATCH_WINDOW_US`       | `10000`                   | 0 to 20000. Zero disables the wait.                                                                             |
| `GRADIATED_INTERLEAVED_SUFFIX_LAYER_QUANTUM`    | `10`                      | 0 to the layer count. Zero runs each suffix cohort to completion.                                               |
| `GRADIATED_INTERLEAVED_SUFFIX_LAYER_MIN_DECODE` | `14`                      | 1 to 24                                                                                                         |
| `GRADIATED_SPECULATIVE_DEPTH`                   | `4`                       | 1 to 8                                                                                                          |
| `GRADIATED_SPECULATIVE_MIN_BATCH`               | `8`                       | 1 to 24                                                                                                         |
| `GRADIATED_CACHE_AFFINITY_MAX_BYPASSES`         | `4`                       | 0 to 1024. Zero disables cache-affinity admission.                                                              |
| `GRADIATED_IDLE_CACHE_RESERVE_SLOTS`            | `0`                       | 0 to 23                                                                                                         |
| `GRADIATED_IGNORE_MODEL_EOS`                    | `false`                   | `0`, `1`, `false` or `true`. Research only.                                                                     |

The production image sets `GRADIATED_FP8_DECODE=tensor`, `GRADIATED_FP8_SUFFIX_MAX_TOKENS=4096`
and `GRADIATED_CACHE_AFFINITY_MAX_BYPASSES=4`. Leave every research-only switch unset in
production.

## Research switches read by the CUDA library

The CUDA library reads more switches directly. They make experiments reproducible. Unless this
section names a production value, leave them unset.

- `GRADIATED_FP8_SUFFIX_MAX_TOKENS` sets the largest packed cached-suffix cohort that uses FP8
  projections. The default 0 keeps suffix prefill in BF16. Full cache-miss prefill is always BF16.
- `GRADIATED_DISABLE_QKV_NORM_CARRIED_AMAX`, `GRADIATED_DISABLE_O_TRANSPOSE_CARRIED_AMAX`,
  `GRADIATED_DISABLE_GATE_UP_NORM_CARRIED_AMAX` and `GRADIATED_DISABLE_GELU_CARRIED_AMAX` roll
  back the producer-carried FP8 maxima one at a time.
- `GRADIATED_FP8_GLOBAL_K`, `GRADIATED_FP8_GLOBAL_KV` and `GRADIATED_FP8_GLOBAL_K_LAYERS` select
  the E4M3 global cache. It failed the completion-quality gate.
- `GRADIATED_INT8_GLOBAL_KV_ORACLE` with its `_MODE`, `_BLOCK` and `_LAYERS` variables round-trips
  global K/V through INT8 to measure quality. It saves no memory or time.
- `GRADIATED_INT8_GLOBAL_K`, `GRADIATED_INT8_GLOBAL_K_LAYERS` and `GRADIATED_INT8_GLOBAL_KV`
  select the INT8 global cache. The tested formats failed the quality or economics gates.
- `GRADIATED_INT4_LM_HEAD`, `GRADIATED_INT4_LM_HEAD_SEGMENT` and `GRADIATED_INT4_BF16_LM_HEAD`
  select the W4A8 and W4A16 LM heads. They did not improve session-live economics.
- `GRADIATED_FP8_COOPERATIVE_MAX_ELEMENTS` sets the largest activation for the cooperative FP8
  quantizer. The default is 2,097,152 elements.
- `GRADIATED_FP8_BF16_LAYERS`, `GRADIATED_FP8_BF16_ATTENTION_LAYERS`, `GRADIATED_FP8_BF16_QKV_LAYERS`,
  `GRADIATED_FP8_BF16_O_LAYERS`, `GRADIATED_FP8_BF16_MLP_LAYERS`, `GRADIATED_FP8_BF16_GATE_UP_LAYERS`
  and `GRADIATED_FP8_BF16_DOWN_LAYERS` take comma-separated layer indices. The listed layers or
  projections stay in BF16 during FP8 decode. `GRADIATED_FP8_BF16_LM_HEAD=1` keeps the LM head in
  BF16.
- `GRADIATED_INT4_LM_HEAD_VALIDATE=1` and `GRADIATED_INT4_BF16_LM_HEAD_VALIDATE=1` log one
  comparison of the INT4 LM-head logits with the reference logits.
- `GRADIATED_SHARED_GLOBAL_KV_ROUNDTRIP=1` stages global K and V as one shared tensor and rebuilds
  them. It measures the quality of that format.
- `GRADIATED_DISABLE_RING_SPECULATION` disables the direct sliding-ring path for speculative
  verification when it has any value.
- `GRADIATED_DISABLE_FP8_HEURISTIC_POLICY` restores cuBLASLt's first algorithm choice.
  `GRADIATED_FP8_HEURISTIC_INDEX` forces one heuristic result in [0, 63]. The retained policy
  table fails closed, and you must requalify it when the CUDA or cuBLASLt image changes.

## Build

Without `GRADIATED_ENGINE_ENABLE_CUDA`, CMake builds and tests only the host parts:

- `gradiated_engine_model`: strict JSON, the Gemma 4 configuration, sharded safetensors metadata,
  the weight plan and `Gemma4Model::open`, which validates a release. It never maps the 62 GB of
  weights to inspect a release.
- `gradiated_engine_runtime`: the CUDA-free runtime modules. They parse the environment, check the
  bearer token, parse the completion request, write responses and streams, render metrics, and
  decide slot placement, admission and which speculative tokens to commit.
- `gradiated-engine-inspect`: validates a release and prints its memory plan.

`ctest` runs the model tests, the runtime module tests and an end-to-end test of
`gradiated-engine-inspect` on a small generated model. The host build also compiles
`src/native_runtime_main.cpp`, but it does not link it. The CUDA build compiles host code with GCC,
so also check changed host sources with `g++ -std=c++20 -fsyntax-only`.

With `GRADIATED_ENGINE_ENABLE_CUDA=ON`, CMake also builds:

- `gradiated_engine_cuda`: the Hopper kernels and execution primitives, compiled for `90a`.
- `gradiated-engine-runtime`: the HTTP runtime.
- `gradiated-engine-load`: loads the weight arena and reports the load bandwidth.
- The parity and benchmark tools in `src/*.cu`, compiled for `90`.

The CUDA build pins the header-only cuDNN frontend to
`b372d39879d44c91a8d5b342022e74802b6a8da2` (v1.17.0) and links the cuDNN 9 runtime from the node
image.

## Tools

These Python scripts reproduce the research results. They are not part of the runtime.

- `tools/generate_layer_fixture.py` writes deterministic BF16 decoder-layer fixtures with a
  manifest and hashes.
- `tools/capture_generation_fixture.py` captures greedy token output from the control server.
- `tools/compare_gemma4_assistant.py` writes a one-prompt PyTorch oracle for the assistant.
- `tools/benchmark_gemma4_assistant.py` measures the assistant draft cost without verification.
- `tools/prepare_humaneval_prompts.py` renders a deterministic HumanEval partition to token IDs.
- `tools/prepare_quality_prompts.py` renders agent traces to token IDs for quality evaluation.
- `tools/smoke_native_runtime.py` sends concurrent long prompts to an authenticated runtime.
