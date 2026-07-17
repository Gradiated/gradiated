# Research log

Opened by the Cycle 83 director as a single-card low-cost AMD falsifier distinct from the closed MI3xx replica screen. It starts with exact `gfx90a` runtime support and owns no provider mutation, image build, checkpoint conversion, or controller work.

## 2026-07-16 — RUNTIME_CLOSE

Question/action: test the exact local checkpoint against at most two current ROCm serving paths using source/config/header evidence only, stopping at the first exact technical boundary.

Evidence: the checkpoint is hash-bound to `Glm4MoeLiteForCausalLM`, 47 layers, 64 routed experts/top-4, and compressed-tensors `pack-quantized` symmetric INT4 W4A16 group-32 (`config.json` SHA `079f8f…7622b9`, index SHA `b9c534…8695`). The shared inventory binds MI210 to `gfx90a`, 64 GB HBM2e, 1.6 TB/s, but no price join. Current SGLang documentation separates AMD Triton `awq` from only partial AMD `compressed-tensors` support and scopes its AMD examples/matrix to MI300-class devices; current vLLM documentation advertises the format at the platform level but its current release notes bind native W4A16/fused-MoE HIP work to RDNA3 `gfx1100`, not MI210 `gfx90a`. The retained SGLang patch is a CUDA-era MLA/loader repair and does not supply a ROCm kernel or pinned MI210 validation.

Interpretation: neither candidate proves architecture registration, exact compressed-tensors parsing, non-CUDA W4A16 kernel selection, and MLA support together on `gfx90a`; CUDA Marlin and dense/dequantized fallbacks are explicitly inadmissible. This is an exact runtime failure, not a throughput or price claim. No venue search or provider mutation was entered; spend remains `$0`.

Artifact: `MI210_GATE_2026-07-16.json`. Next move: none; reopen only after a pinned ROCm stack publishes or measures exact `gfx90a` W4A16/MLA support for this checkpoint.
