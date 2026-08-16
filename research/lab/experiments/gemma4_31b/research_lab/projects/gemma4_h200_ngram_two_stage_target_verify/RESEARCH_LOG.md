## 2026-07-24 — exact two-stage target verifier launched

**Question.** Can the unchanged depth-12 NGRAM tree remain index-exact while
target execution runs rows 1–6 for every high-load request and rows 7–12
only for traversals that reach the continuation?

**Action.** SHA-256 checked every `DIRECTOR_BINDING.json` input and
materialized the admitted bytes under `bound_inputs/` before the claim.
Implemented a target-forward split that uses the unchanged full-tree
retrieval topology to detect continuation survivors, retains the full
12-slot cache allocation and ownership, and feeds combined logits through
the unchanged full-depth greedy verifier. The fixed prefix ends at request
index 870; only its exact positive terminal can start the fixed 1,036-request
candidate trajectory.

**Evidence pending.** The durable owner and measured terminal are the next
entries; no stock, sparse endpoint, adaptive-depth arm, depth, or threshold
is replayed or swept.

## 2026-07-24 — valid prefix closes the row-number split

**Action and repairs.** The first high-load call exposed that the retained
runtime uses the stock variable-width full mask, not compact QLEN mask
storage. That attempt produced no request terminal and was repaired in the
same claim by cropping stage one to `prefix+6` and stage two to the original
`prefix+12`. A missing standard-library import then failed before server
launch; that invalid attempt was also retained and only the resume consumer
was repaired. The next prefix was complete and decision-bearing.

**Measured evidence.** The candidate-only prefix completed 871/871 requests
with zero failures, exact finish reasons and usage, unchanged depth-12
producer hashes, unique full and accepted cache slots, and persisted
accepted/bonus tokens. It evaluated 34,266 target rows versus 56,808 full
rows, a 39.6810% reduction. Stage-one and stage-two target-forward time
totaled 21,430.084 ms and 6,938.858 ms respectively.

Only 791/871 output-token sequences matched the sparse comparator. Every
request from index 791 through 870 diverged after the ≥8-request intervention
activated; first divergent candidate tokens were zero while the comparator
emitted token 51935. This demonstrates that breadth-first row 7–12 logits
can affect earlier alternate-tree traversal even when a sentinel first-stage
probe does not classify the request as a continuation survivor.

**Decision.** Close this exact six-plus-conditional-six row-number split as
semantically invalid. The exact-positive prefix gate failed, so the sole
1,036-request trajectory was not started. Conservative cumulative provider
exposure is `$1.221250733`. The loaded candidate remains on port 30000 and
the bench was released to maintenance for director disposition.
