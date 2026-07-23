# Exact local-attention register-residency redesign

Use `$kernel-research` for this project.

## Question

Can one exact-semantics local sliding-attention consumer reduce the 255-register accumulator footprint enough to improve H200 residency and materially accelerate Gemma 4's 50 local layers without changing KV heads, cache representation, attention math, or outputs?

## Why it matters

The exact residual trace contains 3,050 local `_fwd_kernel` calls totaling `3.366290283 s`, about 14.61% of the attributed request wall. They run with 255 registers/thread, 256 threads, 81,920 bytes dynamic shared memory, and only 32 or 64 total CTAs (`gridX=1/2`, `gridY=32`). This is distinct from the closed 610-call global-attention partition and from the quality-failed 16→8 local-KV-head model change: this project preserves the original 16 KV heads and exact model semantics.

## Bound production geometry

- Phase: decode, 50 local sliding-attention layers, 1,024-token window.
- Batch/query geometry: concurrency 32, 32 query heads, 16 KV heads, QK/V head dimension 256, paged FP8 E5M2 KV.
- Baseline consumer: pinned v0.5.13 `_fwd_kernel`, 255 registers/thread, block 256, dynamic shared memory 81,920 bytes, grid `[1 or 2, 32, 1]`.
- Producer/consumer: unchanged Q/K/V projection and FP8 paged-KV write into the local attention consumer; output returns unchanged to the residual path.
- Strongest baseline and workload identities are mechanically bound in `EVIDENCE_BINDING.json`.

## Scope

Inspect the pinned consumer and current library coverage, then freeze one local-only design that trades cheap recomputation or a bounded second reduction pass for lower value-accumulator register pressure. Preserve head counts, scale semantics, causal/window masking, page layout, and BF16 output. The predicted physical change is at most 128 registers/thread or otherwise measured two-CTA/SM residency, with no spill regression; measure the smallest counters needed to verify that prediction. First run an exact real-consumer component across the observed local decode lengths/batches, including page-boundary cases. Run one c32 control/candidate pair only if correctness passes and the component bound predicts at least 3% whole-request gain, or if stacking with the measured host-gate result reaches the `0.6381105231` ceiling. Do not replay global partitioning, reduce KV heads, change precision, or sweep tiles.

## Correctness and performance gates

- No nonfinite values; relative L2 ≤0.005 and cosine ≥0.9999 against the pinned real consumer.
- Exact causal/window/page semantics at the unchanged downstream consumer.
- Warm median improvement on the exact local family; report registers, spills, active CTAs/SM or equivalent occupancy evidence, and launch/reduction overhead.
- Conditional endpoint requires 32/32 sane rows and exact token/cache accounting.

## Resources and limits

- Reuse `h200-sync-linear-e00vhh6h29fj68x91g` after the higher-priority host-gate project releases it.
- Reuse the exact checkpoint, pinned image, and retained build/CUDA caches; never create or destroy provider resources.
- Maximum four claimed GPU-hours, five wall-clock hours from first claim, 8 GiB retrieved artifacts, and `$16.00` cumulative authorization.

## Portfolio-changing result

A correct component with a ≥3% whole-request bound advances to the single c32 pair and stacks with the retained simple synchronization gain. Incorrectness, failure to reduce the physical limiter, or no positive exact-family movement closes this local-attention realization while preserving the original model.

## Iteration 2 — true two-stage local attention

The exact value-split2 iteration is closed: it duplicated QK/online-softmax work, retained 255 registers/thread and one CTA/SM, raised local-load sectors 17.94%, and regressed the representative family 51.65%. Do not replay it or conditionally dispatch it.

Continue the same scientific question with one materially different design: stage 1 computes QK plus online-softmax state once into a bounded local-window intermediate; stage 2 applies V and writes the unchanged BF16 result. Use `$kernel-research` to decide whether a proven current FlashAttention/FlashInfer/CUTLASS implementation can supply this decomposition before writing custom Triton. The physical prediction is that neither stage allocates more than 128 registers/thread, the QK work is not duplicated, and any probability/LSE traffic costs less than the removed spills/register serialization on the representative grid-z32 family. Preserve all original heads, FP8 cache scales/layout, 1,024-token window, masking, paging, and downstream consumption.

Run one exact real-consumer component over the existing grid-z2/grid-z32 and page-boundary cases, with a paired minimum NCU capture. Advance to one c32 pair only if correctness passes and the conservative whole-request bound is at least 3%, or the measured stack reaches the campaign ceiling. No tile sweep, value split, KV-head reduction, precision change, or global-attention replay is admitted.
