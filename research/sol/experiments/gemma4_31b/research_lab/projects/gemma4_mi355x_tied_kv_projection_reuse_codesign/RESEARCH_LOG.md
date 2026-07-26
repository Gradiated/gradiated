# Research log

## 2026-07-26T15:32Z — typed none: tie is global-only and cannot clear the target

**Question.** Can the exact `attention_k_eq_v` contract remove the V projection
from all 50 sliding and 10 global layers and reduce the unstacked MI355X screen
from `0.6000950932112802` to at most `0.5910500600431771 s/request`?

**Action.** Bound the pinned vLLM Gemma forward/loader, exact config, and local
checkpoint index without reading checkpoint tensor bytes. Implemented and ran
`run_tied_kv_projection_reuse_screen.py`, including dependency-free producer,
separate K/V normalization/RoPE, GQA consumer fixtures at prefill, M32, and
M384, plus a strongest-case whole-request economic floor.

**Evidence.** All 50 sliding layers have separate checkpoint `q_proj`, `k_proj`,
and `v_proj` entries. All 10 full-attention layers have only `q_proj` and
`k_proj`; the pinned loader clones K into V only for those full layers. Global
tied fixtures are exact while forcing the alias on sliding fixtures changes raw
V and attention output in all three phases. The only admissible reduction is
`110,100,480` global V weights, not the preregistered `1,211,105,280`. Even
crediting that subset perfectly and charging every new packing/fork/layout/
graph/fallback/memory/launch cost as zero yields `0.598732148102411 s/request`,
missing the target by `0.007682088059233982 s/request`.

**Interpretation.** `MI355X_TIED_KV_PROJECTION_REUSE_SCREEN.json` is typed
`none`. Implementing the all-layer path would overwrite independently learned
sliding V projections and change semantics. The valid global-only subset is
economically insufficient before any real shape or integration penalty, so it
does not merit target-hardware execution.

**Next move.** Close this mechanism. A successor must change abstraction rather
than schedule the global-only projection fork or alter the preserved paid
MI355X falsifier.
