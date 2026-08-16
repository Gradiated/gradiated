# Research log

## 2026-07-28T08:53Z — fixed c48 closes on static capacity

- Question: can the exact dual-KV representation admit the fixed c48 workload
  on one L40S at the immutable 0.953 split, with a pinned-runtime and
  price-normalized later discriminator?
- Action: reconstructed c32 byte-for-byte, scaled only ownership-bound arenas
  to c48, enclosed all request/graph/scratch allocations once in the 0.047
  reserve, traced scheduler/request-pool/decode-graph ownership at pinned
  SGLang `c6a6200`, and regenerated locked c32/c48 request identities.
- Evidence: c48 static lower/upper are `49,075,971,484..50,043,475,060`
  bytes versus the `46,035,426,607`-byte static limit. The favorable lower
  bound is already `770,172,316` bytes larger than physical HBM before the
  dynamic reserve. Generic SGLang can schedule and graph an exact 48 bucket,
  but the dual-KV composition is c32-hard-bound and no CLI flag resizes its
  arenas. At the current `$1.10/GPU-hour` committed planning rate, a
  hypothetical c48 batch would require `B48 <= 70.9260072052 s`, equivalently
  `B48/48 <= 1.47762515011 s/request`.
- Interpretation: typed none for fixed-c48 saturation. Memory fit fails before
  runtime composition or timing can matter; no GPU command is admissible.
  This does not close dual-KV c32 or other capacity geometries.
- Artifact:
  `L40S_DUAL_KV4_C48_SATURATION_OFFLINE_TERMINAL.json`
  (`9f55a511e3945a74c3ad1b984cce85e7721bb35d32914973c0ba7f765ca04e19`).
