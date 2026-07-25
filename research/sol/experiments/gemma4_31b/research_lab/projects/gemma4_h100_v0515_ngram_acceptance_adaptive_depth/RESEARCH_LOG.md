# Research log

## 2026-07-25 13:40Z — exact-depth representation admitted for a future component

**Question.** Can pinned v0.5.15 express the frozen 12-below-eight/6-at-eight-or-more
rule coherently rather than repeating the prior H200 partial patch?

**Action.** Verified the director binding and all eight bound hashes; streamed
only four decision-bearing members from the immutable H200 compact; traced the
native corpus, worker row packing, NGRAM metadata, Triton target verification,
acceptance interface, KV mover, scheduler settlement, and graph runner. Built
one dual-exact-depth/ragged-carrier CPU representation and ran boundary,
permutation, completion, ownership, and corruption fixtures. The first fixture
construction used duplicate request IDs in a merge and correctly failed; the
harness was amended to disjoint IDs before the only persisted result.

**Evidence.** H200 measured 8/8 exact draft prefixes but 0/8 exact target
prediction prefixes, 0/8 accepted/bonus rows, and only 7/8 accepted-count
matches. Its compact patch identifies the first mismatch at ownership: a
native depth-12 producer was sliced after the worker was mutated to depth 6.
Separately, the exact pinned H100 v0.5.15 source proves that repeating that
partial patch would retain depth-12 Triton metadata around 48 depth-6 rows and
expose immutable result stride 12 to the scheduler. All CPU/state fixtures
then passed for the coherent representation.

**Interpretation.** Classify `source_complete_h100_component_ready`. At high
load the analytical geometry removes 50% of target rows, 75% of square tree
mask elements, and `B(6L+108)` full-mask attention elements. No GPU, provider,
timing, endpoint, economic, or production inference was made.

**Next.** If separately authorized, run the checkpoint-free exact H100
producer→Triton eager attention→greedy acceptance→KV component and verify the
depth-12 graph/depth-6 eager boundary. Any row, ownership, or KV mismatch
rejects.
