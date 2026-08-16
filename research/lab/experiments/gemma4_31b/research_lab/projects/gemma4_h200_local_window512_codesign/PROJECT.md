# Gemma 4 local-window 512 co-design proxy

## Question

If only the 50 local-attention layers use a 512-token window instead of 1,024, can the exact H200 stack reduce its measured local-attention boundary enough to close the remaining service-time gap while retaining all weights, all 32 query heads, all 16 KV heads, all global-attention layers, and exact workload geometry?

## Why this matters

The exact local-attention profile attributes 15.312% of endpoint wall time to 50 local layers using 1,024-token windows, 32 query heads, 16 KV heads, head dimension 256, and FP8 E5M2 KV. Previous value-split and two-stage kernel redesigns are closed: they failed correctness or produced negative physical bounds while remaining register limited. Reducing only the local receptive window is a materially different model/hardware co-design lever: it cuts the key/value span of the measured boundary while preserving parameter count, global attention, head geometry, and every non-attention stack gain.

This is a quality-unsafe performance proxy, not a production candidate. It may proceed during exploration because it is tied directly to a measured bottleneck, but it cannot become production-eligible without later exact served-model GPQA-Diamond, TauBench, tool-call, and feature validation or an explicit training/recovery plan.

## Bound scope

`EVIDENCE_BINDING.json` fixes the model, runtime, image, workload, exact source, current control, and local-attention geometry. Change only the effective local sliding window from 1,024 to 512 for the five-local/one-global pattern. Preserve:

- all checkpoint weights and layer count;
- all 32 query heads, 16 KV heads, and 256-dimensional Q/K/V geometry;
- every global-attention layer and its K/V semantics;
- RoPE positions, token order, cache dtype/layout, sampling, request identities, and output length;
- dynamic FP8, fused QKV, deferred-local-KV, producer-fused metadata, and dense penalizer additions.

No window sweep, head reduction, layer deletion, quantization change, attention-kernel redesign, or MTP combination is allowed. Native n-gram may be present only as the exact frozen, quality-qualified frontier comparator defined by the director; its contract may not change.

## Experiment

Prepare offline behind the higher-priority native n-gram lane. First bind the config-to-runtime-to-kernel flow and prove that the candidate affects exactly the 50 local layers while leaving global layers unchanged. Derive a call-weighted physical bound from the measured 15.312% local-attention fraction and exact 512/1,024 span change.

After the `$14.00` reservation is durable and the n-gram production-validation lane releases the retained bench, claim `h200-sync-linear-e00vhh6h29fj68x91g` only if the watchdog leaves enough time. Run one exact component/path check at the real decode and extend shapes. Require numerical agreement with a 512-window reference, candidate-path events from all and only local layers, unchanged output shapes, and no fallback to a 1,024-token consumer.

If native n-gram passes validation, treat its persisted `0.5967508053 s/request` terminal as the immutable comparator, preserve the frozen n-gram contract in the candidate, and run only one profiler-off n-gram-plus-window512 candidate after the component/path gate; do not replay the n-gram control. If n-gram fails validation, use the original non-speculative scope and contemporaneous control. In either branch, first label the prior `6.5623%` bound as historical and derive a scope-matched physical bound; run the endpoint only if it reaches 5% or materially improves the selected qualified frontier. Require 32/32 finite, nonempty, length-correct responses, exact fresh/cache accounting, and three cheap coherence prompts sufficient to reject obvious breakage. Do not run broad quality in this project.

## Resources and limits

- Bench: retained `h200-sync-linear-e00vhh6h29fj68x91g`, sequentially after native n-gram production validation.
- Spend: `$14.00`.
- Compute: at most 90 claimed H200 minutes.
- Wall clock: at most three hours from first researcher start.
- Storage: at most 8 GiB retrieved artifacts.
- Reuse the resident checkpoint, image, local-attention source/bindings, current-stack bytes, and caches.

## Decision

A performance-positive result remains an experimental co-design proxy and opens a separate quality/recovery decision; it is not stacked into the production frontier automatically. Close this exact 512-window proxy if the 5% physical gate, numerical/path gate, endpoint timing, or cheap-coherence gate fails.
