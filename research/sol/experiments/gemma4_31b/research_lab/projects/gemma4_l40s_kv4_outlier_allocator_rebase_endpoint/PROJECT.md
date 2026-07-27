# L40S KV4-outlier allocator-rebase endpoint

## Question

Can the source-complete local D256 group-64 KV4 plus four-E5M2-outlier
representation run the exact Gemma 4 c32 endpoint on one L40S when the
inherited `--mem-fraction-static 0.85` launch contract is replaced by one
preregistered `0.953` split, and does the resulting price-normalized service
time beat `1.4776251501079425 s/request`?

## Why this changes the portfolio

The predecessor terminal closes only the unchanged-`0.85` placement. Its
candidate-favorable static interval is `45,077,378,048` to
`46,028,104,408` bytes against `48,305,799,168` exposed bytes. The fixed
`0.953` split admits that conservative static upper bound by `7,322,199`
bytes while retaining `2,270,372,561` bytes (`2.114449 GiB`) for dynamic
state. This is tight enough that only the real allocator, compile, model load,
and endpoint can decide fit. The representation is numerically promising:
the checkpoint-free exact D256/window-1024 oracle improved complete-output
relative L2 from `0.707343` to `0.056208` with cosine `0.998419`.

A passing endpoint would establish a materially cheaper placement candidate
for the campaign's locked `0.500119281574996 s/request` H200 target. An OOM,
unsafe output, failed exact consumer, or slower price-normalized result closes
this allocator-rebased placement without sweeping memory fractions.

## Bound identities

- Model: `google/gemma-4-31B-it`
- Revision: `b9ea41a2887d8607f594846523f94c6cc75ac8a4`
- Runtime: official SGLang commit
  `c6a6200a1a778a799ba61c395ac292317f01ebc9`
- Target: one NVIDIA L40S, Ada SM89, `46,068 MiB` measured exposed memory
- Workload: exact content-addressed c32 campaign mix, 4,214 prompt tokens,
  358 output tokens, 535 shared-prefix tokens, page size 1, TP1
- Representation source terminal:
  `../gemma4_l40s_local_kv4_outlier_codesign/L40S_LOCAL_KV4_OUTLIER_OFFLINE_TERMINAL.json`
- Terminal SHA-256:
  `c0a732ef5cf42cb5744a19afab0fe2734ad37cbd5d720ebcc4a16e02a856cfc2`
- Producer SHA-256:
  `6d8a84bd5ef5a1fbacbd95a99e1aa7c180b8d39e590ee1fd657d2da51e4e3944`
- Runtime adapter SHA-256:
  `16bd6477f1be675bbae83492f057fcb37496026ebf1d7ab9c43e9193d66b8163`
- Fixed allocator intervention: `--mem-fraction-static 0.953`

Extract and verify these identities mechanically from the named terminal.
Do not hand-transcribe or silently substitute checkpoint, runtime, workload,
representation, or source bytes.

## Immediate experiment

Within 45 wall-clock minutes, implement one bounded cold-L40S detached owner
and persist `L40S_KV4_OUTLIER_ENDPOINT_OWNER_READY.json`. The owner must:

1. atomically claim only a later director-bound L40S bench, heartbeat the
   exact claim generation, and release with `--expected-claimed-at`;
2. pull only the pinned runtime image and stage the exact checkpoint,
   tokenizer, configuration, and representation integration needed by the
   endpoint;
3. build and load the bound producer and fused SM89 paged-attention consumer;
4. launch one candidate endpoint with the fixed `0.953` split;
5. run exactly one exact c32 campaign workload after a durable
   `science_started` marker;
6. retrieve raw responses, token/cache accounting, timing, memory, failures,
   and a typed terminal; and
7. retain the same claim for bounded hash-bound repair of ordinary pre-science
   build, path, API, mount, or startup defects while the scientific arm is
   unconsumed and the absolute window still fits.

Readiness checks should cover hashes, syntax, owner time bounds, liveness
handling, terminal schema, and cleanup disposition. They must not simulate
CUDA or the full detached lifecycle.

## Decision contract

Pass only if the exact endpoint:

- loads without exceeding exposed memory or weakening the fixed c32 workload;
- reaches the bound local producer and fused consumer for all 50 local layers
  while leaving all 10 global E5M2 layers unchanged;
- produces finite, structurally valid responses with complete request,
  token, cache, and failure accounting;
- records the maximum allocated/reserved memory and dynamic allocator margin;
- has conservative service time at or below
  `1.4776251501079425 s/request` at the campaign's price-normalized boundary;
  and
- persists the exact raw evidence needed for later GPQA-Diamond, TauBench,
  tool-path, and reliability validation. This exploratory arm does not itself
  establish production quality.

Return typed negative on OOM, consumer non-reachability, nonfinite or
structurally invalid output, missing accounting, or a slower complete bound.
Do not sweep allocator fractions, concurrency, batch geometry, cache
representation, outlier count, group size, runtime revisions, or kernels.

## Resources and prohibitions

- Cumulative spend request: `$0.59`
- Maximum provider lifecycle after later authorization: 40 wall-clock minutes
- Conservative lifecycle exposure: `$0.5753222` at the measured
  `$0.8629833/hour` L40S experiment rate
- Researcher profile: `execution`

The request is not provider authority. Do not create, claim, use SSH, stage a
checkpoint, run CUDA, or call an endpoint until a later director observes the
exact durable reservation, creates and identity-verifies the L40S, and binds
the owner to that live bench. Do not replay the expired L40S affine packet,
the closed H200 group-64 kernel, or the predecessor's frozen-`0.85` question.
