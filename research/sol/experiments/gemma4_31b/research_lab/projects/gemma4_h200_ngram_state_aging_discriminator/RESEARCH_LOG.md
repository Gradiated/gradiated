# Research log

## 2026-07-24 — bounded corpus lifetime falsified

Question: did the process-global NGRAM corpus cause the sharp fixed-rate
service transition after request 700?

Action: hash-checked every `DIRECTOR_BINDING.json` input, materialized the
control and source bytes locally, and froze one intervention before claiming
the retained H200: reset only the online `NgramCorpus` at 650 distinct primary
admissions. The arm kept prefix/SWA/KV state, launch settings, 1,036-request
schedule, and arrival rate unchanged. A read-only C++ probe exposed trie
occupancy and match state; Python instrumentation timed `synchronize`,
`batch_get`, `batch_put`, target forward, cache occupancy, HBM, and power.

Measured evidence: before reset the trie held only `552/10,000,000` nodes
(`0.00552%`), unchanged from request 100 through 648. The reset took
`14.669 ms`. Across 8,483 prepares, cumulative corpus time was `47.443 ms`
for synchronize, `915.819 ms` for batch-get, and `360.563 ms` for batch-put;
maximum synchronize was `3.331 ms`. Despite rollover, latency reproduced the
stock phase change: requests 700–799 averaged `3.116 s`, 800–899 averaged
`21.927 s`, and 900–999 averaged `23.247 s`. All `1,036/1,036` requests
completed, but final client queue was `6.432 s`, failing the `0.694610 s`
gate. HBM grew `5,250 MiB`; its first material step was near request 809 with
14 running requests, SWA availability 737 tokens, and 3.35M cumulative
evictions. The finite-run rate was `6,499.23 tokens/s` and `$0.138905/M`
at the planning rate, but remained unsustainable.

Interpretation: reject the bounded corpus lifetime and close corpus aging as
the cause. The trie never approached capacity, corpus operations were too
small to explain the phase change, and resetting it did not move the
transition. The next discriminator should target occupancy-dependent
SWA/KV/allocator or batch-topology behavior.

Comparator note: candidate token IDs, finish reasons, and usage were retained,
but the persisted stock rows contain only whole raw-response hashes. Both
launchers also shallow-copy a shared prompt list and hash the mutable object
after submission; the candidate additionally used compact JSON. The recorded
request/response hashes are therefore not an exact cross-run semantic
comparator. This prevents accepting the intervention but does not weaken the
negative timing/state result, which already fails the service gate. The
consumed arm was not replayed; `COMPARATOR_REPAIR.json` records the defect.

Lifecycle: the first local owner invocation hit an inventory-shape parser
defect immediately after the idempotent claim and before SSH or science; it was
repaired under the same claim. After the valid terminal was retrieved, release
hit an inline-JSON/path CLI defect; only that lifecycle call was repaired. The
bench was released to maintenance at `15:10:45Z` with the healthy instrumented
container retained on port 30000. Cumulative assigned exposure was
`975.247 s`, conservatively `$0.666419` at `$2.46/H200-hour`.

Artifacts: `RESULT_ANALYSIS.json`, `COMPARATOR_REPAIR.json`, and
`artifacts/state-aging-20260724t145451z/`.
