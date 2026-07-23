# Execution packet — exact-token persistent-KV replay

- Hypothesis: cumulative tool turns create exact prefixes whose owner affinity can avoid meaningful prefill.
- Control: no persistence and current four-replica arbitrary routing.
- Candidate: tenant-isolated content-addressed session affinity with LRU KV capacity.
- Inputs: copied exact Gemma tokenizer/template and TauBench-safe request manifest; tool results are deterministic placeholders.
- Quality gate: preserve exact cumulative message construction and token accounting; this is not a model-quality claim.
- Decision gate: avoidable prefill ≥25% or calibrated endpoint-cost reduction ≥20%.
- Budget: local CPU only, $0, under 2 GiB project artifacts.
- Outputs: source manifest, token ledger, capacity ledgers, calibrated decision, and next-cycle packet.
