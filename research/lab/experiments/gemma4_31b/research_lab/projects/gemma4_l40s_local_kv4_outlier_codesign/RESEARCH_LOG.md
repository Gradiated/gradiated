# Research log

## 2026-07-27T05:42Z — fixed local KV4+outlier representation closed on fit

- Question: can the fixed 144-byte D256 local-only representation recover the
  exact c32 endpoint on one exposed 46,068-MiB L40S while directly feeding the
  selected runtime's paged attention?
- Action: bound current SGLang commit `c6a6200a1a77...`; implemented the BF16
  producer, exact packed layout, CPU high-precision oracle, mixed local/global
  pool adapter, and one fused SM89 page-one online-softmax consumer. No GPU,
  CUDA, SSH, provider, endpoint, checkpoint shard, or spend was used.
- Numerical evidence: naïve max/7 scales were a valid negative
  (`0.156313` base-only to `0.143934` corrected complete-output relative L2).
  The causal amendment uses each group's deterministic second-largest
  magnitude/7, intentionally leaving at most one dominant residual per group
  for the four global sidecar entries. On the deterministic synthetic exact
  D256/window-1024/32QH/16KVH decode oracle it changes `0.707343` base-only to
  `0.056208` corrected, cosine `0.998419`, max absolute `0.006247`, and zero
  nonfinites. This is promising checkpoint-free evidence, not model quality.
- Physical evidence: each K or V vector falls from 256 E5M2 bytes to 144
  bytes. One c32 local-layer decode therefore reads `150,994,944` versus
  `268,435,456` compulsory K/V bytes, a 43.75% reduction, with 1,024 CTAs
  (`7.2113` one-CTA/SM waves). Unpack/conversion work rises and compiled
  registers, spills, timing, and counters remain unmeasured.
- Decision: typed `none`. Exact static core plus page-one padding needs at
  least `45,077,378,048` bytes, while the unchanged
  `--mem-fraction-static 0.85` region is only `41,059,929,292` bytes. The
  candidate-favorable static deficit is `4,017,448,756` bytes before all
  other checkpoint tensors and FP8 scales. Charging the complementary dynamic
  reserve gives a complete lower bound of `52,323,247,924` bytes
  (`48.729822 GiB`) versus `48,305,799,168` exposed.
- Checks: six focused unit tests pass, including layout/ties, E5M2 extremes,
  zero/nonfinite policy, GQA/request isolation, causal/window/padding
  boundaries, fused-source invariants, and complete memory rejection.
  Terminal:
  `L40S_LOCAL_KV4_OUTLIER_OFFLINE_TERMINAL.json`, SHA-256
  `c0a732ef5cf42cb5744a19afab0fe2734ad37cbd5d720ebcc4a16e02a856cfc2`.
