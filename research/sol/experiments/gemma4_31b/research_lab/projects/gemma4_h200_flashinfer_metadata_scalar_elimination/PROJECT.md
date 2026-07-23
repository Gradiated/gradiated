# FlashInfer metadata scalar elimination

## Question

Can the pinned SGLang v0.5.13 attention-metadata path construct and consume exact FlashInfer KV indices without reading a 4-byte CUDA scalar on the host every decode step, while preserving the retained `0.6762324541 s/request` endpoint semantics?

## Why it matters

The retained penalizer dense-add intervention is endpoint-positive by 1.492%, but its minimum trace proves the 358 long synchronization boundaries merely moved. Each now immediately follows a 4-byte D2H read after `create_flashinfer_kv_indices_triton`, preceded by scan/copy/add metadata kernels. Those 358 reads align exactly with the 358 decode tokens and retain all 387 long sync calls. This is a new attention-metadata boundary, not a variant of the closed penalizer host gate.

## Bound baseline

- Exact checkpoint, runtime image, representation, workload, and artifact digests are in `EVIDENCE_BINDING.json`.
- Control stack: dynamic E4M3 linears, FP8 E5M2 KV, QKV epilogue, deferred local-KV commit, 2,048-token dynamic chunking, pinned penalty-token transfer, and the retained dense-add min-new-tokens intervention.
- Control endpoint: `0.6762324541249995 s/request`, 32/32 valid requests with exact cache/token accounting.
- Measured causal boundary: 358 4-byte D2H immediate predecessors after `create_flashinfer_kv_indices_triton`; 387 long sync calls totaling `12.897130083 s` in the trace window.

## Scope

Use deep source/runtime reasoning to identify the exact host scalar consumer in the pinned image. Replace only that consumer with host-known metadata, a fixed-capacity device workspace, or an equivalent graph-safe construction that does not require a per-step device scalar. Freeze one source intervention. Preserve KV index contents, indptrs, request ordering, page boundaries, causal masks, CUDA-graph behavior, and every downstream attention consumer. Validate empty, odd, cache-hit, page-boundary, batch filter/merge, and maximum exact-workload cases.

Run exactly one profiler-off control/candidate c32 pair and the minimum candidate trace needed to test the 358→0 4-byte D2H prediction. Do not modify the retained penalizer intervention, sweep metadata strategies, change attention kernels, or replay the closed host-gate arm.

## Resources and limits

- After a durable reservation, claim retained bench `h200-sync-linear-e00vhh6h29fj68x91g`; never create or destroy provider resources.
- Reuse its exact checkpoint, pinned image, server/build caches, and retained host-gate bytes.
- At most three claimed GPU-hours, four wall-clock hours from first claim, 5 GiB retrieved artifacts, and `$18.00` cumulative authorization.
- Release warm for `gemma4_h200_local_attention_register_residency` iteration 2.

## Decision rule

Require 32/32 sane outputs, exact token/cache accounting, candidate-path proof, metadata equality, and no replacement host/device scalar read. The causal prediction is 358→0 four-byte D2H predecessors with a material reduction in long synchronization. Retain any reproducible endpoint gain without material downside; promote only at or below `0.6381105231 s/request`. Close this exact metadata mechanism on semantic failure, unchanged counters, or no positive endpoint movement.
