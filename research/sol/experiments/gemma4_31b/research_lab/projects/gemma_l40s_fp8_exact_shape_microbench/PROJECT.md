# Gemma 4 31B L40S exact-shape FP8 microbenchmark

## Decision question

On one L40S, do the exact Gemma 4 31B attention, MLP, vocabulary, and KV-cache shapes execute through the current Ada FP8 paths with enough numerical and kernel/memory margin to keep the single-GPU cost hypothesis alive, independent of checkpoint staging and end-to-end quality?

This project is a component falsifier, not an endpoint benchmark. It may reject the L40S/FP8 mechanism or justify one later endpoint attempt, but it must not claim workload quality, sustainable request throughput, or production eligibility.

## Why now

Five paid endpoint allocations have produced no exact-model scientific terminal. The latest shared-transport owner created an L40S, then spent about two hours inside remote setup before timing out with no load, request, or useful-GPU artifact. Full checkpoint staging now dominates scored GPU science. The next paid allocation therefore uses the already proven checkpoint-free shared microbenchmark controller and measures only exact, decision-relevant Gemma shapes.

## Required evidence and execution contract

Use these completed packets as authoritative inputs:

- `../exact_geometry_runtime_opportunities/GEOMETRY.json`
- `../fp8_l40s_fit_economic_falsifier/FP8_L40S_PACKET.json`
- `../fp8_l40s_fit_economic_falsifier/MEMORY_ACCOUNTING.json`
- `../l40s_saturation_economic_gate/SATURATION_GATE.json`
- `../fp8_kv_c8_retained_arm/FP8_KV_ARM.json`

## Immutable identity contract

The director mechanically reconciled the named authoritative inputs with `validate_identity_contract.py`. They bind this project to:

- Model: `google/gemma-4-31B-it` at revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Model-index identity: `sha256:d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2`.
- Runtime image: `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`.
- Runtime amd64 manifest: `sha256:8e86cb93b724092cd4dc892fb129a6c5538613b38a5cd34e40aab9e6aea72b03`.
- vLLM source revision: `ab0a20d15129b322f911db578b50c6b35b3167e7`.
- Workload geometry: `text-only non-reasoning; primary 4214 input/358 output centered workload, then one 10K single-stream comparator`.

This component test deliberately downloads no checkpoint. The model/revision, model-index hash, exact tensor geometry, runtime, and workload identities above define which endpoint mechanism the synthetic exact-shape cases represent. Provider creation remains gated on the validator and the project preflight both passing. Render the runtime image as an explicit controller argument; the controller's unrelated historical default is not an admissible substitute.

Use `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py` directly as the provider owner. Do not build a project-local create/SSH/cleanup wrapper. If the controller must accept the exact image, platform, or preset as CLI parameters, make only that narrow reusable change, verify it locally, then continue within this same durable project owner.

Pin the immutable identities above exactly. Use the already admitted `gpu-l40s-a` / `1gpu-8vcpu-32gb` shape and a lowercase resource name. No model, tokenizer, or checkpoint download; no inference server.

Before provider creation, write a typed local preflight that records the exact cases, seeds, tolerances, expected dtypes, image identity, controller command, timeout, cleanup path, and output schema. Provider creation is gated on that preflight passing. One bounded durable owner remains responsible through typed terminal and cleanup; do not kill or restart correct local preparation merely because a model response ends.

Run, at minimum:

1. Seeded BF16-reference versus W8A8 FP8 CUDA measurements for exact decoder projections, the 5:1 sliding/global attention geometry, MLP shapes including `5376 x 21504`, and representative decode `M` at c1/c2/c4/c8 plus representative prefill `M`. Measure the tied vocabulary projection at its actual retained precision rather than silently converting it to FP8.
2. Numerical checks against the seeded BF16 reference. Any unsupported kernel, silent dtype fallback, non-finite output, or preregistered error-tolerance failure is a scientific negative, not an infrastructure retry.
3. CUDA-event and wall timing, warmup/iteration counts, allocated/reserved/peak memory, clock/power/utilization telemetry, useful-GPU seconds, and achieved bandwidth/FLOP interpretation. Explicitly identify tiny-`M` occupancy and launch overhead.
4. Map the component measurements to the completed L40S thresholds—0.717061 req/s planning-base and 1.158355 req/s conservative—only as transparent mechanism bounds. Never report component throughput as end-to-end requests per second.

## Adjacent retained-session arm

Preregister and stage offline, before the live owner ends, one conditional follow-up using the same resident image allocation. If the primary FP8 linear cases pass their typed kernel and numerical gates, run the exact `fp8_per_token_head` E4M3 KV write/read microbenchmark from `FP8_KV_ARM.json` for c8 and the 10K residency geometry. It must be launch-ready within ten minutes, use no checkpoint or server, and remain under the same sequential owner/watchdog. If the trigger is false, skip it and clean up immediately.

## Stop rules and terminal artifact

- The failed first allocation is terminal and cleaned. Permit at most one post-cleanup corrected allocation under the correction sub-budget below; never overlap allocations and create no support successor.
- A create/SSH/image failure permits only bounded diagnosis within the same owner; do not start another allocation unless the first never created a billable resource and the typed cause is corrected within the budgets.
- Stop after the preregistered primary matrix and conditional KV arm, or on a scientific negative that already resolves the mechanism question.
- Cleanup must be attempted and verified on every path.
- Write `artifacts/summary.json` as the typed terminal, with evidence labels, raw artifact paths, timing split (setup versus useful GPU), scientific classification, economic interpretation, retained-arm disposition, cleanup proof, and the precise next decision.

## One admitted in-place correction

The first allocation reached L40S CUDA and entered the KV arm, which proves by control flow that all primary FP8 linear rows passed their finite-output and absolute-error gates. Its script then attempted a monolithic 28.29 GiB BF16 all-layer KV tensor, OOMed, and lost buffered primary detail. Typed cleanup passed after 1,211.451 provider seconds at a derived `$0.255388046`, with zero instances and disks.

Consume `../fp8_kv_contract_reconciliation/KV_CONTRACT.json` and `../fp8_kv_contract_reconciliation/CORRECTED_ARM.md` as the correction contract. Before create, require a typed local terminal that revalidates the immutable identity assertion, the prior cleanup, empty provider inventory, unchanged primary cases/tolerances, atomic primary-row persistence under an injected KV failure, and per-layer/tiled KV shapes. Then run the same shared controller and exact image under one new bounded durable owner:

- Persist the complete primary rows atomically before evaluating the conditional arm.
- Use the corrected dynamic per-token-head E4M3 contract: 4,224 bytes per local resident token/layer and 4,128 bytes per global resident token/layer.
- Run only per-layer cache shapes with 128-token conversion/readback tiles; never allocate `tokens x 450560` or concatenate all 60 layers.
- Keep the original named trigger, numerical tolerance, telemetry, authenticated artifact retrieval, and verified cleanup. No full model, checkpoint, server, or endpoint claim.
- Correction sub-budget: 35 minutes wall clock, 20 provider minutes, at most 0.34 L40S-hours and 1 local CPU-hour, 100 GiB provider disk, 4 GiB retained artifacts, and `$0.50` including disk.
- Whether positive, negative, or operationally failed, this corrected allocation closes the microbenchmark lineage; do not create a third allocation.

## Budgets

- Wall clock: 90 minutes for the durable owner.
- Provider exposure: 45 minutes maximum.
- Compute: at most 0.75 L40S GPU-hours and 2 local CPU-hours.
- Storage: 100 GiB provider boot disk; at most 4 GiB retained local artifacts.
- Spend: at most $3.00 including disk.
