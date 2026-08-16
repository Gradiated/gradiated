# H100 W4 decode residual mechanism

## Question

What causes the exact H100 W4 endpoint's c128 decode/queue critical path to exceed the economic target by 140.035 seconds per batch, and is there one source- and hardware-grounded attention, KV, scheduler, launch, or small model-geometry change that can remove at least 5% of whole-request cost?

## Why this matters

The complete endpoint is now measured, valid, and economically false: c128 completed 128/128 requests with nonempty outputs at 1.6419997604140635 seconds/request versus the 0.5479752315195353 ceiling. The endpoint needs a 0.6662756933768661 batch-time reduction. Prometheus counters show 97.27675090840627 average decode seconds and 59.66513516813282 queue seconds per request, versus only 3.1395833444453203 prefill seconds and zero preemptions. Meanwhile the measured W4-linear-plus-head batch proxy is only 7.308916656345128 seconds. The unexplained residual, not checkpoint delivery or endpoint plumbing, is now the decision-bearing bottleneck.

## Bound evidence

`BINDINGS.json` mechanically binds the exact model, revision, image, workload, H100 placement, endpoint terminal, before/after c128 metrics, successful W4-plus-head component frontier, and the scope-limited c32 actual local-attention result.

## Scope and method

Use deep profile to trace the pinned vLLM implementation, exact Gemma five-local/one-global attention geometry, FP8-E4M3 KV layout, scheduler batching, CUDA graph/launch path, and H100 occupancy/memory behavior. Quantitatively reconcile endpoint counters with the component proxy.

In this same project, implement and run one checkpoint-free retained-H100 discriminator. Its primary c128 arm must separately measure:

- actual unified FP8-KV cache update;
- the actual selected paged local and global attention consumers in their supported nonzero route;
- a scheduler/launch-only control;
- CUDA-event and synchronized-wall timing across the 358-step layer mix; and
- finite, nonzero numerical oracles.

Use c96 only when it distinguishes scaling. Repair ordinary source, import, context, or harness defects in the retained session. The exact-runtime first call is the discovery audit; do not create a separate packet, audit, readiness, or repair project.

Do not transfer or load the 19.22-GB checkpoint, run another endpoint, repeat W4 linears/head, change hardware, or claim quality/deployability.

## Decision rule

Return a concrete causal chain from measured endpoint behavior through exact source and H100 realization to one discriminating change. Promote only a mechanism with measured or tightly bounded whole-request impact of at least 5%. If attention/KV and scheduler/launch accounting cannot expose a change plausibly large enough to matter against the required 66.63% batch reduction, close this W4/H100 optimization line rather than opening another endpoint retry.

## Resources

- Profile: deep.
- Wall clock: 75 minutes.
- Local compute: 4 CPU-hours.
- Provider: one retained H100 development owner, 45 provider minutes / 0.75 H100-hours.
- Storage: one 100-GiB disk; 4 GiB retrieved artifacts; no checkpoint transfer.
- Spend: $1.80 maximum.
- Cleanup: absolute watchdog plus authenticated zero-resource terminal.
