# L40S KV4-outlier SM89 component

## Question

Does the source-complete local D256 group-64 KV4 plus four-E5M2-outlier
producer and fused paged-attention consumer compile correctly on SM89 and beat
the strongest current-runtime E5M2 local-KV consumer after charging both KV
packing and attention on the exact c32 decode geometry?

## Why this changes the portfolio

The representation has a deterministic CPU numerical positive: corrected
attention output improved from `0.707343` to `0.056208` relative L2 with
cosine `0.998419`. Its CUDA source is nevertheless unexecuted. The later
fixed-`0.953` endpoint allocation consumed no claim or scientific sample
because its owners failed at inventory selection. A checkpoint-free component
is now the shortest real CUDA discriminator: it can reject compile, resource,
correctness, or physical-performance failure without another checkpoint
transfer or model load.

A positive component would justify preserving the representation for a later
scope-matched endpoint when authority exists. A negative complete
producer-plus-consumer bound closes this SM89 implementation without spending
the campaign remainder on a full endpoint.

## Bound identities

- Model geometry: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`
- Runtime: official SGLang commit
  `c6a6200a1a778a799ba61c395ac292317f01ebc9`
- Target: one NVIDIA L40S, Ada SM89
- Workload geometry: c32 decode, local window 1,024, page size 1, 32 query
  heads, 16 KV heads, head dimension 256, and 358 output steps
- Candidate producer SHA-256:
  `6d8a84bd5ef5a1fbacbd95a99e1aa7c180b8d39e590ee1fd657d2da51e4e3944`
- Candidate adapter SHA-256:
  `16bd6477f1be675bbae83492f057fcb37496026ebf1d7ab9c43e9193d66b8163`
- Numerical terminal:
  `../gemma4_l40s_local_kv4_outlier_codesign/L40S_LOCAL_KV4_OUTLIER_OFFLINE_TERMINAL.json`
- Endpoint lifecycle evidence:
  `../gemma4_l40s_kv4_outlier_allocator_rebase_endpoint/STATUS.json`

Mechanically extract and verify source, model, runtime, and workload hashes
from those artifacts. Do not read checkpoint shards or hand-transcribe new
identities.

## Immediate experiment

Within 75 wall-clock minutes, use `$kernel-research` to implement one
lifecycle-pure exact component runner and one bounded cold-L40S owner. Persist
`L40S_KV4_OUTLIER_SM89_COMPONENT_READY.json` with:

1. direct hashes of the unchanged producer, fused consumer, runtime seam,
   strongest current-runtime E5M2 comparator, and exact component runner;
2. a real candidate-versus-E5M2 invocation covering production c32 request
   isolation, window/page boundaries, local-to-global isolation, and finite
   numerical correctness under a justified tolerance;
3. separate compile/setup time and repeated steady-state timing for E5M2,
   KV4 packing, and corrected paged attention;
4. compiler registers, spills, shared memory, launch geometry, and allocated
   memory when available from the same component invocation;
5. complete physical and locked-request bounds across 50 local layers and 358
   decode steps without crediting dependent synchronization or omitted
   packing; and
6. an atomic-claim, heartbeat, typed-retrieval, expected-claim-generation
   release owner that retains ordinary pre-science compile/API defects for
   bounded repair.

Do not run CUDA in this offline turn. The runner must reach the real custom
consumer rather than stop at source import, extension loading, or a smoke-only
finite output.

## Decision contract

Promote only if the exact SM89 candidate compiles without nonfinite output or
request/transition corruption and its complete producer-plus-consumer bound is
positive versus the current-runtime E5M2 comparator. Report the measured
component delta and a conservative whole-request bound; do not call it an
endpoint result.

Return typed negative for unsupported compilation, spills/resource use that
invalidates the production shape, incorrect outputs, or a nonpositive complete
bound. Do not tune after the preregistered invocation.

## Resources and prohibitions

- Cumulative spend request: `$0.40`
- Later maximum provider lifecycle: 27 wall-clock minutes
- Conservative exposure: `$0.388342485` at the measured
  `$0.8629833/hour` L40S rate
- Researcher profile: `deep`

This request is not provider authority. Do not create or claim a GPU, use SSH
or provider APIs, run CUDA, pull an image, or invoke an endpoint until a later
director observes both the exact durable reservation and the positive
hash-bound readiness terminal. The paid invocation is checkpoint-free: do not
stage model weights, start a model server, or consume an endpoint request. Do
not sweep group size, outlier count, page size, batch, window, compiler flags,
kernels, or timing geometry.
