# Late-30-layer width-16,384 recovery

## Question

Can the exact width-16,384 intervention be restricted to layers 30–59, with their already-fitted rank-256 corrections merged into `down_proj`, so that the model preserves basic coherence while retaining enough of the measured width-plus-ring speedup to cross the H200 economic ceiling?

This is a fixed layer-placement experiment, not a width, cutoff, rank, selection, or fitting sweep.

## Why it matters

The qualified exact-ring endpoint is `0.6556567115001144 s/request`, versus the `0.6381105231` ceiling. Shrinking all 60 MLPs plus the ring measured `0.6125846611248562 s/request` but was incoherent. Its held-out recovery factors are weakest in early layers; every layer from 30 through 59 recovered more than 91% of discarded residual energy. Keeping layers 0–29 exact removes the earliest distribution shift while retaining half the measured full-width delta. A linear layer-cost projection is `0.6341206863124853 s/request`, 0.63% below the ceiling. This projection is analytical; only the endpoint can establish the result.

## Frozen intervention

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime image: `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- H200 bench: `h200-sync-linear-e00vhh6h29fj68x91g`.
- Layers 0–29: original 21,504-wide gate/up/down weights, unchanged.
- Layers 30–59: the bound 16,384-channel selection plus the already-retrieved rank-256 correction merged into each retained `down_proj`.
- No runtime adapter or extra GEMM.
- Exact E5M2 contiguous ring on the 50 local layers; ten global layers remain paged E5M2 Triton.
- Campaign c32 workload: 17,120 cached and 117,728 fresh prompt tokens.
- Comparator: persisted qualified exact-ring endpoint, never the incoherent full-width or recovery candidate.

Do not refit factors, change the cutoff, rank, selection, attention, runtime flags, workload, or precision. Do not replay any component, ring endpoint, width endpoint, or prior coherence arm.

## Immediate experiment

1. Mechanically verify `DIRECTOR_BINDING.json` and the 30 selected factor rows before paid work.
2. Reuse the prior load-time merge path, applying it only to layers 30–59. Prove 30 original-width rows, 30 recovered-width rows, no adapter/extra GEMM, all 50 ring paths, and all ten global paged paths.
3. Run the same four-row basic-coherence discriminator once. All rows must be transport-valid and semantically correct. Failure closes this exact layer placement without endpoint timing.
4. On pass, run exactly one c32 candidate against the persisted qualified-ring comparator. Require 32/32 finite rows and exact cache accounting.

A coherent positive endpoint is a quality-suite nomination, not production qualification. It must later pass exact GPQA-Diamond and TauBench before deployment.

## Budgets

- Authorized spend: `$12`.
- Compute: one retained H200, at most three claimed GPU-hours.
- Wall deadline: `2026-07-23T22:30:00Z`.
- Storage: at most 8 GiB; reuse the immutable checkpoint and retrieved factor archive.
- Provider mutation is forbidden to the researcher.

