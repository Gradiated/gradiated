# Research log

## 2026-07-15 — frozen replay identity and cache-isolation audit

Question: can the existing `agent_prefix_c8` profile support a tenant-safe cache-off/on control before a paid L40S session?

Contract and code examined: the frozen workload bundle (`f47c7af5e53483524010d06a93313b29f1a10c08f7df4bf18638349b4767193a`), its replay schedule and tokenizer bindings, `replay_api.py`, V21's vLLM command/log, and the OPP-004 contract. The bundle validator and replay unit suite passed unchanged (`9` tests). I produced a deterministic candidate plan and derived-readiness artifact at `artifacts/agent_prefix_c8_tenant_isolated.plan.json` and `artifacts/PREFIX_REPLAY_READINESS.json` using `build_replay_readiness.py`.

Derived evidence: the profile has 24 requests in eight three-turn sessions. Each prompt has 183 server-reported input tokens and a 180-token exact common prefix. With the V21 vLLM block geometry of 16 tokens, up to 176 tokens per reusable request are eligible; the tenant/session-isolated upper bound is therefore 16 reuse requests, 2,816 saved prefill tokens, or 64.12% of the 4,392 input tokens. V21 reported 333,488 KV-cache tokens. Even the conservative all-request prompt-plus-generation-cap upper bound is 6,696 tokens (2.01%), so KV capacity cannot explain a miss for this diagnostic.

Negative result: the frozen replay request schema permits only fixture/prompt/message fields and rejects `cache_salt` with `request fields are not exact`. Its HTTP transport also cannot send that field. Consequently, the schedule's stated `same synthetic session and tenant only` reuse scope is not enforced at the vLLM cache boundary; materializing eight otherwise-identical sessions would permit cross-session reuse. A direct cache-on measurement would be tenant-unsafe and scientifically inadmissible. This was confirmed without changing the frozen bundle; an exploratory runner change was reverted because the bundle validator correctly detected that it invalidated the immutable manifest.

Interpretation: OPP-004 has material analytical headroom, but the present V1 replay is not a paid-control-ready workload. The 100 ms within-session offsets provide a second uncertainty: they do not prove that the first prefill completes before the second request, so even after isolation the 16-hit calculation is an upper bound rather than a predicted observed count.

Next action: create a versioned workload-bundle amendment that adds a protected per-session `cache_salt` to both replay validation and the OpenAI payload, regenerates all content identities, then run a local cache-on smoke that captures per-request query/hit/reused-token telemetry before admitting the matched cache-off/on session. No GPU allocation or provider mutation occurred in this turn.

## 2026-07-15 — V2 tenant-isolated replay amendment

Question: can the isolation defect be repaired without mutating the V1 frozen workload or changing any controlled serving variable?

Implemented and executed `v2_replay_contract.py` with a behavioral test in `test_v2_replay_contract.py`. The V2 plan is content-addressed by `v2_bundle_sha256` `3f768f0e49fe7a3da202e91308651dcc844308651f10299266bce8db5b6c921c` and explicitly derives from immutable V1 bundle `f47c7af5e53483524010d06a93313b29f1a10c08f7df4bf18638349b4767193a`. It preserves the V1 `agent_prefix_c8` fixture, 24 request identities, token bindings, generation (`seed=470100`, greedy), fixed session-relative arrivals, and enabled-cache setting. It adds only the isolation envelope: each of the eight sessions has a deterministic, distinct 64-hex-character salt; all three turns in one session share that salt. The local validator reuses V1 request validation after removing the envelope and rejects a request whose salt no longer binds its declared session.

Measured local-contract result: the behavioral test passed, and `artifacts/agent_prefix_c8_v2_tenant_isolated.plan.json` has 24 requests and eight unique salts. `artifacts/V2_REPLAY_AMENDMENT_MANIFEST.json` records the plan hash `04c1abc58eee139fdfd618d78d5466db93a66888d8667420d7a72d67234aa32f`. The payload constructor places the same salt in the OpenAI request alongside the frozen messages/tools and continuous usage stream options. This matches vLLM 0.15's documented cache-isolation interface; this is source-backed interface evidence, not a measured cache hit.

Constraint check: `CAMPAIGN_STATUS.json` has no active pod, but `claims_permitted` is false and its next bounded paid cycle is reserved for `supervisor-glm47`'s observer recovery. The project scope also prohibits overlap with another lab paid allocation. No provider action was taken.

Interpretation: the original tenant-safety blocker is resolved at the versioned workload-contract layer, while V1 remains reproducible. The remaining evidence gate is operational rather than analytical: a same-stack V2 cache-on server smoke must demonstrate nonzero aggregate cache query/hit deltas and per-request reused prompt tokens, with all tenant/session salts recorded, before a $1.50 matched cache-off/on session can be admitted. The 100 ms arrival uncertainty remains and must be reported as observed hit coverage rather than assumed reuse.

Next action: when the director's retained/approved L40S session is available and no other paid allocation overlaps, run the V2 cache-on smoke first. Require the V2 manifest, V1 model/runtime/checkpoint identities, raw request payload digests, cache counters before/after, per-request reused-token evidence, SLO/tail outcomes, and verified cleanup. Reject promotion if tenant isolation, semantic identity, or cache telemetry is absent.

## 2026-07-15 — launch-ready V2 cache-on smoke packet

Question: can a later provider owner run the V2 smoke with a complete, stack-native telemetry and failure contract, without changing scheduling or creating a competing allocation now?

Local implementation and test: added `cache_on_smoke_packet.py`, parser fixtures under `fixtures/`, and `test_cache_on_smoke_packet.py`. The packet reads and validates the V2 plan, derives the exact V21 AWQ/vLLM/L40S launch command, and requires `--enable-prefix-caching --enable-prompt-tokens-details`. The latter is necessary because vLLM 0.15 exposes per-request cached prompt tokens in `usage.prompt_tokens_details.cached_tokens` only when prompt-token details are enabled. Aggregate prefix-cache queries/hits remain independently captured from `/metrics`.

The fixture experiment passed locally: synthetic counter deltas of 4,392 queries and 2,816 hits plus a successful row with 176 cached prompt tokens satisfy the parser; a successful request without `prompt_tokens_details.cached_tokens` fails closed. This validates parser behavior only, not cache effectiveness. The packet is `artifacts/V2_CACHE_ON_SMOKE_PACKET.json` with experiment id `glm47-agent-prefix-v2-cache-on-smoke`, V2 plan hash `a6b4415b2b87823d518594a8a152bdb25e00c269f278ffcda08988453581fddd`, and V2 bundle identity `cb6617da379ab40cab6ed513e6ed562eeef82afd93ec5f6c82978d7f865288f2`.

Correction: the prior V2 payload used the tokenizer repository name as `model`, while the V21 server is pinned to `--served-model-name glm-4.7-flash-awq`. A regression test exposed that mismatch. V2 now binds the served model name into its content identity and emits `glm-4.7-flash-awq`; no V1 artifact changed.

Preregistered smoke geometry: fixed V21 model path, tokenizer, AWQ/bfloat16 runtime, L40S, 32,768 model length, eight sequences, 65,536 batched tokens, generation seed/greedy settings, and V2 arrivals. Changed variables are only prefix caching, prompt-token-details telemetry, and the per-session isolation salt. Success requires all 24 requests to be non-truncated successes; positive aggregate cache query/hit deltas; positive summed per-request cached tokens; retained V2 salts; TTFT p95 <= 10,000 ms; ITL p95 <= 100 ms; and deterministic output digest identity on a repeat. Missing telemetry, zero cache evidence, request failure/truncation, semantic divergence, or a partial archive stop promotion and preserve only an operational-failure artifact.

No provider operation occurred: the project remains explicitly deferred while `batching_slo_frontier` owns the next paid cycle. When reassigned, the packet limits the smoke to 1,800 seconds and $0.45 allocation exposure, retains a $1.50 session cap, and requires a 60-minute absolute cleanup watchdog plus verified zero-inventory teardown.

Next action: wait for a director handoff naming this project the provider owner; then execute this packet unchanged before admitting any matched cache-off/on arm.

## 2026-07-15 — executable V2 smoke runner

Question: does the launch packet have an executable, fail-closed replay path, or merely a static command and parser specification?

Implemented `v2_cache_smoke_runner.py` and its behavioral test. The runner accepts only the immutable V2 plan, executes exactly two repetitions, warms the session, verifies `/flush_cache`, records raw `/metrics` before and after each measured replay, dispatches the 24 requests at their frozen offsets, and writes per-request payload/SSE identities, salts, final usage, and cached-token details. It invokes the existing cache-counter/cached-token gate for each repetition and then requires exact request-id/SSE-digest sequence equality across repetitions. Any missing `usage.prompt_tokens_details.cached_tokens`, non-success row, absent cache salt, counter failure, or digest divergence causes a typed nonzero result and leaves the raw partial artifacts intact.

The new runner test passed locally, including a positive cached-token/digest-identity case and a missing-cached-token/digest-divergence rejection. The command-line interface and packet regeneration passed. This remains a local execution-path validation; no vLLM server or GPU was available or started, and no provider mutation occurred.

Interpretation: the V2 smoke can now be executed unchanged by the future assigned provider owner rather than reimplemented during a billed allocation. The remaining unknown is strictly empirical cache behavior and service latency on the pinned L40S session. The project remains deferred by the declared `batching_slo_frontier` provider ownership, not blocked by a missing local artifact.

Next action: retain the packet and runner unchanged until a director handoff assigns this project provider ownership; then run `v2_cache_smoke_runner.py` against the retained V21-equivalent server before considering any matched cache-off/on arm.

## 2026-07-15 — paid-smoke preregistration and lifecycle admission

Question: can the eventual paid smoke be admitted without repeating V31's turn-scoped-controller failure or exceeding its own stated all-in cap?

Implemented `paid_smoke_preregistration.py`, its behavioral validation, and `artifacts/V2_CACHE_ON_PAID_PREREGISTRATION.json`. The preregistration content-binds the immutable V2 plan, smoke packet, V2 contract, and executable runner by SHA-256. It permits only the first cache-on evidence gate; a cache-off arm remains prohibited until this smoke produces complete admissible evidence.

Budget correction (derived): the old packet paired 1,800 allocation seconds with a $0.45 exposure cap but also required a $0.07 cleanup reserve. At the V21 measured VM-plus-disk rate of $0.8581222/hour, 1,800 seconds costs $0.4291 before reserve, or $0.4991 all-in, exceeding the cap. The frozen paid contract instead budgets seven phases totaling 1,500 seconds: 90 controller/create, 360 identity/readiness, 180 warmup/reset, 240 repetition one, 240 repetition two, 150 artifact retrieval, and 240 teardown. Compute is $0.3576; with the $0.07 reserve, the all-in cap is $0.4276, below $0.45 and the project-wide $1.50 ceiling.

Lifecycle gate: provider creation is forbidden unless a later director handoff names this project sole owner, V31 teardown and fresh zero inventory are verified, and a factory-managed controller outside the Codex process group has persisted a live controller state and independent watchdog state. Both records must identify the allocation, PIDs, heartbeat, and absolute deadline; no create event may precede their validation. Terminal reconciliation requires controller terminal evidence, watchdog cancellation only after cleanup, instance not-found, zero named instance/disk inventory, and complete hashed local artifacts. A Codex turn may observe but cannot be the sole owner of a live provider controller, transfer, retrieval, or cleanup command.

The preregistration test passed locally. No provider was created, attached, queried for mutation, or cleaned up by this project. `batching_slo_frontier` remains the sole V31 cleanup owner; this project remains local-only until it releases ownership and the director explicitly transfers it.

Next action: await a director handoff after V31 terminal cleanup. The new owner must validate the preregistration source hashes and lifecycle state records immediately before provider creation; otherwise stop without creating an allocation.

## 2026-07-15 — fresh-start budget amendment

Question: does the paid-smoke contract remain feasible when it includes the fresh AWQ checkpoint transfer that V19 actually required?

Action: continued the pre-existing red preregistration test, then amended only `paid_smoke_preregistration.py` and regenerated `artifacts/V2_CACHE_ON_PAID_PREREGISTRATION.json`. The contract now has eight bounded phases totaling 2,700 seconds, including a dedicated 900-second `verified_awq_checkpoint_transfer` phase. The lifecycle deadline binding was changed from `allocation_start_plus_1500_seconds` to `allocation_start_plus_2700_seconds`; the immutable V2 plan, replay contract, smoke packet, and runner remain source-hashed inputs.

Measured/derived evidence: V19 records 894.59 seconds from instance creation through verified AWQ transfer and 1,400.426 seconds through its first retrieved result. The amended compute allowance is `2700 / 3600 * $0.8581222 = $0.64359165`; adding the fixed $0.07 cleanup reserve gives a `$0.71359165` all-in cap. This is below the new $0.75 allocation cap and the existing $1.50 project session cap. The local project suite passes all six tests.

Interpretation: the earlier 1,500-second preregistration was operationally infeasible for a fresh-start session, not evidence against prefix reuse. The amendment makes transfer variance explicit while retaining enough time for two measured repetitions, retrieval, and verified teardown. This is local readiness evidence only; cache effectiveness, latency, and cost benefit remain unmeasured.

Next move: remain local-only until the director names this project sole provider owner and the durable controller project confirms fresh zero inventory. Then validate these source hashes and lifecycle records immediately before creation and run the cache-on gate unchanged.

## 2026-07-15 — deterministic arrival/cache-availability falsifier

Question: do the frozen 100 ms within-session gaps leave enough time for exact prefixes to enter vLLM's cache to clear the campaign's 5% economic target?

Action: added and ran `arrival_cache_bound.py` against the immutable V2 plan and retained V21 L40S/vLLM telemetry. The simulation counts a predecessor as eligible only when its assumed first-token/cache-insertion latency is no later than the next same-session arrival. It does not alter the replay, runner, arrivals, provider, or quality suite. Raw derived output is `artifacts/ARRIVAL_CACHE_AVAILABILITY_BOUND.json`.

Evidence: the 24-request, eight-session schedule has 16 potential reuse requests, 176 reusable tokens per hit, and 2,816 potential reused tokens (64.12% of 4,392 input tokens). One hit saves only 4.01%; at least two hits are required to clear 5%. At the optimistic zero-intercept scaling of the retained V21 c1 TTFT, 580.35 ms * 183/8192 = 12.96 ms, all 16 requests are eligible. At the observed V21 c1 TTFT of 580.35 ms, c8 p50 TTFT of 4,809.27 ms, and c8 p95 TTFT of 4,951.38 ms, zero requests are eligible. The latter measurements use 8,192-token prompts rather than the 183-token V2 prompt, so they are an explicit latency stress bound, not a direct prediction of V2.

Interpretation: the timing hypothesis is not robustly established or falsified locally. The only material case relies on an optimistic, non-scope-matched linear scaling assumption; all retained measured latency cases miss the 100 ms deadline. This preserves the paid cache-on smoke as a conditional measurement, but gives it a sharp falsifier: it must observe at least two same-session hits and positive reused-token telemetry, or the workload-level cache opportunity is rejected. Campaign latency may be traded for cost, but the fixed 100 ms workload identity must remain unchanged.

Next move: do not create a provider allocation in parallel. After sole ownership and zero inventory are handed off, run the immutable cache-on smoke; stop before cache-off if measured hits are below two or reused-token telemetry is absent.

## 2026-07-15 — pinned vLLM cache-eligibility timing audit

Question: is predecessor cache availability governed by request TTFT, or by an earlier vLLM scheduler/cache-commit event?

Action: audited the exact vLLM 0.15.0 source commit used by the V21 image (`f176443446f659dbab5315e056e605d8984fd976`) without provider access. The source audit is embedded in `artifacts/ARRIVAL_CACHE_AVAILABILITY_BOUND.json` with file hashes and line ranges. The V1 cache manager looks up complete cached blocks when a request is scheduled and commits finalized blocks in `allocate_slots`; request block hashes are initialized/extended independently of response completion. Therefore V21 TTFT is a stress bound, not the cache insertion time.

Decision-relevant evidence: retained V21 c8 TPOT p95 is 18.789 ms. Treating that measured scheduler-step cadence as a proxy, all 16 same-session reuse requests fit before their 100 ms successor arrivals, yielding 2,816 reusable tokens / 4,392 input tokens = 64.12%. The prior V21 c1/c8 TTFT cases still yield zero, but they are now explicitly labeled mismatched stress cases. The source-backed timing proxy is material and clears the two-hit minimum for the 5% input-work gate.

Interpretation: the prior timing concern does not kill prefix caching; it used the wrong service event. The paid cache-on smoke is preserved and now has a stronger local admission rationale, while the empirical gate remains unchanged: require positive aggregate hit/query deltas, positive per-request cached tokens, at least two same-session hits, deterministic semantics, and the declared quality boundary. No cache-off arm is admitted before that evidence.

Next move: remain provider-local-only until sole ownership and zero inventory are explicitly handed off, then execute the existing V2 cache-on smoke unchanged.
