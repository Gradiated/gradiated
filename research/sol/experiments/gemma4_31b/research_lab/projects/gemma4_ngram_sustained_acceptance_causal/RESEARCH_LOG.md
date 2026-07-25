# Research log

## 2026-07-25 — source-bound causal result

Decision: promote one candidate, `request_local_verified_trunk`, to a single
candidate-only endpoint arm. Do not replay threshold-8 bypass, built-in
frequency mode, global breadth-one, or a settled scheduler/source arm.

Measured evidence:

- The hash-bound c32 tail terminal ended at speculative acceptance length
  `5.0`, rate `0.363636`, peak queue `41`, and elapsed time `776.618 s`.
  Request 32 is the sole semantic divergence: after 289 dominant tokens it
  emits the three-token transient `25627, 1767, 1154`, then returns to the
  dominant token. The first later low-acceptance observation is length
  `5.1887` with 32 running requests.
- The independent state-aging run has one divergence, request 790, which
  switches from the dominant token to token `3055`; acceptance falls at the
  same time despite a prior corpus reset. Its trie stayed small, closing
  capacity/aging as the primary cause.
- An exact C++ probe compiled against pinned SGLang commit
  `28b095c01005d4a3a2a5b637b7d028b07fba31b2` reproduces four accepted drafts
  after the request-32 transient. Four drafts plus the verifier bonus exactly
  predicts the measured length `5.0`.
- Built-in frequency mode also accepts four drafts in the transient and
  persistent-alternate probes. Global max-breadth-one restores eleven after
  the transient but accepts zero when the persistent alternate is newest.
  Both global policies are rejected.

Interpretation: `NGRAMWorker._update_ngram_corpus` mixes every request's last
18 target-accepted tokens into one online trie. `Trie::buildRecency` gives
recent children fixed breadth entitlement without request ownership or a
support gate. One rare request therefore displaces the dominant continuation
for its peers. At c32, the fixed 12-row verifier magnifies length 5 versus 12
from approximately `29.83` to `71.60` target rounds per 358-token completion.
Every round traverses Gemma's 60 layers (50 local, 10 global) and the
262144-way LM head, explaining the growing service span and queue.

Candidate: retain a bounded per-request trie of only target-verified tokens.
Reserve its longest verified continuation as that request's next draft trunk,
then fill unused rows from the unchanged global recency tree. Keep depth 12
and the target verifier unchanged; fall back globally until a local
continuation exists, and erase local state through the existing finished-rid
cleanup. This differs materially from threshold bypass: no request leaves
NGRAM and all draft tokens remain target-verified.

Predicted counter change: unaffected requests remain near 11 accepted drafts
after the first rare branch; target verification rounds and rows per
completion fall by up to 58.3%, with fewer KV slot allocations and rejected
slot frees. The endpoint should peak below queue 30, drain to zero without
growing release drift, preserve 1036/1036 normalized semantics, and cost at
most `$0.14/M`.

Endpoint: exactly one candidate-only 1036-request full-arrival trajectory,
releasing every request at its bound `arrival_s`. Apply only the hash-bound
request-local verified-trunk overlay and retain the pinned image, model,
launch, c32, depth 12, and global BFS fallback. Persist per-request acceptance
around the first rare-output insertion, target forward/row counts, KV
allocation/free counts, peak/final queue, release drift, elapsed time, cost,
failures, and normalized semantic equality. No control replay.

Artifacts:

- `artifacts/causal-source-probe/RESULT.json` — causal chain, exact geometry,
  bound identities, source probes, and predictions.
- `artifacts/causal-source-probe/CANDIDATE_ARM.json` — minimal candidate-only
  endpoint contract.
- `artifacts/causal-source-probe/probe.jsonl` — exact C++ probe rows.
- `run_causal_analysis.py` and `ngram_tree_probe.cpp` — reproducible local
  analysis.

No GPU bench was claimed and no provider mutation occurred. Actual spend is
`$0.00`.
