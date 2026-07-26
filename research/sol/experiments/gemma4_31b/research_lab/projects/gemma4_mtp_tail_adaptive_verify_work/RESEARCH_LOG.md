# Research log

## 2026-07-26 — Exact adaptive-verify oracle

Decision: falsify request-local target-work adaptation for the admitted
depth-1 Frozen-KV MTP geometry. Do not implement it or claim a GPU.

Hypothesis: an online request-local continuation policy could remove enough
low-acceptance target verification, especially after the batch shrinks, to
beat the exact same-session stock control.

Scope and gate: exact Gemma 4 31B FP8 target, exact accepted-depth capture,
4,214-token prompt, 358-token output, concurrency 32. The gate was a
fallback-inclusive oracle below the measured 21.578427489 s control batch
without changing emitted target semantics. Budget was CPU/source replay only,
zero accelerator seconds, $0, 60 minutes, and at most 2 GiB. The required
terminal was either one source-complete candidate or a typed mechanism
falsification.

Evidence:

- Measured/source-bound: hash-validated the historical boundary, both endpoint
  terminals, all 708 alternating timing events, and the exact worker, verify,
  scheduler, and result-processor sources.
- Derived from measured: replayed 354 ordered request-state transitions. Every
  observed batch size matched the live unfinished set; all requests ended at
  exactly 358 tokens. Totals were 6,544 request-verifies, 4,880 accepted
  drafts, 1,664 rejected drafts, 1.830576429 s assistant time, and
  25.976945748 s target-verify time.
- Derived from measured: calibrated fallback from control request 9, the last
  request to receive its first token and therefore the shortest uninterrupted
  stock trajectory: 8.745451724 s / 357 rounds = 0.024497064 s/round.
  The deliberately optimistic cutoff model omits switching and endpoint
  overhead. Its minimum is zero MTP iterations. The best cutoff using any MTP
  is one iteration at 21.945436717 s, 0.367009228 s slower than control. The
  cutoff before the first batch shrink is 38.624570603 s.
- Analytical clairvoyant lower bound: at depth 1, an accepted proposal uses two
  target positions for two emitted tokens, while a rejection uses two target
  positions for one. Even an impossible future-aware policy that speculates
  only on accepted drafts uses exactly 11,424 target positions, identical to
  stock, and still requires 4,880 assistant request-forwards. Full MTP uses
  13,088 target positions, 1,664 more than stock.

Interpretation: shrinking-tail disablement repairs visible waste but cannot
reverse the regression. The exact worker has a batch-wide
draft → target-verify → accepted-KV-commit sequence with verification width
`speculative_num_steps + 1 = 2`; scheduler filtering preserves the replayed
unfinished-request order. Request-local partitioning cannot create target-work
savings under this proposal geometry, so a patch would only pursue launch
packing while adding assistant work and fallback machinery.

Command:

```text
python3 replay_oracle.py
```

Artifacts:

- `MTP_TAIL_ADAPTIVE_VERIFY_RESULT.json`
- `artifacts/adaptive-verify-oracle-v1/ADAPTIVE_VERIFY_ORACLE.json`
- `artifacts/adaptive-verify-oracle-v1/RECONSTRUCTED_EVENT_STREAM.jsonl`

No GPU was claimed, no provider state was changed, no paid sample was
consumed, and actual spend remained $0.
