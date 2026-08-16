# Gemma 4 causal parallel-offset draft head

## Question

Can one small Gemma-specific causal head predict target offsets 1–16 in a
single forward pass, so exact target verification reduces the qualified
`0.625149101968745 s/request` endpoint to at most
`0.500119281574996 s/request` without changing any accepted target token,
committed KV state, tool behavior, or next autoregressive token?

## Scientific distinction

This is not another DFlash repair or packed-verifier observer. The measured
current drafter is closed at depth 4: it delivered only `3.0063` accepted
target tokens per verification, `521.916` accepted target tokens per
CUDA-event-second, and `1.135%` paired endpoint improvement. This project
changes the draft mechanism itself while retaining the target model and
verifier as the lossless authority.

Freeze `google/gemma-4-31B-it` revision
`b9ea41a2887d8607f594846523f94c6cc75ac8a4`. Train one shared causal block
head from selected target-layer taps plus learned offset embeddings for
offsets 1–16. One head invocation must emit all offset hidden states; score
them as one batched consumer of the tied `[262144,5376]` vocabulary weight.
The head may alter draft proposals only. Target logits, acceptance, bonus
token, KV commit, and subsequent autoregressive execution remain unchanged.

## First bounded cycle

Use `$kernel-research` to produce a working, reproducible offline mechanism
packet before requesting any accelerator:

1. Bind the exact producer/consumer path from pinned SGLang source: target
   layer taps, BF16 hidden-state shapes/strides, offset conditioning, the
   `[batch,depth,5376]` draft-hidden output, the tied-vocabulary scoring
   layout/dtype/scales, acceptance inputs, and KV-commit boundary. Bind the
   production c32/M384 verification phase and the strongest measured DFlash
   depth-4 baseline above.
2. Implement the shared causal block, offset loss, one-forward inference
   path, exact-shape fixtures, and a hardware cost model. Count every
   projection, tied-head byte, launch, materialization, and verification
   invocation; do not credit idealized work that the real consumer still
   performs.
3. Use 4,096 teacher-forced and target-generated examples from the exact
   campaign request distribution, with a disjoint 512-example holdout.
   Weight offsets by prefix survival and measured depth cost. If hidden taps
   are not already durable, bind the smallest one-pass capture packet rather
   than substituting synthetic acceptance evidence.
4. Report recall/accepted-prefix curves for depths 4, 8, 12, and 16 and the
   derived conservative c32 service time. The primary metric is
   `accepted target tokens / (draft + target verification CUDA seconds)`.

Physical hypothesis: sharing the causal transformation across offsets and
batching the tied-head consumer raises accepted work faster than draft cost,
removing enough target forwards for a 20%-class endpoint reduction.

Counter-prediction: offset-conditioned hidden states fail to preserve prefix
survival, or the batched 262,144-way tied projection and verifier work grow
as fast as accepted tokens; in either case the conservative endpoint bound
stays above `0.500119281574996 s/request`.

## Decision artifact

Write `CAUSAL_PARALLEL_OFFSET_HEAD_READY.json` only when it hash-binds:

- working source, tests, immutable data split, checkpoint or deterministic
  initialization/training command, and exact shapes/layouts/dtypes/scales;
- the strongest baseline and a complete physical cost accounting;
- a single matched control/candidate GPU command with explicit timeout,
  artifact root, numerical and semantic gates, and no-fallback checks; and
- a conservative path to the campaign target on the disjoint holdout.

Otherwise write `CAUSAL_PARALLEL_OFFSET_HEAD_RESULT.json` with a typed
mechanism negative. A generic design, literature review, capture request, or
synthetic token-equality claim is not a terminal.

## Resources

- Researcher profile: `deep`
- Initial authorized provider spend: `$0`
- Wall clock: 6 hours for the first offline discriminator
- Local storage: 12 GiB
- GPU claim and provider creation: forbidden until the director consumes the
  ready artifact and a durable project reservation exists
- No replay of the consumed packed-M384 candidate, its control, its component,
  or the closed current-DFlash endpoint/depth samples

