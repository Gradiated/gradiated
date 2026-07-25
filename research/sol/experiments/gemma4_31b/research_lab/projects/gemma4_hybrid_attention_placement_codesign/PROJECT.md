# Gemma 4 hybrid-attention placement co-design

## Question

Can a model-level change to the number or placement of full-attention versus
1,024-token sliding-attention layers materially reduce the exact Gemma 4 c32
critical path on H200, while retaining a credible post-training and quality
recovery path?

## Why it matters

The campaign target is `0.500119281574996 s/request` against the locked
quality-qualified `0.625149101968745 s/request` denominator. Kernel work shows
that attention is important but cannot close the target alone without changing
the model geometry: the complete measured M384 attention family has only a
`17.03–19.42%` maximum whole-request opportunity.

The exact checkpoint has 60 text layers arranged as ten repetitions of five
sliding-attention layers followed by one full-attention layer. The qualified
runtime's exact c32 component measures a `30.0726%` local-attention reduction,
approximately unchanged stock global attention, and a `20.2089%` weighted
attention reduction. This creates a concrete model/chip question: whether
fewer or differently placed expensive global layers, or a related change to
the hybrid geometry, can remove work on the H200 critical path or unlock more
economic batching.

## Bound evidence

- Exact checkpoint configuration:
  `../gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/config.json`,
  SHA256 `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`.
- Exact critical-path and attention ceiling:
  `../gemma4_h200_ngram_fixed_m384_executor_rewrite/FIXED_M384_EXECUTOR_OFFLINE_RESULT.json`,
  SHA256 `87199d4f35a3d4131e1b11cf619547a28ffc1d7d06467237b80cc320efdb67a4`.
- Exact mixed local-only component:
  `../gemma4_h200_ngram_fixed_m384_executor_rewrite/artifacts/mixed-local-m384-20260725t165205Z/preserved-component-attempt-1/COMPONENT_TERMINAL.json`,
  SHA256 `12fb8457e1b54c82de43506e72ef159b40ccf9379eb2f0f84607aef85417b115`.

## Scope and immediate evidence

Work offline and do not claim or provision a GPU. Reconstruct the pinned Gemma
4 layer geometry, SGLang producer/consumer path, exact prompt and verification
shapes, and H200 execution cost at layer granularity. Use the shared
accelerator inventory for stable chip facts and current source or papers only
where they resolve a concrete architectural uncertainty.

Build the smallest reproducible simulator or executable configuration proxy
that compares the baseline 50-local/10-global placement with a small set of
causally justified alternatives. Account separately for prefill, target
verification, KV bytes and residency, tensor-core geometry, launch structure,
memory capacity, and any batch-size consequence. Label a layer-remapping or
weight-reuse proxy as quality-unsafe; do not call it deployable evidence.

Return either:

1. one source-complete candidate with a predicted whole-request delta, the
   H200 counter or physical change that would falsify it, its post-training and
   quality burden, and the cheapest later target-GPU execution proxy; or
2. a typed `none` showing that plausible full/sliding placement changes cannot
   produce a competitive bound or credible quality-recovery path.

Do not broaden this into generic attention-kernel tuning, low-bit execution,
or another literature review. A later GPU experiment requires a new director
decision after the current mixed-M384 and grouped-head sequence.

## Portfolio consequence

A viable candidate becomes a quality-unsafe execution proxy before any
post-training spend. A negative result closes only hybrid layer placement and
releases the deep slot to the campaign's next hardware-specific low-bit or
sparse model intervention.
