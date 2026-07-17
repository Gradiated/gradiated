# Expert-sorted stock-Marlin MoE scheduling on SM89

## Decision question

Can an exact-weight executor preserve the pinned runtime's Tensor-Core W4 Marlin work while replacing per-expert launch fragmentation with expert-sorted persistent scheduling at c16/c32's 64/128 routed assignments?

The predecessor `persistent_moe_executor_sm89` closed because its scalar queue did not group experts, did not reuse the stock W4 kernel, and had invalid output atomics. This successor tests a materially different mechanism: scheduling and launch reuse around the real packed-W4 operation, not a custom scalar GEMM.

## Immediate `$0` contract

Use the exact checkpoint, pinned vLLM source/image, and cached local CUDA image `glm-vllm:0.15.0-transformers-1618d44`; install nothing and use no provider. Within 1,200 seconds:

- Bind the actual compressed-tensors Marlin WNA16 symbol/API, packed layout, scales, group size, and route-weighted reduction used by serving layers 1–46.
- Implement one expert-sorted prefix-sum/work-descriptor path that batches rows per selected expert and schedules existing legal Marlin/CUTLASS tiles persistently. Do not write another scalar dequantizing GEMM and do not preclaim routing fusion.
- Compile for SM89 in the cached nvcc 12.9 image and record cubin/PTX identity, ptxas registers, static/dynamic shared memory, spills, grid, launches, and c16/c32 assignment geometry. Zero or 99-KiB-illegal occupancy, per-assignment full-weight reload, or one unchanged launch per active expert closes.
- Prove host/source numerical binding for duplicate, empty, balanced, and skewed expert assignments, including exact top-4 weights and BF16 output reduction. The fixture must bind the compiled candidate's descriptor contract rather than merely reorder a Python list.

Return `SOURCE_READY_FOR_SM89` only if a compiled tensor-core path plausibly changes launch/scheduling work and preserves semantics. It then nominates one later component A/B, not an endpoint. The later measured floor remains at least `2.349x` if combined MoE/routing work changes; recompute any fused-only floor from the authoritative endpoint before GPU admission. Otherwise return `MECHANISM_CLOSE` or a typed compile/resource close.

## Available evidence

- `../persistent_moe_executor_sm89/` negative source and oracle
- retained L40S V24R2/V25R1 attribution
- `../expert_count_geometry/`
- `../../hardware/L40S.md`
