# Research log

## 2026-07-24 — fixed wave-admission execution in progress

Question: can the bound 1,036-request background trace be admitted as 32
consecutive 32-request NGRAM waves plus its 12-request tail without
cross-wave backlog?

Action: verified every `DIRECTOR_BINDING.json` input, materialized the bound
launch, request rows, and trace under `inputs/bound`, claimed the retained H200
once, removed only the state-aging container, and launched the hash-bound stock
runtime through the shared detached owner. The live owner and compact artifacts
are at `artifacts/wave-admission-20260724t152911z`.

Repairs: a packet-root lookup and then an invalid synthetic warmup token caused
pre-science failures. Both attempts wrote compact diagnostics with
`science_started: false`; the repaired third worker entered
`wave_admission_primary` at 15:36Z. It is the only consumed scientific arm.

Next: retrieve the one terminal, assess exact response/usage, wave-release
drift, completion latency, final queue, and $3.25/H200-hour planning cost; set
the final actual provider exposure before the terminal status.

## 2026-07-24T15:55:40.819511+00:00 — terminal recovered

Retrieved the one consumed terminal through PID-managed adoption; no replay. All 1,036 requests completed, but wave policy did not meet the preregistered acceptance decision. Conservative retained-H200 exposure: $1.106620. Artifacts: `artifacts/wave-adoption-20260724t155535z`.

Evidence: all 1,036 usages matched the bound control and no requests failed.
However, wave 32 (the 12-request tail) released `9.306848 s` after its planned
release—well beyond the permitted `0.694610 s` arrival spacing—and total
planning cost was `$0.140122/M`, just above the `$0.14/M` gate. The server's
final queue metric was zero, so the terminal's client-tail-delay field is not
needed to reject the policy. Raw wire hashes differed in all rows; this is a
non-decision comparator observation because the bound output-ID control was
not persisted, while the tail release miss and cost independently close the
fixed policy. The stock container was removed and the bench released ready.
