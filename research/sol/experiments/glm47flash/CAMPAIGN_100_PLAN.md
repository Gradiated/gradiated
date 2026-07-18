# $100 GLM inference co-design evidence campaign

Status: authorized for execution

Owner: Gradiated inference research coordinator

Primary workspace: `/root/workspace/research/sol/experiments/glm47flash`

Durable repository mirror: `/root/workspace/research/sol`

## 1. Objective

Spend at most $100 of additional RunPod compute to maximize the correctness of the next business decision:

> Is there credible evidence that model-specific software, model representation, and eventually hardware co-design can deliver a material, quality-preserving reduction in SLO-compliant inference cost beyond a tuned general serving stack?

This is an information-gain campaign, not a product build and not a benchmark-marketing exercise. It must seek falsification as aggressively as positive results.

The campaign is successful when it produces enough reproducible evidence to make one of these decisions:

1. `PROMOTE`: spend the next approximately $1,000 on a broader commodity-GPU co-design campaign.
2. `CONTINUE_NARROWLY`: one mechanism remains promising but needs a specifically identified measurement.
3. `STOP_OR_PIVOT`: the measured opportunity is generic, too small, quality-invalid, operationally uneconomic, or the simulator is not predictive.

## 2. Scope and non-goals

In scope:

- GLM-4.7-Flash as the primary model.
- Native BF16 SGLang as the stock control.
- The public GLM-4.7-Flash AWQ checkpoint as a representation and cheaper-device candidate.
- A fair tuned-incumbent control using supported stock serving features.
- One profile-selected software or kernel intervention with an exact on/off ablation.
- A small second-model control if and only if the primary evidence and budget gates pass.
- Prospective Fable/Sol predictions committed before holdout measurements.
- Trace-driven agent workloads, deterministic correctness, a compact executable quality screen, SLO goodput, telemetry, and fully reconciled GPU cost.

Out of scope:

- Building the gateway, billing, control plane, Kubernetes fleet, or customer product.
- Multi-node or custom-silicon validation.
- Claiming Fireworks or Baseten COGS from their public API prices.
- Full GLM-5.2 serving.
- Full-model training or an open-ended healing campaign.
- More than one custom performance intervention.
- Repeating an unchanged failed placement or runtime hypothesis.
- Publishing or pushing results without explicit user direction.

## 3. Existing evidence that must not be repeated

The coordinator must audit current artifacts before acting. At plan creation, the evidence includes:

- Pinned CUDA 13 SGLang commit `f63458b5beaceabbd9d749b9fc956370e1b649e6` natively loads BF16 `zai-org/GLM-4.7-Flash` revision `75fce70` on H100.
- Two deterministic greedy BF16 smoke completions matched.
- Native BF16 reported 56.27 GB of weights and a 284,098-token BF16 KV pool at the successful 16K configuration.
- No valid BF16 throughput result exists because the successful benchmark attempt used an obsolete client flag and later placements missed startup.
- The public AWQ checkpoint revision `ab31d120fbe79988fe2a0259993cf3c222aa8881` selects compressed-tensors WNA16 Marlin with shared-expert fusion disabled after narrow initialization guards.
- The first AWQ fused Q/KV-A metadata defect was reproduced offline and patched with deterministic tests.
- A Secure L40S GPU run reached a later compressed-tensors dequantization boundary. The active pre-plan worker is investigating it. Do not overwrite or duplicate that work.
- Historical pre-plan spend is not charged to this new $100 authorization, but must remain visible in the final lifetime ledger.
- RunPod currently has no active campaign pod. Re-verify this before any mutation.

The latest verified artifacts and `REPORT.md` override this summary if they contain newer evidence.

## 4. Budget contract

The user authorized a hard cap of exactly `$100.00` in additional RunPod compute after this plan.

Before any new pod request, create a signed-off campaign baseline record containing:

- Timestamp.
- All RunPod inventory entries and their status.
- Exact authoritative lifetime spend from every unique allocation.
- The campaign-start lifetime spend.
- `campaign_additional_spend_usd = 0.0`.
- Hash of this plan.

All subsequent budget checks use:

`campaign_additional_spend_usd = current_authoritative_lifetime_spend - campaign_start_lifetime_spend`

If reconciliation is uncertain, use the larger defensible value. Never infer permission above $100.

### Phase envelopes

| Phase | Maximum additional spend | Cumulative cap |
|---|---:|---:|
| A. Offline contracts and workload | $0 | $0 |
| B. Valid stock baseline | $20 | $20 |
| C. AWQ and cheaper-device screen | $15 | $35 |
| D. Compact paired quality screen | $10 | $45 |
| E. Profile-selected intervention | $30 | $75 |
| F. Holdout replication and model-specificity control | $15 | $90 |
| Reserve for failures and final confirmation | $10 | $100 |

Unspent phase money may move forward, but later phases may not begin before their gates pass. The $10 reserve is not ordinary experiment budget.

### Mandatory cost controls

- Only the coordinator may create or terminate RunPod resources.
- Subagents may design, code, test, and review but may not mutate RunPod.
- Every pod has an independent watchdog, an absolute deadline, and a maximum-deadline dollar cost recorded before creation.
- Query the account before and after every mutation.
- Harvest artifacts before deletion when possible; deletion is mandatory even if harvesting fails.
- Verify deletion by API and record the result.
- GPU resources stay off while agents analyze, compile locally, or write reports.
- Use an existing persistent cache or volume where safe; do not repeatedly download weights on expensive GPUs when a cheaper reproducible alternative exists.
- Container startup may use a bounded 15-minute deadline when the provider shows real progress. The earlier five-minute deadline caused repeated low-information failures. Maximum cost still applies.
- At most two placement attempts are allowed for a hypothesis, and the second must change a recorded causal placement variable.
- Never touch unrelated pods.
- Stop before the cap: no request may be created if its maximum-deadline cost could make additional spend exceed $100.

## 5. Claims and evidence hierarchy

The final report must keep these claims separate:

1. `Compatibility`: a model/runtime combination loads and returns correct-form outputs.
2. `Component performance`: a named operation becomes faster or transfers fewer measured bytes.
3. `Serving performance`: the exact intervention improves matched request-level goodput under a frozen SLO.
4. `Economic performance`: matched goodput and actual hourly price reduce GPU dollars per billable token.
5. `Quality retention`: a frozen paired screen does not reveal an unacceptable regression.
6. `Model specificity`: the intervention has a materially different mechanism or effect on a control model.
7. `Predictive validity`: Fable/Sol predicted direction and candidate ordering before measurement.
8. `Business evidence`: the combined evidence supports a larger campaign.

No lower-level result automatically grants a higher-level claim. Public API price is a commercial comparison, not provider cost. Peak throughput is not SLO goodput. A loader patch is not a performance moat.

## 6. Frozen workload contract

Phase A creates a versioned workload bundle before the measured campaign.

### Workload sources

- Use a deterministic subset of public coding-agent traces, preferring UW TraceLab-derived distributions and raw shareable coding-agent trajectories where message content is legally reusable.
- Retokenize raw messages with the exact GLM tokenizer.
- Preserve session boundaries, append lengths, prefix identity, tool-schema size, tool-result size, output length, and pause time when available.
- If only token counts are available, mark the trace as length-only and do not claim exact prefix identity.
- Include a fixed synthetic 8,192-input/1,024-output workload solely for comparison with the existing published anchor.

### Required workload classes

1. `fixed_8k_1k`: published-style comparability.
2. `agent_append`: growing conversation with short appended tool results.
3. `agent_prefix`: repeated system/tool prefixes with tenant-safe exact prefix reuse.

Use a small frozen screen for development and a disjoint holdout for final measurement. Record seeds and content hashes.

### Primary service contract

Optimize for the economy tier while retaining a finite service level:

- p95 TTFT at or below 10 seconds.
- p95 inter-token latency at or below 100 milliseconds during streaming decode.
- request success at or above 99% for the measured replay.
- No silent request truncation.

Also report the cost/latency frontier without promoting configurations that violate the primary service contract. These thresholds are frozen before results and may not be loosened after observing a candidate.

## 7. Measurement contract

Every promoted A/B result must match:

- Model and checkpoint revision except when representation is the declared intervention.
- Runtime source and image digest except when runtime is the declared intervention.
- Prompt set, output-token cap, seeds, sampling policy, request arrival schedule, and tokenizer.
- Hardware identity and cloud class for same-hardware ablations.
- Warmup policy and cache state.
- At least three repetitions of the decisive point where affordable.

Capture:

- Input, output, and total tokens per second.
- Completed-request goodput.
- TTFT, inter-token latency, end-to-end latency, and errors at p50/p95/p99.
- GPU utilization, VRAM, power, temperature, and clock telemetry at a documented cadence.
- HBM or memory-throughput evidence when supported.
- Scheduler iteration, batch composition, prefill/decode split, KV allocation and prefix-cache counters.
- Short low-overhead kernel timeline or profiler capture for causal attribution.
- Model load, cache allocation, and startup timings.
- Provider price, allocation seconds, and conservative dollar cost.

The cost metrics are:

- GPU dollars per million input tokens.
- GPU dollars per million output tokens.
- GPU dollars per million blended billable tokens for each workload class.
- Output-equivalent dollars at the declared input/output ratio.
- SLO-compliant cost using only completed requests that pass the frozen service contract.

Host, network, engineering, and fleet-idle costs are not silently treated as zero. Report GPU-only economics first and include an explicit sensitivity reserve rather than claiming fully loaded COGS.

## 8. Quality contract

This $100 campaign can run a screening gate, not a definitive quality certification.

Build a compact, deterministic, executable paired suite containing approximately:

- Tool-call formatting and argument correctness.
- Coding tasks with executable tests.
- Long-context retrieval.
- Multi-turn agent continuation.
- Perplexity or teacher-forced token-loss sentinel.
- Deterministic serving correctness and malformed-output checks.

Prefer exact or executable scoring over an external LLM judge. Use disjoint development and holdout subsets.

Minimum screen policy:

- No catastrophic category failure.
- Overall paired point regression no worse than two percentage points.
- No individual critical category regression worse than five percentage points.
- Report paired uncertainty; passing the point screen is provisional if the confidence interval crosses the non-inferiority margin.

MTP is evaluated separately. For deterministic greedy fixtures, require exact normalized output identity with MTP disabled versus enabled before interpreting its performance.

## 9. Execution phases and gates

### Phase A: reconcile and pre-register

GPU budget: $0.

Tasks:

1. Let the already-active GLM worker finish its current offline AWQ causal audit, or safely harvest its durable output. Avoid concurrent edits to the same files.
2. Reconcile lifetime spend and create the new campaign baseline.
3. Audit RunPod inventory and prove zero active campaign pods.
4. Freeze the workload, quality screen, metric schema, economic arithmetic, and artifact validator.
5. Run all offline tests.
6. Create prospective prediction records for stock BF16, stock-tuned BF16, AWQ on a 48GB device, and the expected ranking. Predictions are immutable after the associated GPU result begins.

Gate A passes only when all contracts are content-addressed, validators fail closed, and the budget/watchdog tests pass.

### Phase B: valid stock and tuned-incumbent baseline

Maximum cumulative spend: $20.

Use the cheapest credible sequence that obtains a valid matched baseline. H100, H100 PCIe, or A100 80GB are permitted because BF16 fits. Prefer an exact cached image placement or persistent model cache. Do not keep repeating cold H100 placements.

Required configurations:

1. Native BF16 stock, MTP disabled.
2. Best supported stock-tuned configuration chosen without custom source changes. This may include the official EAGLE shape, prefix caching, and documented batching settings, but each feature must be separately attributable.

Run smoke, then the small workload matrix, then the decisive economy-SLO point. MTP requires deterministic identity screening.

Kill conditions:

- No valid stock throughput result by $20 additional spend.
- Native correctness failure that cannot be isolated offline.
- Artifact or telemetry validator failure after one corrected retry.

Gate B requires a reproducible stock and tuned-incumbent SLO-goodput point with reconciled cost.

### Phase C: AWQ and cheaper-device screen

Maximum cumulative spend: $35.

Complete the narrow SGLang compressed-tensors fixes only when each change has a failing regression test and source-level causal evidence. Do not paper over shape or dequantization errors.

Run a cheap 48GB smoke first, then the same small workload matrix. L40S, RTX 6000 Ada, A40, or A6000 are allowed according to current availability and kernel capability. Record the exact device; never relabel a proxy.

Compare:

- Same-runtime BF16 versus AWQ where hardware permits.
- Best BF16 economic point versus AWQ on the cheaper device.
- Stock and tuned settings as compatible.

Kill conditions:

- Full checkpoint load remains semantically unresolved after one new causal runtime defect.
- Deterministic correctness fails.
- AWQ misses the economy SLO and has no plausible cost headroom.

Gate C requires complete AWQ load, deterministic output, valid telemetry, and a measured cost point. A successful public AWQ result is useful hosting evidence but is not yet custom-stack evidence.

### Phase D: paired quality screen

Maximum cumulative spend: $45.

Run the frozen compact screen for BF16 versus the economically best representation. Stop the candidate on catastrophic or material quality failure. Do not run a larger suite when the point screen fails.

Gate D is a provisional quality pass under the exact declared policy.

### Phase E: one profile-selected intervention

Maximum cumulative spend: $75.

Profile the best stock/tuned control and select the single largest modifiable cost center. Candidate ranking must include measured time share, estimated removable fraction, implementation risk, quality risk, and test cost.

The intervention must:

- Exploit a measured GLM shape, representation, DSA/MLA path, expert path, KV behavior, or agent request structure.
- Have an exact on/off switch or source patch for a causal A/B.
- Preserve a fair tuned control.
- Be preceded by a prospective Fable/Sol prediction.
- Have correctness tests before implementation.

Permitted examples include a fused GLM-specific path, corrected/tuned compressed execution, append-length-aware scheduling, a model-specific MTP policy, or removal of a measured synchronization/materialization. Do not force an example if profiling identifies something else.

If no modifiable component plausibly offers at least 15% end-to-end gain, stop and report that negative result instead of inventing an intervention.

Gate E requires a reproducible causal A/B with profiler evidence explaining the observed delta.

### Phase F: holdout replication and specificity

Maximum cumulative spend: $90, leaving $10 reserve.

Tasks, in order:

1. Run three decisive holdout repetitions of the best control and candidate.
2. Run the holdout quality subset.
3. Score prediction direction, magnitude, bottleneck transition, and candidate ordering.
4. If at least $7 remains and primary gates pass, apply or analytically map the intervention to one smaller control model and perform the cheapest valid measurement needed to distinguish generic from GLM-specific behavior.

The reserve may be used only to repair a final artifact defect or repeat the decisive result after a documented infrastructure failure.

## 10. Decision rubric

### Strong promotion

All of:

- Combined candidate reduces SLO-compliant GPU $/token by at least 1.5x versus the best tuned stock control.
- A measurable portion of the gain is beyond moving a public AWQ checkpoint to cheaper hardware.
- Compact quality screen passes provisionally.
- Decisive result reproduces across three runs.
- Telemetry provides a causal explanation.
- Fable/Sol predicts the candidate ordering and correct direction; magnitude error is preferably at most 25%.
- The control-model result or mechanism analysis supports some model specificity.

### Very strong promotion

- At least 2x combined cost reduction under the same gates.

### Continue narrowly

Examples:

- AWQ produces strong economics, but no custom performance gain is yet measured.
- A custom component wins materially, but quality uncertainty remains.
- Prediction direction is correct but magnitude calibration is poor.
- Infrastructure prevents one decisive holdout while all prior gates pass.

The final report must name exactly one next experiment and its expected information value.

### Stop or pivot

Any of:

- No valid stock baseline within the Phase B cap.
- No repeatable gain beyond tuned stock SGLang.
- Combined gain is below 1.2x with no measured discontinuity.
- Quality screen fails.
- Apparent improvement disappears under the frozen SLO or matched workload.
- Simulator predicts the wrong ordering or direction without an identified correctable measurement defect.
- Gain is entirely generic and readily available in the incumbent control.

### Interpretation labels

- `AWQ_ONLY`: hosting/integration opportunity; weak evidence for the co-design company.
- `GENERIC_SOFTWARE`: valuable inference engineering; weak evidence for per-model differentiation.
- `MODEL_SPECIFIC_SOFTWARE`: supports the near-term business thesis.
- `PREDICTIVE_CODESIGN`: supports the experimentation-engine thesis.
- `HARDWARE_HYPOTHESIS_ONLY`: simulation lead, not validated business evidence.

## 11. Coordinator and subagent protocol

Use Sol with maximum reasoning for the coordinator. Spawn bounded subagents when supported:

1. Workload and quality curator, preferably Luna: trace bundle, scoring, and provenance.
2. Telemetry and evidence reviewer, preferably Luna: fail-closed artifact validation and independent economic arithmetic.
3. Runtime/kernel researcher, preferably Sol: causal diagnosis and the one selected intervention.

Rules:

- The coordinator remains the sole RunPod mutator and budget owner.
- Give each subagent a concrete artifact contract and non-overlapping file ownership.
- Review subagent outputs before promotion.
- Do not let multiple agents edit the same experiment harness concurrently.
- Use TDD for code changes: failing test, minimum implementation, refactor.
- Follow the repository `AGENTS.md` and its direct-to-main Git workflow.
- Do not commit or push unless separately requested.
- Continue autonomously while safe work remains. Do not ask the sleeping/user for experiment-level choices already covered by this plan.
- If genuinely blocked, continue with offline analysis, validators, workload preparation, prospective predictions, or report synthesis. Do not spend through a blocker.

## 12. Durable artifacts

Create and maintain:

- `campaign_100/CAMPAIGN_STATUS.json`
- `campaign_100/CAMPAIGN_LEDGER.jsonl`
- `campaign_100/CAMPAIGN_BASELINE.json`
- `campaign_100/workloads/`
- `campaign_100/quality/`
- `campaign_100/predictions/`
- `campaign_100/specs/`
- `campaign_100/artifacts/`
- `campaign_100/analysis/`
- `campaign_100/FINAL_DECISION.md`
- `campaign_100/RESUME.md`

Every GPU artifact must bind:

- Experiment spec hash.
- Workload hash.
- Model/checkpoint revision.
- Runtime/image/source revision.
- Hardware and provider metadata.
- Start/end timestamps and allocation seconds.
- Raw telemetry hashes.
- Validator result.
- Teardown evidence.
- Conservative cost.

Mirror material conclusions into the living `REPORT.md` and the durable `gradiated/research/sol` research tree without committing.

`CAMPAIGN_STATUS.json` must always state the current phase, last completed gate, current additional spend, active pod inventory, active hypothesis, next action, and whether claims are permitted.

## 13. Final deliverables

The coordinator does not finish merely because one experiment succeeds. It finishes after reaching a rubric decision or exhausting the cap, with:

1. Exact lifetime and additional spend reconciliation.
2. Zero active campaign pods, verified.
3. Reproducible stock, tuned, AWQ, and custom results or explicit fail-closed reasons each is absent.
4. Agent-trace workload description and content identities.
5. Cost/latency Pareto table.
6. Paired quality screen with uncertainty and limitations.
7. Profiler-based causal attribution.
8. Prospective prediction-versus-measurement score.
9. Generic versus model-specific attribution.
10. `PROMOTE`, `CONTINUE_NARROWLY`, or `STOP_OR_PIVOT` recommendation.
11. The single highest-information next campaign if promoted.
12. A concise founder-facing summary that clearly separates measured facts, modeled implications, and speculation.

No gateway is to be built during this campaign.
