# Research log

## 2026-07-17 — director admission

Activated after the one corrected H100 FP8 owner was independently quarantined. This deep `$0` project redirects to W4 Marlin and must return one exact source/chip/program mechanism or typed none.

## 2026-07-17 — source-bound H100 W4 discriminator complete

Question: can the actual pinned AWQ-Marlin W4A16 path be bound to a correct exact-shape H100 falsifier, and what SM90 resource should the first CUDA run discriminate?

Action: traced official `quantize_weights`/`awq_pack` through `AWQMarlinLinearMethod`, AWQ-to-standard conversion, `gptq_marlin_repack`, `MarlinLinearKernel`, and `marlin_gemm`. Built `h100_w4_marlin_falsifier.py` with exact source/image assertions, a varied-sign dual oracle, L2-evicted and warm W4/BF16 timing, the 24-row M8/M16/M32/M3679 aggregate, and two NVTX profile cases. Ran the CPU packing/geometry/mutation/aggregation consumer in `CPU_CONTRACT.json`; all checks pass.

Evidence: source-backed Marlin launches one 256-thread CTA per SM with the full opt-in shared-memory request and legacy `mma.sync`/`cp.async`, capping launch warp occupancy at 12.5%. Exact M8/M16/M32 arithmetic intensities are analytically below the H100 SXM ridge; M3679 is above it and is actually split into five launches. Three W4 matrices fit 50 MiB L2, making cold timing compulsory. The current direct-FP8 dependency has reconciled complete with one valid M8 row only; no timing transfers.

Interpretation: return `content_bound_h100_w4_direct_falsifier`, not a W4 performance or quality claim. The smallest CUDA discriminator is the separately retrieved sliding-QKV M8 sentinel, then merged-gate/up M8 and M3679 profiles to test memory/occupancy versus compute. A later H100-only two-CTA dispatch is the concrete intervention if baseline counters support the occupancy hypothesis.

Next move: only under new spend authority, run the sentinel in the immutable image and conditionally the exact 24-row sweep. Any identity, pack, consumer, or dual-oracle failure closes the line; below-ceiling component time remains plausibility only.
