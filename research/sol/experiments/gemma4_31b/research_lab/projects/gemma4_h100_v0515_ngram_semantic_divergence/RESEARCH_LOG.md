# Research log

## 2026-07-25 — request-277 semantic localization

Question: why did native depth-12 NGRAM first diverge at request 277, output
token 19?

Action: verified the director binding and all eight bound hashes; reconstructed
request 277, the observer, corpus/request ownership, target verification,
accepted-KV movement, graph padding, overlap relay, batch filter/merge,
scheduler settlement, and response reduction at exact v0.5.15. Used no
provider, GPU, or packed-mask project.

Evidence: the observer proves a raw `output_ids` difference, not normalized
text, but the endpoint retained only the request and mismatch index. Frozen
source preserves `rid`/row ownership through the traced chain; no
source-proven leak was found. The actual row, batch membership, logits/margin,
and acceptance trace are absent.

Interpretation: `indeterminate_missing_actual_artifact`. Response truncation,
batch-dependent target argmax, a runtime ownership/verification defect, and a
reproducible target-verified difference cannot be separated.

Next: if separately authorized, apply the single
`per_rid_target_accept_settlement_conservation` invariant in the result. Do
not replay the consumed endpoint under this project.

## 2026-07-25 — offline sentinel reconstruction

Question: do the immutable fresh-sentinel artifacts exclude divergence without
inventing a co-batched logical rid assignment?

Action: re-hashed every bound input, recomputed all 128 target/accept/KV/
scheduler rows directly from the 256-row trace, and enumerated both co-batch
rid-to-logical-label permutations. No GPU, provider, or request was used.

Evidence: 128/128 conservation rows pass; all four responses are complete,
identical 358-token arrays. The two permissible co-batched assignments have
the same serialized-output hash sequence.

Interpretation: `sentinel_exact_equivalence_class`. This narrows the fresh
sentinel mechanisms only; request 277 remains unresolved and non-replayable.
