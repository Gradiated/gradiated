# Adaptive depth-6 CUDA-graph decision

Classification: `source_complete_h100_component_ready`.

All five director-bound artifacts match, and the project-local source is based
on clean SGLang v0.5.15 commit `f63458b5beaceabbd9d749b9fc956370e1b649e6`. Exact depth-6 capture is
source-feasible without padding: graph identity now includes speculative depth,
capture and replay use exact `batch * active_depth` slices, and Triton target
verification derives query offsets, mask offsets, and maximum extend length
from the active NGRAM depth.

The deterministic production-contract fixtures passed the 7→8→7 transition
with graph keys `(7,12,84) → (8,6,48) → (7,12,84)`, permutations,
cancellation/completion, empty and partial matches, and slot reuse. Depth/key,
token, position, custom-mask, ownership, completion, and live-slot mutations
all failed closed. The result repeated byte-identically.

The physical design keeps one capacity-12 allocation and the existing shared
CUDA graph memory pool, but depth is semantic graph identity. Depth-6 replay
cannot resolve a depth-12 graph, cannot pad 48 rows to 96, and cannot consume
the stale tail of a prior mask because its captured metadata ends at the exact
depth-6 offsets. Native producer buffers remain separate at depths 12 and 6;
ragged accepted-token offsets and the active result stride preserve ownership
through scheduler settlement, while the existing KV mover consumes the active
accept-index width.

This is offline source and deterministic state evidence. It used no provider,
GPU, checkpoint, endpoint request, or paid resource and makes no latency or
economic claim. The next admissible evidence is one short exact H100
graph-versus-eager component using the immutable source manifest after the
higher-priority endpoint lane releases the compatible bench.

Artifacts:

- `ADAPTIVE_DEPTH6_CUDA_GRAPH_RESULT.json`
- `ADAPTIVE_DEPTH6_CUDA_GRAPH_SOURCE_MANIFEST.json`
- `ADAPTIVE_DEPTH6_CUDA_GRAPH_FIXTURES.json`
