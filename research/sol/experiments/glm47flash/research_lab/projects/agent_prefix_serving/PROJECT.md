# Agent-prefix serving mechanism

## Question

Can tenant-safe exact prefix reuse improve GLM-4.7-Flash SLO-goodput or token cost by at least 5% on a representative agent-session replay under a fixed scheduling and admission policy?

## Why it matters

This is a materially different serving lever from custom kernels. The current fixed burst deliberately disables prefix caching and records zero cache queries and hits, so it cannot measure a common agent-serving opportunity. V19 measured 0.5954 seconds mean queue time at c8, while the later 65K prefill cap reduced it to about 13 microseconds and improved throughput by 3.36%; the remaining benefit of realistic shared prefixes, arrivals, and scheduling is unknown.

## Relevant evidence

- `campaign_100/workloads/`, including the frozen workload contract and replay tooling.
- `campaign_100/allocations/nebius_l40s_vllm_awq_batch_v19/` and `nebius_l40s_vllm_awq_prefill65k_v21/`.
- Opportunity `OPP-004` in `campaign_100/analysis/OPPORTUNITY_REGISTER_2026-07-14.json`.
- Measured limitation: existing cache counters are zero by construction and repeated fixed prompts would exaggerate reuse if caching were simply enabled.

## Scope

Define a content-addressed agent-session replay with explicit tenant boundaries, prefix identities, reusable-token distribution, arrival schedule, and overload points. Establish analytical reuse and KV-capacity bounds before GPU work. If the workload has material legitimate reuse, run matched cache-off/on controls on the same AWQ/vLLM/L40S stack while holding scheduling, admission, generation, model, checkpoint, runtime, request identities, and SLO accounting fixed. Capture cache hits and reused tokens rather than inferring them. Do not modify kernels, recalibrate the quality suite, repair observer tooling, tune batching/scheduling, or generalize from the repeated fixed-prompt workload. Require exact deterministic semantic identity for this diagnostic; the campaign-wide quality claim remains blocked by the separate quality project.

## Available resources

Use the shared factory tools, campaign replay/tokenizer code, vLLM metrics, and existing provider controls. Keep the first paid matched session within $1.50 and 60 minutes, with a single provider owner, an absolute watchdog, immutable arm artifacts, full-session cost accounting, and verified cleanup. Do not overlap another lab paid allocation; queue compatible arms on one retained same-stack session when ownership and the ten-minute retention rule allow it.

The final source/timing audit preserves the empirical cache-on hypothesis, but the V33 reproduction audit freezes this execution lineage. The retained V21 runtime reports Transformers 5.3.0.dev0 while the binding requires 5.12.1, and the available 5.12.1 path yields 164 rather than 183 tokens for every V2 request. Do not repair, create a provider, or spend under this project. Its V21/V2 artifacts are non-transferable historical priors only.

A future prefix experiment must be newly scoped after a content-addressed current control exists. It must regenerate the replay under the current tokenizer/runtime, use an adjacent same-identity cache-off control, and make no direct performance or quality delta claim to V21/V2.

## Portfolio-changing result

This historical project is paused without a scientific cache result. Its analytical reuse bound can inform a newly scoped current-control experiment, but it cannot promote or reject prefix reuse. Any future promotion still requires a matched >=5% cost or goodput gain, measured legitimate reuse, tenant safety, semantic identity, and the declared background reliability envelope.
