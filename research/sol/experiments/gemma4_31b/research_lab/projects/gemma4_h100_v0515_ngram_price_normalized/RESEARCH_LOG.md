# Research log

## 2026-07-25 — H100 fit/economic packet

**Question.** Can the exact official v0.5.15 dynamic-FP8, E5M2 page-1 KV,
native depth-12 NGRAM stack plausibly fit and cross `$0.14/M` on one H100 SXM?

**Action.** Mechanically verified all seven `DIRECTOR_BINDING.json` identities,
the candidate's internal file manifest, the checkpoint geometry, the shared
H100 capability/price rows, and official v0.5.15 SM90/FP8/E5M2/NGRAM/fused-QK
source paths. Materialized the complete non-weight candidate under `packet/`
and added an H100-aware runner that evaluates startup fit, the 171-request
activation/semantic discriminator, and the conditional fresh-container
791-request endpoint.

**Evidence.** Measured, scope-matched H200 SM90 startup evidence records
`33.26 GiB` runtime weights, `0.05 GiB` pre-pool non-weight state, and
`1.43 GiB` CUDA graphs. Analytical Gemma geometry gives `40,960 B` per
full-attention token and `409,600 B` per sliding-window token. Treating the
inventory's 80 GB H100 capacity conservatively as decimal bytes leaves
`30.019935 GiB` for the default 0.8-ratio pools, an `87,439` full-token /
`69,951` sliding-token lower bound, 19 complete 4,572-token requests plus
depth-12 drafts, and `9.745871 GiB` post-graph headroom. This is an analytical
fit bound; H100 allocation and throughput remain unmeasured.

The exact denominators are 3,470,148 tokens for requests 32–790 and 3,616,452
tokens for requests 0–790. At `$2.80/GPU-hour`, `$0.14/M` permits respectively
`624.62664 s` and `650.96136 s`, both `0.82296 s/request`. At a sustainable
90% productive-utilization assumption, the ceilings are `562.163976 s`,
`585.865224 s`, and `0.740664 s/request`.

**Interpretation.** `nominate_one`. Capacity and official feature support clear
the offline gate with conservative headroom. No H100 performance is inferred
from H200; the packet requires direct H100 startup, activation, exactness,
queue, and endpoint-cost evidence.

**Next.** A director may reopen this project only with a positive spend
reservation, a registered 80 GB H100 SXM bench, and authority to materialize
the 62,578,655,208-byte manifest-bound checkpoint under this project before
the claim. Run the 171-request arm once; run the fresh-container 791-request
arm once only if every first-arm gate passes.
