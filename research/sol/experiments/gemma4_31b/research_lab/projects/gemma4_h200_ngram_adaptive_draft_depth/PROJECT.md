# Load-adaptive NGRAM draft depth

## Question

Can one load-adaptive NGRAM draft-depth rule remove wasted high-concurrency
target-verification work and make the fixed arrival trajectory sustainable
without changing deterministic outputs?

## Evidence and physical hypothesis

The retained direct sparse-penalty change is exact and stackable: it removes
an 805,306,368-byte dense penalty pass and cuts the real max-shape
penalty-plus-argmax component from 1.193312 ms to 0.185936 ms. The endpoint
improves only about 0.107%, however, and still ends 7.095 seconds behind the
arrival schedule.

The same measured endpoint exposes a load-dependent NGRAM efficiency
transition. With 1–7 running requests, mean accepted length is 11.876 of the
12 verified drafts. With 8–23 it falls to 5.255, and with 24–31 it is 5.103.
The verifier nevertheless evaluates 12 target rows per request. The frozen
hypothesis is that at eight or more running requests, verifying six drafts
will preserve nearly all accepted work while roughly halving high-load target
rows; below eight requests, depth 12 remains efficient.

## Frozen intervention and experiment

Hash-check `DIRECTOR_BINDING.json`. Inspect only the bound installed
`ngram_info.py`, `ngram_worker.py`, scheduler batch source, and the exact
draft-depth producer. Stack the retained direct sparse min-new-token update.
Freeze exactly this rule:

- running requests 1–7: draft depth 12;
- running requests 8 or more: draft depth 6.

Do not sweep thresholds or depths. Atomically claim the retained H200 and use
one controller-host PID owner. First capture one real high-load target-verify
call proving six rows per request, unchanged greedy consumer behavior, and
exact accepted/bonus tokens versus the bound depth-12 call. Repair only
ordinary source/integration defects in the same claimed environment.

On exact component semantics, run one candidate-only fixed 1,036-request
trajectory against the bound sparse-penalty comparator. Compare index-aligned
output tokens, finish reasons, usage, failures, retractions, target rows,
acceptance length/rate by concurrency, final queue, release drift, throughput,
and planning cost. Replay no stock, sparse-only endpoint, QLEN, ring,
leaf-split, allocator, quality, c32, or 10K arm.

## Resources and limits

- Bench: `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`.
- Exact checkpoint, image, model revision, workload, comparator, sparse patch,
  and telemetry identities are bound in `DIRECTOR_BINDING.json`.
- The healthy sparse-penalty server is a read-only source/runtime donor until
  claim.
- Maximum authorized spend: $8 cumulative.
- Maximum claimed H200 time: 50 minutes.
- Maximum new storage: 12 GB.
- Release by 2026-07-24T22:20:00Z under the verified 22:30Z watchdog.
- Use `research/factory/tools/artifact-snapshot` for every retrieval.

## Decision rule

Retain the adaptive rule if all 1,036 output-token sequences, finish reasons,
and usage rows match, failures and retractions are zero, the final server
queue is empty, planning cost is at or below $0.14/M tokens, and final client
release drift is no more than one 0.694610-second arrival interval with no
positive late-run slope. A negative result closes this one threshold/depth
rule, not NGRAM scheduling generally.
