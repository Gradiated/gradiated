# Adaptive-depth H100 decision

Classification: `source_complete_h100_component_ready`.

The prior H200 result is a valid negative for its partial representation, not
for adaptive depth itself. Its compact patch kept a native depth-12 corpus,
mutated the worker depth to 6, and sliced the producer's tokens and mask. That
is the earliest broken ownership contract even though the adapter returned
six-row arrays. The exact pinned H100 v0.5.15 source shows that repeating the
partial patch would additionally describe 48 rows with depth-12 Triton
attention metadata and return scheduler stride 12 for width-6 result rows.
Those v0.5.15 defects are not transferred claims about uncaptured H200 source.
Together with the observed 0/8 target-prediction-prefix and accepted/bonus
matches, they rule out the partial representation—not the hardware.

One materially different representation is source-complete for a future exact
H100 component:

- use separate native corpus producers configured at depths 12 and 6;
- select only by the frozen batch-size rule and reset stale per-depth match
  state when a request crosses the boundary;
- carry prior accepted rows with per-request offsets, so overlap filter/merge
  never reinterprets a width-12 result with width 6;
- derive target rows, positions, masks, attention metadata, acceptance width,
  KV movement, and scheduler stride from the same active depth;
- keep the existing depth-12 CUDA graph and fail depth 6 closed to the corrected
  eager path. This candidate does not pad or disguise six rows as twelve.

The project-local CPU/state oracle passed positive depth-12 and depth-6 cases,
the 7→8 boundary, request permutation, mixed-width overlap merge, mixed
completion, acceptance/bonus ownership, KV transitions, and fail-closed corrupt
shapes. These are synthetic state fixtures bound to the pinned source contracts;
they are not an execution-equivalent CUDA result.

At eight or more running requests, the analytical bound removes `6B` target
rows (50%) and `108B` tree-mask elements (75%). For equal prefix length `L`,
full-mask attention elements fall from `12B(L+12)` to `6B(L+6)`, eliminating
`B(6L+108)`—50.29% at `L=1024`. There is no latency, endpoint-throughput,
economic, or production claim.

The next admissible action is the preregistered checkpoint-free H100 component
in [ADAPTIVE_DEPTH_H100_RESULT.json](ADAPTIVE_DEPTH_H100_RESULT.json): real
native depth-6/depth-12 producers, real eager Triton target verification,
greedy acceptance, KV movement, and strict graph fallback at batch sizes 7 and
8. This project does not authorize or launch it.

Evidence:

- [H200_FAILURE_RECONSTRUCTION.json](H200_FAILURE_RECONSTRUCTION.json)
- [SOURCE_CONTRACT_TRACE.json](SOURCE_CONTRACT_TRACE.json)
- [ADAPTIVE_DEPTH_CPU_FIXTURES.json](ADAPTIVE_DEPTH_CPU_FIXTURES.json)
- [ADAPTIVE_DEPTH_SOURCE_PLAN.md](ADAPTIVE_DEPTH_SOURCE_PLAN.md)
