# Research log

## 2026-07-28 — exact transition discriminator terminal

- **Question:** Can the retained Gemma 4 DFlash transition preserve the exact
  ordinary target token and KV commit while clearing the
  `0.625149101968745 → 0.500119281574996 s/request` hurdle?
- **Action:** Hash-bound the pinned DFlash worker, immutable request-25
  first-target-step capture, ordinary target terminal, measured depth frontier,
  and complete draft-plus-verifier cost model. Implemented and executed
  `lossless_transition_discriminator.py`; three tests exercise a matching
  multi-token transition, the fail-closed mismatch path, and the real bound
  capture/economic consumer.
- **Evidence:** The real request diverges before acceptance: ordinary target
  `3496`, verifier target/bonus `759`. Both paths advance `4214 → 4215` and
  commit only the pending seed at KV slot `71603`, so commit geometry matches;
  ordinary same-state KV content was not retained and content equivalence is
  not claimed. The executable correction discards speculative-only writes,
  commits the seed, emits `3496`, and carries `3496`, exactly reconstructing
  ordinary one-step semantics. Two initial local attempts produced no result:
  relative-path rendering rejected a sibling input, then the frontier adapter
  expected a superseded `baseline` field; each causal amendment changed only
  that invalidated consumer boundary.
- **Economics:** Even a free drafter with the optimistic D12 verifier needs
  `13.57257` accepted target tokens (`12.57257` drafts), excluding configured
  depths 4/8/12. Charging the measured D16 verifier (`7.00708 ms`) and complete
  one-forward head (`6.07730 ms`) raises the hurdle to `16.054` accepted target
  tokens, `15.054/16 = 94.0875%` accepted draft depth, and
  `1226.96` accepted target tokens/CUDA-event-second. Measured depth-4 DFlash
  delivers `3.00632`, `521.916` tokens/second, and only `1.13495%` paired
  endpoint improvement.
- **Interpretation / next:** Close the captured DFlash transition and current
  depth-4 route. The fail-closed guard proves the exact correction but cannot
  accelerate because it requires ordinary target authority. Reopen only for a
  source/runtime change that makes the request-owned verifier state itself
  reproduce token `3496`, followed by a D16-class hardware falsifier that
  clears both acceptance and cost gates.

Terminal:
`LOSSLESS_TRANSITION_DISCRIMINATOR_RESULT.json`
(`1f185e21f5cadabbf5b152d76b28e986288040fdc3af1160e4e7dece7c887b71`).
