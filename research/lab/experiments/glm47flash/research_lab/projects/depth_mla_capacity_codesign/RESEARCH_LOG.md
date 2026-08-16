# Research log — depth plus MLA capacity co-design

## 2026-07-15 — Zero-cost rank/c32 admission screen

Question: can a source-supported MLA rank reduction make the materialized 39-layer AWQ student robustly c32-admissible on L40S while retaining an economic path?

Action: ran [`depth_mla_c32_fixture.py`](depth_mla_c32_fixture.py) against the content-addressed student config, index, and safetensors headers. It bound the layer-0 BF16 and 38 group-32 W4 `kv_a_proj_with_mqa`/`kv_b_proj` shapes, then derived ranks 448/384/320/256. The pinned vLLM v0.15.0 source (SHA-256 `6a984f…56b4a9`) reads `config.kv_lora_rank` and passes it to MLA attention; no checkpoint was written or loaded.

Evidence: ranks 448, 384, and 320 leave only 25 MiB, 1,273 MiB, and 2,521 MiB of c32 headroom respectively, so all fail the 3-GiB rule before relying on allocator savings. Rank 256 saves 4,992 MiB of c32 KV state across 39 layers and leaves 3,769 MiB (3.68 GiB) without weight-allocation credit; exact sliced projection payload would additionally remove 62.82 MiB. Its group-32 W4 shapes are `[320,256]`/`[320,64]` for KV-A packed/scales and `[8960,32]`/`[8960,8]` for KV-B, alongside layer-0 BF16 `[320,2048]` and `[8960,256]`. The retained calibrated rank-256 `BLOCK_N=64`, stage-2 envelope is 93,440 B, below the L40S 101,376-B block limit, but compilation is still unmeasured.

Interpretation: nominate rank 256 only as a conditional later c32 arm. The student fixed-cost bound is 631.312 tok/s, so the c32 result must retain at least 94.16% of that bound (no more than 5.84% regression) to clear 594.466 tok/s. This fixture establishes capacity and a static loader/tensor representation, not endpoint throughput, successful runtime loading, recovery, or quality.

Next move: only if scheduled, materialize a content-addressed group-32 W4 rank-256 rewrite, static-load it on the pinned image, then measure c32 memory/throughput and recovery quality in one bounded arm. Artifact: [`DEPTH_MLA_C32_BOUND.json`](DEPTH_MLA_C32_BOUND.json).
