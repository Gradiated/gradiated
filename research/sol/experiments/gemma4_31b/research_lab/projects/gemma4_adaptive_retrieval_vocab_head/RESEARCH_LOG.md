# Research Log

## 2026-07-26T01:47:00Z — Exact offline retrieval admission

**Question.** Can request-adaptive retrieval recover the exact tied-head top-1
on the hash-bound 384-row hidden capture with a candidate set and physical
traffic bound credible enough to justify an H200 consumer?

**Action.** Implemented `adaptive_retrieval_vocab_offline.py` and ran it locally
on CPU against the exact hidden capture
`80625b878e7479cd626250396f4be1a319e781245335600cd285037ce00fc66d`,
the exact tied BF16 shard
`eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa`,
and the static-head terminal
`12cdd51e1a1081f95deee4325a558c45e6dfac52abbff5b75ee0c522d385d0ee`.
The first launcher attempt used an incorrect relative checkpoint path and
failed before reading inputs; the path-only defect was amended and the
canonical invocation was run once. No GPU, SSH, provider mutation, or paid
request was used.

**Evidence.**

- Measured: the full tied head returns token `240017` with a `5.08879` FP32
  top-1 margin. Repeating that ID for 384 rows reproduces the prior H200
  control digest `e1ebaa70d782fcec41a707c186f8eac634b07bfb127ac2631d1f8f5b0cfab6aa`.
- Measured: all 384 serialized hidden rows are identical, and every captured
  proposal ID is zero. The effective hidden-state sample size is one, so all
  request/depth strata are repeated observations of the same retrieval.
- Measured: rowwise W8A8 ranks the reference first at one candidate. The
  variance-selected BF16 coordinate families need 32, 512, 2,048, 4,096,
  8,192, and 32,768 tested candidates at widths 4,096, 2,048, 1,024, 512,
  256, and 128 respectively. W4A8 needs 8,192 candidates but is not a native
  H200 tensor-core path.
- Analytical, using vendor inventory peaks with deliberately discounted
  bandwidth/math rates: the best native materialized-score geometry is the
  256-coordinate index with 8,192 candidates (3.125% of vocabulary),
  134,218,240 index bytes, and a 1.023 ms additive H200 bound. Its fused
  lower-bound traffic is 222,331,392 bytes (7.89% of the dense BF16 weight);
  score materialization raises traffic to 1,027,637,760 bytes (36.46%).
  This is physically favorable against the measured 24.808 ms stock component,
  but actual kernel, gather, and graph costs remain unmeasured.

The complete recall curves, per-request/per-depth arrays, geometry, arithmetic,
and bounds are in
`ADAPTIVE_RETRIEVAL_VOCAB_OFFLINE_TERMINAL.json`
(`29644d701a38606f6a8f9230da753b2ecdccd969093ca80af75dfd9d6c3e54dd`).

**Interpretation.** The mechanism is physically credible on the single bound
state, but this capture cannot support a workload-level retrieval claim or a
GPU-spend decision. The apparent 384/384 recall is not 384 independent
decisions.

**Next move.** Close this admission without an H200 claim. A successor may
capture genuinely distinct verifier hidden states, bind their hashes, and run
the same W8A8/coordinate retrieval consumer before any GPU measurement.
