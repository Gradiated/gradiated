# Gemma 4 H200 dense-FP8 linear schedule and dataflow

## Question

Can a quality-preserving dense-FP8 schedule or dataflow change on the dominant exact Gemma linear family yield a measured endpoint-relevant gain without replaying the rejected gate/up tile, static-FP8 ABI, adjacent quantization/down fusion, or 2:4 pruning?

## Evidence and physical scope

The bound exact profile assigns 22.97% of total wall time to FP8 linears, including 38.30% of prefill and 16.16% of decode. A standalone closure of the 7.42% endpoint gap therefore requires roughly a 32.3% reduction across this boundary, while a reproducible smaller gain can stack with the synchronization lane.

Use `$kernel-research`. Trace the pinned v0.5.13 producer, scale convention, GEMM dispatch, output layout, and unchanged downstream consumer for the hottest eligible dense-E4M3 family. Establish exact shapes for decode and prefill from the retained profile. Check current cuBLASLt/CUTLASS support first, then choose one source-justified mechanism such as a better Hopper WGMMA/TMA schedule, grouped gate/up execution with shared activation reads, persistent work partitioning, or a proven epilogue that removes material bytes. Name predicted changes in tensor activity, HBM/L2 traffic, launch count, grid waves, registers, or spills before implementation.

## Immutable binding

Use `../gemma4_h200_v0513_fp8_qkv_residual_profile/BINDINGS.json` at SHA-256 `cebc435c4eb1e5716c4aa9bd854785a3e7cac4b0665c96ea6a44040b3e96fb62` and attribution SHA-256 `f841db590dbe6f2e6b4fb91048e8132c3807f0321310e1e0b70a3957ac99ab48`. Preserve the exact checkpoint, SGLang v0.5.13 image/commit, TP1 dynamic FP8-E4M3FN weights, FP8-E5M2 KV, chunk size 2048, and c32 workload described there.

## Experiment and promotion

Prepare offline only what does not require CUDA, then await the shared director-registered H200. The first GPU action is a tiny real-consumer discovery call, followed by exact decode and prefill shapes using real checkpoint weights. Compare against the strongest current dense consumer, consume the full candidate output, and report relative L2, cosine, saturation/nonfinite counts, warm timing distributions, candidate-path proof, compiler resources, and only counters needed for the physical hypothesis.

Promote immediately to one exact c32 control/candidate endpoint pair if correctness passes and the measured whole-request bound predicts at least a 5% service-time gain, or if it can stack with a measured synchronization winner to cross `0.6381105231 s/request`. Preserve a smaller clean endpoint gain but do not sweep tiles after a negative causal test. Emit actual provider exposure and `actual_spend_usd` in the typed terminal.

## Budget

`$20.00` total, one shared H200, at most four claimed GPU-hours and five wall-clock hours from first claim. Provider lifecycle remains director-only.
## 2026-07-23 — paired gate/up exact consumer

The fresh producer-fused trace still assigns `5.375939818 s` (`24.0589%`) of non-overlapping wall time to FP8 linears, with `14,640` dominant `device_kernel` calls totaling `4.982781 s`. The prior cooperative Stream-K down projection and activation-to-down fusion are closed physical mechanisms; they do not test the independent gate/up adjacency where two exact projections share one input.

Use `$kernel-research` to freeze one paired gate/up consumer that reuses activation quantization/read while consuming both exact real E4M3 weight matrices and preserving scales, BF16 activation/multiply semantics, output layout, and the stock downstream down projection. Measure the exact current decode and observed prefill shapes. Promote to at most one c32 pair only if correctness passes and the component evidence predicts at least 3% whole-request gain. Do not sweep schedules or revisit any closed Stream-K, tile, static-FP8, sparsity, or activation-to-down candidate. The full contract is `GATE_UP_PAIRED_REOPENING.json`.
