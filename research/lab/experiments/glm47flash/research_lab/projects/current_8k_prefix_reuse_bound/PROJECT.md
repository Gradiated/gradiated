# Current-control 8K prefix-reuse bound

## Question

Does the authoritative 8,192-input/1,024-output background-agent workload contain enough legitimate, tenant-safe reusable prefix state to reduce current-AWQ L40S cost by at least 10%, without exploiting the benchmark's duplicated synthetic prompt?

## Why it matters

The measured c16 control deliberately disables prefix caching and reaches 535.286 output tok/s. Retained scope-adjacent traces assign about 14.83% of wall time to prefill and 85.17% to decode, so a prefix mechanism must conservatively remove roughly 67% of prefill work merely to reach the campaign's 9.955% wall-time reduction / 594.466 tok/s gate. That is a narrow but material serving path, and shared KV blocks could also change capacity.

The current benchmark constructs one exact 8,192-token prompt by repeating a tokenizer atom and sends it repeatedly. Enabling cache on that burst would demonstrate vLLM behavior but would not establish representative agent economics. The historical tenant-isolated V2 replay is only about 164–183 tokens and its tokenizer/runtime identity failed reproduction; it is non-transferable to this current 8K control. A new zero-cost bound should either find source-backed 8K agent reuse in the repository or close the opportunity rather than spending on a synthetic cache win.

## Scope

At zero provider spend, bind the exact current checkpoint, tokenizer/runtime, c16 artifact, prompt construction, retained prefill/decode mix, KV bytes per token, and cache-disabled server contract. Search only repository-owned campaign workload bundles, request plans, and durable agent-session evidence for source-backed 8K prompt diversity and prefix identity. Preserve 8,192 input and 1,024 output tokens, explicit tenant/session boundaries, arrivals, and cache isolation; do not invent a production reuse distribution or transfer the short historical V2 replay.

If admissible current-scope requests exist, build the smallest content-addressed replay/bound needed to calculate reusable-token and block distributions, query/hit timing, shared-KV capacity, c16/c32 admission, prefill work removed, scheduler effects, semantic identity, and conservative endpoint/cost transfer. If no such evidence exists, quantify the minimum missing reuse requirement and close. Treat the duplicated synthetic prompt as an upper stress case only, never the promotion case.

Do not run a GPU, mutate a provider, enable cache in the live launcher, build another controller, repair V21/V2, change model weights or KV precision, or perform general quality work. Do not attach work to the native-MTP session.

## Resources

- Current content-addressed control: `../nebius_current_awq_c16_direct/`.
- Current saturation and prefill/decode bounds: `../current_awq_saturation_bound/` and `../sequence_early_exit_architecture/sequence_early_exit_bound.json`.
- Historical prefix work, usable only as non-transferable prior: `../agent_prefix_serving/`.
- Campaign workload bundles and runner source: `/root/workspace/research/lab/experiments/glm47flash/campaign_100/workloads/` and `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_batched_runner.py`.
- Shared tooling: `/root/workspace/research/factory/tools` and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.

## Portfolio-changing result

Nominate at most one later matched cache-off/on current-runtime session only if a source-backed 8K replay passes tenant isolation and conservative reuse/scheduler accounting supports at least 594.466 output tok/s with exact semantic identity. The nomination must state the reusable-token distribution, cache/KV counters, one bounded retained session, and why the workload is representative rather than a duplicated-prompt artifact. Otherwise close current-control prefix reuse without provider work.
