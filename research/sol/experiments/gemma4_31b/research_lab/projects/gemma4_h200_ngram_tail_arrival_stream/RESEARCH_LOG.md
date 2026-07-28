# Research log

## 2026-07-25 — streamed-tail execution launched

Question: can individual bound arrivals for requests 1024–1035 close the remaining `$0.14/M` economic gap without changing the resident NGRAM server or waves 0–31?

Action: durably reserved `$3`; verified `DIRECTOR_BINDING.json` SHA-256 `b1934d88f5ea3e13944c1a26db3f59734096300380bc97311afc30f10cdcf7b2` and all four bound evidence hashes; materialized the input packet locally; then started controller `OWNER_STATE.json` (pid `286612`) to atomically claim `h200-ngram-verifier-e00kcm9nfhwt7e7gbc` and execute exactly one candidate trajectory.

Evidence: the controller is live, and the pool records its claim and initial heartbeat at `2026-07-25T02:39:25Z`. The controller will preserve the healthy resident server, collect normalized-comparator, telemetry, reliability, and economic artifacts, then retrieve a typed terminal before releasing the bench.

Interpretation: this is the sole unconsumed streamed-tail sample. No settled arm is being replayed.

## 2026-07-25 — measured terminal; geometry closed

Action: the controller reused the resident `gemma4-ngram-tail-overlap` container without Docker reload, completed the sole 1,036-request candidate, retrieved the verified compact terminal, recorded conservative provider exposure of `$0.5532576239053587`, and released the still-healthy loaded server to maintenance.

Evidence: [FINAL_TERMINAL.json](artifacts/streamed-tail-20260725t023925z/out/FINAL_TERMINAL.json) SHA-256 `8c92c806ff758fc9b6bc3f75ce6b2d3f3b8ac4cbcaf0b7d096fefc8cdd2c7b73` records 1,036 completed requests and zero transport failures, but exactly one normalized semantic mismatch (first at request 32), peak server queue 41, elapsed `776.618343545` seconds, and `$0.14802072510509962/M`. The 12 tail releases were individual, in index order 1024–1035, and within `0.000097787` seconds of their planned arrivals. The archive SHA-256 is `06c6a3faf3d497d79f1b2a64d3f544fce0b4f3b26a6abf5db70ae34095aa41`.

Interpretation: reject and close this exact client scheduling geometry. The completed result is decision-bearing; no replay or post-hoc repair is admissible.
