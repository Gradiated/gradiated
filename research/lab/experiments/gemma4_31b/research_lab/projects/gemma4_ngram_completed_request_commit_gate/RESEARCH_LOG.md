# Research log

## 2026-07-25 — exact lifecycle gate passed; H200 held in maintenance

Question: can target-verified NGRAM writes remain request-private until an
exact completion boundary, then commit once through the unchanged global trie?

Action: mechanically verified and materialized the director binding plus the
pinned SGLang lifecycle sources. Implemented a buffer capped by 32 active
requests and each request's `max_new_tokens`, with exact normal completion,
abort, request-ID generation reuse, scheduler-prefix abort, exception, and
cache-reset cleanup. Reproduced the bound native-trie scenarios and exercised
the same project-local trie consumer. Preserved one invalid comparator attempt
before correcting only its unrelated persistent-alternate expectation.

Evidence: `artifacts/offline-lifecycle-probe/RESULT.json` is a measured offline
pass. A historical common trunk retains 11 accepted drafts while request 32 is
live; abort and ID reuse commit zero rows; one normal request commits 358 rows
exactly once. The exact post-completion request-32 commit then reproduces the
bound dominant-depth collapse from 11 to 4.

Interpretation: lifecycle ownership and the bounded intervention are valid,
but the post-completion depth-4 result predicts that temporal isolation may be
too short-lived. The preregistered 791-request discriminator remains required;
no GPU sample was consumed.

Next: the priority-8550 predecessor has released, but the compatible retained
H200 is in `maintenance` with a healthy support-two server and no live claim.
The atomic claim failed with the typed pool boundary in
`artifacts/gpu-claim-20260725t0455z/CLAIM_TERMINAL.json`. Director disposition
must mark that bench available; then transfer only `EXECUTION_BINDING.json`
bytes, replace the overlay in place, run one 791-request discriminator, and
run the 1,036-request endpoint only if every PROJECT.md gate passes.

## 2026-07-25 — admitted H200 discriminator launched

Action: reverified `EXECUTION_BINDING.json` and the project-local immutable
inputs, then atomically claimed the returned retained H200 at 05:03:58Z. A
durable controller is staging the hash-bound completed-request overlay,
reloading only the resident container overlay, and running the one permitted
791-request discriminator. Its absolute deadline is 06:00Z.

Evidence: controller identity and claim are recorded in `STATUS.json` under
`active_session` and `artifacts/controller/OWNER_STATE.json`; the pool shows
the claim owned by this project. No candidate terminal existed at the grouped
post-launch snapshot, so no sample outcome is inferred yet.

## 2026-07-25 — valid discriminator rejects completed-request commit

Question: does withholding each live request's target-verified NGRAM writes
until completion preserve exact behavior while protecting peer trunks?

Action: the durable owner staged the project-local immutable packet, installed
overlay SHA-256 `4a36686ac953cb3a7b5d0a9c21fddfef34b6b8493b1bea176f46e6e55f528019`,
proved worker activation, ran the single 791-request discriminator, retrieved
its compact archive, and released the bench to maintenance.

Evidence (measured): all 791 requests completed with zero failures, individual
bound-arrival releases, peak queue 20, and final queue zero. The candidate
nevertheless diverged from the normalized semantic rows (first divergent
request: 78), retained only median/p10 accepted depth 4 after request 32
instead of the required 10/8, and measured `$0.143793/M`, above `$0.14/M`.
Activation identity passed and 2,692 overlay trace rows persisted. The complete
terminal is `artifacts/completed-request-20260725t050358z/out-discriminator-0-790-completed-request-20260725t050358z/FINAL_TERMINAL.json`.

Interpretation: a temporal write barrier removes live contamination but merely
defers the harmful corpus mutation until completion; it neither preserves exact
semantics nor prevents the sustained long-trunk collapse. This is a valid
consumed rejection, not a harness defect. The 1,036-request endpoint was not
admitted, and this candidate must not be replayed without new director
authorization.
