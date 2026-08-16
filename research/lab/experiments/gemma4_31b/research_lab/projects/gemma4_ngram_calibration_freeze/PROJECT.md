# Calibrated immutable NGRAM corpus

## Question

Can a short, disjoint calibration prefix build the useful native NGRAM corpus,
after which suppressing every write preserves exact semantics and long common
trunks at the campaign's `$0.14/M` planning target?

This tests a materially different production policy from request-local merge,
support-two promotion, and completed-request commit. Reads remain the stock
global depth-12 BFS path. Requests 0–31 are calibration only; the measured
candidate is requests 32–790 with all corpus writes disabled before request 32
is released.

## Why this matters

Three live-write policies have failed in different ways:

- support-two retained long trunks and reached `$0.1393159641142523/M`, but
  diverged once at request 790;
- completed-request commit diverged at request 78, collapsed unaffected
  accepted depth to median/p10 4, and cost `$0.14379282819540207/M`;
- request-local merging diverged earlier and was much more expensive.

If a corpus calibrated only on the first 32 requests remains useful and exact
for the following 759 requests, ongoing global mutation—not the native
read/verification path—is the actionable cause. If it still diverges, the
parallel upstream-runtime project has direct evidence that write admission is
not sufficient.

## Bound evidence and identities

Mechanically verify `DIRECTOR_BINDING.json` before implementation. The exact
model, digest image, pinned runtime source, launch, requests, semantic rows,
and two predecessor terminals are bound there. Do not infer from stale bench
description fields.

Evidence labels:

- predecessor endpoints, semantics, and economics: measured;
- source/identity constraints: measured/content-addressed;
- calibration-freeze hypothesis: inferred until this candidate completes.

## Intervention

1. Start from a clean pinned SGLang v0.5.13 server using the exact bound model,
   FP8 stack, E5M2 page-1 KV, and native depth-12 NGRAM.
2. Release only requests 0–31 for calibration and wait for all 32 to complete.
   They are not part of the primary economic or semantic result.
3. Persist a positive activation record containing the corpus state/hash,
   calibration request identities, row count, and the exact transition after
   request 31 completion.
4. Before releasing request 32, make global corpus writes fail closed to a
   no-op. Preserve stock global reads, breadth, depth, target verification,
   tree topology, scheduler, cache, accepted-token mapping, and cleanup.
5. Release requests 32–790 individually with their original inter-arrival
   deltas shifted so request 32 begins at time zero. Measure all 759 requests.
6. Run the 1,036-request full-arrival endpoint only if activation is proved,
   normalized semantics are exact, failures are zero, unaffected trunks remain
   long, queue and release gates pass, and planning cost is at most `$0.14/M`.

No control or settled candidate may be replayed.

## Gates

The 759-request discriminator passes only when:

- every request completes with zero failures;
- every normalized semantic row 32–790 matches its bound row exactly;
- activation proves no corpus write occurred after calibration;
- at least eight unaffected post-request-790 trace samples have median
  accepted drafts at least 10 and p10 at least 8;
- peak server queue is at most 30 and final queue is zero;
- release drift is stable;
- planning cost is at most `$0.14/M` total tokens.

Any semantic mismatch, post-calibration write, missing activation/trace,
reliability failure, trunk collapse, queue miss, or economic miss consumes and
rejects this candidate. The conditional endpoint must not run.

## Exclusions

- No request-local tree, support-two, completion buffering, state aging,
  adaptive depth, breadth/frequency/threshold change, target-verification
  patch, output normalization, semantic exception, scheduler arm, or runtime
  replacement.
- No setting, calibration-size, freeze-boundary, or corpus-content sweep.
- No replay of stock, request-local, support-two, completed-request, or other
  settled arms.
- Researchers may claim/release only the registered retained bench. Provider
  lifecycle mutation is forbidden.

## Resources and limits

- Authorized spend: `$3` cumulative.
- H200 compute: at most 35 claimed minutes including setup and failures.
- Wall clock: 55 minutes.
- Local compute: at most 1 CPU-hour.
- Storage: at most 5 GiB project-local.
- Bench: `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`.
- Release: earlier of 35 claimed minutes or `2026-07-25T06:00:00Z`, under the
  verified `06:15Z` watchdog.

Required artifacts are the verified binding, immutable implementation/launch
packet, activation proof, calibration record, per-request semantics and
arrival timing, acceptance/target-verification telemetry, queue/GPU telemetry,
planning-cost calculation, typed terminal, and release snapshot.

