# Research log

Opened by the Cycle 84 director from the measured r3 graph-mode downgrade. This is a bounded exact-backend and interval falsifier, not a split-tuning, release-survey, profiler, or provider-preparation lane.

## 2026-07-16 — terminal RUNTIME_CLOSE

Question: does an unchanged SM89 MLA path restore full CUDA graphs for the exact r3 mixed prefill/decode workload and reach the campaign gate?

Action: audited the retained r3 archive and its exact launcher/runtime admission, then compared the pinned v0.15.0 source with the one cached current stable v0.25.1 source tree. No provider, GPU, backend build, source patch, or new trace was used.

Evidence: r3 requested `FULL_AND_PIECEWISE`, capture sizes `[1,2,4,8,16,24,32]`, cache-off c16, and selected `TritonMLABackend` with compressed-tensors W4A16/Marlin WNA16. The measured server warning states `AttentionCGSupport.NEVER` and downgraded to `PIECEWISE`; the valid control reached `552.1710554232396` output tok/s. In pinned v0.15.0, Triton MLA inherits `NEVER` and only admits auto/BF16 KV. In cached v0.25.1, Triton MLA changes to `UNIFORM_BATCH` and adds FP8 KV support, but uniform decode support still does not admit the required mixed prefill/decode full graph. The audited MLA declarations contain no unchanged `ALWAYS` mixed-batch path on SM89; alternate backends are constrained by uniform-only support, dependencies, or non-exact hardware/runtime routes.

Interpretation: source admission fails before an economic interval bound can be meaningful. The 6,096 graph-launch count is not converted into savings, and no full-graph A/B is prepared. Terminal result: `RUNTIME_CLOSE`.

Artifact: [`FULL_GRAPH_GATE_2026-07-16.json`](FULL_GRAPH_GATE_2026-07-16.json). Stop this lineage; do not build a backend or prepare provider work.
