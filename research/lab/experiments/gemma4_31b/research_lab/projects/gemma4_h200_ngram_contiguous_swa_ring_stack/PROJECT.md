# Stack the contiguous local-SWA ring into qualified NGRAM

## Question

Can the already-retained contiguous E5M2 local-SWA ring cache compound with
the quality-qualified NGRAM endpoint and its 32-request background-wave policy,
reducing sustainable H200 cost without changing model, draft, attention, or
request semantics?

## Evidence and mechanism

This is a direct stack of two measured survivors, not a new cache design.
`gemma4_h200_swa_contiguous_ring_cache` bound fresh extend bytes from stock
`swa_out_cache_loc`, proved cache-transition bytes exact through the first two
decode steps, passed collision-free request ownership and padded-row no-op
semantics, and improved its c32 endpoint from
`0.6766461551248995` to `0.6556567115001144 s/request`, a
`3.1019822496%` reduction. Its exact local-consumer component improved
`24.8346481%`. The retained manifest freezes the implementation; do not
redesign its ownership or ring geometry.

The qualified NGRAM endpoint uses the same pinned SGLang, Gemma checkpoint,
E5M2 KV representation, 50 local layers with a 1,024-token window, ten global
layers, page size one, and c32 capacity. Its target verification adds exactly
12 query rows per request. The corrected trace reports 900 target-verification
attention launches across 15 steps, or 50 local and ten global layers per
step, making the proven local-ring boundary directly relevant.

The retained background policy releases 32-request waves every
`22.227523626 s`. Its 32 full waves completed in
`17.383966674-17.684530306 s`, leaving at least `4.542993320 s` headroom and
planning at `$0.1371562936/M`. The finite 12-request tail pushed the measured
run to `$0.1401218397/M`; a compatible c32 service reduction can move the
complete finite trace below the campaign's `$0.14/M` target while increasing
steady-state margin.

The exact M384 `1x2x1` cluster orientation is closed: it reached all six live
real-weight shapes, reduced modeled CTA count, but produced divergent or
nonfinite outputs and regressed aggregate medians by orders of magnitude.
Do not repair or replay that schedule. QLEN masks, another attention tile, and
quantization fusion are also outside this project.

## Experiment

Use `$kernel-research` as implementation guidance, but keep this project on
the `execution` researcher profile because the cache mechanism, source, and
repair history are settled. Hash-check `DIRECTOR_BINDING.json` and freeze the
exact files named by the retained ring manifest. Adapt only their established
producer, ownership, and local-consumer hooks to the pinned NGRAM target
verification path:

- local layers use the retained request-owned contiguous circular E5M2 ring;
- global layers remain on the stock paged E5M2 path;
- local window, query/KV heads, head dimensions, scales, page-1 stock
  reference, QLEN masks, M64 tile, NGRAM draft depth and tree semantics remain
  unchanged;
- the 32-request wave policy and every request byte remain unchanged.

First run one exact real-transition component at c32 and `Q=12`. It must cover
all 50 local target-verification consumers, the actual fresh-extend and decode
producer transition, prefix restoration, wrap behavior, request-slot reuse,
dynamic ordering, and padded graph rows. Compare all 12 target-verification
query outputs to the stock paged consumer under the unchanged numerical
oracle. Require exact cache-transition bytes, exact ownership/accounting,
complete candidate-path audit rows, and a positive repeated timing bound. The
ten global layers must remain on the stock path.

Only an exact positive component admits one candidate-only full
1,036-request trajectory using the frozen arrival rows: 32 full c32 waves and
the 12-request tail. Compare it to the persisted wave terminal and steady-state
disposition; do not replay stock. Record wave release drift, server span,
upstream queue, failures, completion/usage/finish accounting, token IDs,
accepted draft telemetry, power, utilization, HBM, cache accounting, and
component-wise production economics. Raw response hashes are not a semantic
comparator. The fresh matched GPQA-Diamond/TauBench terminal remains the
product-quality authority.

Use one durable controller-host outer owner for heartbeats, retrieval, cleanup,
settlement, and release. On an ordinary path/import/staging/consumer defect,
use the shared repair handshake and resume only the invalidated stage in the
same claim. Do not release a healthy warm claim merely to request a repair.

Do not replay the stock endpoint, wave control, ring control, quality suites,
10K view, rolling stream, critical-path trace, QLEN, M384 component, or any
consumed arm. Run no ring-size, wave-size, rate, draft-depth, tile, precision,
backend, concurrency, or scheduler sweep.

## Decision

Retain the stack if:

1. the c32 Q12 local target-verification component is exact, correctly routes
   all 50 local layers and leaves all ten global layers stock, and has a
   positive conservative whole-request bound;
2. all 32 full waves finish before the next `22.227523626 s` release with no
   upstream queue or failures;
3. the candidate preserves request, completion-token, usage, finish-reason,
   cache, and tool/task payload semantics, with no material regression beyond
   the persisted control's single localized synthetic token-ID difference;
4. the complete finite trace plans at no more than `$0.14/M`, while the
   steady-state cost remains stable and no worse than `$0.1371562936/M`.

An exact but non-positive component, an exact non-positive candidate, or a
valid economic/semantic failure closes only the interaction between the
retained ring and qualified NGRAM. An ordinary integration failure is not a
scientific close; repair it once in the same retained environment without
replaying valid stages.

## Resources

- Priority: `7500`
- Researcher profile: `execution`
- Authorized cumulative spend: `$8`
- Bench: retained `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`
- Compute: at most 60 claimed H200-minutes
- Wall clock: complete and release by `2026-07-24T18:50:00Z`
- Storage: at most 10 GiB of new project-local artifacts
- Provider mutation: forbidden

## 2026-07-24 director continuation — repair the live suffix

The first integrated trajectory does not close this stack. Its real first
extend contained 2,048 tokens, but the local ring has 1,024 physical slots.
The producer issued both logical halves to the same destinations, and the
observer then reread all 2,048 logical positions after the ring had wrapped.
Exactly 1,024 K tokens and 1,024 V tokens matched stock. One member of every
aliased position pair must differ after overwrite, so the reported whole-row
relative errors do not establish a mismatch in the live 1,024-token window.

Consume `DIRECTOR_REPAIR.json`. Preserve the positive component without
replay. Starting from the hash-bound post-null-guard patch, filter the
canonical paged E5M2 producer bytes, request IDs, and absolute positions to
each request's last `min(extend_len, 1024)` current tokens before the Triton
store. This removes duplicate destinations rather than depending on their
write order. Apply the identical live-suffix mask to the transition observer.

Run one real 2,048-token extend discriminator. Require exact live-suffix K/V
bytes, no duplicate physical destinations, and exact stock-versus-ring output
for the first local consumer and first subsequent Q12 target-verification
transition. Reuse all other exact component evidence. Only that pass admits
one resumed candidate-only 1,036-request trajectory; the earlier stop produced
no complete interpretable wave sample. Do not replay stock, the positive
component, or any consumed project.

This continuation remains `execution`: the physical cause and exact source
boundary are localized. If the live suffix or first real consumer still
diverges, or if the repaired trajectory is semantically or economically
non-positive, close the ring-plus-NGRAM interaction.
