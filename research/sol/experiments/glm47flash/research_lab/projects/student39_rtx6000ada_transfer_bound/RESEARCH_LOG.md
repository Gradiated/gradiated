# Research log

Delegated in Cycle 55 as a zero-cost placement screen after the measured 39-layer L40S pass. Reuse the same-day RTX 6000 Ada evidence and return one exact post-quality arm or close; do not invoke a provider or refresh the general price inventory.

## 2026-07-16 — exact student capacity and lifecycle rebound

**Question/action.** Rebound the prior same-SM89 RTX 6000 Ada floor to the measured student39 c16/c32 profiles with no provider mutation or price refresh. The bound separates performance transfer (`0.98` kernel legality × `0.90` sustained workstation clocks/cooling × `0.98` runtime support = `0.86436`) from productive utilization (`0.95`) instead of silently folding lifecycle into a chip claim.

**Evidence.** The source archive hash is `f9f3f77da53d30e87604d8a0f8c1ddd81e8bed65bab100896b06b5c6a7b35383`. Its L40S reports only `46,068 MiB` card-visible FB memory (not a favorable nominal-48-GB conversion); c32 uses `43,665 MiB` in terminal telemetry. The corrected analytical c32 peak is `44,459.517 MiB`, leaving `1,608.483 MiB` / `3.49%` if RTX reports the same visible capacity. Subtracting the exact c16→c32 KV delta (`1,152 MiB`) yields a c16 peak of `43,307.517 MiB` and `2,760.483 MiB` headroom.

**Result.** Conservative sustainable retention is `0.821142–0.99`: c16 `553.798–667.679` tok/s and c32 `603.175–727.211` tok/s. At the deliberately non-production `$0.847/h` lifecycle rate, they are `$0.4248/M` and `$0.3901/M`; required productive utilization is `78.522%` and `72.094%`, respectively. Thus both pass the `$0.514/M` gate without treating the old marketplace listing as a committed quote; c32 retains a 21.58% cost margin.

**Decision.** Nominate exactly one **conditional** later RTX 6000 Ada c32 arm after quality recovery. It must fail closed unless `nvidia-smi memory.total >= 46,068 MiB`, runtime c32 use is `<=44,459.517 MiB`, recovered quality passes, all 64 exact 8K/1K requests succeed cache-off, and raw throughput is `>=634.921` tok/s at `>=72.094%` productive utilization (therefore `>=457.739` lifecycle-adjusted tok/s). This is not an allocation authorization or production-rate claim. See [STUDENT39_RTX6000ADA_BOUND.json](./STUDENT39_RTX6000ADA_BOUND.json) and [student39_rtx6000ada_bound.py](./student39_rtx6000ada_bound.py).
