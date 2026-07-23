# Residual small-H2D synchronization residency

## Question

On the exact stacked H200 frontier, do the residual 8-byte and 16-byte host-to-device transfers still precede workload-critical long synchronizations, and can one source-bound residency, batching, or producer change remove that serialization without changing model, cache, request, or sampling semantics?

## Why it matters

The retained exact-stack attribution still assigns roughly one third of profile wall time to synchronization, but the closed scheduler penalty snapshot proves that apparent waiting time is not automatically removable. The most specific unresolved signature is from a later measured trace: after eliminating 358 four-byte device-to-host predecessors, 29 long synchronizations totaling `4.691957794 s` remained, with 14 preceding 16-byte H2D copies, 14 preceding 8-byte H2D copies, and one missing predecessor. That trace used the endpoint-negative fixed-capacity metadata candidate, so it is a source-discovery prior only; it cannot be transferred to the retained producer-fused frontier without a scope-matched trace.

This is distinct from the closed four-byte metadata scalar, producer-fused SWA translation, schedule-stream penalty snapshot, continuous-decode flags, attention partitioning, and FP8 Stream-K mechanisms.

## Bound baseline and evidence

- Exact identities and workload are mechanically bound in `EVIDENCE_BINDING.json`.
- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, image digest `6113665a…`.
- Workload: 32 requests at c32, 4,214 prompt and 358 completion tokens per request, with exact `117728` uncached and `17120` cached prompt-token deltas.
- Retained simple frontier: producer-fused SWA translation at `0.6746877474374742 s/request`; economic ceiling: `0.6381105231 s/request`.
- Prior residual signature: `CANDIDATE_SYNC_COUNTER.json` SHA256 `7222069e…`, backed by trace SHA256 `74774be0…`. It is explicitly not a scope-matched endpoint result.

## Scope and immediate experiment

After the reservation is durable, claim the retained warm H200 and run one minimum synchronization trace of the current stacked producer-fused frontier. Bind every repeated 8-byte/16-byte H2D predecessor to its exact runtime API, thread, source callsite, immediate GPU consumer, phase, count, and non-overlapping endpoint relevance.

If the signature is absent, initialization-only, candidate-specific, or not independently removable, close without inventing an intervention. If one repeated source path survives with a credible whole-request bound, freeze exactly one semantic-preserving residency, batched-transfer, or device-producer intervention in this project and run one profiler-off c32 control/candidate pair plus only the minimum counter trace needed to test the preregistered prediction. If the binding lands in a Triton/CUDA producer or consumer, use `$kernel-research` and bind exact layouts, dtypes, shapes, and consumer semantics before implementation.

Require 32/32 sane outputs, exact token/cache accounting, real candidate-path proof, and no replacement synchronization or hidden scalar read. Retain a clean simple gain; promote only at or below `0.6381105231 s/request`.

Do not replay the closed four-byte capacity gather, scheduler overlap, continuous-decode steps, attention candidates, Stream-K, or a flag/tile sweep. Do not create or destroy provider resources.

## Resources and limits

- Bench: `h200-sync-linear-e00vhh6h29fj68x91g`, shared sequentially with the accepted-depth project.
- Reuse resident checkpoint, image, producer-fused metadata bytes, and CUDA/Triton/Nsight caches.
- Spend: `$12.00`.
- Compute: at most 90 claimed H200 minutes.
- Wall clock: at most three hours from first researcher start.
- Storage: at most 8 GiB retrieved artifacts.

## Portfolio effect

A scope-matched absent/off-critical signature closes this residual class cheaply. A clean gain stacks onto the current frontier. A negative source-bound pair closes only that exact transfer/residency mechanism and returns the warm bench for the independent MTP accepted-depth lane.
