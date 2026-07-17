# Research log

Opened by the Cycle 81 director after the request-complete exit-35 archive and verified cleanup landed. This project uses terminal artifacts only and may not touch the active config-native MoE falsifier or any provider.

## 2026-07-16 — terminal artifact attribution

Question/action: attributed the verified exit-35 endpoint only from its terminal archive and the named contextual r3 control; no provider, CUDA, inference, patch, or successor action was used.

Evidence: both endpoints bind model revision, cache-off 8,192/1,024 c16 geometry, and 32 complete requests. Exit-35 verified 47-layer prefill and 35-layer decode, reaching 559.969097 tok/s versus r3's contextual 552.171055 tok/s (0.826414 s / 1.4123% endpoint difference). The 594.466 gate would still require 3.395775 seconds, or 5.8030% of exit endpoint time, to be removed. Neither archive has a target-geometry prefill/decode/head/scheduler wall-time partition. The only profiler traces are both `fixed_8k_128_c8`, so they are ineligible for c16/1,024 wall-time attribution; row resampling would also be invalid because rows are correlated within the c16 schedule.

Interpretation/next move: `UNIDENTIFIABLE`. The evidence cannot close all further decode-layer work and cannot nominate a distinct residual mechanism. The sole resolving measurement is a matched alternating target-geometry stock/exit run with request-bound phase interval-union timing; it is stated only, not prepared or executed. See `terminal_attribution.json`.
