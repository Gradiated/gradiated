# Research log

## 2026-07-25 14:59Z — exact depth-6 graph source complete

**Question.** Can the frozen depth-6-at-batch-eight-or-more NGRAM path own an
exact CUDA graph without padding, stale metadata, graph-key aliasing, or
ownership/KV risk?

**Action.** Verified `DIRECTOR_BINDING.json` and all five bound hashes against
clean SGLang v0.5.15 commit `f63458b5beaceabbd9d749b9fc956370e1b649e6`.
Traced graph identity, the shared capture pool, static replay buffers, Triton
target-verify metadata, dual native producers, ragged result carriers,
scheduler stride, and KV movement. Materialized and patched a project-local
source snapshot: speculative depth is part of `ShapeKey`; capture and replay
use exact `batch * active_depth` slices; Triton derives query/mask geometry
from active depth; producer buffers are native depth-12/depth-6 banks; result
filter/merge uses ragged offsets.

**Evidence.** The deterministic suite passed twice with byte-identical SHA-256
`f19e6f6bbfc4043b8e83e762ceef975f207a48bdc12c5c2cb214f23b82b30ae9`.
It exercised typed production graph keys and the actual patched ragged-carrier
methods, plus 7→8→7 keys `(7,12,84) → (8,6,48) → (7,12,84)`,
permutations, cancellation/completion, empty/partial matches, and slot reuse.
Wrong depth, depth-12 padding, token/position/mask shape, ownership,
completion, and live-slot mutations failed closed. Two pre-result observer
defects (Python 3.13 import registration and absent local PyTorch) are retained
as invalid attempts; neither entered CUDA or produced a decision-bearing
sample.

**Interpretation.** Classify `source_complete_h100_component_ready`. The exact
depth-6 graph is source-feasible with one capacity allocation and the existing
shared graph pool because graph identity and captured metadata are
depth-specific. This is source-backed plus deterministic offline state
evidence, not target-GPU execution.

**Next.** After the higher-priority retained endpoint lane releases a
compatible H100, run one short exact graph-versus-eager component from the
immutable source manifest. No provider, GPU, checkpoint, endpoint request,
latency claim, economic claim, or spend occurred in this project.
