# Research log

## 2026-07-23 — director admission

Admitted one fixed recovery experiment after the mirrored-ring direct-E5M2 FA3 component closed on semantic error despite an 8.85% point speedup. The measured width-16,384 plus exact-ring endpoint is a `0.6125846611 s/request` cost floor below the H200 ceiling but remains incoherent. This project asks whether a single rank-256 activation-aware residual per layer, merged into the retained down projections, can restore basic coherence without changing that inference geometry. The exact ring endpoint at `0.6556567115 s/request` remains the qualified comparator. No result from this project is production-qualified without the campaign GPQA-Diamond and TauBench suite.

## 2026-07-23 — fixed rank-256 recovery rejects on basic coherence

Question: can one activation-aware rank-256 residual per layer, merged into the fixed 16,384-wide `down_proj`, recover the measured cost floor without an inference adapter?

Action: claimed retained H200 `h200-sync-linear-e00vhh6h29fj68x91g`, validated the immutable checkpoint, captured 768 calibration and 256 request-disjoint holdout activations from deterministic exact-c32 content windows, fit exactly 60 reduced-rank regressions, and load-time merged their `5376x256 @ 256x16384` corrections before the unchanged dynamic-FP8 consumer. No control, component, standalone endpoint, or c32 request was replayed.

Evidence (measured): all 60 factors were finite and exact rank 256. Global held-out MLP relative L2 improved from `0.4996438671` to `0.1708653067`; recovered residual energy was `88.3054%`, with 58/60 layers improved, so the preregistered reconstruction gate passed. The actual merged SGLang path audit proved 60 recovered `down_proj` weights, no runtime adapter/extra GEMM, and the exact ring construction. All four coherence rows then failed (`C/KCK...`, repeated `//S`, repeated slashes for arithmetic, and `L/CCCC...`). The c32 marker remained false, so no endpoint candidate was invoked.

Interpretation: layer-local MLP reconstruction is not sufficient to arrest end-to-end error accumulation across 60 narrowed layers. The fixed representation is `reconstruction_or_coherence_reject`; do not nominate a quality run.

Retrieval repair: after the scientific terminal, guest `tar` could not read root-owned factors. A retrieval-only re-claim used `sudo tar`; no scientific stage was replayed. The 668,538,880-byte archive hash is `6c9760dfc4d05186336f0bc2618218a1d6a83ac02611f1c28e2b03a9dcf92021`, and all 60 files match the persisted manifest. Conservative cumulative provider exposure is `$0.80`.
