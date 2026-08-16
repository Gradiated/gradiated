# Research log

## 2026-07-16 — Director opening handoff

- Rebase only the rank448-plus-c40 discontinuity against the verified stock KV pool and c32 endpoint; keep the earlier rank project closed.
- Require exact rewrite/loader closure, block-rounded capacity with reserve, SM89 legality, and a conservative `606.355`-tok/s path before nominating one later proxy.
- No checkpoint materialization, CUDA/provider work, shared-code edit, training, or quality evaluation.

## 2026-07-16 — Director audit closes rank448+c40

Exact block accounting closes the interaction before materialization. The stock pool is `20,843 * 866,304 = 18,056,374,272` bytes. At rank448, one 16-token block is `770,048` bytes; after also crediting the previously omitted 47 rank-layernorm vectors, the maximal derived pool is `23,473` blocks / `375,568` tokens. Exact c40 needs `23,040` blocks / `368,640` tokens, leaving only `433` blocks / `6,928` tokens (`1.879%`) and missing the prior 5% reserve by `719` blocks.

The earlier representation sketch was incomplete because all 47 `[512]` `kv_a_layernorm.weight` vectors must become `[448]`, alongside config, packed weights/scales, `weight_shape` values, and manifests. Hardware does not supply the intended discontinuity: BLOCK_N=32/stage-2 remains legal at `80,896 B` but one block/SM, while BLOCK_N=64/stage-2 remains illegal at `143,360 B`. Finally, measured c16/c32 establish no conservative c40 lower bound above `596.852`; a curve extrapolation beyond `606.355` is inferred, not nomination evidence. Close at `$0` with no checkpoint, CUDA, provider, or quality work.
