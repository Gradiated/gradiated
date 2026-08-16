# Research log

## 2026-07-17 — director delegation

Activated as an independent `$0` representation and capacity line while the paid FP8 project performs its one in-place controller correction. The immediate decision is whether byte-exact W4 plus an actual SM89 consumer admits c16 and cuts the optimistic primary service lower bound by at least 25% versus FP8. No GPU, provider mutation, controller work, full weights, or quality transfer is allowed. Budgets are 50 wall minutes, 1 local CPU-hour, 2 GiB storage, 256 MiB bounded probes, and `$0`.

## 2026-07-17 — deterministic W4 bound and consumer audit

Reconstructed all exact TP=1 Gemma fused linear shapes from `GEOMETRY.json`. Every K/N dimension is divisible by group 128 and Marlin's 128-K/64-N tile family, so no payload padding is required. The byte model uses packed INT4 (0.5 byte/weight), FP16 scales (2 bytes/group), and packed 4-bit zero-points (0.5 byte/group). Quantized language linears are 15.273 GB; tied BF16 embedding/output plus BF16 residual/vision remainder are 6.571 GB; total retained W4 weights are 20.343 GiB. With a 5 GiB reserve, primary c16 is 36.738 GiB with BF16 KV and 34.234 GiB with explicit per-token-head FP8 KV; 10K c16 is 37.794 GiB with explicit FP8 KV. c32 is 48.132 GiB with BF16 KV and 43.125 GiB with explicit FP8 KV.

The derived 864 GB/s primary mix bound at M=16 is 0.138421 req/s for W4 versus 0.081979 req/s for inherited conservative FP8, a 40.776% reduction. This is a weight-streaming lower bound only, not endpoint evidence. Pinned first-party vLLM source confirms Marlin WNA16 on CUDA/SM89, AWQ uint4 or GPTQ uint4b8, group sizes -1/32/64/128, FP16/BF16 activations, and tile constraints; all critical Gemma fused shapes pass with zero padding. No exact-revision W4 producer/checkpoint route exists, and the tied head remains BF16. Interpretation: capacity and arithmetic gates pass, but the exact producer/quality and actual execution gate does not; terminal typed `none`.

Artifact: `W4_C16_BOUND.json`; concise decision: `DECISION.md`. No provider, CUDA, weight transfer, compile, controller, or quality action was taken.

## 2026-07-17 — director reopens one accounting correction

Preserve the first artifact, but correct three material scope errors in place: prompt prefill was charged as 4,214 full weight streams despite large-M weight reuse; inactive vision residency was included in text decode traffic; and primary/10K FP8 KV used `0.555684/0.778127 GiB` instead of the authoritative `0.363423228/0.585865974 GiB` source contract. Produce a phase-aware V2 bound and only a conditional synthetic Marlin component packet if it changes the next decision. This remains `$0`, no-provider, no-CUDA work under a 25-wall-minute, 0.5-CPU-hour, 512-MiB correction cap. Use project-local temporary storage because shared `/tmp` is full.

## 2026-07-17 — corrected phase/KV branch changes

Action: recomputed W4 capacity using the source-bound FP8-KV contract (`0.363423228 GiB` primary input, `0.377186537 GiB` primary peak, `0.585865974 GiB` at 10K), separated resident bytes from active text traffic, and charged prefill one large-M weight stream rather than one stream per prompt token. The W4 active text stream is 16.849 GiB; total resident weights remain 20.343 GiB. With the 5 GiB reserve, W4 primary c16 is 31.158 GiB and c32 is 36.973 GiB; 10K c16 is 34.717 GiB and c32 is 44.091 GiB, leaving 0.613 GiB logical 10K c32 headroom before allocator rounding.

For primary prefill, the 12.7% cache-read mix leaves 3,678.822 uncached tokens. The analytical language-GEMM BF16-peak floor is 0.597408 s per batch; weight-only prefill floors are 0.020939 s (W4) and 0.037286 s (FP8). At c16, phase-aware service floors are 0.507631 s/request W4 versus 0.873407 s/request FP8, a 41.880% reduction. W4 clears both 0.717061 and 1.158355 req/s hurdles under this optimistic floor; remaining time is 0.356 s/request against the conservative budget for attention, scheduling, sampling, transfers, and reliability. These are analytical bounds, not endpoint measurements.

Interpretation: the corrected accounting changes the branch from typed none to one conditional checkpoint-free synthetic Marlin component packet. `W4_COMPONENT_PACKET.json` is not executed or provider-ready: it is gated on terminal cleanup of the live FP8 owner, later director admission, actual Marlin invocation for all critical shapes, measured allocator/transient fit, numerical oracle, and a candidate p50 component result at least 25% better than matched FP8. Exact W4 producer provenance and quality remain absent.

Artifacts: `W4_C16_BOUND_V2.json`, `W4_COMPONENT_PACKET.json`. No provider, CUDA, weight transfer, compile, controller, or quality action was taken.
