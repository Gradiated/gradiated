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
