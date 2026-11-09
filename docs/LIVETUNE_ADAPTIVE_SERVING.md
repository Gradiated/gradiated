# Adaptive serving with livetune

livetune keeps SGLang servers tuned to the traffic they carry. It observes each server, proposes changes, measures them against the traffic the server actually saw, and applies the winners while it watches the SLO. This document describes the data it collects, the levers it can move, the harness that decides between them, and how changes reach production. The code is in [`product/inference/livetune`](../product/inference/livetune).

## The loop

| Step       | What runs                                                                                   | Cadence            | Output                                                                        |
| ---------- | ------------------------------------------------------------------------------------------- | ------------------ | ----------------------------------------------------------------------------- |
| Observe    | The plugin in each scheduler; `/metrics`; the controller's windows                          | Continuous         | Per-request records, per-batch counters, utilization windows                  |
| Act        | `livetune control` applying the current policy                                              | Every 5 s          | Live settings that follow the traffic shape, judged on probation              |
| Advise     | `livetune advise` over a trailing window                                                    | Every few minutes  | Proposals with evidence, in three tiers                                       |
| Experiment | `livetune improve` running `tune --trace` on a canary against production's recorded traffic | Per proposal batch | Confirmed winners, or no change                                               |
| Decide     | `livetune policy`                                                                           | Per experiment     | A policy, scoped to the runtime that measured it                              |
| Roll out   | Policy file, launch flags or a bundle, by tier                                              | Per tier           | A policy file in seconds; restart-tier and code-tier changes through a canary |

Each step's output feeds the next, and nothing skips a measurement. A proposal is only a hypothesis. A setting is applied only after it beats the startup settings on the same traffic. A live change is kept only if it holds the SLO during probation.

## Data

### What is collected

| Source                                            | Contents                                                                                                                                                                                                                                                                                  | Where                                              | Cost                                                  |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- | ----------------------------------------------------- |
| Metric windows (`/metrics` every 5 s)             | <ul><li>demand, prompt length, cache hit and output length per request</li><li>per-request decode rate and TTFT p90</li><li>KV used, evictable and free</li><li>eviction seconds, `run_batch` seconds, retractions</li><li>queue-time p90</li></ul>                                       | The controller's log                               | One scrape per window                                 |
| Per-request records (`LIVETUNE_TRACE_DIR`)        | <ul><li>prompt, cached and output tokens</li><li>queue time, scheduler TTFT and decode time</li><li>finish reason and retractions</li><li>spec accept length</li><li>temperature, `max_new_tokens`, and whether constrained, LoRA or session</li><li>keyed prefix-family hashes</li></ul> | JSONL beside the server, rotated at 64 MB, 8 files | One line per finished request, on attention-TP rank 0 |
| Per-batch counters (readback `telemetry.batches`) | Batches, requests, tokens, CUDA-graph batches and seconds, per forward mode                                                                                                                                                                                                               | `/server_info`                                     | A few additions per batch                             |
| Runtime scope                                     | Launch arguments, weights, GPU, KV capacity, source and package digests, kernel and autotune artifacts                                                                                                                                                                                    | Every policy                                       | Computed once, at the first readback                  |

The plugin records each request from SGLang's own output path (`SchedulerOutputStreamer._maybe_log_time_stats`) and each batch from `Scheduler.process_batch_result`. It needs no source patch. A failure to record drops that record and is counted, and it never fails the request.

### What is not collected, and why

Records never contain prompt or output text or token ids. Prompt prefixes appear only as 8-byte BLAKE2b digests at depths of 256, 2,048 and 16,384 tokens, plus one at the cached length. The digests are keyed by `LIVETUNE_TRACE_KEY`, or by a random key kept in the trace directory (`.trace-key`, mode 0600) when that is unset, so data-parallel schedulers sharing a directory hash alike and separate deployments do not. A digest groups requests that share a system prompt or document without revealing either. Under the [data classification policy](security/policies/data-classification-policy.md) the records are usage records and so Confidential. Prompt and output content is Restricted, and it stays in the governed trace store of the [traces plan](TRACES_PLAN.md). Any analysis that needs content, such as building a kernel benchmark from real prompts, must go through that store's access controls. It joins records by request id, never by copying content into livetune.

### What the data answers

| Question                         | Evidence                                                                                                                     |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Is the GPU the bottleneck?       | `forward_share` (time in `run_batch`), decode batch sizes, graph coverage                                                    |
| Is the scheduler the bottleneck? | Eviction share, `get_next_batch_to_run` time, queue time while the GPU has slack                                             |
| What is the traffic?             | Prompt-length bands, output lengths, arrival rate, cache hit, prefix families and their sizes, constrained and greedy shares |
| Where would a kernel pay off?    | Forward time split by mode, mean decode batch, mean extend size, context lengths                                             |
| Did a change help?               | The same trace replayed under each candidate, confirmed in interleaved rounds                                                |

## Levers

Levers come in three tiers, by how they change and what a change risks.

### Live: `/set_internal_state`, applied in milliseconds

| Lever                                        | Effect                                                        | Notes from SGLang `f171859`                                                                                                            |
| -------------------------------------------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `max_running_requests`                       | Running-batch cap: TTFT against per-user speed                | Applied as `pp_max_micro_batch_size`; bounded by the startup value, which sized buffers and graphs                                     |
| `chunked_prefill_size`, `max_prefill_tokens` | Prefill granularity: decode stalls against prefill efficiency | Returned as context overrides, so the sliding-window eviction path sees them too. The dynamic chunk sizer (PP > 1) ignores live values |
| `schedule_policy`                            | Queue order; `lpm` and `dfs-weight` raise prefix hits         | Rebuilds the scheduler's `SchedulePolicy`; a policy that cannot be built is rejected at validation                                     |
| `schedule_conservativeness`                  | Decode headroom reserved at admission                         | Rebuilds `NewTokenRatioTracker` after the override                                                                                     |
| `stream_interval`                            | Tokens per streamed chunk                                     | Read fresh on every output step                                                                                                        |
| `max_queued_requests`                        | Admission limit; 0 = unlimited                                | Rejects only new arrivals                                                                                                              |

Considered but not exposed:

- `num_continuous_decode_steps`: nothing reads it.
- Turning priority scheduling or the prefill delayer on or off: queued requests and collectives assume the startup choice.
- Speculative-decoding geometry: baked into CUDA graphs.
- `enable_mixed_chunk`: forced off for DeepSeek V4.

Speculative accept thresholds are already handled natively by SGLang. They can be added once a deployment runs speculative decoding.

### Restart: launch flags on a canary

These need a restart and a rolling deploy. Examples are CUDA graph batch sizes, memory fraction, speculative-decoding steps and drafts, attention and MoE backends, mixed chunk, histogram buckets, and FlashInfer autotune data. The advisor proposes them with the evidence for each (for example `cuda_graph_max_bs_decode` when decode batches run without graphs). They are measured on a canary started with the new flags, against the same recorded trace.

### Code: forward variants and kernels

Forward variants are Python patches over the model's forward pass or the scheduler. They can call new Triton or CUDA kernels compiled at runtime. A variant's id is the first 48 bits of its code's sha256, so an id names the same code on every host. A variant is installed at startup (`LIVETUNE_STARTUP_VARIANT`) or switched live (`LIVETUNE_LIVE_VARIANTS=1`, on in every GLM runtime mode).

A live switch never frees graphs that are serving. Each variant gets its own runtime state, built while it is installed, and a switch applies a state by pointer:

- **Speculative servers.** The state holds attention backends plus target-verify, draft and draft-extend graphs, built with SGLang's adaptive-speculation builder.
- **Other servers.** The state holds a fresh attention backend and decode graphs.

Measured:

- **GLM-5.3 Flash with EAGLE on B300.** Building a state paused serving for about 9 s and used 0.4 GB per GPU. A switch to a built state happens at the next forward pass without draining. Under a 12-user, 16k-token load it took 2–3 ms with 0 request errors. Ten alternating switches under 24k-token agentic bursts, plus a runtime-compiled Triton kernel, ran with no errors.
- **DeepSeek V4.1 Flash.** Three rounds plus eight switches under a 40-user, 24k-token load ran with 0 errors. The earlier design recaptured graphs in place, and long-context traffic after switching back crashed it with an illegal memory access.

Code a state cannot hold (memory pools, KV layout, weight layout) still needs a startup variant and a rolling restart.

GLM's stock decoding is not repeatable, so the gate also scores each probe prompt teacher-forced and tests the mean logprob shift against stock's own. Live on GLM it kept identity and runtime-compiled Triton variants, and rejected a ×1.05 logit scale at z = −17.

The code tier runs inside `improve`:

1. **Targets.** Each cycle writes `code-targets.json` to its work directory: the advisor's code proposal (whether decode or prefill dominates forward time, the mean decode batch, extend size, context length and cache hit), plus the snapshot of the production window replayed in that cycle.
2. **Variants.** An agent loop such as the [Together Compiler reproduction](../research/tkcc) writes variants for those shapes into `--candidates`. livetune does not write kernels itself.
3. **Gate.** Each new file is gated once per revision on the canary. A failure is rejected for good.
4. **Tuning.** Variants that pass become values of `forward_variant` in the tuning grid. They are measured against the startup settings on the same recorded trace as the live knobs, with the same interleaved confirmation. A candidate that loses `--variant-tries` cycles (default 3) is retired.
5. **Publish.** A winning rule's variant travels inside the policy: the policy carries its code. Each replica's controller registers that code in its variants directory before applying the rule. The policy then goes through the staged replica and fleet guard like any other.

## Experiments

- **Trace replay.** `replay --trace` and `tune --trace` send each recorded request at its recorded time, open loop. Each request keeps its prompt and output length, its temperature, and its shared prefix within its family. A family is the deepest fixed-depth prefix hash that several requests share. Every member gets the same synthetic prefix, including a cold first request, but only to a length proven common: that depth, or a longer cached prefix whose hash two or more members share. Replay sends recorded priorities. It refuses traces it cannot reproduce: constrained decoding, LoRA adapters, sessions, multimodal inputs, separate cache namespaces, and non-streaming early stops. A replay server with `LIVETUNE_REPLAY_STOPS=1` (the GLM runtime's `canary` mode) ends each streaming early stop at its recorded length itself, exactly. Without it, replay cuts the stream and sees the cutoff only at a chunk boundary, so it refuses streaming early stops when a stream interval above 1 or speculative decoding could put several tokens in one chunk. Non-streaming requests are judged on the per-request first-token latency and decode rate SGLang returns with `--enable-metrics`. A tuned rule's cache-hit guard comes from the cache hits production recorded. Every measurement starts from a flushed prefix cache, so no candidate inherits another's warm cache. Prefix-cache behaviour is therefore reproduced without any recorded content. `--speed` compresses time.
- **Closed-loop profiles.** `tune --profiles` sweeps user counts and prompt lengths for policies that must cover shapes the trace has not shown yet.
- **Decisions.** A candidate must beat the startup settings on the SLO first, then on throughput by at least 2%. It must win on the worse of two interleaved repetitions. A result missing per-user speed or TTFT is inconclusive.
- **Staged rollout.** Replay cannot reproduce prompt content, which drives MoE routing, speculative acceptance and numerics. Nor can it reproduce hours of cache state or the fleet router. So a winner runs on one replica first, and `livetune.rollout.judge` compares it with its peers window for window under matched load. Promotion needs an SLO pass rate within 5 points of the peers and per-user speed within 5%. For code-tier changes this stage is mandatory.
- **Production guard.** A live change is on probation for 45 s from the moment it took effect. It is rolled back and penalised if it breaks an SLO that held before. Live per-user speed comes from SGLang's per-request histogram, whose buckets must be fine around the SLO (`--bucket-inter-token-latency`).

## When a change is rolled back

| Layer                                                 | Watches                                                                                                                          | Rolls back when                                                                                                                                                                                                                                  | How                                                                         |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| Tuning                                                | A candidate against startup on the same recorded traffic                                                                         | It does not beat startup on the worse of two interleaved repetitions                                                                                                                                                                             | Never published                                                             |
| Variant gate (`variant-eval`, `improve --candidates`) | Greedy continuations, their logprobs and teacher-forced prompt logprobs against stock, relative to stock's agreement with itself | Prefix agreement falls more than 0.25 below stock's where stock repeats itself; logprob drift exceeds 1.5× stock's (at least 0.08 nats); or the mean prompt-logprob shift exceeds 3× stock's (at least 0.03 nats) at more than 4 standard errors | Switched back; rejected for that revision                                   |
| Each server                                           | The SLO for 45 s after a live change takes effect                                                                                | The SLO held before and fails in most windows                                                                                                                                                                                                    | Previous rule restored; the rule banned for 10 min                          |
| Variant switch                                        | Install and graph recapture on every rank                                                                                        | Either fails on any rank                                                                                                                                                                                                                         | Previous variant restored, then stock; the scheduler stops if neither works |
| Staged replica                                        | The replica against its peers, window for window, at matched load                                                                | SLO pass rate more than 5 points lower, per-user speed more than 5% lower, or TTFT more than 5% worse and over the SLO, over at least 12 measured windows                                                                                        | The replica's previous policy restored; nothing published                   |
| Fleet guard                                           | The fleet for `--guard-seconds` after publishing, against the same span before                                                   | The same thresholds as the stage                                                                                                                                                                                                                 | The previous policy republished                                             |

A large shift in demand between the compared spans makes the stage or guard inconclusive rather than a regression. The stage publishes nothing; the guard keeps the change, which has already passed replay and the stage.

## Rollout

| Tier    | How a change ships                                                                                                                                                                                      | Blast radius                                                       |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Live    | Canary replay picks a winner. One production replica runs it beside its peers on the same live traffic. It reaches the fleet only if the replica is no worse, and is reverted otherwise                 | One replica, then the fleet; each server still on probation        |
| Restart | New launch flags in the runtime config, through a canary and a rolling restart                                                                                                                          | Rolling, one host at a time                                        |
| Code    | Forward and scheduler code: a policy carrying the variant, through the canary, the staged replica and the fleet guard, switched live. Code a runtime state cannot hold: a startup variant in the bundle | One replica, then the fleet; or rolling, with bundle qualification |

A policy only runs on the server it was tuned on. The scope covers launch arguments, weights, GPU, KV capacity, page size, startup settings and variant, whether live variants are on, and digests of the SGLang and livetune sources, installed packages and bundle artifacts. A rebuilt bundle therefore needs new measurements, which the loop produces from the traffic it is already recording.

## Findings

All of these were measured on DeepSeek V4.1 Flash, TP4, on 4×B300, on SGLang `f171859`.

- **Throughput fell as the prefix cache filled, and the fix is still open.** On a server that had run replays for hours, a 40-user long-context probe ran at 43.9 tok/s per user and 1,092 output tok/s. After `/flush_cache` the same probe ran at 65.5 and 1,768.
  - Decode speed at a fixed batch shape did not change over 5.5 hours of uptime: 113 tok/s per request at 40 requests. GPU clocks were at their maximum with no throttling. The lost time was in the scheduler.
  - With the cache full, eviction took 17.1 s of the 150 s probe (44 ms per call), and batch scheduling time doubled.
  - On a fresh server filled with 20 prefix families over 40 minutes, the first probe reproduced it: 51.3 tok/s per user, with 10.1 s of eviction in 150 s.
  - In that reproduction, every later probe ran at 66 tok/s with 0.6 s of eviction, at the same occupancy and with no intervention. The original server stayed slow for hours, so the slow state depends on what fills the cache, not only on how full it is.
  - A hook that raised the minimum eviction size did not engage on this model. Most allocations evict through the sliding-window path or a joint-reclaim walk, which the hook left alone, and the lever was removed.
  - The eviction cost has a cause in the pinned source. Every eviction call rebuilds its priority heap from all evictable leaves. That is `RadixCache.evict` (`list(self.evictable_leaves)`, then `heapify`), and the unified hybrid cache GLM and DeepSeek V4 use (`_evict_device_start`, which scores each leaf's session refs and strategy in Python). A call costs time in proportion to the number of leaves, not the tokens it frees. That fits the 44 ms per call in the family-filled slow state above.
  - A second slow state is not eviction CPU time but lost cache hits. After 10 minutes of unique 8k-token prompts filled the cache, a 40-user, 24k-token probe with 80% shared prefixes ran 14% slower per user: 39.2 against 45.6 tok/s, with TTFT p90 at 3.97 s against 3.54 s. A flush restored 45.1 and 3.30. Eviction stayed at 0.4 s of the probe in both, but the prefix-cache hit fell from 0.799 to 0.735 (measured). That is about a third more uncached prefill per request: 6.4k tokens instead of 4.8k.
  - The in-process sampler (`livetune set profile_seconds=N`) shows where that time goes. Eager prefill (`_execute_extend`) took 61% of the scheduler thread with a fresh cache and 65% with a full one, while the rest of the scheduler's profile scaled with it. That is more prefill work, not slower code.
  - Why hits fall is inferred, not measured. DeepSeek V4's cache is hybrid, and a prefix hit needs both full-attention KV and sliding-window state. The full cache spent visibly more time splitting nodes and freeing sliding-window segments (`redistribute_on_node_split` from 0.2% to 1.1% of samples). So the probe's hot prefixes plausibly lose their sliding-window state to the fill, even though LRU keeps their full KV.
  - GLM-5.3 Flash does not show the unique-prompt slowdown. On a B300 replica, 15 minutes of unique 8k-token prompts (15.5M tokens, more than its 13.8M-token cache) left a 10-user, 20k-token probe at 103.3 tok/s per user against 104.0 on a fresh cache. Its cache hit held at 0.779 against 0.783, although the probe evicted 3.4M tokens.
  - Neither cost is fixed. The eviction rebuild needs one heap kept across calls, as an SGLang overlay with its own A/B. The lost hits need the hybrid cache's per-component eviction to protect a prefix whose full KV is hot, or a periodic trim of cold unique entries before they crowd out hot families.
  - Until then, `advise` reports `eviction_share` and KV occupancy, so the condition is visible when it happens.
- **Live control with a tuned policy** met the SLO in 5 of 5 traffic phases against 3–4 for static settings. Per-user speed in a long-context burst was 112–115 tok/s against 66–67 (see the [livetune README](../product/inference/livetune/README.md)).
- **The default per-request TPOT buckets** are too coarse around an 80 tok/s SLO: live windows read 86 tok/s while the client measured 77.
- **On GLM-5.3 Flash, the qualified launch settings are already near the best live settings.** Profile tuning on a B300 TP2 replica (12-user chat at 2k tokens, 12-user agent at 24k, 24-user burst at 8k) found one gain: 8192-token prefill chunks for chat, 950–986 against 925–929 output tok/s. In a chat → agent → chat replay, alternating live control with the static startup settings twice each, chat phases ran at 969–985 against 953–986 tok/s. That is within run-to-run variation. The agent phase was slower under control: TTFT p90 6.1–6.2 s against 4.8–5.2 s, because the controller kept the chat rule's smaller chunks for the first windows of long prompts. Every phase met the SLO both ways. So on GLM, `observe` is the right mode until a policy shows a gain larger than that noise; the runtime's value there is its telemetry and hot-reloadable variants.
- **The improve loop runs end to end on GLM.** One replica served 12 minutes of mixed chat and agent traffic in `observe` mode; the other ran in `canary` mode. `improve --once` advised from production: requests shared prefixes (cache hit 0.78), so it proposed cache-aware schedule orders, plus a code-tier decode target, since decode was 80% of forward time. It waited for its 420 s window to finish and be written, checked the trace was complete, and replayed the window on the canary for each candidate. Each replay took 427–429 s and completed 1,162 requests with 0 errors. The cache-aware orders lowered TTFT p90 from 7.5 s to 6.2 s but not throughput (691.7–694.5 tok/s), so nothing was published. The first attempt found a recording bug: under attention context parallelism both CP ranks wrote every request. The doubled trace gave the canary twice production's load, with TTFT p90 at 70 s against 1 s and about 450 errors per replay.
- **Replay stops end requests exactly.** With `LIVETUNE_REPLAY_STOPS=1`, the requests carried `max_new_tokens=512` with EOS ignored and a stop at 7 tokens. Streaming and non-streaming both finished at 7 tokens with a `length` finish, and a request without a stop ran its full 40. Non-streaming responses carried SGLang's `first_token_latency` and `decode_throughput`. This server does not use speculative decoding; trimming a speculative run past the stop is covered by unit tests only.
- **The plugin costs about 1% at most.** Recording was on, and the plugin was compared with a server without it, in two alternating restarts per arm. A 40-user, 24k-token agentic phase ran at 45.3 tok/s per user with the plugin and 45.2 without, with TTFT p90 at 3.1 s in both. A 64-user burst of 1.5k-token prompts ran at 48.6 against 49.0 tok/s per user (−0.9%), with TTFT p90 at 1.22 s against 1.18 s.
  - The scheduler thread spent 0.05 s recording about 3,000 requests, 17 µs each. Before hashing moved to a writer thread, a 120k-token prompt cost 5 ms of scheduler time per finished request.
  - The small burst gap is consistent with the writer thread holding the GIL while it serializes records.

## Status

| Piece                                                                                                                 | State                                                                 |
| --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| Live levers, controller, tuner, scope checks                                                                          | Implemented and tested on the pod                                     |
| Per-request records, per-batch counters, utilization windows                                                          | Implemented and tested                                                |
| Advisor rules across the three tiers                                                                                  | Implemented; rules are thresholds, to be calibrated on canary traffic |
| Trace replay and `tune --trace`                                                                                       | Implemented                                                           |
| `livetune improve`: advise → canary replay → publish, with policy hot-reload in `control`                             | Implemented; needs a canary host per scope                            |
| Starting `control` from the GLM runtime's `service.py` (`LIVETUNE_MODE` off, observe, act or canary)                  | Implemented; `improve` runs as an operator job against a canary       |
| `livetune variant-eval`: register, switch live, gate against stock, measure on a trace, switch back                   | Implemented                                                           |
| Fleet guard after promotion                                                                                           | Implemented                                                           |
| Code tier in `improve`: code targets out, variant candidates in, gated, tuned on the trace, shipped inside the policy | Implemented; the agent loop that writes variants is `research/tkcc`   |
