# L40S actual FP8 single-rank-context falsifier

## Decision question

When the exact pinned-vLLM single-rank tensor/model-parallel context that exists in a real endpoint is initialized, can the actual online-FP8 producer/consumer execute the exact Gemma 4 shapes on L40S and leave a viable c12 component margin?

The predecessor created and reached CUDA but emitted zero rows because `Fp8OnlineLinearMethod` required an initialized tensor-model-parallel group. This project changes that missing runtime execution context only. It is the final actual-consumer attempt for this line: one allocation, sentinel first, no repair. It is checkpoint-free and makes no endpoint or quality claim.

## Mechanically bound scope

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only non-reasoning, TP=1.
- Runtime image: `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`.
- Exact linears: sliding QKV `5376->16384`; global QKV `5376->20480`; sliding output `8192->5376`; global output `16384->5376`; merged gate/up `5376->43008`; down `21504->5376`.
- Exact model/workload/image/shapes/consumers/economic gates are inherited byte-for-byte from the passing director assertion in `../l40s_online_fp8_actual_consumer_floor/artifacts/DIRECTOR_IDENTITY_ASSERTION.json`.
- The predecessor terminal `../l40s_online_fp8_actual_consumer_floor/artifacts/RECONCILED_TERMINAL.json` is bound and must say zero rows, zero useful GPU, `tensor model parallel group is not initialized`, cleanup zero, and no FP8/W4 inference.
- The independent residual floor prescribes `0.164631539 seconds/request`; strict planning/conservative maximum component totals are `1.229949102` / `0.698661566 seconds/request`.
- Background queue evidence makes c12 primary: logical peak headroom `0.827762 GiB`; c14 has only `0.073388 GiB` and is allocator-sensitive. At the strict planning rate, a natural average decode M=12 requires about `16.735 seconds` of decode residence; no interactive SLO is imposed.

The director-generated `artifacts/DIRECTOR_IDENTITY_ASSERTION.json` must pass before delegation. No checkpoint, tokenizer, server, model weights, or provider-resident state is allowed.

## Direct experiment

Use the same proven shared `mla_microbench_control.py`, lowercase L40S placement, exact image, scripts and actual consumer construction as the predecessor, changing only to initialize and later destroy the exact installed vLLM single-process/single-rank distributed tensor/model-parallel context before constructing `Fp8OnlineLinearMethod`, `ParallelLMHead`, or AWQMarlin. Resolve the installed API/signatures/source hashes in the exact image before create. Do not monkeypatch `get_tp_group`, substitute a fake group, call direct `torch._scaled_mm`, or add a new provider wrapper. Require environment-isolated rendezvous, rank/world-size/local-rank 0/1/0, TP=PP=DP=1, actual NCCL/CUDA group identity, and typed teardown.

Before provider create, stage the complete primary and conditional programs and behaviorally audit exact execution/context order, all loops, oracle/timing/telemetry, aggregation, trigger, immutable transitive bytes, owner/watchdog, accounting and cleanup. Any failed pre-create terminal closes.

On the one L40S, run a sentinel first: actual online-FP8 producer/process/apply for sliding QKV `5376->16384` at M=12 with matched actual BF16 output-consuming oracle, finite positive CUDA/wall distributions, observed single-rank group identity, and allocator/telemetry. Persist it atomically. Sentinel failure or zero rows closes and cleans immediately.

Only a sentinel pass unlocks the full c12 primary: all six exact linears at decode M=12 and fresh-prompt M=3,679, actual FP8 KV writer, actual BF16 `ParallelLMHead`, matched BF16 linears, raw CUDA/wall stability, nontrivial oracle, allocator/HBM/power/utilization telemetry, and disjoint architecture weighting. Compare component total with the planning/conservative maxima `1.229949102/0.698661566`, not merely the raw service ceiling. c14 is optional diagnostic only if c12 passes, measured peak reserve leaves at least 0.25 GiB inside the 44.704-GiB envelope, and time remains; it cannot drive promotion by itself.

`FP8_CONTEXT_ADMISSION` requires sentinel and all c12 rows/oracles/stability/telemetry pass, actual group identity, c12 fit, and component total below the planning maximum. Passing admits only one later exact-revision endpoint/quality test.

## Same-session conditional W4

Because image/bootstrap dominates scored work, prepare before create one actual AWQMarlin program under the same real single-rank context. `W4_RESIDUAL_TRIGGER` requires valid c12 FP8 science, FP8 component total at/above the planning maximum or residual below 0.35 seconds/request, W4 start-ready within ten minutes, at least ten provider minutes remaining, and the unchanged retained owner/watchdog. Any invalid/zero-row FP8 or strong pass cleans immediately. W4 must be at least 20% faster than matched FP8 on all six M=12/M=16 shapes with passing oracle and component floor at most 0.60 seconds/request; it remains a semantics-changing proxy only.

## Budgets and terminal

- Primary slice: 35 wall minutes, 25 provider minutes, 0.42 L40S GPU-hours, 2 local CPU-hours, `$0.40`.
- Conditional increment: 10 wall minutes, 8 provider minutes, 0.14 L40S GPU-hours, `$0.14`.
- Combined hard caps: 45 wall minutes, 33 provider minutes, 0.56 L40S GPU-hours, 3 local CPU-hours, one 100-GiB disk, 768 MiB retained plus 3 GiB temporary, `$0.54`, one allocation, no repair.

Write identity/source/final-audit terminals, sentinel and primary/conditional raw rows, group/teardown evidence, telemetry/manifests, typed triggers, cost/useful-time accounting, concise log/status, summary, and authenticated zero-resource cleanup.
