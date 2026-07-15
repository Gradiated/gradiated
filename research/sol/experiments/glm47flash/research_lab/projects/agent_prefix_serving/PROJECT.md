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

The final source/timing audit is accepted as readiness evidence: pinned vLLM 0.15.0 commits full cache blocks at scheduler allocation before response completion, and retained V21 TPOT p95 provides a measured scheduler-step proxy supporting all 16 timing-eligible reuse requests under the unchanged 100 ms gaps. This does not measure V2 cache behavior. Pause local work and do not mutate the provider while quality owns the paid session. After a later explicit handoff and fresh zero inventory, execute the existing V2 cache-on smoke unchanged. At least two same-session hits and positive reused-token telemetry are required only to continue to a cache-off arm; promotion still requires a matched >=5% SLO-goodput or token-cost gain, deterministic semantic identity, declared reliability/SLO compliance, full-session cost accounting, and verified cleanup.

## Portfolio-changing result

A repeated >=5% SLO-goodput or derived token-cost improvement with measured legitimate reuse becomes the tuned serving incumbent that later model-specific work must beat. Negligible reusable-token share or a matched gain below 5% deprioritizes caching and scheduling for this workload. Output divergence, tenant-unsafe reuse, or SLO-tail regression rejects the candidate regardless of throughput.
