# Research log

## 2026-07-22 — activated

Opened as the independent full-stack lane. The required output is a current source-supported GPU endpoint result, not a compatibility report.

## 2026-07-22 — current vLLM candidate and direct H200 launch prepared

Question: which current full-stack runtime is strong enough to spend the one independent H200 arm on?

Action: inspected the live empty GPU pool once, current official vLLM source, its Gemma 4 recipe/model implementation, engine-cache configuration, and the Linux/amd64 image manifest. Bound vLLM main commit `1a659a0c370942bae3c8567902e38bddbbae95f3` and `vllm/vllm-openai@sha256:f0b9a0dc75a9fca3b6811e3279367b2d6a448055a000bfd13859587d74cef268`. Materialized the c32 request runner under this project and prepared `remote_current_vllm_h200.sh`, which records pre-science CUDA state, server identity/logs, GPU telemetry, exact 32×4,214/358 request rows, prefix-cache counters, and a typed terminal.

Evidence: current source has `Gemma4Attention` and current cache configuration lists `fp8_e5m2`, documented as CUDA-supported; the image digest is resolved for linux/amd64. The prior pinned vLLM terminal used a July image and stopped at its E5M2 admission assertion, so it is not a replay of this current source/image.

Interpretation and next move: vLLM is the strongest direct independent candidate, with BF16 checkpoint weights plus FP8-E5M2 KV explicitly labeled as a representation difference from the dynamic-FP8 SGLang frontier. The only present blocker is typed external capacity: the shared pool reports zero benches and the reservation is not durable. On reservation, claim one independent H200 and run the prepared endpoint exactly once; do not add another readiness stage.
