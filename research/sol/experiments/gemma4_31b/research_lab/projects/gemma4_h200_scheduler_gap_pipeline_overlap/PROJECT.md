# Scheduler-gap pipeline overlap

## Question

Can one source-bound overlap of next-step CPU scheduling/metadata preparation with the current H200 CUDA work reduce the exact c32 scheduler gap while preserving request order, cache accounting, and the retained `0.6762324541 s/request` endpoint semantics?

## Why it matters

The contemporaneous retained dense-add Nsight trace assigns 1.142505439 seconds, 5.086% of its non-overlapping window, to scheduler gaps; decode alone contributes 0.783702916 seconds. A later diagnostic trace reported an even larger 12.416% gap, but that slower profile is only supporting evidence. The retained trace is sufficient to justify one source-correlated pipeline experiment and avoids transferring attribution from an older BF16 stack.

This is independent of the metadata-scalar lineage: it targets CPU/GPU scheduling overlap, not KV-index translation, attention arithmetic, FP8 linear scheduling, continuous-decode-step flags, or output streaming.

## Bound baseline

- Exact checkpoint, runtime image, workload, trace, and hashes are in `EVIDENCE_BINDING.json`.
- Stack: pinned SGLang v0.5.13 dynamic E4M3 linears, FP8 E5M2 KV, QKV epilogue, deferred local-KV commit, 2,048-token dynamic chunking, pinned penalty-token transfer, and retained dense-add host gating.
- Frontier: `0.6762324541249995 s/request`; economic ceiling: `0.6381105231 s/request`.
- Target: the largest repeated scheduler-gap host path in the supplied exact trace, correlated to its pinned source call stack before intervention selection.

## Scope

Use deep source/runtime reasoning to identify the single repeated host path responsible for the largest scheduler-gap class. Freeze one bounded change that prepares or double-buffers the next scheduling/metadata state while the current CUDA graph or kernels execute, with an explicit stream/event/lifetime contract. If source evidence instead identifies an equivalent single avoidable serialization in that gap, the researcher may remove that serialization rather than force overlap.

Preserve request admission and completion order, sampling semantics, KV slot ownership, prefix-cache accounting, CUDA-graph padding, dynamic shapes, allocator lifetimes, and failure/reload behavior. Reject any intervention that replays continuous-decode-steps, changes concurrency/load shape, sweeps flags, or weakens synchronization without a proven ownership dependency.

Run exactly one profiler-off c32 control/candidate pair and the minimum trace needed to measure the preregistered gap class. Require 32/32 sane outputs, exact token/cache accounting, candidate-path proof, and no new race, stale metadata, or synchronization predecessor. Retain any reproducible endpoint gain without material downside; promote only at or below `0.6381105231 s/request`.

## Resources and limits

- After the priority-1300 metadata iteration releases, claim `h200-sync-linear-e00vhh6h29fj68x91g`; never create or destroy provider resources.
- Reuse the pinned image, exact checkpoint, workload, and warm caches.
- At most two claimed GPU-hours, three wall-clock hours from first claim, 5 GiB retrieved artifacts, and `$16.00` authorization.
- Release the bench warm with updated contents after the typed terminal.

## What changes the portfolio

A clean gain stacks onto the frontier and triggers a fresh residual profile only if needed for the next decision. A semantic failure, unchanged gap, or non-positive endpoint result closes this exact overlap/serialization mechanism without reopening continuous-decode flags or a scheduler sweep.
