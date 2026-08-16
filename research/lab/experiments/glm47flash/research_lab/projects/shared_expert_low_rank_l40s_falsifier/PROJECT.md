# Shared-expert low-rank L40S falsifier

## Question

Can only the 46 always-on BF16 shared experts be factorized into tile-aligned low-rank linears with enough exact-weight and shared-MLP proxy fidelity to support at least a 3% c32 endpoint improvement?

## Why this is a new model/chip line

Each serving layer 1–46 has BF16 shared-expert gate/up `[1536,2048]` and down `[2048,1536]` linears: exactly `18 MiB/layer` and `828 MiB` total. Retained evidence gives the always-on shared path a `7.101%` optimistic endpoint ceiling. A sufficiently compact factorization could reduce small-M BF16 work and payload while preserving the 1,536-wide SwiGLU nonlinearity.

This project does not factor or couple the 64 routed W4 experts, delete intermediate width, skip shared execution, change top-k, change precision, factor the output head, or alter depth/MLA/KV/scheduling. Those terminal lineages do not cover the exact always-on shared-linear intervention here.

## Fixed candidates and evidence

Use exact BF16 weights from `/root/.cache/glm47flash-awq-ab31d120` (revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, config `079f8f...fa7622b9`, index `b9c534...988695`) and screen exactly:

1. concatenate gate/up to `[3072,2048]`, use a shared rank-512 input factor, and independently factor down at rank 512; execution is `2048 -> 512 -> 3072`, split/SwiGLU, then `1536 -> 512 -> 2048`. This is `8.5 MiB/layer`, a `52.7778%` MAC/byte cut, and `437 MiB` saved;
2. independent rank-384 factors for gate, up, and down, `7.875 MiB/layer`, a `56.25%` MAC/byte cut, and `465.75 MiB` saved.

All factor dimensions are multiples of 128. Exclude rank 640: its joint-factor `40.972%` cut is below the `42.247%` component reduction needed by the retained shared-path ceiling and the 3% hurdle. Inputs include `../moe_dense_residual/` trace ceilings, `../residual_w4_completion/residual_w4_completion_bound.json`, `hardware/L40S.md`, and the c32 control archive `94e2f841...86dbf` with mean `602.157121` and `1.03x` gate `620.221834`.

## Immediate `$0` experiment

Within 1,800 seconds, 16 GiB RSS, 96 MiB new artifacts, and `$0`, compute deterministic exact-weight truncated/randomized spectra for all layers or a fail-closed stratified design, then exercise reconstructed gate/up -> SwiGLU -> down with fixed-seed Gaussian and heavy-tail hidden vectors. Retain hashes, spectra, error summaries, factor geometry, and economic arithmetic, not full factor payloads. Count extra GEMM launches/intermediates explicitly. Do not write a checkpoint, patch a runtime, use CUDA/provider resources, train, or run a broad quality suite.

First require at least `50%` component MAC/payload reduction and at least a `3.5%` optimistic endpoint ceiling. Then require every evaluated layer/family to have relative-Frobenius reconstruction error `<=0.10`; shared-MLP proxy median cosine `>=0.99`, p05 cosine `>=0.98`, p95 relative-L2 `<=0.10`, finite outputs, and no layer relative-L2 above `0.15`.

Return `SHARED_FACTOR_CLOSE` on any economic, geometry, or fidelity failure. Return `NOMINATE_SHARED_FACTOR_PROXY` for exactly one better variant only if all gates pass. State but do not prepare its later full47 c32 endpoint, which must beat `max(606.355, 1.03x contemporaneous bracket mean)` on complete exact 8K/1K requests inside 300 seconds. All evidence is quality-deferred architecture-cost evidence.

## Available resources

Use the fixed projects above, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
