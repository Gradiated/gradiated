# Gemma 4 persistent-KV replay

## 2026-07-24 — exact-token replay and calibrated decision

Question: does realistic cumulative tool traffic justify tenant-isolated persistent KV?

Action: copied the exact campaign tokenizer/chat template and TauBench-safe request
manifest into `inputs/`; implemented `replay_exact.py`; rendered cumulative OpenAI-style
user → assistant tool-call → tool-result conversations with the exact Gemma template;
tokenized with `tokenizers.Tokenizer.from_file`; replayed 165 sessions / 905 model
requests in interleaved turn rounds under no persistence, arbitrary four-replica radix
routing, tenant/session affinity with LRU capacity, and ideal unlimited KV.

Evidence (measured): 600,735 total request tokens and 481,820 exact repeated-prefix
tokens (80.2051%) under ideal affinity. At 16 GiB FP8-KV capacity, affinity retained
481,820 hit tokens with zero reloads; arbitrary routing retained 120,125 (19.9963%) and
reloaded 361,695. At 1 GiB, affinity retained 116,660 hit tokens, reloaded 365,160,
and evicted 879 entries. At 0.5 GiB it retained 33,605 and reloaded 448,215.

Calibration (derived, not endpoint timing): using the campaign's prefill-share anchor
0.3937552326, a 0.80–1.00 net recovery range, and a 0.60 upper sensitivity, 16 GiB
affinity implies 25.26–48.12% endpoint-compute reduction; arbitrary routing implies
6.30–12.00%; 1 GiB affinity implies 6.12–11.65%. FP8 KV traffic for ideal retained
hits is 41.59 GiB; 1 GiB affinity reloads 31.52 GiB during this replay.

Interpretation: the 20% cost route is plausible only when repeated turns are routed to
an owner and at least roughly 16 GiB of persistent KV is available. Arbitrary routing
and small caches fail the gate. Same-tenant/session reuse is the only admitted reuse;
no cross-tenant fingerprints are used.

Limitation: TauBench source cases are single-turn captures. Tool results in this replay
are deterministic safe placeholders derived from expected actions, not real environment
responses. The artifact is therefore an exact-token workload-bound and calibration, not
an end-to-end savings claim. A same-runtime cache on/off endpoint run is nominated for
the next separately authorized paid cycle in `artifacts/NEXT_CYCLE_PACKET.json`.

Artifacts: `artifacts/SOURCE_MANIFEST.json`, `TURN_LEDGER.jsonl`,
`CAPACITY_LEDGERS.jsonl`, `POLICY_SUMMARY.json`, `CALIBRATED_DECISION.json`, and
`NEXT_CYCLE_PACKET.json`.
### 2026-07-24 — paid 905-request persistent-KV endpoint pair

Measured on the retained H200 with the exact pinned checkpoint/image, 165 sessions, and 905 requests per arm. Control disabled radix caching; candidate used tenant-isolated session-affine radix/LRU persistence with a 50,000-token cache budget derived as 16.25 GiB. Both arms completed 905/905 with no request errors and separate raw response plus before/after Prometheus artifacts. Candidate reused 286,127/600,735 prompt tokens (47.6331%), versus 0 cached tokens in control; endpoint e2e metric was 702.328 s versus 718.941 s (2.3108% lower), and client wall time was 770.869 s versus 787.726 s (2.1406% lower). Actual provider exposure was $1.188205.

The quality gate rejected promotion: strict content matched 564/905, raw tool-call structures 418/905, and semantic tool-call structures after removing generated IDs 698/905. Both arms returned empty token-ID arrays, so exact token identity was not evidenced; raw response hashes matched 0/905. This is decision-bearing scientific evidence: cache reuse and a small endpoint win are present, but identical token/tool behavior was not. Close the route and do not retry either consumed arm. The runner’s metric-name parser missed the current SGLang histogram/counter names; raw runtime Prometheus captures and response usage were retained for the measured decision.
