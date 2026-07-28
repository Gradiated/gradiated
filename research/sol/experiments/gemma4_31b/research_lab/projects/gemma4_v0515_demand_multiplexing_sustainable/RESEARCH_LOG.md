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

## 2026-07-25 — stock multiplexing execution dispatched

Question: does the admitted official v0.5.15 stock (no-NGRAM, no-speculation)
two-stream geometry improve service time beyond measured timing noise while
preserving the bound request and semantic invariants?

Action: mechanically verified the director binding and six bound evidence
digests; generated `stock_packet/` (manifest SHA-256
`bb0cb24d390ab3ab619300045b7ad364468fdd2210e60b7067a916e3bf1bd9d1`) whose
launch argument list contains neither NGRAM nor speculative flags, and packed
the exact manifest members (`artifacts/stock_packet.tar`, SHA-256
`7ee71e84d1f1b9157f58543720f1adc236d81a9486208814e2769cc416597380`). Claimed
the retained H200 and dispatched durable local owner PID 518373 (start ticks
108231360) through `detached-owner`; its absolute state file and 08:25Z fence
are in `STATUS.json.active_session`.

Evidence: the owner staged hash-verified packet and worker bytes, stopped only
containers named `gemma4-ngram*`, and recorded remote phase
`stock_identity_and_launch`. The next persisted phase is the 139-request
control/candidate discriminator. The owner heartbeats, retrieves raw output,
computes the paired service-time delta and 95% noise bound, runs the 759-request
endpoint only if every discriminator gate passes, records actual spend, and
releases the H200 by the binding fence.

Repair: the first remote worker stopped before candidate CUDA or request
submission because the manifest archive was extracted at the remote root while
the worker correctly required `stock_packet/STOCK_LAUNCH.json`. `WORKER.log`,
`INVOCATION_STATE.json`, and Docker inspection proved no stock container had
started. Preserved this invalid integration artifact, opened and requested the
hash-bound repair handshake, extracted the already-verified archive under
`stock_packet/`, and restarted only the remote worker in the same claimed
session. The repaired worker has persisted `science_started=true`, phase
`stock_139_control_and_candidate`, and stock container
`gemma4-stock-multiplex` is running. No scientific sample was replayed.

## 2026-07-25 — retrieval-only terminal

Action: verified `DIRECTOR_STOCK_RETRIEVAL_BINDING.json` plus its failed-owner,
container-id, and invocation-state hashes; claimed the retained H200 only to
retrieve the existing remote invocation. No container, server, discriminator,
or endpoint was launched or modified.

Evidence: `artifacts/stock-retrieval-20260725t083312z/` contains the container
inspect/logs, invocation marker, and worker logs. The sole worker error is a
missing `stock_packet/PACKET_ID.json` during packet validation, before it could
construct request bodies, submit `/generate`, or persist request rows. No
scientific terminal exists. The director's conservative consumed status is
preserved; the conditional endpoint was not started.

Interpretation: typed incomplete remote runner/manifest boundary, not an
acceptance or rejection result. Conservative project exposure through this
retrieval release is $1.49, within the $4.00 ceiling. The loaded stock server
is released to maintenance for director disposition.

## 2026-07-25 — packet-ID repair dispatch

Action: verified `DIRECTOR_STOCK_PACKET_ID_REPAIR_BINDING.json`; created an
archive-only manifest that declares the immutable existing `PACKET_ID.json`
plus all original members. `manifest-pack` built
`artifacts/packet-id-repair/stock_packet_complete.tar` (SHA-256
`6481ff8ba2353ab1ffd33d6caf5c1eb92113ae4401fd26a164ec5c404c9d1fe9`). The
complete packet validates and the otherwise identical missing-ID fixture fails
closed before claim.

Dispatch: claimed the retained H200 and started durable owner PID 554828,
start ticks 108490102, with the 09:25Z release fence recorded in
`STATUS.json.active_session`. The remote worker performs a pre-science packet
validation before recording the first-request marker, then runs the admitted
139-request discriminator once; the endpoint remains strictly conditional.
