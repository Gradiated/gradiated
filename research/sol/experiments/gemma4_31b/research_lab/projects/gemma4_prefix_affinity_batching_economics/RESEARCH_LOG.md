# Research log

## 2026-07-27 — director admission

Admitted one zero-GPU cache-affinity scheduling discriminator against the exact
content-addressed c32 workload. No result exists yet.

## 2026-07-27 — exact identity and policy terminal

- Question: can bounded prefix-affinity admission and replica routing expose
  prompt reuse beyond FIFO in the exact qualified c32 workload?
- Action: reconstructed all 32 token-ID requests from the bound exact runner,
  verified every request hash against the authoritative workload, implemented
  one 50 ms bounded affinity policy and its FIFO comparator, and replayed the
  qualified completion trace at identical offered work.
- Evidence: `PREFIX_AFFINITY_BATCHING_OFFLINE_TERMINAL.json` (SHA-256
  `9c074b1b482ab55b1c2814fc3d98e86ecbf7efc42bde5323e8144aa3d1f4f9bb`).
  All prompts share exactly 535 tokens and have 32 distinct tokens at the next
  position. The qualified cache already realizes the warm-state oracle:
  17,120 cached and 117,728 fresh prompt tokens. Affinity and FIFO therefore
  have zero incremental hits, identical order, occupancy 1.0, zero realized
  wait, and identical p50/p95 completion of 18.501630/19.921629 seconds. The
  portable worst-case queue bound is 541,504 bytes; extra KV storage is zero.
- Interpretation: typed negative. Even the oracle cost reduction is 0%; a
  nonzero bounded wait can only worsen the 0.625149101968745 s/request
  denominator (50 ms worst-case batch delay gives 0.626711601968745 at c32).
  No finite within-window arrival/reuse rate breaks even.
- Next: close this policy and redirect the independent lane. Exact-runtime
  consumer is typed `none`; no GPU/provider/SSH/checkpoint operation occurred.
