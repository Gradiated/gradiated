# Research log

## 2026-07-15 — zero-cost representation/runtime/hardware bridge audit

**Question.** Can a single causal factor be isolated between the retained BF16/SGLang/H100 V13 endpoint and AWQ/vLLM/L40S V21 endpoint without changing model semantics, fixed c1/c8 geometry, generation, quality diagnostic, cache state, scheduling intent, or SLO accounting?

**Contract.** Zero provider cost and no provider mutation.  Inspect OPP-005, retained V13/V21/V14 artifacts, campaign controllers, embedded manifests, runtime capability records, model sizes, and loaded-memory telemetry.  Preserve the evidence as `FEASIBILITY_MATRIX.md`.

**Measured/derived evidence.** V13 binds the native checkpoint `zai-org/GLM-4.7-Flash@33facc...` (48 shards, 62,444,175,504 bytes) to SGLang on an 81,559 MiB H100.  V21 binds the distinct public checkpoint `cyankiwi/GLM-4.7-Flash-AWQ-4bit@ab31d...` (4 shards, 20,170,199,928 bytes) to vLLM 0.15.0 on an L40S; its exact serving configuration consumed 38,985 of 46,068 MiB.  Native BF16 weight bytes alone equal 59,551 MiB, exceeding L40S capacity by 13,483 MiB before serving overhead.  V14 did start patched SGLang with AWQ on L40S, but its controller terminally failed on a missing typed artifact and retained no fixed-workload or quality result.

**Interpretation.** A representation-only comparison is not causally interpretable: it changes to a third-party checkpoint with no retained, hash-bound derivation from V13.  The runtime-only SGLang/vLLM bridge is conceptually possible but not measurement-ready, because its SGLang path includes a GLM-specific loader patch and has only an invalid smoke artifact.  The narrowest ready bridge is AWQ/vLLM H100 versus V21 AWQ/vLLM L40S: it changes hardware only and has a large positive H100 memory margin.  It can estimate only hardware effect for that public AWQ/vLLM stack.

**Decision.** Reserve the hardware-only arm for a later independently authorized session, contingent on an offline SM90 preflight and repeated fixed c1/c8 service results with a >=5% absolute c8 effect gate.  Do not claim representation or runtime attribution.  The observed +16.63% throughput and 81.01% derived-cost differences remain bundled endpoint facts; both endpoints' absolute-quality failures remain in force.

**Next action.** Director may schedule the hardware-only preregistration only after quality and provider-lifecycle gates allow it.  Otherwise close OPP-005 attribution and retain the endpoint result as bundled.
