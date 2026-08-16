# NGRAM sparse penalty verification

## Question

Does the dense large-vocabulary penalty application immediately before greedy
NGRAM verification remain a material H200 throughput boundary after removing
its allocator staircase, and can one sparse or consumer-fused application
stabilize the fixed arrival trajectory without changing results?

## Why this matters

The allocation-attribution project proved that
`BatchedPenalizerOrchestrator.apply` creates a maximum
`[384, 262144]` FP32 temporary while verifying 12 draft tokens per request.
Broadcast reuse removed 4,648 MiB, or 90.08%, of the HBM staircase with
1,036/1,036 exact output-token, finish-reason, and usage matches. Sustainable
throughput did not recover: final client drift remained 7.858 seconds and the
last-100 slope remained +0.042519 seconds/request.

The exact workload is greedy (`temperature=0`) with `min_new_tokens=358` and
`ignore_eos=true`. The installed path calls
`penalizer_orchestrator.apply(logits, repeat=12)` immediately before
`NgramVerifyInput._greedy_verify`. This makes an effectively sparse penalty
set—possibly only the EOS/min-new-token constraint—a high-information
candidate for eliminating a full-vocabulary read/write pass rather than only
its temporary allocation.

## Scope and immediate experiment

Use `$kernel-research` for the exact source/consumer boundary. Hash-check
`DIRECTOR_BINDING.json`, atomically claim the retained H200, and capture the
installed penalty classes, `NgramVerifyInput.verify`, greedy verifier, and
sampling consumer from the healthy retained container before mutation.

Freeze one exact real-call component at draft count 12 and production
batch/vocabulary geometry. Record active penalizer classes, nonzero additive
coordinates, bytes touched, kernel/launch time, and selected-token semantics.
If the active penalty is sparse and the pass has a credible positive
whole-request bound, implement exactly one source-specific intervention:
direct sparse-column application or a fused penalty/greedy consumer. Do not
run a broad kernel, block-size, or scheduler sweep.

Run one correctness-bearing captured-call component against the installed
broadcast implementation. Only an exact, credibly positive component admits
one candidate-only fixed 1,036-request trajectory against the bound request
comparator. Compare index-aligned output tokens, finish reasons, usage,
failures, retractions, final queue, release drift, throughput, and planning
cost. Replay no stock, broadcast-only endpoint, leaf-split, QLEN, ring,
quality, c32, or 10K arm.

## Resources and bounds

- Bench: `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`.
- Model/checkpoint/image/workload identities are mechanically bound in
  `DIRECTOR_BINDING.json`.
- The loaded broadcast-reuse container is a read-only source/runtime donor
  until the project claims the bench.
- Use one controller-host PID-managed outer owner and
  `research/factory/tools/artifact-snapshot` for every retrieval.
- Maximum authorized spend: $8 cumulative.
- Maximum claimed H200 time: 70 minutes.
- Maximum new storage: 15 GB.
- Release by 2026-07-24T22:20:00Z under the verified 22:30Z watchdog.

## Decision rule

Retain a candidate only with exact component and endpoint semantics, zero
failures/retractions, an empty final server queue, planning cost at or below
$0.14/M tokens, final release drift no greater than one 0.694610-second
arrival interval, and no positive late-run drift. A negative component closes
only this penalty-application mechanism.
