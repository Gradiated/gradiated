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

## 2026-07-25 — pre-sample H200 packet-staging defect

**Action.** Verified the director binding and all local manifest hashes, then
started a detached outer owner for the admitted H200 run. The owner atomically
claimed the retained bench, connected to the healthy v0.5.15 host, and staged
the immutable packet before any container restart or candidate request.

**Evidence.** Remote `verify_packet.py` failed on the required
`DIRECTOR_BINDING.json`: the controller tar omitted that manifest member.
The preserved diagnostic is
`artifacts/request217-decode-20260725t071138z/OWNER_EXCEPTION.json`; remote
inspection confirms the prior server remained running and no
`INVOCATION_STATE.json` or candidate terminal exists. The claim lasted about
7.5 seconds, conservatively charged as `$0.005117`.

**Interpretation and amendment.** This is an ordinary, pre-sample staging
defect, not scientific evidence. `run_request217_outer.py` now includes
`DIRECTOR_BINDING.json` in the staged tar. The owner released the bench to
maintenance after its failed retrieval, so one director reclaim is required
before the single permitted repaired discriminator launch. The 218 requests
remain unconsumed.

## 2026-07-25 — second pre-sample staging boundary

**Action.** After the director returned the H200, reverified the execution
binding and local manifest, audited the patched packet, and launched the one
permitted replacement durable owner.

**Evidence.** The replacement again failed before a container restart or
candidate CUDA/request call. Remote `verify_packet.py` reports the next absent
manifest member, `analyze_localization.py`; the original tar also omitted the
manifest-bound `source/` tree. Its immutable local evidence is
`artifacts/request217-decode-20260725t072124z/OWNER_EXCEPTION.json`; the
read-only remote verification preserves the exact missing-member assertion.
The two failed claims total a conservatively derived `$0.009132`.

**Interpretation and next move.** This is a second ordinary harness failure,
not a scientific sample. The controller now stages every manifest member
(`DIRECTOR_BINDING.json`, `analyze_localization.py`, `source/`, and all prior
members), and records remote stage stdout/stderr. Because the first detached
owner and its replacement both died before a valid sample, do not chain a
third owner this turn; hand the available H200 to the director for deliberate
recovery. Requests 0–217 and the only candidate discriminator remain
unconsumed; the 791-request endpoint remains prohibited.

## 2026-07-25 — residual audit proves the decode-attention flag was inert

**Question.** Why did the consumed `--speculative-attention-mode decode`
discriminator preserve request 217's verifier-bonus divergence, and does one
materially distinct exact repair remain?

**Action.** Stream-verified the compact archive against every retrieved member,
recomputed `FINAL_TERMINAL.json` from all 218 request rows and 301 telemetry
rows, compared the first 218 normalized semantic rows with the prior endpoint,
and traced the digest/commit-bound v0.5.15 attention construction and dispatch.
No GPU was claimed and neither consumed sample was replayed.

**Evidence.**

- Measured: all ten archive files match the retrieved bytes; the terminal hash
  is `ed726a2…80e12`, its decision recomputes exactly, all 218 requests
  completed with zero failures, and request 217 again changes from `51935` to
  verifier bonus `3055` at output index 19. The request-217 window observes
  native acceptance length 12.
- Measured: the candidate's first 218 normalized semantic rows and the rejected
  prior endpoint's first 218 rows have the same canonical SHA-256
  `6f4c5542…3eb1d`; the complete token/finish/accounting trajectory is
  identical, not merely the first mismatch.
- Source-derived: the measured launch explicitly sets both
  `--prefill-attention-backend triton` and
  `--decode-attention-backend triton`. At commit `f63458b5`, `ModelRunner`
  constructs `HybridAttnBackend` only when those resolved names differ. The
  flag's backend-selection read is inside that unconstructed wrapper.
- Source-derived: even inside `HybridAttnBackend`, target verification delegates
  to the selected backend's `forward_extend`; base attention dispatch sends all
  non-`DECODE` modes there, and Triton target verification retains
  `extend_attention_fwd` plus the tree mask. The flag never means
  `forward_decode` or `decode_attention_fwd`.

**Interpretation.** The launch delta was behaviorally inert, which fully
explains the preserved trajectory. A same-backend wrapper patch would still
execute the same Triton extend path; changing backend class would be an
unsupported backend sweep rather than a localized repair; serial ordinary
decode verification would remove the depth-12 transformer amortization that
makes NGRAM economically relevant. Return typed `none` and close this route.

**Artifacts.** `RESIDUAL_MECHANICAL_VERIFICATION.json`
(`89ee8382…a51ef`) and `TYPED_NONE.json` (`4212ea6c…dc1a`).
