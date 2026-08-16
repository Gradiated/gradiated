# Research log

## 2026-07-25 — deterministic H100 replica-headroom replay

**Question.** Does the settled H100 v0.5.15 NGRAM service rate remain below
`$0.14/M` after discrete replicas and the exact 1,036-row demand trace?

**Action.** Hash-bound the settled 171-request terminal
(`c068fd…951bf`) and request trace (`10e7ed…46135`), then ran the project-local
deterministic FIFO, earliest-free-replica replay. Service time is constant per
request; the sensitivity is explicitly `0.8x`, `1.0x`, and `1.2x` of the
measured `0.7073339939 s/request`, with no invented service distribution.

**Evidence.** The trace is 1,036 ordered requests, 4,736,592 total tokens, and
718.921467 seconds of arrivals. At 90% headroom, the central service rate needs
two replicas; their finite-trace utilization is 50.915% over the drain span,
with zero FIFO wait and a 0.707334-second p95 latency in this constant-service
model. The planning-rate continuous 90%-utilization model is `$0.133700/M`,
but the discrete two-replica trace-provisioned result is `$0.236335/M`
(`$0.248996/M` at the actual `$2.95/h` rate). A one-replica fleet needs at most
`0.624546 s/request` to preserve 90% headroom—an 11.704% reduction from the
settled rate. Full result: `HEADROOM_RESULT.json`.

**Interpretation.** This is analytical, not an endpoint measurement. The
pending endpoint's exact `service_seconds_per_request` and queue trajectory
are decisive: service at or below the one-replica ceiling removes the discrete
two-replica cost step; otherwise sustained pooled demand near 90% utilization
is required for the continuous planning estimate to apply.

**Next.** Consume no further H100 work here. Let the sole 791-request direct
endpoint provide its measured service time and queue fields.

## 2026-07-25 — background buffering and retail-overflow frontier

**Question.** Can background queueing or minimal retail spillover avoid the
two-H100 step without presenting finite draining as sustainable demand?

**Action.** Verified the five hashes in `DIRECTOR_BACKGROUND_OVERFLOW_BINDING.json`,
reproduced the two-replica control, and ran deterministic one-H100 FIFO
replays for the finite trace, 64 periodic repetitions, and every 0/1/5/10/30/
60/120-second local-wait cap. Greedy overflow is the minimum required to honor
each cap for this fixed constant-service FIFO model.

**Evidence.** One local H100 drains the finite trace with 13.169216 seconds
maximum wait but grows 13.876550 seconds per repeated period, reaching an
888.099228-second extension at period 64. Periodic one-second caps spill 20
requests (91,440 tokens) per period and cost `$0.120663/M` planning at the
capability-listed retail tier and `$0.120715/M` at the methodology-matched
tier—both below their frozen retail comparators. The nominal tier is
`$0.120349/M`, above its `$0.119/M` comparator. Full source-bound evidence is
in `BACKGROUND_OVERFLOW_RESULT.json`.

**Interpretation.** `endpoint_dependent_nominate`: finite buffering alone is
rejected as non-sustainable; bounded overflow is an analytical viable
capability/methodology cost point pending the exact 791-request service field.
No retail latency or reliability is claimed.

**Next.** Do not claim or inspect the live H100. Reconcile this frontier only
when the direct endpoint supplies an exact `service_seconds_per_request`.

## 2026-07-25 — measured-endpoint overflow reconciliation

**Action.** Verified the reconciliation's six content hashes, reproduced the
prior 0.707333994-second control, then replayed the measured 791-request
prefix at 0.780757973 seconds/request and separately extrapolated all 1,036
requests at that rate.

**Evidence.** The measured prefix's finite one-H100 wait reaches 68.057 seconds
and its 64-period drain extension reaches 4,405.604 seconds. Its one-second
periodic cap spills 88 requests at `$0.133066/M` capability-listed and
`$0.133369/M` methodology-matched. The 1,036-row extrapolation reaches 89.163
seconds finite wait, 5,756.403 seconds periodic extension, and needs 115
one-second-cap spills. Exact frontiers and actual-rate values are in
`ENDPOINT_OVERFLOW_RESULT_20260725.json`.

**Interpretation.** Deployment reject: the endpoint has normalized semantic
divergence at request 277. These economics remain analytical and cannot be
promoted without a semantic repair.
