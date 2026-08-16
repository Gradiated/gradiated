# Gemma 4 31B W4 c16 economic and consumer bound

## Decision question

Can an SM89-supported 4-bit weight representation of the exact Gemma 4 31B geometry both fit the campaign workload at background concurrency 16 and reduce the decode weight-streaming lower bound enough to keep the `$0.000614–$0.000621` per-request market target plausible, before spending on a W4 CUDA consumer?

This is an independent `$0` representation/capacity falsifier. It must not delay or mutate the active FP8 consumer bridge and cannot transfer quality from BF16 or any community checkpoint.

## Why now

The active FP8 lane is correcting its shared retained-session controller before one actual-consumer L40S run. Even if FP8 works, the measured M=8 MLP and M=1 tied-head priors suggest c8 weight streaming may consume most or all of the 0.717061 req/s planning envelope. W4 could approximately halve weight bytes and unlock c16 batching, but only if exact Gemma fused shapes, scale metadata, unquantized tensors, runtime workspaces, KV state, and an actual Ada consumer agree. Establish that decision surface in parallel rather than waiting for the FP8 terminal.

## Authoritative inputs

Consume:

- `../exact_geometry_runtime_opportunities/GEOMETRY.json`
- `../fp8_l40s_fit_economic_falsifier/MEMORY_ACCOUNTING.json`
- `../l40s_saturation_economic_gate/SATURATION_GATE.json`
- `../gemma_l40s_fp8_exact_shape_microbench/artifacts/gemma-l40s-fp8-corr-20260717t000000z/summary.json`
- `../gemma_l40s_vllm_fp8_consumer_bridge/IDENTITY_ASSERTION.json`
- `../exact_fp8_checkpoint_delivery_route/DELIVERY_ROUTE.json`
- fresh `research/factory/data/gpu_prices.json` and `research/factory/data/accelerator_inventory.json`

Bind all geometry and workload calculations to `google/gemma-4-31B-it` revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4`, TP=1, 4,214 input/358 output, 12.7% prompt-cache reads, the 10K single-stream view, L40S 48 GB/864 GB/s, and the completed planning/conservative throughput hurdles. Runtime may differ from the current pinned vLLM only when the exact official source revision and consumer are recorded; no throughput transfers across runtimes.

## Required evidence

1. Reconstruct a byte-exact W4 payload for at least one realistic group size/layout, including scales/zeros, padding, duplicated or fused projection effects, tensors the consumer leaves BF16/FP16, tied embedding/output behavior, allocator/workspace reserve, and both BF16 and explicit per-token-head FP8 KV. Report primary and 10K c8/c16/c32 totals against the 44.704 GiB conservative envelope.
2. Derive transparent optimistic decode weight-streaming and whole-request service lower bounds at M=8/16/32 using 864 GB/s and the campaign token mix. Use measured predecessor timings only where the tested shape really matches; do not sum overlapping kernels or relabel generic matrices as an endpoint.
3. Inspect current first-party runtime source and producer metadata for one real SM89 weight-only INT4/W4 consumer that covers Gemma's fused `5376→16384`, `5376→20480`, `5376→43008`, output projections, and tied head. Record kernel/layout/tile restrictions, activation dtype, supported group size, checkpoint format, runtime commit/image, and exact base-revision provenance. Distinguish an exact checkpoint route from a synthetic non-quality-preserving execution proxy.
4. Compare the W4 bound directly with the FP8 c8 hypothesis and the `$1.10/GPU-hour` production planning rate. Nominate at most one later paid checkpoint-free component arm only if W4 admits c16 with allocator slack, reduces the optimistic primary-workload service lower bound by at least 25% versus FP8, and has an actual SM89 consumer for the critical fused shapes. Otherwise return typed `none` and close W4 for this cycle.

Quality remains a hard later gate: any W4 checkpoint or proxy must eventually pass raw-output and feature validation against the exact target before production eligibility. This project may use source inspection, metadata, deterministic arithmetic, and bounded CPU simulation; it may not download full weights, compile CUDA, create a provider resource, or author a controller.

Write `W4_C16_BOUND.json` and `DECISION.md` with input hashes, evidence labels, byte accounting, concurrency fit table, bandwidth/service equations, consumer support table, uncertainties, and one nominated component arm or typed `none`.

## Budgets

- Wall clock: 50 minutes.
- Compute: at most 1 local CPU-hour; no GPU.
- Storage/network: at most 2 GiB retained storage and 256 MiB bounded metadata/source probes; no complete weight shards.
- Spend: `$0`; provider mutation forbidden.

## One admitted phase/KV accounting correction

The first terminal is preserved as negative evidence but is not decision-safe. It multiplied a full weight stream by all 4,214 prompt tokens even though large-M prefill GEMMs reuse weights, mixed inactive vision residency into text-only decode traffic, and used `0.555684 GiB/request` for primary FP8 KV instead of the source-reconciled `0.363423228 GiB/request` from `../fp8_kv_contract_reconciliation/KV_CONTRACT.json` (SHA-256 `d495553dab98eac4d101802e668469fea3758ba378a8bd89641075a277a07802`). The source-bound 10K FP8-KV value is `0.585865974 GiB/request`. These errors materially change both c16/c32 fit and the economic interpretation.

Make one `$0` correction in this project and publish `W4_C16_BOUND_V2.json` plus, only when warranted, `W4_COMPONENT_PACKET.json`:

- Separate capacity-resident bytes from text-path bytes actually streamed. Keep vision/inactive tensors in capacity, but exclude them from text decode traffic.
- Separate prefill from decode. Do not charge one full model stream per prompt token. Bound prefill with exact large-M GEMM FLOPs/arithmetic intensity or shape-valid measured rows and explicit batching/chunk scenarios; keep attention and missing operators explicit. Decode may use `batch * bandwidth / (active_text_weight_bytes * 358)` only as an optimistic weight-streaming ceiling.
- Recompute c8/c16/c32 primary and 10K capacity from the reconciled FP8-KV contract, scale/layout bytes, tied BF16 head, W4 payload, and the 5 GiB unmeasured reserve. State allocator uncertainty separately.
- Compare phase-aware service time with `1/0.717061 = 1.39458 s/request` planning-base and `1/1.158355 = 0.86329 s/request` conservative. Report how much time remains for attention, scheduling, sampling, and reliability rather than converting a ceiling into endpoint throughput.
- Preserve the missing exact-producer result. However, if corrected capacity/economics remain plausible and the pinned first-party Marlin method is an actual SM89 consumer for every critical fused shape, prepare one deterministic checkpoint-free synthetic W4 component packet as an explicitly non-quality-preserving cost-mechanism proxy. It is not an exact checkpoint route and cannot run until the live FP8 owner is terminal, cleaned, and a later director admits it. Name its decision trigger and reject it if the correction cannot change the next portfolio decision.

Correction sub-budget: 25 wall minutes, at most 0.5 local CPU-hours, 512 MiB additional project-local storage, and `$0`; provider mutation, CUDA compilation, and full weight downloads remain forbidden. The shared `/tmp` tmpfs is currently full, so use a bounded project-owned temporary directory under this project and delete only files created by this correction. Total project budget becomes 75 wall minutes, 1.5 local CPU-hours, and 2.5 GiB storage.
