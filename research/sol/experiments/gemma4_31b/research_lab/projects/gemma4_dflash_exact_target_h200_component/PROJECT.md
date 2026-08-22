# Gemma 4 exact-target DFlash H200 component

## Decision question

Can the exact public DFlash revision generate a useful 15-token parallel draft
for the exact Gemma 4 31B target while preserving greedy target semantics and
improving accepted target tokens per combined draft-plus-verify second over
both autoregressive and NGRAM exact-target controls on the fixed c32 workload?

## Scope

- Target: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Draft: `z-lab/gemma-4-31B-it-DFlash@eabd648301ce28583cc14757912e5e0f84e152e1`.
- Runtime source: SGLang `f63458b5beaceabbd9d749b9fc956370e1b649e6`.
- Workload: 32 requests, 4,214 prompt tokens and exactly 358 output tokens
  each, temperature zero, seed `20260718`.
- Component only: exact-revision loading, acceptance/KV correctness, and
  component economics. This project cannot claim endpoint promotion.

## Gates

Before any GPU claim, materialize a hash-complete, lifecycle-pure owner packet
that verifies every model, tokenizer, runtime, runner, command, and workload
identity. Preserve block size 16 and measure DFlash against matched
autoregressive and NGRAM controls. Record proposal/acceptance distributions,
first mismatch, next-round logits/KV audits, and CUDA-event interval unions.
Adopt the fixture-validated request-pool ownership repair from the closed
request-25 lineage; never replay or infer evidence from that consumed,
uninterpretable request.

Close this exact DFlash revision if immutable revisions cannot load for a
model/shape reason, target semantics or KV ownership fail after bounded local
repairs, or combined producer-plus-verifier throughput does not exceed both
controls. Promote only to a matched endpoint if all semantic gates pass and
the measured component margin makes a 20% endpoint reduction plausible.

## Resource contract

Request an exact cumulative `$6` H200 reservation. Until it is durable and
`DFLASH_H200_COMPONENT_READY.json` verifies, use CPU/source work only and do
not claim a bench or call provider APIs. The currently warm H200 is merely a
conditional compatible target through its existing `23:55Z` lifecycle fence.
