# Research log

## 2026-07-23 — director admission

- Measured: the prior actual-paged E4M3 local FA3 component reduced consumer time `26.5422%` and its producer-consumer boundary `24.0777%`, with relative L2 `0.004103`.
- Measured: the required E4M3 local representation made the endpoint `4.1445%` slower, so that exact hybrid was correctly closed without an endpoint.
- Derived: applying the measured conservative local-bound reduction without the representation penalty implies about `3.6868%` whole-request savings from the qualified E5M2 frontier.
- Hypothesis: one direct E5M2 FA3 load/dequant path preserves that consumer gain while leaving page-one E5M2 storage and all global Triton layers unchanged.
- Decision: admit one source-bound component and conditional c32 candidate. No FA3 tuning, E4M3 conversion, or second candidate is allowed.

## 2026-07-23 — exact direct-E5M2 component is unsupported

- Question: can pinned SGLang v0.5.13 FA3 v3 consume the qualified page-one E5M2 local KV pool directly at c32, context/window 1,024?
- Action: froze `SOURCE_BINDING.json` (`e54dfce…69e49`), claimed `h200-sync-linear-e00vhh6h29fj68x91g`, ran the actual stock E5M2 `SWAKVPool.set_kv_buffer` producer, audited all 50 local layers to `FlashAttentionBackend` and all ten global layers to unchanged `TritonAttnBackend`, then issued the first direct FA3 CUDA call.
- Measured: the call reached `torch.ops.sgl_kernel.fwd.default` and failed exactly with `FlashAttention only supports fp16, bf16, and fp8_e4m3 data type`. Invocation markers prove the candidate CUDA/scientific call began; the router audit contains one binding plus all 60 layer dispatches with E5M2 on both pools. Raw stdout/stderr and hashes are under `artifacts/e5m2-local-fa3-20260723/component/`.
- Interpretation: this is the preregistered unsupported direct-consumer stop, not a launcher defect. The pinned FA3 v3 load/dequant path has no E5M2 specialization; adding an E4M3 conversion would replay the closed representation penalty and violate scope.
- Decision: close without timing or c32 endpoint. Actual assigned shared-bench exposure was `$0.04290740815`; the H200 was released ready with checkpoint/image/caches retained.
