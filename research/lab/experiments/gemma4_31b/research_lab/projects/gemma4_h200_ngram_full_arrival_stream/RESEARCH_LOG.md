## 2026-07-25 — full individual-arrival trajectory (measured)

Question: can releasing every request at its bound `arrival_s` retain the
depth-12 NGRAM stream under `$0.14/M`?

Action: ran the sole candidate-only 1,036-request trajectory against the
verified resident SGLang server, using the project-local immutable comparator
snapshot. The durable owner retrieved terminal and compact artifacts, then
released the occupied server to maintenance.

Evidence (measured): [`FINAL_TERMINAL.json`](artifacts/full-arrival-20260725t030310z/out/FINAL_TERMINAL.json)
(`cc24f1c62ab1cdc4c7c49d80df94dddd535c4254be266b5467fd1eafc987f2d8`)
records 1,036/1,036 normalized semantic matches, zero failures, 12 peak queued
requests, zero final queue, and no growing release drift. It took
`764.136148123 s` for `4,736,592` tokens, or `$0.145641663/M`; 376 telemetry
samples and all request rows were retrieved in compact artifact
`7b146e527ec4e67572b9dbcbeec44019f585ecdf41303e082148b8c7a0459e4b`.

Interpretation: individual arrivals remove the queue/reliability failure mode,
but do not meet the economic gate (29.600034892 s / 4.03% over the
734.536113231 s threshold). This scheduling geometry is a settled economic
reject; do not replay it. Conservative provider exposure is `$0.5318295255`.
