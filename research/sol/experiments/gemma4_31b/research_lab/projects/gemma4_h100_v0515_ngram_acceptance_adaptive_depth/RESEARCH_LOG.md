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

## 2026-07-25 14:14Z — valid checkpoint-free H100 component terminal

**Question.** Does the bound dual-depth native representation preserve the exact producer/consumer state contract on H100 at batch 7/depth 12 and batch 8/depth 6?

**Action.** Verified the binding and every bound hash, claimed the named H100 once, materialized the bound v0.5.15 sources project-locally, reran all CPU/state fixtures, and executed native NGRAM producers, eager Triton target verification, greedy acceptance, KV movement, scheduler settlement, and graph/eager selection. Two pre-measurement harness defects were repaired in place; the final run alternated 200 total repetitions, 100 per arm, and captured a short trace.

**Evidence.** [ADAPTIVE_DEPTH_H100_COMPONENT_RESULT.json](ADAPTIVE_DEPTH_H100_COMPONENT_RESULT.json) records matching producer bytes, Triton max absolute error 0.0003734, passing acceptance/KV/scheduler checks, depth-12 graph admission, depth-6 eager fallback, and median combined intervals of 0.4141 ms and 0.3970 ms. These are component timings only, not endpoint or quality evidence.

**Interpretation.** The source-complete adaptive-depth mechanism survives the exact checkpoint-free H100 component contract. The 50% row reduction remains an analytical mechanism bound; whole-request benefit is unmeasured.

**Handoff.** [ADAPTIVE_DEPTH_H100_COMPONENT_TERMINAL.json](ADAPTIVE_DEPTH_H100_COMPONENT_TERMINAL.json) is persisted, conservative spend is recorded as $1.25, and the bench was released ready at 14:14Z.

## 2026-07-25 14:25Z — offline endpoint lifecycle integration complete

**Question.** Can the frozen depth-12/depth-6 representation be integrated into one pinned v0.5.15 endpoint lifecycle without changing ownership, scheduler stride, or graph policy?

**Action.** Verified the new binding (`6168e592905625e593e759785e316ade538baa6c9de883c0855d6ad50c7c2a69`) and all eight bound hashes. Materialized the unchanged consumer sources plus the project-local lifecycle adapter under `inputs/candidate-v0.5.15`, froze their hashes, and ran the endpoint fixture suite with no provider, GPU, checkpoint, or request submission.

**Evidence.** [ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_RESULT.json](ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_RESULT.json) is `endpoint_ready_offline`. Thresholds 1/7/8/23 and 7→8→7 passed; permutation, cancellation, completion, empty/partial bonus-only matches, reused slots, graph/eager routing, KV/scheduler ownership, and four fail-closed cases passed. The immutable source/config manifest is [ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_SOURCE_MANIFEST.json](ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_SOURCE_MANIFEST.json), SHA-256 `1eebff421da4299a51a2e82861571cc4da3c0f3a248653955d1b374f25a4f0e5`.

**Interpretation.** Classify `endpoint_ready_offline`. This is integration correctness evidence only; it makes no endpoint latency, quality, throughput, or economic claim.

**Handoff.** [ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_DECISION.md](ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_DECISION.md) and the result are persisted by the deadline. No GPU claim or provider spend was added; cumulative recorded spend remains $1.25 from the prior component run.
