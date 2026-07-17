# L40S MLA-rank and tile co-design

## Question

Can a tile-aligned reduction in GLM-4.7 Flash's MLA latent/value geometry make the faster two-stage decode tile legal on L40S and reduce KV state enough to create a credible 10% endpoint-cost or capacity-discontinuity path?

## Why now

The MoE project now owns the only paid expert-geometry test, and the output-head lane is closed. The strongest disjoint chip mismatch is MLA: the attractive `BLOCK_N=64`, two-stage decode tile required 159,744 shared-memory bytes against Ada's 101,376-byte per-block limit, its one-stage repair regressed, and current 512-rank MLA state contributes about 7.436 GiB at the full c16 request geometry. Earlier split-count tuning saved substantial traced attention work but transferred only about 1.05% to endpoint throughput, so rank work earns promotion only if it changes both tile realization and a capacity boundary.

## Research scope

Use [`../../hardware/L40S.md`](../../hardware/L40S.md), the exact vLLM grouped-MLA source, retained V22/V23 microbench artifacts, the V24–V28 serving traces, current c16 telemetry, and the corrected c8/c16/c32 memory bounds. At `$0` provider spend, enumerate only tile-friendly latent/value candidates supported by the architecture and weight shapes, beginning with KV ranks 384 and 256 when valid. For each candidate, derive or compile the exact two-stage kernel resource use, reject any block above the 101,376-byte limit, and report registers, shared bytes, warps/blocks per SM, tile/grid geometry, arithmetic intensity, and expected L2/DRAM traffic. Calculate full-workload KV allocation and whether c32 or a materially cheaper memory tier becomes admissible under the conservative runtime band.

Build the smallest executable exact-shape proxy available without provider mutation. Calibrate its endpoint transfer against the retained split-MLA A/B rather than treating summed kernel duration as wall time. A useful result is either one specific rank/value geometry whose legal two-stage component gain plus capacity discontinuity conservatively supports the 10% campaign gate, or a closure showing no recoverable tile-aligned geometry can do so. Do not explore MoE geometry, residual precision, the output head, generic profiling, or training in this project.

## Decision

Nominate at most one MLA geometry for a later target-GPU arm only when it is hardware-legal, has an executable component result, and supports at least 10% lower sustainable endpoint cost or a concrete cheaper-chip/capacity discontinuity after conservative transfer. Otherwise close MLA-rank/tile co-design and return capacity to depth or draft-head architecture. This project has no provider authority or spend.
