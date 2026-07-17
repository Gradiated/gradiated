# Research log

## 2026-07-16 — Director opening handoff

- Resolve the conflicting old full-model rank accounting using exact headers plus the valid r3 and depth42/depth43 measurements.
- Screen only ranks 448, 416, and 384 at `$0`; no checkpoint materialization or provider preparation.
- Nominate only on both `<=44,532 MiB` c32 peak and `>=606.355` tok/s conservative endpoint evidence.

## 2026-07-16 — FULL47_RANK_CLOSE

- Parsed the exact full-47 `ab31d120` config and safetensor headers, then inspected the local pinned vLLM image. `Glm4MoeLiteDecoderLayer` reads `config.kv_lora_rank` and passes it to MLA attention; all three ranks have a coherent group-32 `kv_a`/`kv_b` rewrite geometry, though no payload was written.
- Exact robust-memory accounting gives peaks of `45,352.971`, `44,591.607`, and `43,830.434 MiB` for ranks 448, 416, and 384. Thus only rank384 clears `44,532 MiB` (by `701.566 MiB`). All retain a legal `BLOCK_N=32` stage-2 envelope; all fail the preferred `BLOCK_N=64` stage-2 SM89 shared-memory envelope.
- Applied the closest measured c32/c16 packing ratio (`636.469100/600.704460`) to the valid full-model r3 c16 endpoint, then granted the complete scope-matched MLA transfer (`1.05%/14.35%`). The deliberately optimistic endpoint upper bounds are `589.802594`, `592.180830`, and `594.559066` tok/s. Rank384 remains `11.795934` below the robust `606.355` gate, so no unmeasured runtime, tile, or quality credit is admissible.
- Terminal `FULL47_RANK_CLOSE`; no CUDA, provider, checkpoint, or quality work occurred. Artifact: `artifacts/FULL47_RANK_CLOSE_2026-07-16.json`.
