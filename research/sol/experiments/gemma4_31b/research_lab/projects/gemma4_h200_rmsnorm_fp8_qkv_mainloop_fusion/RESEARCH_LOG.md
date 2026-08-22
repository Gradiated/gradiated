# Research log

## 2026-07-30 — exact producer-to-QKV handoff

- Question: can exact decode RMSNorm plus dynamic E4M3 reach the pinned real-QKV SM90 mainloop without globally materializing the FP8 activation?
- Contract: zero GPU, zero CUDA, zero spend, fixed `M=1/16/32`, `K=5376`, `N=16384`, exact producer bytes, and complete-output GPU evidence required before any performance promotion.
- Trace: the pinned SGLang consumer launches 256 64-column CTAs with cluster `[1,1,1]` and passes global activation/weight pointers to `KernelTmaWarpSpecializedFP8FastAccum`.
- Falsification: one eight-CTA cluster serializes 32 N tiles per CTA; bounded groups duplicate the producer 256/128/64/32 times; concurrency parity needs 16 producer copies, four row rounds per CTA at M=32, three publication phases, and 21,504 persistent activation bytes per block while preserving all QKV weight and WGMMA work.
- Oracle: `FRAGMENT_ORACLE_RESULT.json` passes exact activation reassembly, scale ownership, sampled real Q/K/V fragment arithmetic, and signed-zero behavior for M=1/16/32. It is explicitly not a CUTLASS accumulation-order or complete-output claim.
- Invalid attempts: the first local oracle load exposed a Python 3.13 dynamic-module registration defect; a later replay exposed a missing required CLI input. Both exited before a decision-bearing result, are preserved under `artifacts/`, and were repaired without changing source bytes, seeds, or the scientific question.
- Decision: `MECHANISM_TERMINAL.json` closes the prescribed cluster-handoff and bounded-recomputation families as a typed analytical negative. The source-complete materialized exact producer remains the priority path; its funded H200 measurement belongs to the separate project.
- Spend and lifecycle: `$0.00`; no bench claim, SSH, CUDA, reservation, provider mutation, or R5 inspection.
