# Research log

## 2026-07-25 — analytical geometry passes; dependency closes production packet

Question: can independent production demand remove the v0.5.15 B200
single-stream arrival floor without compressing a tenant clock, duplicating a
request, or gaining from unrepresentative process-global NGRAM state?

Action: mechanically verified every `DIRECTOR_BINDING.json` digest; rebuilt
the 791-request and post-calibration 759-request economics from bound arrivals,
semantic token counts, and the fresh shared H200/H100/B200 planning rates;
traced the exact v0.5.15 scheduler, CUDA-graph, queue metric, worker, Python
corpus wrapper, and C++ BFS trie at commit
`f63458b5beaceabbd9d749b9fc956370e1b649e6`. Constructed two disjoint scored
views: source requests `32..411` at phase zero and `412..790` at a
`0.347305056649303`-second phase, each preserving its own bound arrival
offsets. Requests `0..31` are an exact calibration prefix and must complete
with queue zero before the scored epoch.

Evidence:

- `BINDING_VERIFIED.json` is a complete digest pass.
- `ARRIVAL_ECONOMICS.json` derives a single-stream scored span of
  `526.514465880342926` seconds and a multiplexed span of
  `263.257232940171476` seconds: effectively `2.0x`, above the
  `1.7227397374x` gate. On B200, the analytical 90%-sustainable
  zero-latency arrival floor falls to `$0.12058534587085345/M`; the allowed
  elapsed ceiling remains `305.6425500582524` seconds, leaving
  `42.38531711808093` seconds for the completion tail.
- The bound bodies are unique across all 759 scored requests. Their only
  prompt mutation is position 535, while all last-18 prompt tails and all
  frozen 358-token completions are identical; the completion token is always
  `51935`.
- The executed official C++ corpus probe, binary SHA-256
  `68d38cefbc15361dc3af9935bb928c8aaf0c5b99dfe37616dbc038632efe2603`,
  compared isolated and shared two-stream BFS proposal tensors over all 358
  completion states after calibration and returned exact. This is measured
  component evidence; the scheduler/corpus interpretation in
  `SCHEDULER_CORPUS_CAUSAL_MAP.json` is source-backed, and multiplexed
  endpoint economics remain analytical.
- While this project was active, the scope-matched official unmodified
  v0.5.15 first-791-request H200 endpoint closed. Terminal SHA-256
  `7e6ba230931ccf0db83917ae0797e89c4fe983d6f53923fa1fcb84e744893367`
  records `normalized_semantics_exact=false`, first divergence at request 217
  output token 19, elapsed `575.8700554510033` seconds, queue peak 14/final
  zero, and `$0.14375489815676315/M`.
- The rejected analytical geometry is retained as
  `sha256:beb392e8ee3024c56c78cad50ced5f5d20616748ff478ce02cb86da68aa00939`.
  Its manifest covers immutable inputs, exact geometry, evidence, dependency
  terminal, and the unadmitted discriminator runner.

Interpretation: typed `none`. Exact-copy streams remain forbidden because the
process has one online trie and BFS duplicate inserts refresh LRU state. The
disjoint post-calibration geometry avoids that bias and reaches the economic
density requirement, but it is not production-valid: the newly closed
scope-matched official endpoint fails its exact semantic invariant. Different
batching might change that trajectory, but this zero-GPU project cannot assert
that it restores semantics. The offline geometry is rejected evidence, not a
readiness substitute or throughput claim.

Invalid harness attempts: the first builder pass stopped before science on a
missing packet control directory; the first corpus compile used C++17 although
the pinned source requires C++20. After the repaired probe completed and
persisted, a price-inventory list/map parser mismatch stopped only the
consumer. The parser was repaired and the persisted probe was reused without
replaying that producer.

Next: no GPU action is admitted. Reopen only if a content-bound official full
trajectory with exact normalized semantics supersedes the dependency reject,
or a new director binding admits a runtime semantic repair plus a
scope-matched multiplex discriminator. Never replay the consumed H200
endpoint.
