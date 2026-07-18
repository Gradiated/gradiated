# Exact Gemma 4 weight-structure intervention screen

## Decision question

Do the exact Gemma 4 31B transformer projection weights expose a plausible hardware-realizable 2:4 sparsity or low-rank model-change mechanism large enough to merit one later quality-aware H200 experiment if measured BF16 linears prove economic-limiting?

This is materially independent `$0` evidence while `h200_bf16_exact_linear_floor` owns provider mutation and spend. It must not poll, alter, or wait on that owner. It may nominate one future model intervention, but it cannot establish quality, H200 speed, or endpoint economics.

## Exact inputs and scope

- Read-only verified checkpoint: `../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint`, target `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Geometry: `../exact_geometry_runtime_opportunities/GEOMETRY.json` and the six transformer-linear shapes in `../gemma_l40s_w4_c16_economic_bound/W4_COMPONENT_PACKET.json`.
- Screen only text-transformer Q/K/V/O and MLP gate/up/down matrices. Exclude embeddings, tied vocabulary head, vision, norms, and non-matrix tensors from promotion arithmetic.
- Use read-only safetensors/mmap or bounded streaming. Do not copy, rewrite, materialize a new checkpoint, use CUDA, or mutate any provider.

## Immediate experiment

Build a reproducible tensor inventory binding every included tensor name, shape, dtype, shard, byte range when available, and source hash/terminal identity. For each of the six architectural classes, select a deterministic layer-stratified sample covering early/middle/late and sliding/global variants; expand to all applicable matrices only if it fits the budget.

Measure:

1. Exact zero density and compliance with NVIDIA-style 2:4 groups along both plausible contraction layouts. Natural-zero absence is a useful negative.
2. For deterministic magnitude 2:4 pruning, relative Frobenius error, retained energy, per-row error quantiles, outlier sensitivity, and variation across layers/classes. This is a synthetic non-quality-preserving proxy, not a deployable weight set.
3. Randomized-SVD energy curves or another bounded deterministic spectral sketch for ranks aligned to 128, reporting parameter/byte reduction versus reconstruction error. Do not extrapolate from a single matrix or convert FLOPs/bytes into endpoint throughput.
4. Architecture-weighted reducible BF16 bytes per decode step, including metadata/index overhead for a supported 2:4 representation and factorization overhead for low rank. Compare the maximum mechanism with the campaign's 5% whole-request relevance threshold only as an upper bound.

Name at most one future candidate. Promotion requires consistent structure across representative layers, at least 20% architecture-weighted weight-byte reduction after metadata/factor overhead, a concrete H200-capable consumer format or instruction path, and a later calibration/fine-tuning plus raw quality plan. Otherwise emit typed `none`. A natural sparse pattern alone does not establish speed; a pruning error alone does not establish quality.

## Budgets and artifacts

- Wall clock: 50 minutes.
- Compute: 4 local CPU-hours; no GPU.
- Storage: 4 GiB retained and 2 GiB project-local temporary; no shared `/tmp`, no copied weight shards.
- Spend/provider: `$0`; provider mutation forbidden.

Write reproducible code, `WEIGHT_STRUCTURE_SCREEN.json` with evidence labels and tensor coverage, concise `DECISION.md` and `RESEARCH_LOG.md`, and terminal `STATUS.json`.
