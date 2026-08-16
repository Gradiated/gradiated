# Qualified NGRAM wave frontier stack

## Question

Can the previously sustainable 32-request NGRAM wave admission become an
exact, economically positive production placement when it is stacked with
the already-proven broadcast penalty reuse and direct sparse min-new-token
update?

## Evidence and scope

The fixed-wave run completed all 32 full waves in `17.384-17.685 seconds`,
below their frozen `22.227523626-second` release period, with zero failures
or server queue. Its all-in planning cost was `$0.140121840/M`; only the
finite 12-request tail waited behind wave 32. The broadcast-reuse candidate
was exact `1,036/1,036` and removed `4,648 MiB` of allocator growth. The
direct sparse penalty update was exact and cut the real penalty-plus-greedy
component by `84.42%`.

The threshold-8 ordinary-decode bypass is now closed. Its full trajectory
completed all 1,036 requests but matched only 1,034 token sequences, reduced
throughput by `3.216%`, increased late queue slope from `0.03827` to
`0.13118 seconds/request`, and raised planning cost by `3.323%` despite
removing `71.75%` of target rows. This project must not reuse that bypass.

## Frozen experiment

Consume and hash-check `DIRECTOR_BINDING.json`. Claim retained bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc` once and run exactly one
candidate-only fixed 1,036-request trajectory:

- preserve the qualified depth-12 native NGRAM runtime at every load;
- preserve all request bodies, original arrival timestamps, unique suffixes,
  max-running 32, model, checkpoint, FP8 weights, page-1 E5M2 KV, and NGRAM
  settings;
- use the exact prior wave policy: release each consecutive group of 32 when
  its 32nd arrival exists and the prior wave has completed, then release the
  final 12-request tail after the fixed trace ends;
- stack only the source-bound broadcast view of the repeated penalty tensor
  and the exact direct min-new-token column writes;
- keep full NGRAM target verification. Do not load the threshold-8 bypass,
  truncate a tree, split verification, or alter admission size/rate.

Persist index-aligned output-token matches, finish reasons, usage, failures,
all wave release/completion spans, cross-wave drift, final-tail wait, client
latencies, queue depth, NGRAM acceptance, cache/HBM realization, target
forwards, total tokens, elapsed time, and all-in provider/planning economics.
Use the persisted fixed-wave and rolling terminals as comparators; replay no
control, wave, sparse, broadcast, quality, component, prefix, suffix, or
bypass arm.

## Decision gate

Retain this stack only if all 1,036 token sequences, finish reasons, and usage
match the persisted comparator, failures and server queue are zero, every
full wave completes before the next `22.227523626-second` release, cross-wave
drift does not grow, the finite tail completes within one full-wave service
window, and planning cost is at most `$0.14/M` total tokens. A semantic miss,
growing full-wave drift, or non-positive economics closes this exact stack.

## Limits

- Priority: `8200`.
- Researcher profile: `execution`.
- Authorized spend: `$3`.
- Compute: one unconsumed candidate trajectory on the retained H200, release
  by `2026-07-25T02:20:00Z`. The invalid pre-science claim is recorded
  separately and does not consume the scientific arm.
- Cleanup watchdog: verified through `2026-07-25T02:30:00Z`.
- Storage: at most 6 GiB of new project-local artifacts.
- Provider creation or deletion: forbidden to the researcher.
