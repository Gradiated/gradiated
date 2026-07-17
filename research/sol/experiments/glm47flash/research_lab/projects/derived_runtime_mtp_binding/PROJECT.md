# Derived-runtime native MTP binding

## Question

Does the exact current-AWQ layer-47 MTP payload bind and plan correctly in the actual derived vLLM runtime used by the measured c16 service?

## Why it matters

`current_awq_mtp_layer` closed after the digest-pinned base vLLM 0.15.0 image's bundled Transformers failed to recognize `glm4_moe_lite`. That closure is valid only for the base image. The successful current-AWQ c16 launcher builds `glm-vllm:0.15.0-transformers-1618d44` by installing Transformers commit `1618d44b9295361607ec74d7be860ba886aac039`; this derived runtime demonstrably parses and serves the same checkpoint. Meanwhile vLLM 0.15.0 already contains the exact `Glm4MoeLiteMTP` model, registry entry, planner rewrite, and layer-47 weight-name mapping. The prior failure therefore cannot be transferred to the measured serving identity.

The exact MTP payload contains 606 tensors / 1.543 GiB, and the existing c16 bound needs only 0.10 accepted draft tokens per round at zero draft overhead, 0.155 at 5%, or 0.21 at 10% to reach the 10% cost gate. Before another paid session, the decisive question is whether the actual serving runtime binds this payload without a second complete model or unsupported substitution.

## Scope

At zero provider spend, build or inspect the exact derived runtime specified by:

- base image `vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`;
- Transformers revision `1618d44b9295361607ec74d7be860ba886aac039`;
- derived tag and Dockerfile contract in `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`;
- checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`.

Reuse and extend the content-bound fixture and tensor manifest from `../current_awq_mtp_layer/`. Inside the derived image, prove or falsify exact config parsing, model registry resolution, `SpeculativeConfig`/CLI planning for the one native MTP layer, layer-47 tensor-name rewrite, quantization/dtype compatibility, shared embedding/head behavior, memory accounting, and whether the target plus MTP can be instantiated without a second full checkpoint. Use the smallest fail-closed local source/loader fixture; a full GPU allocation is prohibited and a CPU weight materialization is unnecessary if planner/loader contracts can be content-bound without it.

Do not upgrade vLLM, select a different speculative method, repair the base image, edit the provider launcher, train a head, or repeat the acceptance sweep. Source presence alone is not a pass. If a remaining stage requires CUDA allocation, bind everything before that boundary and return the exact one-GPU load falsifier rather than claiming execution.

## Resources

- Base-scope closure and fixture: `../current_awq_mtp_layer/`.
- Measured runtime and launcher: `../nebius_current_awq_c16_direct/` and `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/`.
- Exact checkpoint: `/root/.cache/glm47flash-awq-ab31d120`.
- Existing acceptance/economics evidence: `../current_awq_mtp_layer/current_awq_mtp_bound.json`.

## Portfolio-changing result

Nominate at most one later matched L40S c16 MTP off/on arm only if the exact derived-runtime fixture passes through payload binding/planning and no second full-model copy is required. State the remaining GPU-only load check and reuse the existing acceptance/overhead gates. Any exact config, quantization, loader, planner, or memory failure closes native MTP across the actual current serving identity. This project has no provider authority or spend.

## Director GPU preregistration — Cycle 44

The zero-cost binding passed and provider inventory is reconciled empty. Preregister one final native-MTP L40S session through `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, using local checkpoint and tokenizer `/root/.cache/glm47flash-awq-ab31d120`, base image digest `sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`, Transformers revision `1618d44b9295361607ec74d7be860ba886aac039`, `max_num_seqs=16`, `num_kv_splits=4`, cache off, and the exact 8,192-input/1,024-output c16 workload. Its future maximum provider exposure is 4,500 seconds and `$1.15`, including cleanup reserve, under one external systemd owner and watchdog.

Use the passed fixture and integrate only the native `num_speculative_tokens=1` MTP launch contract into the proven derived runtime. After image/checkpoint staging, the first scientific gate is one-GPU MTP target-plus-draft load, residency, and health with no second full target allocation. If that passes, run adjacent stock-c16 and MTP-c16 arms on the retained allocation. Require all requests complete, exact geometry, greedy output digest identity, proposal/acceptance counters, accepted tokens per round, draft/verify wall time, fallback/errors, peak VRAM/KV, GPU telemetry, useful GPU seconds, spend, and verified zero inventory.

The campaign economic gate is authoritative: promotion requires at least `594.466` output tok/s, not the earlier rounded `588.815` threshold. Retain bounded server stdout/stderr, exit status, and the remote archive before teardown; the recent FP8 route's missing archive must not recur. One material in-place startup correction is allowed. A target/MTP loader, memory, quantization, identity, or sub-gate result closes native MTP scientifically; another pre-science server-start/archive failure closes this provider execution route without an MTP claim or another controller successor. Cycle 45 transferred sole provider ownership to this project after the cache-profile diagnostic reached terminal cleanup; the active cap is `$1.15` and 4,500 seconds.
