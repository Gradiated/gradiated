# Research log

No researcher turn has completed. The endpoint is a telemetry-conditioned direct cache packet or quantified closure, not a provider run.

## 2026-07-17 — deterministic source-accounting bound completed

Question: can the observed 12.7% cached prompt-token share plausibly clear the 5% endpoint-cost gate for exact Gemma 4 31B?

Action: captured the pinned vLLM cache source and ran `run_prefix_bound.py`. The synthetic 500-request trace uses content-addressed repeated prefixes, actual 16-token cache boundaries, a zero-reuse case, a half-prefix sensitivity, and a content-keyed LRU under c1/c8/c16 capacity screens.

Evidence: `PREFIX_WORKLOAD.json` (SHA-256 `b7d6b9cde90ab6150427da91c09d460c3ed16fa375c272c461cc0bb7221b925c` after the final deterministic run), `PREFIX_BOUND.json`, `source_snapshot/`, and `DECISION.md`. The source shows full-block hashing and an all-but-last-token cache-hit limit; the base trace conservatively credits 267,584, not 267,589, prompt tokens. The deterministic burst realizes 450 source-accounted hits, while interleaved churn realizes only two at c1 in the optimistic-capacity LRU model.

Interpretation/next move: a 5% endpoint effect needs at least 39.3755% measured prefill wall share even before overhead. One raw-server-telemetry-gated on/off packet is in `PREFIX_ARM_PACKET.json`; do not use synthetic saved tokens as an endpoint claim and do not touch the exclusive H100 owner.
