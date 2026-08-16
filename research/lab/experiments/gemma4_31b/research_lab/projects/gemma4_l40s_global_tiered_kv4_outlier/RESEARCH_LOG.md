# Research log

## 2026-07-27T06:52Z — fixed D512 mixed tier passes offline, fit remains negative

- Question: can the exact c32 D512 global cache keep 1,024 E5M2 tokens and
  compact older history as G64 signed KV4 plus eight E5M2 residuals while
  preserving one paged online-softmax consumer?
- Action: implemented the deterministic producer, high-precision CPU oracle,
  compact canonical-page directories, one source-complete SM89 producer and
  mixed-tier consumer, and a current-SGLang E5M2 component comparator. Ran
  seven focused checks and one fresh checkpoint-free D512 full-history
  experiment. No GPU, CUDA, provider, endpoint, shard, training, sweep, or
  D256 numerical evidence was used; spend is `$0`.
- Evidence: at positions `4,214` and `4,571`, corrected relative L2 is
  `0.0230824` and `0.0228473`; cosine is `0.9997398` and `0.9997478`.
  The latter consumes 357 rows packed from their retained E5M2 bytes. All
  outputs are finite; 1,023/1,024/1,025 transitions, empty-old, padded rows,
  deterministic outlier order/uniqueness, and request ownership pass.
  Exact global allocation falls from `5,312,020,480` to `3,722,669,724`
  bytes, saving `1,589,350,756` bytes (29.92%) and reducing the inherited
  lower fit deficit by 39.56%.
- Interpretation: the fixed representation passes the offline discriminator
  and has a real later SM89 command against pinned
  `decode_attention_fwd`. It does not make the complete endpoint fit:
  the conservative complete requirement is
  `50,733,917,648..51,701,421,224` bytes versus `48,305,799,168`, leaving
  `2,428,118,480..3,395,622,056` bytes unresolved. Registers, spills,
  occupancy, and producer-plus-consumer latency remain unmeasured.
- Next: preserve the offline pass for a later director-admitted shared-L40S
  component run, but require another allocator/residency mechanism before
  any endpoint-fit or production claim.

Artifacts:

- `L40S_GLOBAL_TIERED_KV4_OUTLIER_OFFLINE_TERMINAL.json`
- `artifacts/OFFLINE_NUMERICAL.json`
