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
