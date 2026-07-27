# Observable attained-service graph batching

## Question

Can one deterministic, semantics-preserving scheduling change based only on
observable attained output service keep the exact Gemma 4 c32 decode workload
in fuller, more stable CUDA-graph batch buckets, reducing padded inactive
row-steps or scheduler/graph-transition work relative to FIFO without an
output-length oracle?

## Why this matters

The locked qualified service-time denominator is
`0.625149101968745 s/request` and the target is
`0.500119281574996 s/request`. The measured decode scheduler gap is
`0.766971497 s` over the bound request batch, while the currently executing
one-step metadata task has only a `0.0002388184375 s/request` conservative
bound. The completed prefix-affinity project found no additional exact-prefix
reuse in the same c32 requests, so the next zero-cost scheduling question must
not depend on invented cache hits. Background latency can be traded for cost,
but model semantics and compulsory token work are fixed.

## Evidence and inputs

- `../gemma4_decode_scheduler_task_graph/DECODE_SCHEDULER_TASK_GRAPH_OFFLINE_TERMINAL.json`
  binds the current scheduler source path, exact c32 geometry, decode-gap
  attribution, and the small one-step intervention now being measured.
- `../gemma4_prefix_affinity_batching_economics/PREFIX_AFFINITY_BATCHING_OFFLINE_TERMINAL.json`
  binds the exact workload identity and closes additional prefix reuse for
  this trace.
- `CAMPAIGN.md` locks the model, workload economics, qualified denominator,
  and target.

Treat those artifacts as evidence, not permission to replay or modify their
settled candidates.

## Scope

Within 90 wall-clock minutes:

1. Recover the exact content-addressed c32 arrival, prompt, completion, and
   current-runtime graph-bucket identities from the named artifacts and their
   direct inputs. Missing arrival or bucket evidence is `unknown`, not license
   to synthesize it.
2. Define exactly one causal policy using only state available at each
   scheduling decision: arrival ordinal/time, prompt length, tokens already
   generated, request age, completion events, and current resident batch
   state. Future output length, future arrivals, hidden oracle labels, and
   synthetic prefixes are forbidden.
3. Implement the policy source-completely from the pinned scheduler's ready
   queue/selection boundary through the first consumer that determines the
   CUDA-graph batch shape or padded row set. Implement an exact FIFO comparator
   against identical arrivals, tokens, memory capacity, and deadlines.
4. Replay or analytically reconstruct the exact trace and report compulsory
   token work, active and padded row-steps, graph-bucket transitions,
   admission/completion ordering, queue delay, completion time, KV residency,
   and any scheduler CPU work. Do not count dependent synchronization or
   merely delayed work as removed.
5. Persist `ATTAINED_SERVICE_GRAPH_BATCHING_OFFLINE_TERMINAL.json` with direct
   hashes, exact observability contract, source/consumer ownership, physical
   mechanism, FIFO parity, complete latency/memory/cost bounds, and either one
   real current-runtime H200 consumer command or typed `none`.

## Stop and decision rules

- A positive result requires fewer causally attributable padded row-steps,
  graph transitions, or scheduler operations with identical compulsory model
  work and bounded background latency/memory. Queue rearrangement alone is
  not a cost improvement.
- If the exact workload is one simultaneous full c32 batch, lacks admissible
  arrival evidence, or the policy cannot change a real graph consumer without
  an oracle, record a typed negative and stop.
- Do not sweep policies, bucket widths, waits, or thresholds; choose one
  evidence-backed policy and its FIFO comparator.
- Do not claim a GPU, use SSH/provider/endpoints, read checkpoint shards,
  contend with the live scheduler-component bench, or request spend. This is
  an independent zero-GPU mechanism lane.

## Result that changes the portfolio

A source-complete positive with a nonzero locked-request bound queues one
future exact H200 consumer only if later spend authority exists. A typed
negative closes observable attained-service graph batching for this trace and
redirects the next independent lane away from scheduling policy.
