# Decode-equivalent native NGRAM verifier

## Question

Can one source-bound target-verification path preserve the exact one-token
autoregressive logits and emitted token IDs while retaining enough native
NGRAM proposal amortization to serve the campaign c32 workload at or below
`0.6381105231 s/request`?

## Why this matters

Native NGRAM is the only measured performance candidate below the sustainable
H200 ceiling: `0.5967508053 s/request`. It is not production-qualified because
temperature-zero target verification emitted different greedy token sequences:
the single-tool row used 41 whitespace-expanded IDs instead of the control's
24 compact IDs, and only 1/32 ordinary c32 sequences matched control even as
unordered multisets. Because every request used `temperature: 0` and a fixed
seed, RNG accounting cannot explain the divergence. The remaining falsifiable
mechanism is the numerical/dataflow difference between ordinary one-token
decode and NGRAM's multi-token target verification.

This is a new verifier mechanism, not permission to reopen unchanged NGRAM,
route around tools, canonicalize output, or sweep proposal settings.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime image:
  `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Accelerator: one NVIDIA H200 SXM.
- Workload: exact c32 mix, 4,214 prompt and 358 output tokens per request,
  12.6958% cache reads, `temperature: 0`, seed `20260718`, exact runner SHA-256
  `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.
- Closed grammar-safe disposition SHA-256:
  `6cd9888912aae9fd4a8d5c173cb537fb49c60b73ffdaa8c6fb9216c6af67fcf4`.
- Closed final terminal SHA-256:
  `e226d78cbdede8d94a9892f2ef72505f5d946b0db3404ffa3cc6d7d6b4e64f1a`.
- Control/candidate server-boundary traces:
  `af777e64553df10dd8a2ce35572703ecad738cc9b34686f49b379a384005a317`
  and
  `e569b8af4e64c06e267ac4099296558bd69e298594dce57e490b18bdc3917b9a`.

## Scope and immediate experiment

Inspect the pinned SGLang NGRAM target-verification source, ordinary
one-token decode source, Gemma hybrid-attention dispatch, cache-location and
sequence-position construction, graph padding, and FP8 linear/attention
consumer shapes. Build one first-divergent-token discriminator over the
ordinary, repeated-pattern, single-tool, and one c32 row. Persist for the same
prefix and target weights:

- target input IDs, cache locations, sequence positions, attention mode, and
  CUDA-graph batch/padding shape;
- top-two target logits and argmax token from ordinary decode and NGRAM
  verification at the first divergence;
- accepted draft length and the exact target-forward symbols used.

Then implement exactly one decode-equivalent target-verification path justified
by that trace. It may change verification scheduling, attention/cache dispatch,
or numerical accumulation, but must not change NGRAM proposal settings,
sampling, tokenizer, weights, output formatting, or request routing.

Run the four-row discriminator first. Only an exact argmax/token pass admits
one sequential AR/candidate ten-row token/tool suite and one matched c32 pair.
Require exact scheduler and emitted token IDs, normalized text/tool semantics,
finish reasons, and accounting on every row, real NGRAM proposals and accepted
tokens, 32/32 complete c32 requests, and candidate service time
`<=0.6381105231 s/request`.

## Resources and limits

- Profile: `deep`; use `$kernel-research`.
- Spend: `$20` cumulative authority, including cold setup and cleanup.
- Compute: at most 6.5 claimed H200 hours and 8 local CPU-hours.
- Wall clock: complete by `2026-07-24T17:00:00Z`.
- Storage: one 250-GiB provider disk and at most 12 GiB new project artifacts.
- Provisioning: the director creates and registers one preemptible H200 only
  after this reservation is durable. Use the proven Nebius H200 launcher,
  pinned image, exact checkpoint revision, mutable in-place repairs, and an
  absolute cleanup watchdog covering the full itinerary.

Do not replay unchanged NGRAM, sweep proposal parameters, canonicalize output,
change grammar/tool routing, run broad quality, or interact with the retired
L40S.
