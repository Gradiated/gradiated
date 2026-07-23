# Gemma 4 H200 DFlash endpoint

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
