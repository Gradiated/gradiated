# Research log

## 2026-07-16 — Director opening handoff

- Reconcile the two immutable full-47 stock sessions, including c32 `596.852 -> 609.606` run spread and the c36 `549.799` collapse.
- Treat `$0.514/M`, the 300-second background envelope, shared planning rate/range, and complete lifecycle loss as authoritative; do not use the experimental rate for production COGS.
- Return one terminal sustainable/market-only/close classification at `$0`; every result remains quality-conditional.

## 2026-07-16 — Archive economics close

- **Question/action:** SHA-256 verified the maxseq32 (`ff873b...`) and maxseq36 (`ee558...`) immutable archives; used the shared L40S planning rate/range ($1.10/h; $1.00–$1.25/h), with no provider action or price search.
- **Evidence:** maxseq36 recorded 241.605 scored c32+c36 seconds out of 1,392.848 allocation seconds (17.346% productive) and 1,151.243 seconds of lifecycle/non-profile time. Its faster c32 steady-state quotient is $0.501234/M, but needs 97.5164% productive time: 421 64-request c32 batches (12.892 h) merely to absorb the measured loss, leaving $0.000448 and 1.467 s for every non-GPU and additional-loss term. The earlier c32 is $0.511945/M and needs 99.6003% productive time / 2,613 batches. Full details: `artifacts/SUSTAINABLE_COGS_DECISION_2026-07-16.json`.
- **Decision:** `SUSTAINABLE_CLOSE`, quality-conditional. The c32 2.137% run spread (596.852 to 609.606 tok/s), the c36 9.811% collapse, and unpriced storage/transfer/orchestration/retry/interruption terms prevent treating 609.606 tok/s as a sustainable denominator. A matched c32 repeat alone would not change the decision; it must be coupled to a measured long-session lifecycle policy that bounds all non-GPU costs.

## 2026-07-16 — Director arithmetic-label correction

The terminal classification and formulas stand. The artifact's `136,192` output-token label is a typo; `64*1,024 + 72*1,024 = 139,264`, and `$3.056011923/M` used that correct denominator. Its `0.481 s` cleanup label is the failed post-retention verification, not cleanup-to-zero; actual cleanup happened later and lies outside the recorded `1,392.848 s`, making the envelope optimistic. Leave this project terminal. The live AA session cannot establish the required 421-batch/12.89-hour exact-workload policy or price missing non-GPU terms.
