# Research log

## 2026-07-18 — one admitted TRTLLM-MHA decode candidate running

Question: can supported SGLang TensorRT-LLM MHA decode on Hopper improve the frozen c32 endpoint while keeping Triton prefill, BF16 weights, FP8-E5M2 KV, dynamic chunking 2048, and fused QK/RoPE?

Action: atomically claimed `h200-attention-endpoint-e00vbbb709tzxscaan` and launched one bounded durable owner, `gemma4-trtllm-decode-c32-20260718t1937z.service`, through 20:45Z. It verifies identities, removes only vLLM containers, starts the pinned SGLang image with TRTLLM-MHA decode and page size 64, records the zero-queue/HTTP-200 flush boundary, invokes the frozen exact runner once, retrieves raw artifacts, writes a typed terminal, and releases the shared bench without teardown.

Result (measured): `startup_failure`. The one candidate reached the actual Gemma 4 CUDA warmup in `trtllm_mha_backend.py`, which calls FlashInfer's `trtllm_batch_decode_with_kv_cache`, but its XQA JIT rejected the model's `head_dim=512`: `Invalid head_dim: 512, must be divisible by 16 and in range [16, 256]`. The server never became HTTP-ready, so no cache flush or exact-mix runner invocation occurred. The retained remote diagnostic is `artifacts/trtllm-decode-c32-20260718t1937z/remote-retrieved/server.log` (hash manifest `remote-retrieved.sha256`); the owner terminal is `remote-retrieved/OWNER_TERMINAL.json`. Claim exposure was 491.257 seconds at $2.46/hour, conservatively recorded as `$0.336`; the bench was released ready without teardown.

Interpretation: source-level SM90/page-size admission was insufficient for Gemma 4's exact 512-wide head geometry. This is a terminal incompatibility for the sole permitted TRTLLM-MHA candidate, not evidence about endpoint performance. No retry, fallback, page/backend sweep, or comparator run is authorized.
