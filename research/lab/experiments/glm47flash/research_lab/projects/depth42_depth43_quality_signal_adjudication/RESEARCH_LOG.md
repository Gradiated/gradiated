# Research log

## 2026-07-16 — Director opening handoff

- Bind the two terminal archives and reproduce their frozen V1 scores without alteration.
- Decide whether depth43 contains any unambiguous semantic improvement over depth42 after applying only the already-approved archived-response boundary policy.
- This is a `$0` directional adjudication, not a scorer repair, new evaluation, provider task, or quality claim.

## 2026-07-16 — Terminal adjudication: SERIAL_DEPTH_CLOSE

- Verified both terminal archives, all 40 internal manifest entries per archive, the response and paired-quality member hashes, and the frozen development suite identity.
- Reproduced the frozen scores: depth42 `1/6` with NLL `7.582576970259349`; depth43 `0/6` with NLL `7.507868369420369`.
- Applied only the archived fail-closed fence normalization and boundary policy. The only score delta is retrieval: depth43 returns `K-4702: amber-orbit-17` instead of the value-only answer; the prompt does not specify value-only formatting, so this is an underspecified contract. Continuation is the same semantic failure in both. Fenced tool/code/serving responses are transport/schema boundary defects in both; the lower depth43 NLL is below neither frozen absolute gate and is uncalibrated.
- Decision: `SERIAL_DEPTH_CLOSE`. Do not fund depth44 on quality-restoration grounds; preserve depth42 as the eventual V2-canary finalist. See `QUALITY_SIGNAL_ADJUDICATION.json`.
