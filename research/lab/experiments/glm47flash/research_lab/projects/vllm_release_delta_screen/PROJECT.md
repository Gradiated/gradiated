# Current vLLM release delta screen

## Question

Does a current pinned vLLM release contain exact GLM-4.7-Flash/AWQ/MoE or high-concurrency scheduler changes versus the campaign's retained v0.15.0 runtime that justify one later matched runtime A/B with a credible path to at least 5% lower cost per output token?

## Why it matters

The active measurement still pins vLLM 0.15.0, while current exact-model recipes and the NVFP4 audit reference substantially newer vLLM code. Runtime improvements are a mechanism distinct from batching and alternate representation, but generic release churn is not enough to justify GPU spend. A source-scoped delta and metadata-only load/config check can cheaply promote or reject one exact runtime candidate while the current-control attempt proceeds independently.

## Relevant evidence

- `current_awq_frontier_v2` binds vLLM 0.15.0 and the verified AWQ revision `ab31d120...`; its eventual c8 arm would be the only admissible runtime denominator.
- The current exact-model scan found official GLM-4.7-Flash vLLM recipes but no transferable numeric result for this exact checkpoint/workload.
- The NVFP4 screen verified current vLLM architecture and compressed-tensors mappings at commit `66b6c684...`, but did not evaluate deltas relevant to the retained AWQ/L40S path.
- Kernel work without a conservative >=5% serving-wall path has already been closed; code changes must be tied to this model and workload rather than assumed beneficial.

## Scope

Complete one zero-cost source and CPU/config screen. Pin exactly one current stable vLLM release or commit. Compare it with v0.15.0 only across paths that can affect this checkpoint and workload: `Glm4MoeLiteForCausalLM`, compressed-tensors AWQ loading, MoE routing/grouped kernels, MLA/attention, KV allocation, long-prefill scheduling, high-concurrency admission, and GLM tool/reasoning frontends where they affect correctness. Bind commits, source files/diffs, release notes, and any exact-model benchmark/config evidence. Label measured upstream results separately from inferred relevance.

Using only model config/tokenizer/index metadata and a CPU or no-GPU container, verify that the candidate runtime recognizes the exact current AWQ architecture and quantization scheme, constructs the launch/config path without fallback, supports the required 32,768+ context, 65,536 scheduler budget and c32 admission flags, and exposes the prompt-logprob/metrics interfaces needed by the campaign. Do not download weights already absent, load a GPU model, or modify the active project. Retain a machine-readable compatibility result and bounded diagnostics.

Rank the delta's likely effect against the 5% gate. Promote at most one runtime A/B spec only if exact-model source changes or scope-matched upstream evidence provide a concrete mechanism and the metadata/config path passes. The prospective A/B must hold checkpoint, tokenizer, workload, concurrency, scheduler policy, quality, hardware, and cost accounting fixed against the new current c8 control. If evidence is generic, frontend-only, correctness-risking, or lacks a plausible >=5% path, close the runtime upgrade without paid work.

Do not use credentials, mutate a provider, run a GPU benchmark, repair V21, or produce a broad changelog. Budget is $0 and this project has no provider ownership.

## Available resources

Use official vLLM source/releases/recipes, the verified current AWQ metadata, `campaign_100` runtime/controller artifacts, current external-scan evidence, and shared source/evidence tools.

## Portfolio-changing result

A compatible exact-model runtime delta with a specific >=5% mechanism earns one bounded same-hardware A/B after the current c8 control exists. No credible delta or failed compatibility closes runtime upgrade as a useful negative and keeps capacity on serving/hardware mechanisms.
