# Research log

## 2026-07-26T06:18Z — exact c32 depth oracle: typed none

Decision: close request-adaptive DFlash verification depth for this exact c32
distribution. This was a zero-cost, zero-GPU offline simulation; no endpoint was
contacted and request 25 was not replayed.

Measured input: 32 distinct completed requests from the immutable exact
depth-4 c32 SSE final frames. The canonical 10,103-byte projection was hashed
before analysis as
`4eb1865ca7890eb268a4016931cf5fbfb48c021de89a39288123629ca4db026d`.
The later boundary probe whose response bytes were not recovered was excluded.

Derived result: the real acceptance histogram for 0–3 accepted drafts was
`[469, 788, 684, 1843]` over 3,784 verification cycles. A perfect pre-decision
oracle choosing depth `accepted_drafts + 1` preserves all 7,685 accepted draft
tokens and request completion while reducing unpadded target rows from 15,136
to 11,469, a 24.227% logical ceiling. It removes no draft invocation and no
batched target-forward launch; the retained telemetry cannot resolve padding,
so the guaranteed physical row saving is zero.

Decision bound: applying the row ceiling to the exact depth-4 H200 CUDA-event
cost yields a derived 1.349269 s/request service floor. Even the deliberately
more generous whole-service scaling floor is 1.153328 s/request. Both miss the
0.625149 s/request qualified denominator and 0.500119 s/request campaign
target. The telemetry also contains only post-verification outcomes, not the
pre-decision predictor state a realizable controller would require.

Artifact:
`DFLASH_VERIFICATION_DEPTH_ORACLE_TERMINAL.json`
(`67f5ae04b36f6e0fa38bf3cf495077969129245857e7c7840effb4f48b22e594`).
