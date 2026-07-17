# Research log

No researcher turn has completed. The endpoint is one start-ready retained-session FP8-KV c8 packet or a typed closure, not another provider or support project.

## 2026-07-17 — pinned FP8-KV scale binding

Question: can the pinned runtime express FP8-KV c8 with an explicit scale identity for exact Gemma 4 without provider mutation?

Action: inspected the exact pinned vLLM revision and Gemma4 model/config/index inputs; fetched only the pinned first-party source files and did not touch the live owner or provider. The scalar `fp8` path loads checkpoint K/V scales when present and otherwise defaults to `1.0`; the exact 1,188-tensor index has no K/V scale tensors. The same revision exposes `fp8_per_token_head`, maps it to `FP8_PER_TOKEN_HEAD`, and its Triton cache writer stores native Ada FP8 bytes with inline dynamic FP32 K/V scales.

Evidence: source hashes and the launch binding are in `PINNED_SOURCE_EXCERPT.md` and `FP8_KV_ARM.json`. Exact derived memory is 43.820 GiB at primary c8 including inline scale bytes, with 0.884 GiB below the 44.704 GiB envelope; 10K is 40.131 GiB with 4.573 GiB headroom. No CUDA or throughput evidence exists.

Interpretation: the ordinary scalar FP8-KV launch is closed for this arm because its scale identity is ambiguous and current first-party Gemma4 reports flag the scalar path as corrupt. The explicit per-token-head E4M3 route is start-ready conditional, with deterministic raw-token and memory/cost gates. It is not executed until the stock retained owner emits the preregistered trigger; a false trigger requires immediate existing-owner cleanup.

Next move: the direct owner consumes this packet only if stock correctness passes, c4 completes, and c8 is memory-limited or misses the sustainable-cost hurdle; otherwise reconcile cleanup and close the arm.
