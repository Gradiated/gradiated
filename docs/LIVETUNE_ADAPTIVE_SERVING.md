# Adaptive serving with livetune

livetune keeps SGLang servers tuned to the traffic they carry. It observes each server, proposes changes, measures them against the traffic the server actually saw, and applies the winners while it watches the SLO. This document describes the data it collects, the levers it can move, the harness that decides between them, and how changes reach production. The code is in [`product/inference/livetune`](../product/inference/livetune).

## The loop

| Step | What runs | Cadence | Output |
| --- | --- | --- | --- |
| Observe | The plugin in each scheduler; `/metrics`; the controller's windows | Continuous | Per-request records, per-batch counters, utilization windows |
| Act | `livetune control` applying the current policy | Every 5 s | Live settings that follow the traffic shape, judged on probation |
| Advise | `livetune advise` over a trailing window | Every few minutes | Proposals with evidence, in three tiers |
| Experiment | `livetune improve` running `tune --trace` on a canary against production's recorded traffic | Per proposal batch | Confirmed winners, or no change |
| Decide | `livetune policy` | Per experiment | A policy, scoped to the runtime that measured it |
| Roll out | Policy file, launch flags or a bundle, by tier | Per tier | A policy file in seconds; restart-tier and code-tier changes through a canary |

Each step's output feeds the next, and nothing skips a measurement. A proposal is only a hypothesis. A setting is applied only after it beats the startup settings on the same traffic. A live change is kept only if it holds the SLO during probation.

## Data

### What is collected

| Source | Contents | Where | Cost |
| --- | --- | --- | --- |
| Metric windows (`/metrics` every 5 s) | <ul><li>demand, prompt length, cache hit and output length per request</li><li>per-request decode rate and TTFT p90</li><li>KV used, evictable and free</li><li>eviction seconds, `run_batch` seconds, retractions</li><li>queue-time p90</li></ul> | The controller's log | One scrape per window |
| Per-request records (`LIVETUNE_TRACE_DIR`) | <ul><li>prompt, cached and output tokens</li><li>queue time, scheduler TTFT and decode time</li><li>finish reason and retractions</li><li>spec accept length</li><li>temperature, `max_new_tokens`, and whether constrained, LoRA or session</li><li>keyed prefix-family hashes</li></ul> | JSONL beside the server, rotated at 64 MB, 8 files | One line per finished request, on attention-TP rank 0 |
| Per-batch counters (readback `telemetry.batches`) | Batches, requests, tokens, CUDA-graph batches and seconds, per forward mode | `/server_info` | A few additions per batch |
| Runtime scope | Launch arguments, weights, GPU, KV capacity, source and package digests, kernel and autotune artifacts | Every policy | Computed once, at the first readback |

The plugin records each request from SGLang's own output path (`SchedulerOutputStreamer._maybe_log_time_stats`) and each batch from `Scheduler.process_batch_result`. It needs no source patch. A failure to record drops that record and is counted, and it never fails the request.

### What is not collected, and why

Records never contain prompt or output text or token ids. Prompt prefixes appear only as 8-byte BLAKE2b digests at depths of 256, 2,048 and 16,384 tokens, plus one at the cached length. The digests are keyed by `LIVETUNE_TRACE_KEY`, or by a random key kept in the trace directory (`.trace-key`, mode 0600) when that is unset, so data-parallel schedulers sharing a directory hash alike and separate deployments do not. A digest groups requests that share a system prompt or document without revealing either. Under the [data classification policy](security/policies/data-classification-policy.md) the records are usage records and so Confidential. Prompt and output content is Restricted, and it stays in the governed trace store of the [traces plan](TRACES_PLAN.md). Any analysis that needs content, such as building a kernel benchmark from real prompts, must go through that store's access controls. It joins records by request id, never by copying content into livetune.

### What the data answers

| Question | Evidence |
| --- | --- |
| Is the GPU the bottleneck? | `forward_share` (time in `run_batch`), decode batch sizes, graph coverage |
| Is the scheduler the bottleneck? | Eviction share, `get_next_batch_to_run` time, queue time while the GPU has slack |
| What is the traffic? | Prompt-length bands, output lengths, arrival rate, cache hit, prefix families and their sizes, constrained and greedy shares |
| Where would a kernel pay off? | Forward time split by mode, mean decode batch, mean extend size, context lengths |
| Did a change help? | The same trace replayed under each candidate, confirmed in interleaved rounds |

## Levers

Levers come in three tiers, by how they change and what a change risks.

### Live: `/set_internal_state`, applied in milliseconds

| Lever | Effect | Notes from SGLang `f171859` |
| --- | --- | --- |
| `max_running_requests` | Running-batch cap: TTFT against per-user speed | Applied as `pp_max_micro_batch_size`; bounded by the startup value, which sized buffers and graphs |
| `chunked_prefill_size`, `max_prefill_tokens` | Prefill granularity: decode stalls against prefill efficiency | Returned as context overrides, so the sliding-window eviction path sees them too. The dynamic chunk sizer (PP > 1) ignores live values |
| `schedule_policy` | Queue order; `lpm` and `dfs-weight` raise prefix hits | Rebuilds the scheduler's `SchedulePolicy`; a policy that cannot be built is rejected at validation |
| `schedule_conservativeness` | Decode headroom reserved at admission | Rebuilds `NewTokenRatioTracker` after the override |
| `stream_interval` | Tokens per streamed chunk | Read fresh on every output step |
| `max_queued_requests` | Admission limit; 0 = unlimited | Rejects only new arrivals |

Considered but not exposed:
- `num_continuous_decode_steps`: nothing reads it.
- Turning priority scheduling or the prefill delayer on or off: queued requests and collectives assume the startup choice.
- Speculative-decoding geometry: baked into CUDA graphs.
- `enable_mixed_chunk`: forced off for DeepSeek V4.

Speculative accept thresholds are already handled natively by SGLang. They can be added once a deployment runs speculative decoding.

### Restart: launch flags on a canary

These need a restart and a rolling deploy. Examples are CUDA graph batch sizes, memory fraction, speculative-decoding steps and drafts, attention and MoE backends, mixed chunk, histogram buckets, and FlashInfer autotune data. The advisor proposes them with the evidence for each (for example `cuda_graph_max_bs_decode` when decode batches run without graphs). They are measured on a canary started with the new flags, against the same recorded trace.

### Code: forward variants and kernels

Forward variants are pinned Python patches over the model's forward pass, hashed into the scope. They can call new Triton or CUDA kernels compiled at runtime. A variant is installed at startup (`LIVETUNE_STARTUP_VARIANT`) or switched live (`LIVETUNE_LIVE_VARIANTS=1`). A live switch drains the scheduler, installs the variant and recaptures decode graphs with SGLang's own runtime sequence. On DeepSeek V4.1 Flash, three switches under an 8-user load each paused serving for 27–33 s with 0 errors, and switching back reproduced stock greedy output exactly. Long-context traffic after switching a variant in and back out still crashes it, with an illegal memory access. That happened with or without a cache flush, and not under `CUDA_LAUNCH_BLOCKING=1`, which points to a race in runtime recapture. Startup variants and rolling restarts are therefore the production path for code changes. Live switching is for short-context checks on a canary until the race is fixed upstream or here. Once it is fixed, testing a variant costs one switch on a running canary, not a restart. The [Together Compiler reproduction](../research/tkcc) is the agent loop that writes and checks such variants. It has a persistent engine, a correctness gate, a cost model and a message board. livetune gives that loop its targets. The advisor's code-tier proposal names whether decode or prefill dominates forward time, along with the mean decode batch, extend size, context length and cache hit. A recorded trace replays the traffic the variant has to win on. A winning variant goes to a staged replica, live or at startup, and ships in the bundle.

livetune does not write kernels itself today. The path is:
1. The advisor names the hot shapes.
2. The agent loop writes and checks a variant for them.
3. The canary measures it on the recorded trace.
4. A bundle rollout ships it.

## Experiments

- **Trace replay.** `replay --trace` and `tune --trace` send each recorded request at its recorded time, open loop. Each request keeps its prompt and output length, its temperature, and its shared prefix within its family. A family is the deepest fixed-depth prefix hash that several requests share. Every member gets the same synthetic prefix, including a cold first request, but only to a length proven common: that depth, or a longer cached prefix whose hash two or more members share. Replay sends recorded priorities. It refuses traces it cannot reproduce: constrained decoding, LoRA adapters, sessions, multimodal inputs, separate cache namespaces, and early stops it cannot cut off exactly. Those are non-streaming early stops, and streaming ones while any stream interval in play is above 1, since replay sees the cutoff only at a chunk boundary. A tuned rule's cache-hit guard comes from the cache hits production recorded. Every measurement starts from a flushed prefix cache, so no candidate inherits another's warm cache. Prefix-cache behaviour is therefore reproduced without any recorded content. `--speed` compresses time.
- **Closed-loop profiles.** `tune --profiles` sweeps user counts and prompt lengths for policies that must cover shapes the trace has not shown yet.
- **Decisions.** A candidate must beat the startup settings on the SLO first, then on throughput by at least 2%. It must win on the worse of two interleaved repetitions. A result missing per-user speed or TTFT is inconclusive.
- **Staged rollout.** Replay cannot reproduce prompt content, which drives MoE routing, speculative acceptance and numerics. Nor can it reproduce hours of cache state or the fleet router. So a winner runs on one replica first, and `livetune.rollout.judge` compares it with its peers window for window under matched load. Promotion needs an SLO pass rate within 5 points of the peers and per-user speed within 5%. For code-tier changes this stage is mandatory.
- **Production guard.** A live change is on probation for 45 s from the moment it took effect. It is rolled back and penalised if it breaks an SLO that held before. Live per-user speed comes from SGLang's per-request histogram, whose buckets must be fine around the SLO (`--bucket-inter-token-latency`).

## When a change is rolled back

| Layer | Watches | Rolls back when | How |
| --- | --- | --- | --- |
| Tuning | A candidate against startup on the same recorded traffic | It does not beat startup on the worse of two interleaved repetitions | Never published |
| Variant gate (`variant-eval`) | Greedy continuations and logprobs against stock, relative to stock's agreement with itself | Prefix agreement falls more than 0.25 below stock's, or logprob drift exceeds 1.5× stock's (at least 0.08 nats) | Switched back to stock; rejected |
| Each server | The SLO for 45 s after a live change takes effect | The SLO held before and fails in most windows | Previous rule restored; the rule banned for 10 min |
| Variant switch | Install and graph recapture on every rank | Either fails on any rank | Previous variant restored, then stock; the scheduler stops if neither works |
| Staged replica | The replica against its peers, window for window, at matched load | SLO pass rate more than 5 points lower, per-user speed more than 5% lower, or TTFT more than 5% worse and over the SLO, over at least 12 measured windows | The replica's previous policy restored; nothing published |
| Fleet guard | The fleet for `--guard-seconds` after publishing, against the same span before | The same thresholds as the stage | The previous policy republished |

A large shift in demand between the compared spans makes the stage or guard inconclusive rather than a regression. The stage publishes nothing; the guard keeps the change, which has already passed replay and the stage.

## Rollout

| Tier | How a change ships | Blast radius |
| --- | --- | --- |
| Live | Canary replay picks a winner. One production replica runs it beside its peers on the same live traffic. It reaches the fleet only if the replica is no worse, and is reverted otherwise | One replica, then the fleet; each server still on probation |
| Restart | New launch flags in the runtime config, through a canary and a rolling restart | Rolling, one host at a time |
| Code | A variant registered by hash in the bundle, selected by `LIVETUNE_STARTUP_VARIANT`, through the bundle release pipeline | Rolling, with bundle qualification |

A policy only runs on the server it was tuned on. The scope covers launch arguments, weights, GPU, KV capacity, page size, startup settings and variant, the variant catalog, and digests of the SGLang and livetune sources, installed packages and bundle artifacts. A rebuilt bundle therefore needs new measurements, which the loop produces from the traffic it is already recording.

## Findings

All of these were measured on DeepSeek V4.1 Flash, TP4, on 4×B300, on SGLang `f171859`.

- **Throughput fell as the prefix cache filled, and the fix is still open.** On a server that had run replays for hours, a 40-user long-context probe ran at 43.9 tok/s per user and 1,092 output tok/s. After `/flush_cache` the same probe ran at 65.5 and 1,768.
  - Decode speed at a fixed batch shape did not change over 5.5 hours of uptime: 113 tok/s per request at 40 requests. GPU clocks were at their maximum with no throttling. The lost time was in the scheduler.
  - With the cache full, eviction took 17.1 s of the 150 s probe (44 ms per call), and batch scheduling time doubled.
  - On a fresh server filled with 20 prefix families over 40 minutes, the first probe reproduced it: 51.3 tok/s per user, with 10.1 s of eviction in 150 s.
  - In that reproduction, every later probe ran at 66 tok/s with 0.6 s of eviction, at the same occupancy and with no intervention. The original server stayed slow for hours, so the slow state depends on what fills the cache, not only on how full it is.
  - A hook that raised the minimum eviction size did not engage on this model. Most allocations evict through the sliding-window path or a joint-reclaim walk, which the hook left alone, and the lever was removed.
  - Next: profile the scheduler with py-spy in the slow state. Then test two options against the original replay pattern: proactive eviction to a watermark, and a smaller prefix-cache budget.
  - Until then, `advise` reports `eviction_share` and KV occupancy, so the condition is visible when it happens.
- **Live control with a tuned policy** met the SLO in 5 of 5 traffic phases against 3–4 for static settings. Per-user speed in a long-context burst was 112–115 tok/s against 66–67 (see the [livetune README](../product/inference/livetune/README.md)).
- **The default per-request TPOT buckets** are too coarse around an 80 tok/s SLO: live windows read 86 tok/s while the client measured 77.

## Status

| Piece | State |
| --- | --- |
| Live levers, controller, tuner, scope checks | Implemented and tested on the pod |
| Per-request records, per-batch counters, utilization windows | Implemented and tested |
| Advisor rules across the three tiers | Implemented; rules are thresholds, to be calibrated on canary traffic |
| Trace replay and `tune --trace` | Implemented |
| `livetune improve`: advise → canary replay → publish, with policy hot-reload in `control` | Implemented; needs a canary host per scope |
| Starting `control` and `improve` from the runtime's `service.py` | Next |
| `livetune variant-eval`: register, switch live, gate against stock, measure on a trace, switch back | Implemented |
| Fleet guard after promotion | Implemented |
| Code-tier targets handed to the variant agent loop, which calls `variant-eval` | Next; the loop exists in `research/tkcc` |
