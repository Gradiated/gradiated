# Research log

## 2026-07-16 — Director opening handoff

Combined selective W4 measured `630.195398` tok/s and `$0.484858/M` raw planning-GPU COGS, but its `1,310.638 s` allocation contained only `159.965 s` useful GPU time and the candidate is not quality eligible. Independently determine whether any conservative long-session cell at the fresh L40S planning range preserves explicit economic reserve after fixed lifecycle loss. Reuse the settled top-3 frontier method, not its result; this project is `$0`, terminal, and disjoint from scope-localization execution.

## 2026-07-16 — Terminal economic classification

Question/action: verified the immutable combined selective-W4 result and computed the offline session frontier at `$1.00/$1.10/$1.25` per GPU-hour with `1%/2%/3%/5%` target reserves. No provider, model, launcher, price-search, quality, or spend work was performed.

Evidence: archive hash `58349e47b405ae7f62645be89aa0b9c256de1c6082b1671ad64a69a5185c2a72` matches the typed summary. It reports `630.1953984207183` tok/s, `1,310.638 s` allocation, `159.965 s` useful GPU time, `$0.312413211` measured exposure, cleanup pass, and final inventory `0/0`. Derived fixed lifecycle loss is `1,150.673 s`; measured productive fraction is `12.2051%`.

Derived frontier: at the `$1.10/h` base rate, raw GPU COGS is `$0.484858436/M`. The reserve cells require `224/285/391/1559` 64-request batches, or `6.471/8.233/11.295/45.035` productive hours for `1%/2%/3%/5%` reserves; total sessions including the measured fixed loss are `6.790/8.552/11.614/45.354` hours. At `$1.00/h`, all four cells are feasible with `2.080–2.975` productive hours. At `$1.25/h`, steady-state COGS is `$0.550975496/M`, so no reserve cell is feasible even with infinite amortization. The measured `12.2051%` productive fraction is incompatible with every admissible cell.

Decision: `W4_ENVELOPE_EVIDENCE_OPEN`. Mathematical cells at the base rate mean `W4_MARKET_ONLY_CLOSE` is unsupported, but no production maximum-session/reliability policy or recurring bounds for interruption, retry, storage, transfer, orchestration, and cleanup are evidenced. That policy bundle is the single missing fact; this economics result does not reopen quality or authorize paid work. Artifact: `artifacts/SUSTAINABLE_W4_SESSION_FRONTIER_2026-07-16.json`.
