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
