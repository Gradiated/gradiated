# Research log

No project turn completed yet. The initial shared resource model is [`../../hardware/L40S.md`](../../hardware/L40S.md).

## 2026-07-15 — zero-cost rank/tile falsifier

Question: can changing MLA KV/value rank make the attractive `BLOCK_N=64`, two-stage grouped decode legal on L40S and create the campaign's 10% endpoint-cost path?

Action: used the retained source-pinned exact-shape microbench and V22/V23r1 compiler outcomes as calibration points, then ran [`rank_tile_bound.py`](rank_tile_bound.py). The bound sweeps ranks 512/384/256, query/value widths, `BLOCK_N` 32/64, and stages 1/2. It is explicitly a derived compiler-resource envelope, not a claim that a new rank compiled; no provider or GPU mutation occurred. Existing campaign MLA tests still pass (10 tests).

Evidence: the calibrated `BLOCK_N=64`, stage-2 shared-memory envelope is 159,744 B at rank 512 (measured failed V22), 126,720 B at rank 384, and 93,440 B at rank 256. Against the 101,376-B L40S limit, rank 256 is the only legal candidate and has one block/SM on shared-memory residency alone. Its KV vector is 320 BF16 elements / 30,080 B per token. Using the corrected vLLM profile bound of 294,912 live c32 tokens, KV is 8.262 GiB versus 14.871 GiB at rank 512; with the existing conservative 10-GiB non-KV band and 43.2-GiB allocation ceiling, the derived c32 headroom is 24.938 GiB. This is capacity evidence, not measured c32 throughput or a cheaper-chip fit.

Interpretation: rank 256 does answer the hardware-legality half of the hypothesis, but not the economic gate. The retained split-MLA A/B transferred 14.35% component work reduction into only 1.05% endpoint gain, implying a scope-adjacent 7.32% endpoint share. Applying that measured transfer to the rank-256 44.44% work-reduction proxy gives only a 3.25% endpoint bound, below the 10% promotion gate. The unscoped 37.38% summed-kernel share is not used as an Amdahl coefficient. Rank 256 makes c32 memory-admissible in the conservative bound, but the independent c24/c32 saturation falsifier already found an optimistic 544.211 tok/s ceiling versus the 562.050 tok/s promotion hurdle; rank reduction supplies no measured scheduler or wall-time recovery to overturn that closure.

Decision: close the MLA-rank/tile lineage for this campaign. Do not nominate rank 256 for a paid arm. A future independently authorized exact-source GPU compile could validate the 93,440-B envelope, but would be confirmatory rather than a current promotion path. Return capacity to depth or draft-head architecture.

Artifact: [`RANK_TILE_BOUND.json`](RANK_TILE_BOUND.json). Evidence labels: retained compiler measurements; derived calibrated resource envelope; derived KV/capacity bound; synthetic rank-work proxy; inferred transfer bound.
