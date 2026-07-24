# Research log

## 2026-07-24 — admitted from the final native-NGRAM token trace

Hypothesis: disable speculation only for grammar-constrained/tool requests,
where unchanged native NGRAM produced the sole measured token divergence, and
retain NGRAM for the campaign's no-grammar completion workload.

Evidence: unchanged NGRAM measured `0.5967508053` versus `0.7022385985
s/request`. The final ten-row server-boundary comparison found nine exact rows.
The single-tool control generated 24 compact-JSON tokens while NGRAM generated
41 whitespace-expanded tokens; parsed API semantics matched, but exact tokens
and accounting did not. The fixed c32 runner contains no tools, response
format, or grammar.

Decision contract: under `$8`, 90 claimed H200 minutes, 150 wall minutes, and
8 GiB, run one sequential control/routed-candidate feature suite and c32 pair.
Require exact tokens for all feature and endpoint rows, no speculative activity
on grammar requests, real NGRAM acceptance on ordinary traffic, and
`<=0.6381105231 s/request`. No tuning, canonicalization, broad quality replay,
or DFlash interaction is authorized.

## 2026-07-24 — routed endpoint terminal reject

Implemented the project-local `ScheduleBatch.init_new` fallback and ran the
retained H200 control/candidate sequence. Two ordinary launcher defects were
repaired before their scientific operations: missing entrypoint staging and a
host-side instead of Docker-side c32 invocation.

The candidate feature run diverged on both tool rows: control returned compact
parsed tool calls (24 and 80 completion tokens), while candidate returned
whitespace-expanded content and `length` at 128 tokens. Candidate trace finals
were 39 versus control 45, so zero tool-row speculation was not established.
Candidate c32 was finite at `0.6020959245 s/request`, below the ceiling, but
the pinned runner returned zero streamed token IDs, so the required 32/32
exact-token gate was not established.

Decision: terminal reject; no quality evidence transfers. The candidate server
is retained in H200 pool `maintenance` with container, port, and memory state
recorded for director disposition. Conservative project exposure is `$0.40`.
