# Exact v0.5.13 FP8+QKV residual profile and intervention

## Question

On the proven Gemma 4 31B v0.5.13 dynamic-FP8 plus QKV endpoint, what non-overlapping kernel/runtime boundary now dominates exact c32 service time, and can one source-justified change reduce endpoint time toward `<=0.6381105231 s/request`?

## Why this matters

The current stack is `0.6928421805 s/request`, while sustainable `$0.14/M` H200 economics at 90% utilization require another 7.90% reduction. Old BF16 attribution is not transferable: the current run averages 97.3% GPU utilization, 564 W, and about 123 GB HBM after dynamic FP8 and QKV fusion. Profiling alone is not a result; the same project must immediately test one change at the hottest measured boundary.

## Bound evidence and scope

- Exact model, runtime, representation, source bytes, and workload are fixed by `BINDINGS.json`.
- Use the authoritative reconciled QKV terminal only as prior evidence. Establish a fresh exact v0.5.13 FP8+QKV c32 control on H200 before judging the intervention.
- Attribute non-overlapping wall time across prefill/decode, FP8 linear families, attention/KV, normalization/activation, cache conversion/write, launch, synchronization, and scheduler gaps.
- Start with Nsight Systems or equivalent. Collect only the minimum Nsight Compute counters on the top one or two kernels needed to distinguish tensor-core compute, HBM/L2 traffic, occupancy/register/shared-memory pressure, underfilled grids, and synchronization.
- After attribution, implement exactly one source-justified intervention at the hottest boundary. Admissible classes include fused FP8 GEMM epilogues, activation/normalization fusion, attention/KV dataflow, launch elimination, or persistent execution. Do not optimize a boundary below 5% attributed relevance and do not run a flag sweep.

## Immediate experiment

After the harness durably reserves this project and the director registers one H200 bench, use one bounded durable owner to stage the exact checkpoint and pinned image. Run one profiled exact c32 FP8+QKV control, persist a non-overlapping attribution table and the minimum decisive counters, select and implement one intervention, then run one contemporaneous unprofiled control/candidate pair. Require 32/32 valid rows, exact token/cache accounting, FP8 consumer proof, QKV epilogue proof, and candidate-path invocation proof. Repair ordinary pre-invocation defects in place; do not replay a consumed arm.

## Decision rule

- Promote the candidate if it is semantically valid and `<=0.6381105231 s/request` against its contemporaneous control.
- Retain a stable simple gain of at least 5% even if it misses the full ceiling, then move to the next independently attributed bottleneck.
- Close the chosen boundary if its valid endpoint gain is below 5%, and return the attribution so the director can select a materially different route.

## Budgets and resources

- Researcher profile: `deep` for causal attribution through the first exact intervention result.
- Wall clock: 210 minutes.
- H200 claim: at most 135 minutes, plus 15 minutes reserved for retrieval and release.
- Compute: at most 2.25 H200 GPU-hours and 6 local CPU-hours.
- Storage: one 250-GiB boot disk; at most 20 GiB retained profiles and compact endpoint artifacts.
- Authorized spend: `$8.00`; one allocation only.
- Provider creation is forbidden until the reservation is durable and a director-registered bench exists.

## Director continuation — exact Triton attention subtype specialization

The first iteration closed only `stream_interval=32`. Its retained profile is now the authoritative starting point: attention/KV accounts for `6.507778421 s` or `28.2473%` of non-overlapping wall time, while Triton `_fwd_kernel` accounts for `6.322473394 s` or `47.9%` of GPU kernel time across 3,660 launches. Existing evidence already closes generic KV-split tuning, continuous-decode and stream flag sweeps, explicit dense KV gather/repetition, the old stock fused-GQA specialization, FlashInfer TRTLLM for the 512-wide global head, and the destructive local-KV8 model change.

Continue this same deep project rather than opening a profile successor. Use the retained SQLite and pinned v0.5.13 Triton attention source to distinguish the dominant `_fwd_kernel` subtype by local/global layer, prefill/decode phase, launch geometry, and exact tensor shape. Explain a causal chain from that subtype's work or traffic through the pinned source to one source-level scheduling/dataflow specialization. It must preserve exact model geometry and avoid dense cache materialization, backend substitution, KV-head mutation, and split-count or generic flag tuning. Do not spend a turn producing another broad profile.

After project-local compilation and an exact candidate-path audit are ready, claim `h200-v0513-fp8qkv-e00t4pa49nhc2g7jwe` and run one contemporaneous unprofiled FP8+QKV c32 control/candidate pair. Require 32/32 rows, exact token/cache accounting, FP8 and QKV consumer proof, semantic smoke, and intervention proof. Promote at `<=0.6381105231 s/request` or a stable `>=5%` gain. Under the incremental-wins policy, retain a stable simpler positive result below 5% but close this attention attempt after the pair. Release by `2026-07-20T11:10:00Z`; no provider creation or additional profile arm is authorized.

## Director continuation — exact SM90 FP8 linear realization

Retain the valid deferred local FP8-KV commit (`sha256:4e11a14e...`) in both arms; it improved the exact endpoint by 0.26599% and is now part of the working stack. The next non-overlapping boundary is FP8 linear work at `5.292656685 s` or 22.9730% of wall time. The retained trace contains 14,400 `cutlass_3x_gemm_sm90_fp8` launches totaling `4.893305693 s`, using a 128x128x128 tile, 2x1x1 cluster, ping-pong fast accumulation and scaled BF16 epilogue, plus `0.323396400 s` of per-token quantization.

Continue the same deep project. Map those launches to the dominant exact Gemma projection shapes from the existing SQLite, model geometry, and pinned dynamic-FP8/CUTLASS dispatch source. Establish a causal limiter—tensor-core work, HBM/L2 traffic, occupancy/register/shared-memory pressure, underfilled grid, accumulation, epilogue, or repeated quantization. If the existing source and trace do not decide it, collect only the minimum Nsight Compute counters on the top one or two exact shapes. Then implement one source-level exact-shape tile/cluster/schedule/epilogue or quantization-dataflow specialization. This is not permission for a generic configuration sweep or a new broad endpoint profile.

Run exactly one contemporaneous c32 control/candidate pair on `h200-v0513-fp8qkv-e00t4pa49nhc2g7jwe`, with dynamic FP8, QKV, and deferred local KV commit present in both arms. Require 32/32 exact-mix rows, cache accounting, semantic smoke, FP8/QKV/attention proof, and candidate-path proof. Promote at `<=0.6381105231 s/request` or `>=5%`; retain a stable simple positive result below 5%, then close this FP8-linear attempt. The replacement watchdog is active through 13:00Z; release by 12:45Z. No provider creation is authorized.

## Director continuation — global head-512 extend-attention residency

The single exact gate/up tile candidate executed correctly but regressed the stacked endpoint by 7.2596%; discard it and close FP8-linear specialization. The profile's scheduler-thread `cudaStreamSynchronize` calls align with dependent model-step completion, so their apparent 36.58% attribution is not independently removable without changing the GPU path. The remaining distinct current-runtime opportunity is the global extend-attention subtype: only 10 layers account for 610 launches and `2.956183111 s`, nearly the 50 local layers' total. Its exact kernel uses QK/V head dimension 512, 32 Q heads, 4 KV heads, `BLOCK_M=32`, `BLOCK_N=64`, 256 threads, 255 registers/thread, and 102,400 bytes of dynamic shared memory.

Continue this same `deep` project for one counter-guided global-kernel realization. Use the H200 132-SM dossier and collect only the minimum NCU counters on the exact global kernel needed to decide whether tensor work, HBM/L2 traffic, register/shared-memory occupancy, or grid realization is limiting. Inspect the pinned Triton source and implement one source-level change to live state, tile realization, staging, or global-head-512 dataflow. Do not sweep parameters, alter head/model geometry, substitute a backend, reopen local attention, or reuse the rejected FP8 gate/up path.

Run one contemporaneous c32 control/candidate pair with dynamic FP8, QKV, and the retained deferred local KV commit in both arms. Require 32/32 rows, exact token/cache accounting, semantic smoke, FP8/QKV/local-attention proof, and global-kernel candidate proof. Promote at `<=0.6381105231 s/request` or `>=5%`; retain a stable simpler positive result below 5%, then close this global attempt. Release the existing H200 by 12:45Z under the 13:00Z watchdog; no provider creation is authorized.
