# H100 actual Marlin W4 exact-shape direct falsifier

## Decision question

Do actual pinned-vLLM AWQ-Marlin W4A16 linears at all six exact Gemma 4 31B fused shapes leave the H100 planning envelope open, and do the cold-vs-warm rows plus two counter profiles support the one-CTA/latency-hiding mechanism?

Reuse the content-bound `h100_w4_marlin_exact_shape_mechanism/h100_w4_marlin_falsifier.py`. No checkpoint is needed. The prior paid attempt failed before timing only because tensor-parallel state was uninitialized; that is a recoverable runtime-context defect, not W4 science.

Director continuation: repair that exact defect offline in this same project and prepare an immutable adjacent packet for the already-live `h100_parallel_lm_head_single_stage` H100 development session. Do not create or mutate a second H100 allocation. Only that session's owner may stage or run the packet, sequentially, after its primary head result and only if setup materially exceeds scored time, the packet is ready within ten minutes, at least seven provider minutes and project-local spend remain, and the owner judges W4 to be the best adjacent evidence. Ordinary runtime-context/import/API/telemetry corrections remain in this project; do not create an audit/repair/successor project.

## Authoritative identity and arms

`assert_identity.py` mechanically binds `CAMPAIGN.md`, the W4 mechanism/status/program/CPU contract, and this brief before provider creation. Required identity is `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, observed vLLM `0.19.1.dev6+g6d4a8e6d2`, and `NVIDIA H100 80GB HBM3` capability 9.0.

Primary first retrieves the separately typed sliding-QKV M8 sentinel. It must prove actual AWQ production/packing/repacking/Marlin consumption, exact identity/source hashes, finite nontrivial dual oracles, warm and L2-evicted candidate plus matched BF16 timings, allocator evidence, and durable telemetry. Only a passing retrieved sentinel unlocks the exact 24 rows: six shapes at M8/M16/M32/M3679. Aggregate cold W4 and cold BF16 independently using the mechanism multiplicities and 358 output steps, against `0.5479752315195353 s/request`. Above closes H100 W4 economics; below is component plausibility only.

If all rows pass, profile merged-gate/up M8 and M3679 over the named NVTX interval with the mechanism's exact DRAM/L2/active-warps/tensor-pipe metrics. Missing counters fail the mechanism interpretation but do not erase valid timed rows. Profile work is part of the primary W4 decision, not an adjacent arm.

## Adjacent same-session arm

Before the owner ends, spend at most ten wall minutes preparing one immutable actual H100 BF16 `ParallelLMHead` arm from the already proven pinned-image H200/L40S consumer programs. It must be ready without checkpoint or compilation and use the same retained session/image, one sequential owner/watchdog, varied-sign input/weight, actual `ParallelLMHead`, output oracle, M8/M16/M32/M3679 timing, allocator and telemetry.

Run it only under `W4_SWEEP_PASS_AND_SETUP_DOMINATES_AND_HEAD_READY`: the 24 W4 rows pass, measured bootstrap plus image setup exceeds total scored W4 CUDA time, head bytes are staged and content-bound, and at least seven provider minutes remain. Report the head floor separately and combined only as a component lower bound. If preparation or trigger fails, record the disposition and clean immediately. No other retained arm.

## Budgets and stop rules

- Wall clock: 30 minutes.
- Provider exposure: 20 minutes.
- Compute: 0.34 H100 GPU-hours plus 2 local CPU-hours.
- Storage: one 100-GiB provider disk; 1.5 GiB retained plus 768 MiB temporary local.
- Spend: `$1.30` maximum at actual provider-metered rates.
- No new allocation in this continuation; the existing head-session owner is the sole mutation/cleanup authority and runs at most one sequential W4 arm under its watchdog.

Offline continuation budget from director reopen: 12 wall minutes, 1 local CPU-hour, 512 MiB retained plus 256 MiB temporary, `$0`; the existing H100 owner's remaining exposure/spend limits are not expanded.

## Director paid continuation authorization

The immutable single-rank TP packet `artifacts/TP_CONTEXT_ADJACENT_PACKET.json` (`sha256:2c7a9bd493cf54a5f9d9d17357980890f89110460a665875cd98906784aa0909`) passed exact-image import/parse and repairs the sole prior pre-timing defect. Its historical `no_new_provider_authority` field records why it was not allowed to race the already-cleaned head session; this director authorization supersedes only that session disposition and does not change packet bytes or science.

Launch this same project in one new mutable retained H100 development session through the proven lifecycle from `h100_parallel_lm_head_single_stage/h100_head_owner.py`. Mechanically bind the packet, exact campaign image, H100 placement, and actual `$2.15/H100-hour` experiment rate before create. Set `STATUS.json.active_session.mode` to `development` after create. The first exact-runtime action is the packet's sliding-QKV M8 sentinel and discovery audit; repair ordinary runtime-context, import, API, benchmark, profiler, and telemetry defects in place while preserving packet/source identities, scientific arms, H100/image, watchdog, deadline, and spend cap. On sentinel pass, run the 24 exact W4/BF16 rows and required profiles sequentially. Do not repeat the already-measured head arm and do not open an audit, repair, or successor project.

Paid continuation budgets: 30 wall minutes; 20 provider minutes; 0.34 H100 GPU-hours plus 1 local CPU-hour; one 100-GiB disk; 1.5 GiB retained plus 768 MiB temporary; `$1.30` maximum. One allocation and zero repair/restart applies to provider resources; ordinary in-session discovery corrections remain permitted. Stop for a typed scientific endpoint, unsafe/unintelligible state, required hardware/image change, exhausted budget, or an evidence-based faster route; always record setup versus scored CUDA time, actual spend, and authenticated cleanup.

Stop and clean on identity/source/kernel/packing/oracle/telemetry/deadline failure. The sentinel must be atomically retrieved before the sweep. Retain only for the named true trigger; otherwise clean normally. Terminal artifacts must separate setup, scored CUDA, profiling, provider exposure, derived cost, and authenticated zero-instance/zero-disk cleanup. No endpoint or quality claim is authorized.

## Actual selected-kernel continuation

The TP-initialized discovery terminal (`primary-stage.json`, sha256 `6bb196dd9b7059fee1ee6438fa250b419cf32e0c69fe3a48360ae39686a5b770`) proves the single-rank NCCL repair and exact H100/image/runtime identity, but falsifies the expected Marlin selection: pinned vLLM chooses `vllm.model_executor.kernels.linear.mixed_precision.machete.MacheteLinearKernel.apply_weights`. No timing row exists, so this is runtime-selection evidence rather than W4 performance evidence.

Continue this same actual-H100-W4 project by adapting the evaluator to content-bind and time the selected Machete consumer, preserving the exact six shapes, M8/M16/M32/M3679 rows, W4/BF16 pairing, representation and kernel oracles, cold/warm timing, aggregation, telemetry, and profiling intent. Do not force Marlin or create a successor. Mechanically bind the terminal's exact image/runtime/GPU and selected-kernel source hashes; the first GPU atom must prove actual Machete consumption before unlocking the 24 rows.

After the local evaluator is bound, launch one retained H100 development session through the proven lifecycle with `repair_window_seconds=600`. Recoverable import, context, API, evaluator, profiler, telemetry, or packaging failures are repaired in place under the same owner; scientific identity/oracle/kernel negatives stop normally. No checkpoint or repeated head arm. New continuation limits: 30 wall minutes, 20 provider minutes, 0.34 H100-hours, one 100-GiB disk, and `$1.30`. Record the prior terminal's separate 573.14-second/`$0.343839696` exposure and authenticated cleanup without charging it to the new limit.
