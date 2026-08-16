# Research log

## 2026-07-17 — director delegation

Activated as independent `$0` model/runtime evidence after the actual BF16 head measured 1.402982 seconds/request at M1 and 0.178124 at M8, overturning FLOPs as the latency proxy. Find one truthful single-storage joint one-byte embedding/output consumer with a later CUDA and raw-quality falsifier, or close typed none. Budgets are 50 wall minutes, 2 CPU-hours, 2 GiB/512 MiB probes, and `$0`; no provider/checkpoint/compile/CUDA/endpoint/quality work and no W4/shortlist/output-only successor.

## 2026-07-17 — typed consumer-route closure

Question: does the exact installed stack expose a truthful shared one-byte consumer? Action: inspected the retained exact vLLM runtime metadata and the available Gemma/SGLang source probe, and checked the shared tools before any lifecycle action. Evidence: the only execution-measured consumer is `vllm.model_executor.layers.vocab_parallel_embedding.ParallelLMHead` with `UnquantizedEmbeddingMethod` at vLLM `0.19.1.dev6+g6d4a8e6d2`; the exact source hashes are bound in `NONE.json`. The Gemma SGLang source at revision `6e3be088a9b7b1ec1f34b0fc0f3eb421e2bd05e2` ties `lm_head` by direct alias to `model.embed_tokens` and constructs `ParallelLMHead` only when untied. Generic FP8/int8 flags do not prove an embedding lookup, loader, scales, or output projection consumer.

Interpretation: the analytical capacity discontinuity is genuine (45.046 -> 43.7335 GiB at primary c8), and the measured head remains material at M8 (0.178124 s over 358 steps), but no pinned execution-equivalent one-byte joint consumer exists in scope. A packet would be an invented readiness claim; no CUDA, provider, checkpoint, compile, or quality work is authorized. Terminal: `NONE.json`; no successor is opened.
