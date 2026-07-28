# Research log

## 2026-07-25 — offline support-two gate passed

Question: can distinct-request support-two write admission preserve the native
global NGRAM tree while quarantining the measured request-32 and request-790
branches?

Action: materialized the source, causal result, requests, exact semantic rows,
launch, and required request template bytes project-locally; implemented a
16,384-entry deterministic-FIFO probation gate keyed by exact packed token
suffix bytes; changed only `_update_ngram_corpus` write admission and reset
cleanup. Reproduced the bound C++ source scenarios and ran the candidate
through the same pinned trie consumer.

Evidence: `artifacts/offline-source-probe/RESULT.json` is a measured offline
pass. The bound probe reproduced accepted-draft depths 11, 4, 2, and 4. With
support two, the common path retained depth 11, while request-32's transient
and five repeated request-790 persistent branches left alternate depth 0 and
dominant depth 11. A capacity-2 behavioral probe proved deterministic
eviction, clear-to-zero, and no one-request self-promotion. The first probe
attempt contained an invalid post-eviction assertion and is preserved in
`INVALID_ATTEMPT.json`; correcting only that assertion produced the pass.

Interpretation: the offline causal prediction holds and admits the one
candidate-only 791-request GPU discriminator. This is not an endpoint claim.

Next: wait behind the live priority-8600 controller, atomically claim its
released H200, run the bound discriminator, and run the full endpoint only if
activation, exact semantics, zero failures, and the preregistered post-790
long-trunk gate pass.

## 2026-07-25 — measured support-two discriminator: semantic reject

Question: does support-two, distinct-request write promotion retain long
unaffected NGRAM trunks while preserving the exact request semantics?

Action: the durable owner in `artifacts/controller/OWNER_STATE.json` claimed
the released retained H200, activated overlay
`9fdd5227380c922e921be1b32e77716254f496219ddb9672e1b47bc6b4595e94`, ran
the one admitted 791-request discriminator, retrieved the compact terminal,
and released the loaded server to maintenance.

Evidence: `artifacts/distinct-request-20260725t043053z/out-discriminator-0-790-a0-distinct-request-20260725t043053z/FINAL_TERMINAL.json`
(SHA-256 `fd6bbba8d0015e7e3cac694aa4ebadd1569456ba9363c9dd58036f7a13e7adb1`)
records 8,604 overlay trace rows and positive activation identity. All 791
requests completed with zero failures; queue peak and final queue were 0;
post-790 unaffected requests had median and p10 accepted drafts of 11; and
the planning cost was $0.139315964/M. Its normalized-semantics decision is
false, however. This is a complete candidate sample, not an activation,
retrieval, or ordinary harness failure.

Interpretation: the exact semantic gate rejects this intervention. The
conditional 1,036-request endpoint is not admitted, and neither scientific
arm may be replayed. Conservative cumulative provider exposure is
$0.41334839026658643, below the $3 reservation.
