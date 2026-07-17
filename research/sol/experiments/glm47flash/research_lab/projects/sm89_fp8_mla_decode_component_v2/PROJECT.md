# Exact one-head SM89 FP8-MLA decode component v2

## Question

Can an actual one-KV-head GLM-4.7 MLA attention implementation on L40S reduce long-context cache bytes and component wall time with FP8-e4m3 KV while preserving BF16 query/output numerics closely enough to justify later full-model integration?

## Why this changes the portfolio

FP8 MLA is campaign priority 2 and remains scientifically untested. Prior lineages either failed before CUDA or never executed full attention, used 20 KV heads instead of the exact one-head cache, omitted split reduction/LSE, or failed their own numerical proxy. This project is a new direct target-GPU experiment, not a backend survey or repair packet. A real component pass identifies a model/chip mechanism; a real fail closes FP8 MLA on this exact implementation geometry.

## Direct execution contract

Use the supplied-script interface in `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py`, but override its broken v0.25.1 image with the proven pullable L40S base `vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`. Reuse the proven one-line SSH/cloud-init path, one external user-systemd owner, and one independent instance/disk watchdog. Do not use or repair the manifest-incompatible image from `marlin_moe_microblock_sm89`.

Provider mutation is blocked until that sole Marlin owner is inactive and authenticated direct inventory is zero instances/disks. Then group exact script/spec hashes, Python/Triton syntax, matching SSH pair, fresh price/orderability, unique resource names, deadline cost, and zero inventory once, and launch in the same researcher turn. Authorize one preemptible L40S create, no retry, at most 1,800 allocation seconds and `$0.55` experiment spend.

The first scientific arms must execute real matched BF16-KV and FP8-e4m3-KV attention, not conversion-only or byte-only proxies:

- exact MLA geometry: 20 query heads, one KV head, latent+rope width 576, value alias `:512`, page size 16, four KV splits, shuffled page tables, cache `[pages,16,1,576]`;
- seed 1234, B1/B8 sanity and B32 decision rows at context lengths `8193,8449,8705,8961,9215`;
- explicit FP8 scale policy and saturation counters;
- matched writer, stage-1, split reduction, complete attention output, and LSE against a BF16/FP32 oracle;
- allocated bytes, source/kernel identity, launch grid, registers/shared memory/spills/occupancy, warmup, p50 and p95.

Pass only if every decision row is finite, no fallback or saturation occurs, output is within `atol=0.03, rtol=0.03`, LSE within `atol=0.10, rtol=0.03`, exact one-head byte accounting passes, and every B32 length improves both stage-1 and full-attention p50 by at least 10% without p95 regression. Any wrong-head, serial-context, unwired-kernel, missing reduction/LSE, compile, numerical, resource, timeout, or artifact defect is terminal.

Return one typed `FP8_MLA_COMPONENT_PASS`, `NUMERICAL_CLOSE`, `PERFORMANCE_CLOSE`, `IMPLEMENTATION_CLOSE`, or `OPERATIONAL_NULL`. There is no retained follow-up: no frozen full-model integration path can be ready within ten minutes. Clean immediately after the component endpoint and authenticate zero resources. No readiness-only return or successor packet.

## Available evidence

- `../sm89_fp8_mla_kv_kernel/` negative implementation evidence and exact geometry warnings
- `../full_model_fp8_kv_c32_corrected/` stock-runtime backend close
- exact stock c32 endpoint `609.606365 tok/s`
- `../../hardware/L40S.md`
- shared campaign and factory tools supplied by the lab
