# Research log — decode-tail MoE bypass architecture

## 2026-07-15 — Director delegation

Opened as an independent `$0` model/chip screen after the same-identity H100 transfer closed at 935.036 tok/s versus its 1,513.186-tok/s economic gate. The project keeps stock full-depth prefill plus all 47 decode attention/KV paths, bypassing routed and shared MoE only in selected late decode layers. It must bind the exact runtime, distinguish ideal kernel-work savings from a conservative 594.466-tok/s endpoint bound, and return one source-bound fixture plus a close or single future-arm nomination. No provider, CUDA, shared-launcher edit, training, or quality claim is authorized.

## 2026-07-15 — Last-12 source fixture and upper-bound falsification

Question: can decode-only bypass of sparse layers 35–46 clear the 594.466 tok/s L40S c16 gate while retaining all attention/KV work? Action: ran `source_bound_decode_tail_moe_bypass.py`, binding checkpoint `ab31d120`, runtime `glm-vllm:0.15.0-transformers-1618d44`, recorded vLLM target SHA `6a984f…6b4a9`, the authoritative c16 control, and retained V25R1 trace. The fixture passed stock identity, full-depth prefill, all-47 decode attention/KV, absent post-attention norm/router/routed/shared/add only in 35–46, stable `[16, 2048]` shape, final norm/head, and mixed-phase rejection.

Evidence: the bypass removes 1.132B active MLP FLOPs plus 3.146M router-projection FLOPs per decode token (18.119 GFLOPs MLP per c16 step), but attention/KV/prefill/head receive zero credit. Scaling the retained c16 trace's routed Marlin (14.393%), routing/sort (3.719%), and deliberately generous all-layer shared-path ceiling (7.101%) by 12/46 yields only 6.577% decode-kernel credit. Even by treating that summed-kernel credit as non-overlapped wall time with zero dispatch overhead, the decode-only ceiling is 572.973 tok/s; retaining the 14.830% prefill wall share lowers the end-to-end ceiling to 567.053 tok/s / `$0.539/M`, 27.413 tok/s short. Kernel sums and runtime overlap make this an optimistic upper ceiling, not a prediction.

Decision: close at `$0`; do not nominate an L40S arm or recovery work. Artifact: `decode_tail_moe_bypass_bound.json`.
