# Scheduler-gap pipeline overlap

## Question

Can one source-bound overlap of next-step CPU scheduling/metadata preparation with the current H200 CUDA work reduce the exact c32 scheduler gap while preserving request order, cache accounting, and the retained `0.6762324541 s/request` endpoint semantics?

## Why it matters

The contemporaneous retained dense-add Nsight trace assigns 1.142505439 seconds, 5.086% of its non-overlapping window, to scheduler gaps; decode alone contributes 0.783702916 seconds. A later diagnostic trace reported an even larger 12.416% gap, but that slower profile is only supporting evidence. The retained trace is sufficient to justify one source-correlated pipeline experiment and avoids transferring attribution from an older BF16 stack.

This is independent of the metadata-scalar lineage: it targets CPU/GPU scheduling overlap, not KV-index translation, attention arithmetic, FP8 linear scheduling, continuous-decode-step flags, or output streaming.

## Bound baseline

- Exact checkpoint, runtime image, workload, trace, and hashes are in `EVIDENCE_BINDING.json`.
- Stack: pinned SGLang v0.5.13 dynamic E4M3 linears, FP8 E5M2 KV, QKV epilogue, deferred local-KV commit, 2,048-token dynamic chunking, pinned penalty-token transfer, and retained dense-add host gating.
- Stacked frontier: `0.6746877474374742 s/request`; economic ceiling: `0.6381105231 s/request`. The control must include the bit-exact producer-fused SWA translation bound in `EVIDENCE_BINDING.json`.
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

## Iteration 2 — bind the scheduler mechanism to the observed retained source

The first owner did not measure the scheduler intervention. The retained runtime exposed `schedule_batch.py` SHA256 `b6480f792867d7aba3dc39ef66048408c6c92ddad3ed81b23934493a351be459`, not the frozen `eea77dac02f593da24e953f0a0ea03237f2874d0ef27522044e8fd6397fcb874` source. The candidate therefore failed closed before scheduler-path proof. Its persisted endpoint pair merely repeats the stacked producer-fused metadata result, and its candidate trace cannot pass the hash-bound analyzer. Both are quarantined and are not scheduler evidence.

Keep this scientific question in the same project. In one retained claim, first copy the observed live source into a fresh project artifact namespace before any mutation, verify its hash, and diff it against the frozen source. Re-establish the corresponding current call chain for the same 358 gaps totaling `0.643528382 s`; then freeze exactly one equivalent observed-source intervention with an explicit stream, ordering, and lifetime contract. Only after that binding passes may the researcher run the first valid scheduler measurement: one fresh profiler-off c32 control/candidate pair followed by one minimum candidate trace.

If the observed source already implements the overlap, invalidates the 358-gap causal chain, or admits no single equivalent source-bound intervention, close this mechanism without an endpoint run. Do not reuse or relabel the prior pair or trace, replay continuous-decode steps, sweep flags, change workload geometry, or introduce a second scheduler candidate. The iteration contract is `ITERATION2_SOURCE_REBIND.json`.

Iteration 2 has `$12.00` authorization and must not claim the retained bench until that reservation is durable.

## Iteration 2 candidate-injection repair

Iteration 2 successfully rebound the 358-gap mechanism to the observed live source, but its candidate-labeled endpoint did not instantiate the scheduler intervention. SGLang multiprocess startup reran the non-idempotent retained predecessor installer before scheduler installation. The control and candidate audits are byte-identical at SHA256 `93312a0ba2895ed972a18901a2a444817f4eab9e5ee6e1a5d18e976f07382afc`, and neither includes `Scheduler.run_batch.observed_source_schedule_stream_forward_penalty_snapshot`. Therefore the raw `0.674524976→0.674440688 s/request` delta is control-equivalent noise, not scheduler evidence, and the candidate arm is unconsumed.

Keep the same project and frozen scientific intervention. After the `$6.00` repair reservation is durable, use the retained H200 to change only worker-local installer ordering/idempotency and add non-semantic installation-complete proof. Do not change the observed-source intervention implementation SHA256 `3b5aa497985a400c16189db8359a458d981adff66d8465c26a92ed54394414e6`, checkpoint, runtime image, workload, stacked predecessor, comparator, or decision gates.

Once the actual serving worker proves successful installation before requests, rerun only the invalidated candidate endpoint in a fresh artifact namespace against the retained valid control `0.6745249759062517 s/request`. Require 32/32 exact accounting and the runtime scheduler-path event, then collect one minimum candidate trace. Do not replay control or repair after any partial or ambiguous candidate execution. The bounded contract is `ITERATION2_CANDIDATE_INJECTION_REPAIR.json`.
