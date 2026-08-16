# Decision — 2026-07-17

Retain c16/c32 with one ranked direct falsifier: an exact-revision W4 c16 endpoint run with raw quality capture and queue/service telemetry.

The measured pinned L40S head rows replace the prior head proxy. At the primary 4,214-token workload, the derived batch cycles are 8.391 s (c8), 8.415 s (c16), and 8.560 s (c32). c16 and c32 retain 0.337 s and 0.596 s/request against the conservative 0.86329 s envelope; c8 is short by 0.186 s/request. At 10K input, c16 retains 0.286 s and c32 0.570 s, while c32 has only 0.613 GiB logical headroom and is allocator-sensitive.

At the $1.10/hour planning rate, conditional costs are $0.000232/request (c16) and $0.000118/request (c32), below the $0.000614–$0.000727 market hurdles. These are analytical W4 surfaces, not endpoint results. The exact-revision checkpoint, quality, non-head decoder timing, and allocator behavior remain unmeasured.

The direct falsifier is c16 because it has useful conservative residual and materially safer 10K capacity than c32. It must use a pinned exact-revision producer/consumer and the real raw-capture quality scorer. The previously tested tied one-byte shared consumer remains terminal `NONE`; this decision does not reopen that lineage. No provider action follows automatically.
