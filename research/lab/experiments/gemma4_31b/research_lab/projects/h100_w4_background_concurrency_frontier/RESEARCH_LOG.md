# Research log

## 2026-07-18 — director admission

c32 is closed by a measured absolute lower bound: valid local FP8 producer-plus-attention costs `0.17950119981542229 s/request`, so W4 linears + actual head + local attention total at least `0.6536132414387539`, above the `0.5479752315195353` H100 ceiling. The campaign permits background latency-for-cost tradeoffs, so activate one checkpoint-free actual-consumer sweep at c48/c64/c96/c128. Reuse the proven W4 retained lifecycle and run the compatible actual head sequentially on resident image state if ready without delaying the primary. No c32 or endpoint claim transfers.

## 2026-07-18 — retained frontier owner launched

Question: whether c48/c64/c96/c128 changes the component frontier. Action: launched `gemma-h100-w4-frontier-20260717t22121784319137z.service` through the shared Nebius retained controller, with a 1,319-second provider deadline and `$0.7913` derived maximum exposure. The pre-create terminal passed (pinned image, empty inventory, bindings, budget, durable service ownership); the owner PID is `2202355` and provider create is in progress. It will run 24 exact paired W4/BF16 rows first and invoke the actual `ParallelLMHead` stage only after the typed primary result passes. Artifact root: `artifacts/gemma-h100-w4-frontier-20260717t22121784319137z/`.

## 2026-07-18 — attached owner progress

Measured lifecycle evidence: Nebius successfully created `computeinstance-e00hmt044zjv0vm3ed` and the owner bound cleanup watchdog `gemma-h100-w4-frontier-20260717t22121784319137z-watchdog.service` (PID `2202539`). SSH became ready after `94.619 s`. No bootstrap or first-call diagnostic exists yet, so this is normal setup rather than a recoverable integration failure; preserve the resident session for the actual primary measurement.

## 2026-07-18 — bootstrap still progressing

Attached once: the bound H100 remains `RUNNING`; no host-bootstrap, primary-stage, or typed failure artifact has been emitted. With `1,052 s` left to the retained owner's provider deadline, preserve the pinned-image bootstrap rather than restart or duplicate the allocation.

## 2026-07-18 — measured frontier reconciled

The retained H100 produced 24 exact Machete W4/BF16 rows at c48/c64/c96/c128; all actual-consumer identities and dual numerical oracles passed. The only primary failure was the stale predecessor M8/M16/M32/M3679 aggregate assertion. Re-aggregating the retained rows for the admitted M-set and running the staged actual `ParallelLMHead` arm on the same H100 passed all four head oracles. Combined generated-token component times (W4 linear + head) are `0.132040`, `0.098819`, `0.073818`, and `0.057101 s/request` for c48/c64/c96/c128; c128 has the largest component-only residual, `0.490874 s`, but its batch-duration proxy is `7.309 s`. Attention, prompt work, KV, and endpoint behavior remain unmeasured, so every point is only component-plausible. Authenticated cleanup passed after `864.598 s`, with `$0.518692361` derived exposure. Terminal: `artifacts/gemma-h100-w4-frontier-20260717t22121784319137z/RECONCILED_FRONTIER_TERMINAL.json`.
