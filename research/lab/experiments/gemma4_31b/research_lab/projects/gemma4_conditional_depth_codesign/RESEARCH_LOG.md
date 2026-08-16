# Research log

## 2026-07-26T09:12:18Z — exact-geometry physical discriminator

**Question.** Can executable phase-specific block skipping reduce the locked
`0.625149101968745 s/request` c32 denominator to
`0.500119281574996 s/request` after new routing and runtime overhead?

**Action.** Bound the exact 60-layer Gemma geometry and the measured per-layer
placement reconstruction, materialized pinned SGLang
`28b095c01005d4a3a2a5b637b7d028b07fba31b2` source locally, and implemented a
dominating layer-loop bypass. The physical proxy executes contiguous groups
`[0,10)`, `[25,35)`, `[50,60)` for prefill and `[0,10)`, `[50,60)` for target
verification/decode. Verification is a subset of prefill, so every executed
verification layer owns native layer-indexed KV; mixed-route batches fail
closed.

**Evidence.**

- Measured/source-bound: the supplied reconstruction attributes
  `0.1859440808125 s/request` to prefill attention plus FP8 linears and, using
  the conservative 33.3125-pass reconstruction, `0.11386745088915104
  s/request` to target-verification attention plus all four FP8 projections.
- Derived: 30/60 prefill layers and 20/60 verification layers preserve
  `0.12629242022349502 s/request` of that work and remove
  `0.17351911147815602 s/request`. Holding the entire
  `0.3253375702670939 s/request` unmodeled residual fixed and adding a
  `0.012 s/request` router/graph/compaction/synchronization/fragmentation
  envelope yields `0.46362999049058895 s/request`, a
  `0.036489291084407016 s/request` target margin.
- Source-backed: the candidate branch dominates
  `Gemma4DecoderLayer.forward`, so each skipped verification layer removes its
  attention call and the trace-ordered QKV, O, gate/up, and down launches,
  along with uncredited norms, quantizers, residual kernels, and KV writes.
- Sensitivity: the target survives up to `0.04848929108440703 s/request` total
  incremental overhead at zero fallback, or a `0.21028975294747632` full-depth
  fallback fraction at the frozen 12 ms envelope.
- Validation: six behavioral/source-binding tests pass; the candidate source
  parses and the skip dominates the layer load and call.

**Interpretation.** `DYNAMIC_DEPTH_PHYSICAL_SCREEN.json` is
`source_complete_physical_candidate`, SHA-256
`3922fc6f00cc5069365bd1cdba25114662b0272cde909339d613b695e473f8f4`.
This is an intentionally semantics-changing, quality-unsafe physical proxy,
not a GPU measurement or accuracy claim.

**Next move.** Preserve the candidate. Any reopening requires separate
authorization for checkpoint recovery, hard-schedule distillation/continued
training, scope-matched GPQA-Diamond, TauBench, long-context and tool-use
quality gates, then a target-GPU c32 endpoint measurement. Do not download the
checkpoint, claim a GPU, or contact a provider under this project.
