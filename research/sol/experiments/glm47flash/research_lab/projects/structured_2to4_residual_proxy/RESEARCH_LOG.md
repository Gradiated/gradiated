# Research log

Opened by the Cycle 83 director as the campaign's first focused 2:4 residual proxy. It must fail fast on exact representation/runtime support and conservative economics; it owns no provider, checkpoint mutation, custom kernel, training, or quality work.

## 2026-07-16 — RUNTIME_CLOSE at $0

Question: can a deterministic 2:4 proxy over the current BF16 `lm_head`, 141 shared-expert matrices, and eight layer-0 matrices provide an unchanged L40S SM89 execution path and robust economics?

Action: processed the exact safetensors weights with per-output-channel top-2 magnitude retention in every contiguous K-group of four; audited pinned `glm-vllm:0.15.0-transformers-1618d44` and one current stable tree (vLLM v0.15.1, `1892993b`). The physical `sparse_24_bitmask` layout is BF16 `[N,K/2]` values plus uint8 `[N,K/8]` metadata, with no padding in the selected tensor set.

Evidence: the proxy reduces 1,612.5 MiB to 907.031 MiB (705.469 MiB saved). Per-family recovery burdens (pruned relative L2) are 0.3873 head, 0.3595 shared experts, and 0.3569 layer 0. Even granting the complete storage credit, projected c32 peak remains 46,170.231 MiB, 102.231 MiB over the 46,068-MiB envelope. More importantly, both audited runtimes return minimum compute capability 90 for `CompressedTensors24`; its `cutlass_scaled_sparse_mm` route therefore cannot run on L40S SM89. The checkpoint’s AWQ configuration contains no sparse map.

Interpretation: close on the exact runtime gate, before endpoint/cost measurement. A new sparse checkpoint/config, loader, or kernel would violate scope. Artifacts: `artifacts/structured_2to4_proxy_source_audit.json`, `artifacts/DECISION_2026-07-16.json`, and `structured_2to4_proxy.py`.
