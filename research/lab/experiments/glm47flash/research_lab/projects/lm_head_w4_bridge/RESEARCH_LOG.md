# Research log

No researcher result yet. This is a zero-provider exact-pack and runtime-binding falsifier. Do not time on a GPU or edit the shared launcher unless a later director turn explicitly transfers the paid component slot after native-MTP cleanup.

## 2026-07-15 — Exact head W4 bridge closes at the derived loader

Question: can the stock BF16 `lm_head.weight` alone use the checkpoint's group-32 W4 representation and the pinned vLLM Marlin path strongly enough to earn a later L40S component timing?

Action: added and ran [`source_bound_head_pack_fixture.py`](source_bound_head_pack_fixture.py) against the immutable checkpoint and local derived image. It streamed all 317,194,240 real BF16 head values, emitted and immediately unpacked a symmetric group-32 signed-W4/K-packed representation (no checkpoint mutation or retained packed payload), then queried the actual compressed-tensors selection logic for the actual `ParallelLMHead` class.

Evidence: [`lm_head_w4_bridge.json`](lm_head_w4_bridge.json) binds the source bytes (SHA-256 `9cf128f3…3bba5eb0`) and produces the native tensor contract: `weight_packed` I32 `[154880,256]`, BF16 scale `[154880,64]`, and I64 shape `[154880,2048]`, 170.156 MiB total. The real round trip has RMSE `0.002948`, MAE `0.002443`, max absolute error `0.028320`, and relative L2 `0.092608`. The source Marlin shape predicate passes K=2048/N=154880/group-32 for SM89, but this does not reach dispatch: after removing `lm_head` from the ignore list, `CompressedTensorsConfig.get_quant_method(ParallelLMHead, "lm_head")` returns `None`, and target resolution fails with `Unable to find matching target for lm_head`. `ParallelLMHead` inherits `VocabParallelEmbedding`, not `LinearBase`, while this runtime assigns the W4 method only to `LinearBase`, attention, and fused-MoE layers.

Interpretation: the representation and Marlin geometry are not the limiting factor; the exact pinned loader cannot bind W4 to the stock output-head module. The required mixed loader/Marlin-dispatch gate fails before CUDA, so the 3.408x component-speed threshold is unreachable in scope. Close without the $0.40 timing nomination or launcher edits. Reopen only with a source-supported quantized `ParallelLMHead` path or a separately approved output-layer implementation; that is a new runtime intervention, not this bridge.
