# H200 QKV → Q/K-normalization/RoPE FP8 epilogue

## Question

Can the exact Gemma 4 decode QKV projection boundary be changed so Q/K
normalization, layout conversion, and RoPE consume the projection epilogue
without materializing and relaunching every intermediate, while preserving the
pinned SGLang consumer semantics and improving an exact H200 hot-block?

## Why it matters

The campaign must move the qualified `0.625149101968745 s/request` denominator
toward `0.500119281574996 s/request`. The gated-activation fusion is fast but
quality-unsafe at production row counts, so the next direct experiment changes
operator boundary rather than extending that arithmetic repair. QKV
projection, Q/K normalization, RoPE, and attention preparation recur across
Gemma's hybrid attention stack and are a plausible launch/dataflow target.

## Exact scope

- Model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: pinned SGLang
  `v0.5.13@28b095c01005d4a3a2a5b637b7d028b07fba31b2`.
- Initial phase: decode, concurrent batch 32.
- Target: NVIDIA H200 SXM / sm_90a.
- Stock control: the pinned current-runtime QKV projection output followed by
  its exact Q/K normalization, RoPE, layout, and first attention consumer.
- Candidate: one source-justified epilogue/dataflow change through that same
  consumer. Mechanically extract local/global head geometry, strides, dtypes,
  scale conventions, and symbols from the pinned config/source before the
  first call; do not infer them from historical prose.

## Immediate experiment

Use `$researcher` with the deep profile, `$kernel-research`, and
`$experiment-run`. Once the durable reservation and a fresh director execution
binding exist, claim the retained H200 and make the first tiny exact-runtime
call the discovery test. Inspect the actual producer/consumer source in the
claimed mutable environment, implement the smallest working exact-shape
candidate, and continue directly to correctness plus a profiler-off component
comparison. Ordinary compile/API/layout defects are repaired in the same claim.

The first result must include exact geometry and symbols, consumed-output
numerical evidence, candidate-path proof, baseline/candidate warm timings, and
one physical prediction such as launch count or materialized bytes. No endpoint
claim is allowed until a correct positive component establishes a credible
request-level bound.

## Resources and limits

- Cumulative project authorization: `$10.00` after the endpoint packet
  re-entry binding; the settled prior exposure remains `$2.94`.
- Initial lifecycle: at most 45 minutes on one H200, including repair,
  terminal, and release.
- Storage: 2 GiB additional.
- Reuse the lab's pinned image, checkpoint, CUDA/JIT caches, strict SSH
  identity, and shared claim/release plumbing.

## Portfolio-changing result

Promote a correct positive component to a scope-matched endpoint integration
when its measured bound makes that inexpensive. Close only the implemented
epilogue/dataflow decomposition if its real consumer is incorrect or its gain
vanishes; preserve useful source and counter evidence for another
decomposition.

## Endpoint integration phase — 2026-07-29

The accepted exact-consumer component is positive and closed to replay. Its
measured local/global decode-c32 reductions are `26.7%`/`18.6%`, with a
non-transferable analytical request bound of `0.0568951 s/request`. Build the
smallest pinned-runtime adapter and durable endpoint owner in this same
project, then let a later director authorize one fresh exact c32 endpoint.
The endpoint must compare directly with the fixed qualified
`0.625149101968745 s/request` result and report progress toward
`0.500119281574996`; component timing alone is not a campaign result.

## Cold endpoint execution packet — 2026-07-29

The retired warm H200 is not a dependency. The project-local packet binds the
exact workload, qualified comparator, launch configuration, runtime adapter,
driver, and 62,578,655,208-byte checkpoint by SHA-256. A future owner may act
only under a fresh director execution binding naming one H200, its watchdog,
rate, GPU UUID, absolute release fence, and this readiness hash. The owner
keeps claim and heartbeat across bounded pre-science repair, treats ambiguous
post-launch state as retrieval-only, accepts one endpoint submission, and
releases only after an interpretable terminal plus physical zero-GPU proof.
