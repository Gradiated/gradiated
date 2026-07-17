# Research log

## 2026-07-16 — Director opening handoff

Top-3/shared clears its bracket but raw planning-GPU COGS leaves only narrow headroom to `$0.514/M`. Reuse the immutable bracket and settled lifecycle evidence to decide whether any conservative sustainable operating envelope remains. Keep experimental cost, production COGS, and unresolved quality separate.

## 2026-07-16 — Terminal utilization/headroom classification

Question/action: verified the three immutable typed summaries and applied the candidate economics against the settled lifecycle archive and shared L40S planning rate; no provider action, price search, new lifecycle study, or spend.

Measured evidence: all three arms are typed `PASS`, 64/64, exact geometry, semantic-pass, prefix-cache-disabled/zero. The bracket is `611.326249 / 644.318005 / 601.371981` tok/s; useful/allocation seconds are `107.203/1321.987`, `101.714/361.005`, and `108.977/371.969`. The retained typed cost through post retrieval is `$0.489835297`; cleanup-tail cost was not aggregated, but authenticated final cleanup is zero instances and zero disks.

Derived bound: candidate raw planning-GPU COGS is `$0.474230975/M`, requiring at least `92.2628356%` productive utilization and allowing at most `7.7371644%` lifecycle loss. At the settled `1,151.243 s` lifecycle-loss archive, `135` 64-request batches (`3.8143 h` productive) are needed; the resulting bound is `$0.513990710/M`, leaving only `$0.000009290/M` for storage, transfer, orchestration, interruption, retry, cleanup, and headroom. The observed settled productive fraction is `15.4696%`, so it is not a sustainable envelope.

Decision: `MARKET_ONLY_HEADROOM`. The exact-model non-reasoning retail hurdle remains below the raw result’s cost, but the authoritative sustainable self-hosted target fails conservatively. Preserve as architecture-cost/market evidence only; result artifact: `artifacts/SUSTAINABLE_COGS_DECISION_2026-07-16.json`.
