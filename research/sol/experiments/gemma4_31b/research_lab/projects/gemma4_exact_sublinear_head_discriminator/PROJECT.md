# Exact sublinear output-head discriminator

## Question

Can an executable, certified index over the exact
`google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`
output-head weights avoid enough of the 262,144-way dense projection on c32
decode states to justify a target-hardware component test, while preserving
the required token-selection semantics?

## Why it matters

The campaign requires a complete result at or below
`0.500119281574996 s/request` on the qualified H200 scope, or the equivalent
20% price-normalized improvement on another accelerator. The large vocabulary
head is compulsory recurring work and is materially independent of the live
B200 native-NVFP4 endpoint integration. A certified candidate-pruning or
clustered-head mechanism could remove a meaningful fraction of projection
work; a poor certified pruning rate would cheaply reject the mechanism before
another paid allocation.

## Relevant evidence

- The exact model has a 262,144-way dense output head, named by the campaign
  as a leading ambitious mechanism.
- The first executable discriminator used one FP32 centroid and one scalar
  L2 residual radius per contiguous 128-row block. It preserved certified
  greedy top-1 on 32/32 exact c32 request rows but still evaluated 98.4619%
  of the vocabulary; index plus verified-weight traffic was 100.0616% of
  dense on average. Terminal
  `artifacts/CENTROID_BLOCK_DISCRIMINATOR_RESULT.json`
  (`5a7db872acc7fc2a303afbd8b22c4a7f08b085c8dcece937a59c07e5a9af1141`)
  rejects that single-centroid/scalar-radius representation, not every
  certified sublinear-head representation.
- The live B200 lane is transferring the exact checkpoint for a same-B200
  BF16-control versus native-NVFP4 endpoint. Do not inspect, mutate, claim, or
  depend on that bench.
- The fixed qualified denominator is `0.625149101968745 s/request`; the target
  is `0.500119281574996 s/request`. Component work must state a credible
  whole-request path and may not be reported as endpoint performance.

## Scope

- Work CPU-only and read existing checkpoint, source, and trace artifacts
  read-only. Do not call provider APIs, request spend, or claim a GPU.
- Bind the exact checkpoint revision, hidden width, vocabulary geometry,
  dtype, target-token semantics, and any activation-capture identity used.
- Inspect only the smallest relevant pinned model/runtime source and existing
  hidden-state evidence. Implement one executable certified discriminator
  with a materially tighter representation than a single centroid plus scalar
  residual radius—for example hierarchical multi-prototype clusters or a
  low-rank/anisotropic residual bound—rather than writing a design survey.
  Do not repeat the rejected contiguous centroid-radius method.
- Compare against the exact dense projection on representative existing c32
  decode hidden states when available. If no such capture exists, execute on
  deterministic model-shaped fixtures, clearly label that evidence synthetic,
  and persist the smallest exact-runtime capture hook for a later matched
  test.
- Measure exact candidate/top-k agreement, evaluated vocabulary fraction,
  index bytes, index-build cost, bound/verification FLOPs and bytes, and a
  conservative whole-request relevance bound. Explicitly distinguish
  greedy/top-k equivalence from full-softmax or sampling semantics.
- Keep derived artifacts below 20 GiB and finish the first discriminator
  within 60 wall-clock minutes.

## Portfolio-changing result

Advance to a target-hardware component only if the new certified
representation preserves its stated semantics and its measured pruning plus
index overhead can credibly remove material output-head work. Localize the
smallest corrective change if one bound or join is wrong. Close the broader
certified-index line if the tighter representation still leaves total
analytical work or byte traffic at dense, or if exact serving semantics cannot
be preserved.
