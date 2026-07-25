# Gemma 4 H200 DFlash endpoint

## 2026-07-25 request-level semantic localization

The immutable one-cycle oracle now passes all 112 captured cycles and the tied
head adapter is bit exact, yet the completed depth-4 c32 pair reports
`target_emitted_token_equivalence=false` and unequal cache accounting. That
combination rejects the measured online integration, but it localizes the open
question to request-level relay, acceptance/bonus commit, sequence/KV commit,
or stream emission across cycles rather than DFlash logits in isolation.

Use deep reasoning on the pinned target/draft source and the already-retrieved
complete c32 rows, raw token IDs, accepted-prefix telemetry, and cycle-oracle
artifacts. Find the first request and cycle at which the verifier's accepted
target sequence, committed request state, and emitted stream cease to agree.
Build a deterministic request-indexed replay fixture that crosses at least one
reject, one accepted prefix, one bonus-token decision, and a subsequent cycle.
Implement the smallest source repair only when the replay demonstrates the
causal invariant.

Write `DFLASH_REQUEST_LEVEL_REPAIR_RESULT.json` as either
`source_complete_request_level_repair` with a passing replay and exact source
patch, or `online_semantics_falsified` with the first irreparable invariant and
scope. This phase is `$0`, must not claim a GPU, must not replay either endpoint
arm, and must not weaken target-token or cache-accounting equivalence. A source
candidate may nominate one later director-bound diagnostic; it does not
authorize one.

## 2026-07-25 depth-4 endpoint continuation

The immutable 112-cycle oracle passes and the offline c32 CUDA-event controller
selects depth 4. The prior `/generate` consumer is invalid evidence because it
decoded no complete request; repair that observer against the already-retrieved
SSE bytes before claiming a GPU. On parser pass, run exactly one matched
same-runtime AR versus DFlash depth-4 c32 pair on the retained H200. Do not
replay the oracle, four-request diagnostic, or four-depth producer.

The direct decision requires 32/32 complete requests, 358 output tokens,
request ownership, target/emitted token equivalence, accepted-prefix telemetry,
cache and usage equality, service time, p95, failures, and clean shutdown.
Compare both the paired AR control and the qualified
`0.625149101968745 s/request` denominator; the campaign target remains
`0.500119281574996 s/request`. The exact binding and remaining reservation are
in `DIRECTOR_DEPTH4_ENDPOINT_BINDING.json`.

## 2026-07-25 deep continuation: lossless repair and adaptive verification

The adapted diagnostic reached real DFlash drafting and target verification
but reproduced the deterministic AR control on only two of four requests.
That result closes the tested integration, not lossless parallel drafting:
accepted target tokens and committed verifier state should be equivalent to
ordinary target decoding.

Use the persisted producer and source to find the first semantic divergence.
Construct a one-cycle oracle containing the AR target IDs, draft proposals,
target verifier logits and IDs, accepted prefix, bonus token, KV write
locations, committed sequence length, and the next ordinary target token.
Localize whether the defect is in hidden-state capture, row/depth ownership,
verification logits, acceptance, bonus-token handling, or KV/state commit.
Implement the smallest source-complete repair when the evidence identifies
one; do not rerun the four-request producer or claim a GPU in this phase.

In the same project, derive a D-Cut/DSpark-style c32 controller for verification
depths 4, 8, 12, and 16 using measured H200 verification cost and per-position
draft survival. Keep the block-16 draft checkpoint fixed initially. The
controller should maximize accepted tokens per measured draft-plus-verification
GPU time across the batch rather than maximizing accepted length. Persist a
small simulator or exact cost model and the acceptance telemetry it requires.

The next portfolio-changing result is either:

- a source-complete lossless repair plus an exact one-cycle fixture, ready for
  one later director-bound H200 diagnostic and adaptive-depth c32 pair; or
- a precise invariant-level blocker showing that the current Gemma checkpoint
  or pinned runtime cannot implement the target-equivalent commit path.

This stage has `$0` new provider authority and must not disturb either active
GPU owner. Relevant recent evidence is summarized in
`../../evidence/RECENT_INFERENCE_RESEARCH_LANDSCAPE_2026-07-25.md`.

## Question

Can the public Gemma 4 31B-specific DFlash draft reduce the exact background
c32 endpoint below the lab's qualified `0.6518282820 s/request` frontier while
preserving target-model token semantics?

## Why this matters

The public `z-lab/gemma-4-31B-it-DFlash` model card reports a 2B BF16 draft
paired specifically with `google/gemma-4-31B-it`, with c32 throughput gains of
1.9x on MT-Bench and 2.6–3.8x on its code/reasoning tasks on B300. Those are
vendor/author measurements on a different accelerator and runtime, not
transferable campaign results. They make one direct H200 falsifier much more
valuable than another repair of the closed static multi-token graph lineage.

Read
`../../evidence/HIGH_IMPACT_INFERENCE_LITERATURE_REVIEW_2026-07-24.md`
(SHA-256 `a182503e20eecfec49d200267d377632b65be9d1b059ea45523ae5ba682a02e6`)
and use `$experiment-run`. Use `$kernel-research` only if a measured target
verification or draft kernel becomes the limiter; do not start with a custom
kernel.

## Bound scope

- Target: `google/gemma-4-31B-it` at revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Draft: `z-lab/gemma-4-31B-it-DFlash`. Resolve and record the exact immutable
  Hugging Face revision before paid execution; do not use an unrecorded moving
  branch.
- Runtime: begin with one upstream integration explicitly supported by the
  model card: SGLang PR 23000 or vLLM PR 41703. Resolve the exact source commit,
  image, driver, CUDA, and dependency identities. Choose the path with the
  shortest executable H200 route; do not prepare both before the first signal.
- Hardware: one independent Nebius H200 SXM bench. Do not race or mutate
  `h200-sync-linear-e00vhh6h29fj68x91g`, which is reserved for the current
  native-n-gram and operation-overlap itinerary.
- Workload: the campaign's exact 32 concurrent requests, 4,214 prompt tokens,
  358 forced output tokens, 17,120 cached plus 117,728 fresh prompt-token
  accounting, text-only non-reasoning mode, temperature zero.
- Candidate geometry: the upstream-recommended 15/16 speculative-token
  configuration for the selected runtime. Do not sweep before the first full
  result.
- Comparator 1: same-runtime autoregressive target with identical model,
  precision, request and cache geometry.
- Comparator 2: the absolute campaign frontier in
  `../gemma4_h200_fp8_tied_head_endpoint/iterations/c32-topology-settled-resume-20260723t2110z/resident-consumer-repair-artifacts/FINAL_TERMINAL.json`
  (SHA-256 `167c2de86c6316d836b9dc9cbf486dfcf09dc59274f39b45ff5a9388d68690a5`).

## Immediate experiment

1. On the retained new H200 session, install the one chosen upstream runtime,
   stage the exact target and draft once, and keep downloads/build caches
   resident.
2. Run a four-request exact-workload diagnostic. Record accepted tokens per
   target verification, draft time, target verification time, fallback/reject
   frequency, HBM peak, target forwards per emitted token, and raw token IDs.
   Repair ordinary runtime/API integration defects in place.
3. If real drafting and target verification are present, run one matched
   same-runtime autoregressive/DFlash c32 pair. Preserve every row and exact
   cache/accounting delta.
4. Require deterministic greedy token equality against the same-runtime
   autoregressive control, finite outputs, 32/32 completion, exact request
   ownership, positions and KV transitions. A batch-state mismatch is an
   integration result to localize once, not a performance result.
5. Compare the candidate's absolute service time with `0.6518282820`.
   `<=0.5214626256 s/request` is a measured 20% reduction and
   `<=0.4562797974` is a measured 30% reduction. Retain any valid positive
   result; these levels are decision descriptions, not a minimum gate.
6. If the upstream candidate is positive but the upstream autoregressive
   runtime is slower than the lab stack, identify the narrow DFlash integration
   boundary needed for pinned SGLang. Do not port it overnight unless the
   measured absolute bound still clears the current frontier.

Do not run broad GPQA-Diamond or TauBench tonight. Exact greedy equivalence and
batch-state evidence are the first quality gate. A positive performance result
nominates the later production suite.

## Contract

- Causal hypothesis: parallel block drafting lowers target forward passes per
  emitted token enough to offset draft and batched-verification cost at c32.
- Competing explanation: target verification or ragged-batch alignment
  dominates at this workload, erasing the published low/concurrency transfer.
- SLO: 32/32 complete requests, 358 output tokens each, exact accounting and
  deterministic token equivalence; latency may be slower per streamed block.
- Maximum spend: `$28`.
- Compute: one H200, at most ten provider hours including setup and idle repair.
- Deadline: `2026-07-24T10:00:00Z`, with cleanup protection beyond the science
  deadline.
- Storage: at most 250 GiB attached disk and 20 GiB new repository artifacts;
  retain bulk checkpoints and build caches on the protected bench.
- Artifacts: source/model manifests, phase events, raw diagnostic and c32 rows,
  telemetry, control/candidate summaries, acceptance/verification attribution,
  spend, compact hashed terminal, and resident-state handoff.
- Provider lifecycle: director creates/registers and ultimately drains the
  independent bench. The researcher claims/releases it and never creates or
  destroys provider resources.

## 2026-07-24 continuation — bind the missing Gemma 4 capture hook

The upstream route is closed exactly as shipped, but its terminal is
pre-request: the same-runtime AR diagnostic passed and DFlash accepted no
request solely because `Gemma4ForConditionalGeneration` lacks
`set_dflash_layers_to_capture`. Consume
`GEMMA4_CAPTURE_HOOK_CONTINUATION.json` and use `deep` reasoning to trace the
pinned DFlash worker, supported target implementations, Gemma 4 hybrid-layer
ordering, captured hidden states, and target-verification consumer. Implement
one source-bound hook only when that contract preserves target semantics.

Reuse the retained H200, exact target/draft downloads, source checkout, image
layers, flags, and runner. Do not replay the consumed AR diagnostic. After the
patched candidate reaches health, run only the four-request DFlash
acceptance/verification diagnostic, then the original matched c32 pair if real
drafting, target verification, acceptance telemetry, and deterministic output
evidence pass. A semantic incompatibility closes this integration; ordinary
source, build, API, or consumer defects remain same-claim repairs.

## 2026-07-25 continuation — tied embedding head adapter

The previous candidate initialized DFlash, captured the correct six target
features, admitted requests, and reached target prefill. It stopped at one
narrow runtime contract: DFlash expects a vocab-parallel head with `weight` and
`shard_indices`, while Gemma 4 correctly reuses `embed_tokens` as its tied
output head. This does not physically reject DFlash.

Consume `DIRECTOR_TIED_HEAD_ADAPTER_REOPENING.json`. First implement and test a
TP=1 adapter that exposes the unchanged tied weight and full-vocabulary shard
range to the pinned DFlash greedy consumer. It must preserve complete logits,
lowest-index ties, and token IDs. After that gate, request one H200 and run a
fresh four-request candidate diagnostic; run one matched c32 AR/DFlash pair
only if drafting, acceptance, and target-exact outputs are real. Do not replay
the prior unadapted diagnostic or repeat checkpoint/runtime discovery.

## 2026-07-25 continuation — exact request-state capture

The retained endpoint evidence now falsifies the request-indexed relay-only
repair. Three requests diverge at target-prefill token zero, before acceptance
or relay, and request 25 first diverges at verify cycle one despite an
AR-equal pending seed. The retained producer did not record the committed KV,
length, or target-verifier state needed to choose an exact repair.

Consume `DIRECTOR_EXACT_REQUEST_STATE_CAPTURE.json`. Bind and fixture-test the
observer without CUDA, then—only after the certified-lazy and FP8 component
owners release—run one matched exact-c32 AR/DFlash diagnostic capture on the
retained H200. Localize the earliest difference across target-prefill output,
first-verify result, sequence/committed length, KV locations/content digest,
accepted prefix, bonus, and stream emission. Do not implement a repair,
retune DFlash, or make a performance claim in this phase.
## 2026-07-25 request-ownership observer continuation

The exact request-state owner completed the AR c32 producer with 32/32 valid
responses and persisted 28 state events, then stopped at a typed retrieval
boundary before the DFlash arm began. The observer errors are decision-bearing:
request segments sometimes contained multiple injected markers, and physical
schedule slots were rebound across requests. The completed AR producer is
settled and must not be replayed.

Use `$researcher` for a deep, zero-GPU continuation. Consume only
`artifacts/request-state-capture-owner-20260725T232227Z/retrieved-final`,
the bound observer, and the pinned request/cache-pool source. Reconstruct the
authoritative lifetime from request-pool identity through padded schedule rows,
cache slots, prefix reuse, and slot rebinding. Explain which identity is stable
at target prefill, ordinary AR decode, and DFlash verify/accept/bonus.

Return `DFLASH_REQUEST_OWNERSHIP_OBSERVER_REPAIR_TERMINAL.json` with either:

- a content-addressed observer repair and CPU fixtures that can capture only
  the unconsumed DFlash arm while preserving the settled AR producer; or
- a typed limit proving that a scope-matched candidate-only comparison cannot
  reuse the retained producer and stating the smallest valid future pair.

Do not claim a GPU, compile, launch an endpoint, rerun AR, implement the
semantic DFlash repair, weaken token equivalence, or mutate provider lifecycle.
Budget at most 120 minutes and 2 GiB of new durable artifacts.
