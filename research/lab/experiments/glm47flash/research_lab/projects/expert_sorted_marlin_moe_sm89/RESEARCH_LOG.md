# Research log

## 2026-07-16 — Director opening handoff

The predecessor scalar queue is terminal and must not be compiled. Test one materially different exact-weight mechanism: expert-sort the 64/128 routed assignments and persistently schedule the pinned runtime's actual Tensor-Core W4 Marlin tiles. The cached nvcc 12.9 image makes compile/resource evidence `$0`. Close on scalar fallback, unchanged per-expert launches, invalid reduction, or SM89 resource illegality; a source-ready result only nominates a later component A/B.

## 2026-07-16 — MECHANISM_DUPLICATE

Close before implementation. Pinned vLLM already calls `moe_align_block_size` to generate expert-sorted token/expert descriptors, then issues one `moe_wna16_marlin_gemm` for gate/up and one for down per MoE invocation; the kernel globally schedules padded expert blocks. Retained L40S evidence corroborates one routed-Marlin signature per layer/step (`11,684 = 46 x 254`) with a 426-block grid. Rebuilding this descriptor path would duplicate stock rather than test a new mechanism.
