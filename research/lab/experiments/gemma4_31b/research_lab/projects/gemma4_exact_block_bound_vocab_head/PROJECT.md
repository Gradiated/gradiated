# Exact block-bound vocabulary head

## Question

Can an exact, certifying blockwise maximum-inner-product search reduce Gemma
4 31B's `262144 x 5376` tied output-head work below the measured dense H200
component while preserving the identical top-1 token for every row of the
recovered diverse c32 capture?

## Why it matters

The predecessor's 256-coordinate approximate retrieval was fast enough in an
analytical bound but scientifically failed recall: it reached only `0.555990`
global exact top-1 recall at 8,192 candidates. That rejects the coordinate
representation, not exact sublinear evaluation. The output head remains a
recurring exact target consumer, and even a small clean saving can stack
toward the campaign's `0.500119281574996 s/request` target.

## Frozen evidence and geometry

- Model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Tied weight key: `model.language_model.embed_tokens.weight`, SHA-256
  `eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa`.
- Capture: 1,536 finite BF16 rows, hidden width 5,376, 32 requests, SHA-256
  `ce7095836aea47701fc34ebacb2f0754c9066066062500a05fbd6136c59b4d54`.
- Capture terminal SHA-256:
  `fc7297d3bf51e9118e0cf5bde4eec7c2bd22dc2d07a6608c3b19f8b55d55a9bc`.
- Dense top-1 identity SHA-256:
  `27d7de2f664f46b7b743abccc751287414820d3e55175c870b8fdda2f2538816`.
- Dense H200 comparator: `0.004182975769042969` seconds.
- Predecessor terminal:
  `../gemma4_adaptive_retrieval_vocab_head/artifacts/h200-diverse-retrieval-score-20260727t0045z/H200_DIVERSE_RETRIEVAL_SCORE_TERMINAL.json`,
  SHA-256
  `e424ed4c1775545ece50270d4099ceff4c64ccc6db0f08106c9aea6ee028d611`.

## Mechanism and first discriminator

Use `$kernel-research`. Partition or hierarchically cluster tied-weight rows,
precompute compact block representatives and rigorous residual-norm bounds,
and use Cauchy-Schwarz or a stronger mathematically valid bound to skip blocks
whose maximum possible score cannot exceed the current exact best. Every
returned token must be certified against all unevaluated blocks; approximate
recall is not admissible.

Implement `exact_block_bound_vocab_head.py` and
`run_h200_exact_block_bound_owner.py`. The first target-GPU invocation is the
execution-equivalent discovery check. Measure the strongest dense baseline
and the exact bounded candidate on the full frozen capture, with warm timing,
evaluated-row and pruned-block fractions, index bytes, compiler/resource
metadata where applicable, and complete output consumption. Exclude index
construction from steady-state latency but report it and its amortization
assumption.

## Decision contract

A positive component requires:

- identical top-1 IDs and dense-reference hash for all 1,536 rows and all 32
  requests;
- finite scores and a proof that every skipped block was safely bounded;
- lower warm end-to-end candidate latency than the `4.182976 ms` dense
  comparator, including bound evaluation, traversal, and exact rescoring;
- a credible resident-index memory and amortization path.

If correct and positive, return the smallest runtime integration needed for a
scope-matched c32 endpoint. If exact bounds prune too little or the complete
candidate is not faster, close this exact block-bound mechanism. Repair
ordinary CUDA, source, layout, or owner defects in the retained claim; do not
change the frozen model, weight, capture, oracle, or dense comparator.

## Resources and limits

- Reuse only H200 bench `h200-causal-head-e00b9qw8d6qd7wrjj1` and its
  bench-owned checkpoint/image; never retransmit checkpoint shards.
- Current work is source implementation. GPU claim remains closed until the
  exact `$2.00` project reservation is durable and a director claim binding is
  issued.
- Future claim budget: at most 15 H200 minutes, 4 GiB additional storage, one
  scientific invocation, no endpoint, no capture replay.
- Expected terminal: `EXACT_BLOCK_BOUND_VOCAB_HEAD_TERMINAL.json`.

