# Research log

## 2026-07-25 — launched final-tail overlap candidate

Question: whether releasing the final c12 at 718.921467264 seconds while wave 31 remains active crosses the $0.14/M boundary.

Action: reserved the admitted $3, mechanically verified binding SHA-256 `7c220386416a91e1822e772cb02c7434b13f09b693192e21f36219d92169a443` and all four evidence hashes, materialized hash-bound inputs locally, then started durable controller `OWNER_STATE.json` (pid 266097) which atomically claimed the retained H200. The remote packet preflight completed and the controller heartbeat is live.

Evidence: `BINDING_VERIFIED.json`, `artifacts/tail-overlap-20260725t020427z/REMOTE_PACKET_PREFLIGHT.json`, and `OWNER_HEARTBEAT.json`.

Interpretation: the sole unconsumed candidate trajectory is now running under the existing watchdog. The controller will retrieve terminal evidence, calculate conservative actual spend, and release the bench; do not replay this arm.

## 2026-07-25 — recoverable launch defect and pool boundary

Question: continue the admitted tail-overlap trajectory without replaying any scientific sample.

Action: retrieved the failed worker archive. It failed before `science_started` because the warm-up passed string `"warmup"` into the request-index arithmetic. The remote terminal explicitly records `candidate_science_consumed: false`; the server container remained running. Patched the local packet to leave warm-up unindexed and reuse that healthy resident server, then launched a fresh durable controller.

Evidence: `artifacts/tail-overlap-20260725t020427z/out/ATTEMPT_TERMINAL.json` and `OWNER.log` contain the full `TypeError`; `artifacts/tail-overlap-20260725t020733z/claim.stderr` records the retry boundary. The second controller could not claim because the first owner had released the bench to `maintenance`; pool returned `no available GPU bench matches this project`.

Interpretation and next move: this is not scientific evidence and no candidate trajectory was consumed. Director intervention is required to make `h200-ngram-verifier-e00kcm9nfhwt7e7gbc` claimable while preserving the resident `gemma4-ngram-tail-overlap` container; then the already-patched controller can run the one permitted trajectory.

## 2026-07-25 — admitted resident-server retry launched

Action: consumed `DIRECTOR_REPAIR.json`, retained binding SHA-256 `7c220386416a91e1822e772cb02c7434b13f09b693192e21f36219d92169a443`, replaced the warm-up index with deterministic integer sentinel `0`, and proved body construction in `WARMUP_BODY_PROOF.json`. Durable owner `OWNER_STATE.json` (pid 273681) atomically claimed the returned H200; its heartbeat and packet preflight are current.

Interpretation: the controller is now verifying the bound resident model and running the sole unconsumed final-tail-overlap trajectory without Docker run, reload, or removal. It will retrieve the terminal and release by 02:50Z.

## 2026-07-25 — measured terminal: reject final-tail overlap

Action: retrieved the complete candidate terminal and all 1,036 request rows. The candidate is consumed; no replay is admissible.

Evidence: terminal `artifacts/tail-overlap-20260725t021502z/out/FINAL_TERMINAL.json` SHA-256 `ea83796c0ad6f5e366fc42b910db81a96f16ead3db921c830d0cfef91358f3b5`. All requests completed with zero failures and normalized semantic equality. The tail was released 0.000089785 seconds from its planned arrival while wave 31 was active, and the final server queue was zero. Full-wave drift did not grow.

Interpretation: reject this exact scheduling geometry. It reached 734.979990111 seconds and `$0.140084601/M`, above the `$0.14/M` gate, while observed transient server queue depth reached 30, above the bound of 12. Conservative cumulative provider exposure is `$0.600890179`, within the `$3` reservation. The healthy container was retained and bench released to maintenance for director disposition.
