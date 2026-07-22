# Research log

## 2026-07-22 — activated

Opened as the independent full-stack lane. The required output is a current source-supported GPU endpoint result, not a compatibility report.

## 2026-07-22 — current vLLM candidate and direct H200 launch prepared

Question: which current full-stack runtime is strong enough to spend the one independent H200 arm on?

Action: inspected the live empty GPU pool once, current official vLLM source, its Gemma 4 recipe/model implementation, engine-cache configuration, and the Linux/amd64 image manifest. Bound vLLM main commit `1a659a0c370942bae3c8567902e38bddbbae95f3` and `vllm/vllm-openai@sha256:f0b9a0dc75a9fca3b6811e3279367b2d6a448055a000bfd13859587d74cef268`. Materialized the c32 request runner under this project and prepared `remote_current_vllm_h200.sh`, which records pre-science CUDA state, server identity/logs, GPU telemetry, exact 32×4,214/358 request rows, prefix-cache counters, and a typed terminal.

Evidence: current source has `Gemma4Attention` and current cache configuration lists `fp8_e5m2`, documented as CUDA-supported; the image digest is resolved for linux/amd64. The prior pinned vLLM terminal used a July image and stopped at its E5M2 admission assertion, so it is not a replay of this current source/image.

Interpretation and next move: vLLM is the strongest direct independent candidate, with BF16 checkpoint weights plus FP8-E5M2 KV explicitly labeled as a representation difference from the dynamic-FP8 SGLang frontier. The only present blocker is typed external capacity: the shared pool reports zero benches and the reservation is not durable. On reservation, claim one independent H200 and run the prepared endpoint exactly once; do not add another readiness stage.

## 2026-07-22 — pre-invocation SSH access blocker

Action: materialized the bound 59-GiB immutable checkpoint under `inputs/checkpoint`, verified its index/config/tokenizer hashes, atomically claimed `h200-current-runtime-e00s5ggxfqbn6ctb02`, and launched the bounded outer owner.

Evidence: the provider returned `195.242.29.186` and accepted the SSH host handshake, then rejected `/root/.config/nebius/glm-campaign/ssh_ed25519` for `glmrunner` with `Permission denied (publickey)`. `artifacts/current-vllm-h200-20260722t1231z/OUTER_TERMINAL.json` and the systemd journal record the failure; remote retrieval consequently had no worker terminal. No checkpoint transfer, Docker pull, CUDA call, model load, server start, or scored endpoint request began.

Interpretation: this is a typed remote-access integration blocker, not a candidate outcome or an invocation of the current-vLLM arm. The bench is maintenance-marked for director SSH-key/access repair. The outer owner is patched so a future ordinary pre-invocation access/retrieval fault writes `REPAIR_READY.json` and preserves a claim rather than releasing it.

## 2026-07-22 — current-vLLM FP8-E5M2 terminal incompatibility

Action: reused the resident, hash-verified eight-file checkpoint on the retained H200 and repaired the Docker image-entrypoint duplication in place. The corrected current image started vLLM 0.25.1, loaded the Gemma 4 execution path, and reached its first GPU profile call. The outer owner retained its 45-second heartbeat, retrieved the nested terminal and raw server log, then released the bench available.

Evidence: the live run failed in `vllm/model_executor/layers/attention/attention.py:517` because the Gemma 4 attention path asserts `kv_cache_dtype in {fp8, fp8_e4m3, nvfp4}`. The admitted `--kv-cache-dtype fp8_e5m2` value therefore fails during model profiling, before server readiness or endpoint requests. `INVOCATION_STATE.json` records `candidate_cuda_started: true` and `candidate_science_started: false`; the typed terminal and full trace are retained in `artifacts/current-vllm-h200-20260722t1231z/`.

Interpretation: this is a measured source/CUDA incompatibility for the selected *current* vLLM image, not a replay of the historical July image and not a throughput result. FP8-E4M3 or `fp8` would change the required cache representation, so it is not a repair or substitute arm. The 71.5-minute allocation exposure is approximately $2.94 at $2.46/hour, within the $12.00 reservation. The bench was released available; any next candidate requires a materially distinct director admission.

## 2026-07-22 — current-vLLM FP8-E4M3 c32 endpoint reject

Action: under the director-admitted E4M3 representation change, reused the resident checkpoint and current vLLM 0.25.1 image. The server reported `Using fp8_e4m3 data type to store kv cache`, served `google/gemma-4-31B-it`, and completed the one exact c32 batch. A warm-up request initially carried `stream_options` with `stream=false`; its documented HTTP-400 validation error was repaired in-place without rerunning the producer server or the 32-request batch.

Evidence: all 32 requests returned finite, nonempty text with exact `4214` prompt and `358` completion tokens. Batch service time was `30.053227711` seconds, or `0.939163366 s/request`; output throughput was `381.1903 tokens/s`. The `0.0205364 USD` useful-service cost is recorded at the $2.46/hour metered H200 rate. The request-side metric delta exactly accounts for `134848` prompt tokens, but vLLM did not export an uncached-prompt metric, so the cached/fresh split remains explicitly unavailable rather than inferred.

Interpretation: E4M3 is a real, runnable representation but misses the absolute `0.6381105231 s/request` H200 ceiling by `0.301052843 s/request` (47.2%). This is a measured endpoint reject, not a comparison to the closed E5M2 representation. The H200 was released available at 13:51:18Z with the watchdog reserve intact; estimated cumulative project allocation exposure is about $3.18, below the $12.00 cap.
