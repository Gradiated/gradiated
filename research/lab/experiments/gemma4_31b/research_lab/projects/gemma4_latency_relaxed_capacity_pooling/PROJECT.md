# Gemma 4 latency-relaxed capacity pooling

## Question

Can admission-controlled c32 batch formation and replica pooling reduce the
exact qualified Gemma 4 workload's sustainable all-in cost toward the locked
20% target by spending background-agent queueing latency, without assuming a
faster GPU kernel or changing model outputs?

This is a scheduling and workload-economics hypothesis, independent of the
unmeasured H100, B200, and MI355X hardware candidates.

## Bound scope

- Model: `google/gemma-4-31B-it` at revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Workload: text-only, non-reasoning traffic around 4,214 prompt and 358
  output tokens per request, c32 saturation geometry, and the campaign's
  prefix-cache accounting.
- Qualified service-time denominator:
  `0.625149101968745 s/request`.
- Locked target at unchanged hardware price:
  `0.500119281574996 s/request`, approximately `$0.109725/M` total tokens at
  the existing 90%-utilization planning mapping.
- Bound input:
  `../gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/QUALIFIED_LATEST_TERMINAL.json`
  with SHA-256
  `b02d02c2283f5a018384cacf6522e123ce8e603ad0cfa2cd2c61ed6cb9eda363`.
- Do not replay a GPU sample, transfer B200/MI355X analytical speed, assume
  c48/c64 gains, or convert utilization into reduced device service time.

## Immediate evidence path

Build a deterministic trace-driven or uncertainty-bounded discrete-event
simulator. Use existing content-addressed qualified request/service rows when
available; otherwise use explicitly synthetic arrival and service
distributions constrained by the durable mean and any durable quantiles, and
label the weaker boundary.

Compare at least:

1. the current fixed c32/90%-utilization planning policy;
2. admission-controlled wait-to-fill c32 with bounded queue delay;
3. pooled replicas with failure/reload reserve and burst-aware routing; and
4. a deliberately latency-relaxed background policy at p95 queueing budgets
   of 5, 15, 30, and 60 seconds.

For each, report achieved utilization, queue and completion p50/p95/p99,
requests dropped or timed out, replica/headroom requirement, failure/reload
reserve, and fresh-input/cache-read/output plus blended dollars per million
tokens. Separate measured, derived, inferred, and synthetic quantities.
Include sensitivity to burstiness, arrival-rate error, and one replica loss.

The candidate must be an executable admission/routing policy, not a capacity
spreadsheet. If no policy can reach the locked cost target without an
unmeasured service-time gain or unusable queueing/reliability, return the
negative bound and quantify the remaining physical speedup required.

## Terminal

Write `LATENCY_RELAXED_POOLING_SCREEN.json` as exactly one of:

- `source_complete_pooling_candidate`: one executable policy reaches the
  locked all-in target under a product-usable latency/reliability point and
  remains within the bound service evidence; or
- `typed_none`: queueing, utilization, headroom, or reliability cannot close
  the target, with the best attainable cost and residual speedup requirement
  preserved.

Planning prose, an unconstrained utilization ratio, or a GPU-readiness packet
is not a terminal.

## Budgets

- Wall clock: 120 minutes.
- Compute: at most 8 local CPU-hours; zero accelerator compute.
- Storage: at most 2 GiB of new durable artifacts.
- Provider spend: `$0.00`.
- Provider contact, mutation, and GPU claims: forbidden.
