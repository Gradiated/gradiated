# Research log

## 2026-07-25 — request-217 target-verifier localization and one exact candidate

**Question.** Why does official v0.5.15 first change request 217 from token
`51935` to `3055` at output index 19, and is one exact repair worth a retained
H200 discriminator?

**Action.** Mechanically rehashed all eight director-bound paths, materialized
the executed v0.5.15 source and response bytes project-locally, traced corpus
proposal, greedy target verification, accepted-KV movement, scheduler
settlement, and request ownership, then froze one startup-only launch delta and
a 218-request runner. No GPU was claimed and no provider or bench state was
mutated.

**Evidence.**

- Measured: requests 0–216 emit only token `51935`. Request 217 emits 19
  `51935` tokens followed by 339 `3055` tokens; its bound row is 358
  `51935` tokens. The only later mismatch is request 512 at output index 37.
- Source-derived: before request 217, `_update_ngram_corpus` can insert only
  the fixed last-18 prompt tail and accepted outputs. That prompt tail contains
  no `3055`, and no prior output contains `3055`. Therefore `3055` is not a
  corpus proposal: it is the greedy target verifier's bonus token.
- Source-derived: v0.5.15 consistently carries bonus-inclusive `accept_lens`,
  passes `accept_lens - 1` to accepted-KV movement, and lets the scheduler
  commit the complete sliced run. Corpus state and KV movement are keyed by
  request identity/slot; neighboring requests do not emit `3055`. These facts
  exclude observer normalization, proposal contamination, and an off-by-one
  accepted-token interpretation at the first mismatch.
- Source-derived: stock `TARGET_VERIFY` selects the prefill attention backend,
  while ordinary decode selects the decode backend. Official v0.5.15 exposes
  `--speculative-attention-mode decode` specifically to select that backend
  for verification.

**Interpretation.** The first divergence is localized before greedy argmax in
the target-verification attention/numerical path. The evidence does not include
request-217 logits, margins, or KV bytes, so it does not distinguish an
attention numerical difference from a verifier-specific KV dataflow difference
more finely. Promote exactly one semantics-preserving candidate:
`decode_attention_target_verify`. It changes only the official attention
routing flag; model, proposals, tree, greedy verifier, sampling, cache
ownership, accounting, and request bytes remain unchanged.

**Next move.** Under a new director binding only, restart the digest-pinned
v0.5.15 container with `inputs/decode_attention_launch.json` and run
`remote_request217_discriminator.py` for requests 0–217 at their bound
arrivals. Require 218/218 exact rows, zero failures, native NGRAM activation,
bounded release drift, and request 217 token 19 equal to `51935`. A complete
result consumes this discriminator. It does not admit or replay the rejected
791-request endpoint.

Artifacts: `LOCALIZATION.json` (`6cdd3101…daa1f1`),
`REPAIR_CANDIDATE.json` (`21e2a538…e9ae5`),
`DISCRIMINATOR_PACKET.json` (`0dc70e48…ef22f`), and
`PACKET_MANIFEST.json` (`f9eb015f…217681`).
