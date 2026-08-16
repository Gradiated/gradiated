# Lossless Gemma parallel-draft frontier

## Question

Can a target-verified Gemma-specific parallel draft path reduce the qualified
`0.625149101968745 s/request` endpoint to at most
`0.500119281574996 s/request` while preserving the target model's accepted
tokens, committed KV state, tool behavior, and next autoregressive token?

## Why this matters

This is the strongest software route to a 20%-class cost reduction because it
can remove target forward passes rather than optimizing one kernel family.
Prior DFlash work produced useful acceptance and timing evidence but also
semantic divergence. For target-verified speculation, that divergence is
localization evidence: draft disagreement is allowed; an accepted target token
or committed target state changing is not.

Use the existing DFlash endpoint, verification-depth oracle, request-217
semantic-causal, and launch-pipeline artifacts. Do not rerun a literature
survey or create another observer/readiness project.

## Immediate experiment

Build and execute one deterministic first-divergence reproducer around a real
persisted DFlash cycle. Capture target autoregressive argmax, draft tokens,
target verifier logits/argmax, accepted prefix, bonus token, request/sequence
identity, KV write locations, committed sequence length, and the first
subsequent autoregressive token. Include an A/A observer control.

Localize and repair the first incorrect observer, acceptance, request mapping,
or KV-commit boundary in working source. If the existing artifacts cannot
reconstruct it, produce the smallest exact runtime hook and executable runner
needed for one fresh cycle; do not substitute synthetic token equality.

After exact target semantics pass, bind one c32 GPU experiment comparing draft
depths 4, 8, 12, and 16 using measured:

`accepted target tokens / (draft cost + target verification cost)`.

If the current drafter cannot plausibly clear the 20% service target, return a
concrete Gemma-specific causal one-forward parallel draft-head intervention
with its smallest training/data and GPU falsifier. Do not extend integration
plumbing indefinitely.

## Decision

Write `PARALLEL_DRAFT_FRONTIER.json` as either:

- `exact_adaptive_draft_candidate`: the first-divergence path is repaired,
  target/KV semantics pass, and a runnable c32 adaptive-depth experiment is
  bound with a credible route to the target; or
- `typed_none`: measured acceptance, target verification cost, or a localized
  mechanism limitation prevents a 20%-class result.

An operational source or observer defect is not `typed_none`; repair it within
this project while expected value remains high.

## Resources

- Researcher profile: `deep`
- Initial spend: `$0`; use persisted traces and local source first
- Wall clock: 4 hours for the first decision-bearing reproducer
- Storage: 4 GiB
- No provider creation, GPU claim, broad quality run, or checkpoint transfer
  until the exact semantic repair and GPU command are durable

