# H100 sustainable replica-headroom replay

## Question

Does the settled H100 v0.5.15 NGRAM service rate remain at or below the
campaign's approximately `$0.14/M` total-token target after explicit queueing,
replica headroom, and burst absorption on the exact 1,036-row arrival trace?
If not, what endpoint service-time ceiling would make it sustainable?

## Why this matters

The paid H100 lane directly measures the sole 791-request endpoint, but its
settled 171-request discriminator currently supports only a 90%-utilization
planning estimate. Production economics also require discrete replicas,
queue stability, latency headroom, and the exact prompt-heavy request mix.
This project can quantify that boundary without using or delaying the H100.

## Bound evidence

- Settled discriminator:
  `../gemma4_h100_v0515_ngram_price_normalized/artifacts/h100-repair5-20260725t0746z/FINAL_TERMINAL.json`
  (`171` requests, `0.7073339939181298 s/request`, `781812` total tokens,
  queue peak `14`, queue final `0`, no failures).
- Exact arrival and token trace:
  `../gemma4_h100_v0515_ngram_price_normalized/packet/candidate-v0.5.15/inputs/requests.jsonl`
  (`1,036` content-bound rows).
- Direct-lane binding:
  `../gemma4_h100_v0515_ngram_price_normalized/DIRECTOR_200GIB_ENDPOINT_BINDING.json`
  SHA-256
  `9e39c7705391708fcaa43360d961478e5b57014e06db2bc79e9adcfd5f9e6b2d`.

## Scope

Build a deterministic discrete-event replay from the bound scheduled times,
token counts, and request order. Use the measured discriminator service rate
as the central estimate and an explicit sensitivity envelope rather than
inventing a per-request distribution. Report:

- minimum stable replica count and utilization;
- queue peak, final queue, and latency percentiles under each admissible
  replica/headroom point;
- total-token cost at the campaign's committed H100 planning rate and at the
  actual experiment rate, with assumptions labeled;
- the maximum endpoint seconds/request consistent with `$0.14/M` after the
  selected headroom; and
- which measured field from the pending endpoint would most change the
  conclusion.

Persist the replay code, input hashes, and `HEADROOM_RESULT.json`. Fail closed
if the trace schema, hashes, or token accounting cannot be reconciled. This is
analytical/inferred evidence and must not be presented as a measured endpoint.

## Boundaries and budget

- CPU only; no GPU, provider, SSH, or current-bench mutation.
- At most 45 CPU minutes, 1 GiB RAM, and 256 MiB of artifacts.
- Finish or persist a typed terminal by `2026-07-25T11:20:00Z`.
- Do not replay the consumed discriminator or infer endpoint consumption.

## Portfolio-changing result

A stable headroom point below the target strengthens the H100 production
candidate; a negative result supplies the exact service-time or rate reduction
needed from the pending endpoint or a future mechanism. An irreconcilable
trace closes only this replay.

## 2026-07-25 background buffering and overflow iteration

The strict 90%-headroom replay selects two H100 replicas, but the settled
single-H100 service capacity is only slightly below the exact trace's average
arrival rate. Because the campaign explicitly permits latency-for-cost trades
for background traffic, test the materially different scheduling question:
whether finite buffering or minimal retail overflow can remove the discrete
second-replica step without hiding sustained overload.

Reproduce the prior control, replay one H100 on both the finite trace and
periodic repetitions, and construct a deterministic cost-versus-wait Pareto
frontier that spills the minimum requests needed to bound predicted FIFO wait.
Keep the current nominal, capability-listed, and Artificial Analysis retail
tiers separate. This remains analytical CPU evidence and must not inspect the
live endpoint owner or touch any provider.

The exact contract and hashes are in
`DIRECTOR_BACKGROUND_OVERFLOW_BINDING.json`. Persist
`BACKGROUND_OVERFLOW_RESULT.json`, `BACKGROUND_OVERFLOW_DECISION.md`, and the
reproducible simulator by 2026-07-25T11:58:00Z.
