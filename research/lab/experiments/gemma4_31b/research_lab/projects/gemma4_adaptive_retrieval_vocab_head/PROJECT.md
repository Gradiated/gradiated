# Adaptive retrieval vocabulary head

## 2026-07-26 diverse-capture continuation

The first offline terminal is a valid negative only for its degenerate input:
all 384 nominal verifier rows were one identical hidden state. Continue the
same scientific question without a GPU claim by implementing the smallest
exact-path capture hook at the pinned NGRAM `TARGET_VERIFY` hidden-state
producer immediately before the tied LM head. The capture must preserve
request, depth, and row ownership and must be demonstrably non-interfering
with logits and acceptance on a genuinely diverse synthetic multi-request,
multi-depth fixture.

Emit `DIVERSE_HIDDEN_CAPTURE_HOOK_TERMINAL.json` with the exact producer and
consumer symbols, source hashes, ownership schema, fixture diversity,
non-interference evidence, and the single later capture command. Do not use
SSH, claim a GPU, issue an endpoint request, or rerun retrieval on the
degenerate historical capture. A later director decision will decide whether
the bound capture command merits a short H200 capture.

## Question

Can a request-adaptive retrieval index over Gemma 4's tied
`262144 x 5376` vocabulary weight shortlist a small fraction of rows while
retaining the full-head top-1 on exact captured verifier hidden states, with a
credible H200 dataflow advantage?

## Why this matters

The exact dense output head is a compulsory multi-gigabyte consumer. The
settled static certified hierarchy scored every row and certified `0/384`; its
candidate took `25.477 ms` median versus `24.808 ms` for stock. That rejects
that static certificate realization, not request-adaptive approximate retrieval
followed by exact scoring of a much smaller candidate set.

## Bound evidence

- Exact checkpoint: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Exact 384-row request-major/depth-minor hidden capture:
  `../gemma4_certified_lazy_vocab_head/artifacts/exact-c32-capture/hidden_proposals.pt`,
  SHA-256 `80625b878e7479cd626250396f4be1a319e781245335600cd285037ce00fc66d`.
- Static-hierarchy negative:
  `../gemma4_certified_lazy_vocab_head/artifacts/bound-comparison-20260725t2234z/LAZY_VOCAB_H200_COMPONENT_TERMINAL.json`,
  SHA-256 `12cdd51e1a1081f95deee4325a558c45e6dfac52abbff5b75ee0c522d385d0ee`.
- Tied embedding weight key
  `model.language_model.embed_tokens.weight`, recorded weight SHA-256
  `eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa`.

## Immediate experiment

Work strictly offline and zero-GPU. Build a request-adaptive retrieval
falsifier whose index uses only the tied vocabulary weight geometry—for
example coarse centroids plus residual/product quantization or another
source-justified representation. For each of the 384 captured hidden rows:

1. compute the full-head reference top-1;
2. retrieve bounded candidate sets over several candidate fractions;
3. exact-score only the retrieved weight rows;
4. report exact top-1 recall, request/depth stratification, candidate rows,
   index bytes, estimated HBM bytes, arithmetic work, and routing overhead;
5. map the best viable geometry to H200 tiles, L2/HBM residency, and a
   production producer-to-consumer path.

This is an explicitly quality-unsafe discovery proxy unless recall is exact.
Do not claim deployability, endpoint performance, or benchmark quality. Do not
train or mutate the checkpoint. Do not claim a GPU, use SSH, or issue a paid
request.

## Decision

Emit `ADAPTIVE_RETRIEVAL_VOCAB_OFFLINE_TERMINAL.json`. Continue toward an
exact-shape H200 consumer only if the measured recall/candidate curve and
physical byte/work bound leave a credible advantage over the `24.808 ms`
stock component after index and routing costs. Close this representation if
high recall requires scoring most vocabulary rows or its lower-bound traffic
cannot beat stock; propose a materially different sublinear representation
only when the evidence identifies one.
