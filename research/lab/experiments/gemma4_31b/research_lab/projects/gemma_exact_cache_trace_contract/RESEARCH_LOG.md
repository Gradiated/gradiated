# Research log

## 2026-07-17 — passing exact cache-trace packet

Question: can the exact 4,214/358 primary workload encode approximately 12.7% prefix reuse without accidental suffix sharing or false cache credit?

Action/evidence: CPU-safe inspection of immutable image `sha256:952594c2…732a79` observed vLLM `0.19.1.dev6+g6d4a8e6d2`, 16-token full-block hashing, token-count query/hit counters, and `CompletionRequest.prompt: list[int]`; `prompt_token_ids` is not a valid field. `TRACE_PACKET.json` (SHA-256 `ccc55909…25d68`) binds the verified tokenizer hashes and contains exact scored c1/c4/c8/c16 barrier groups, unique suffix IDs/hashes, explicit warmups/metric snapshots, and a disjoint exact 10K/358 stream. `TRACE_TERMINAL.json` passes all checks; project storage is 3.1 MiB and spend is `$0`.

Interpretation/next move: 535 common tokens are 12.6958% of the prompt, but exact-image block granularity permits at most 528 cached tokens (12.5297%); construction cannot claim the campaign's realized 12.7%. Offer the packet without delaying the live owner and require scored `vllm:prefix_cache_hits`/query deltas plus returned-token and simultaneous-in-flight assertions.

## 2026-07-17 — director delegation

Resolve the exact tokenizer/block-aware request-trace semantics at `$0` while the corrected H200 baseline is provider-gated. The output must distinguish constructed sharing from measured cache reads, prove distinct suffixes, and remain independent of provider mutation.
