# Research log

## 2026-07-30 — admitted

- **Question:** Can the exact M384 output-head → sampler → acceptance path
  avoid global full-vocabulary logit materialization?
- **Scope:** Zero-GPU source tracing, physical model, deterministic oracle, and
  source candidate or typed negative under the pinned qualified endpoint.
- **Next:** Trace the real consumers and run the cheapest exact semantic
  discriminator before proposing H200 spend.

## 2026-07-30 — exact greedy consumer survives

- **Question:** Does any legal M384 decomposition remove the global vocabulary
  tensor while preserving the pinned target-verification and first KV-commit
  consumers?
- **Action:** Traced the clean v0.5.13 source from the tied BF16 head through
  FP32 softcap, NGRAM-owned sampling, tree verification, completion, page-1
  eviction, and committed-length updates. Falsified request-row slabs and a
  general sampled/custom/logprob streaming path. Implemented a fail-closed
  vocabulary-tiled greedy producer/acceptance candidate.
- **Evidence:** The qualified request is temperature-zero and therefore greedy.
  The deterministic oracle has zero selection, acceptance, completion, and KV
  ownership mismatches; its full-shape C case covers all `384 x 262,144`
  post-processor selections. The survivor removes `2,006,971,392` logical
  interface bytes per full M384 wave in exchange for a 3-MiB partial buffer and
  a 32-CTA request reducer. The row-slab alternative rereads 2.625-GiB weights
  twelve times. Sampled top-k/top-p, custom processors, logprobs, and TP>1
  remain exact stock fallbacks.
- **Interpretation:** Source and CPU semantics support one narrow candidate;
  H200 arithmetic, resources, traffic, latency, and endpoint effect remain
  unmeasured. The zero-cache peak-HBM scale is only `0.41811904 ms` per full
  wave and `0.0774642%` of the qualified service denominator after request-wave
  normalization, so this is a small stackable component hypothesis, not an
  endpoint claim.
- **Next:** Execute `H200_DISCRIMINATOR_CONTRACT.json` only under a later
  positive reservation and lab claim. Reject on any bitwise state mismatch,
  spill/resource failure, absent traffic reduction, or nonpositive paired
  component timing.
