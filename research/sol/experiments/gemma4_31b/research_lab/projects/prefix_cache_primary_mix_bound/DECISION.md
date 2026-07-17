# Prefix-cache primary-mix bound

Decision: nominate one conditional direct cache on/off packet, but do not claim an endpoint saving or alter the active H100 owner.

The deterministic content-keyed simulation has 500 requests at 4,214 prompt / 358 output tokens. It creates 267,584 real 16-token-boundary prefix hits out of 2,107,000 prompt tokens (12.69976%); the five-token difference from 12.7% is not credited. The locality-favourable burst ordering realizes all 450 intended hits at concurrency 1/8/16 under an optimistic, pre-runtime H100 capacity calculation. An interleaved churn replay realizes only two hits at c1 (1,216 tokens) and is therefore a falsifier of any claim that aggregate cache-read share alone establishes reusable locality.

Automatic prefix caching can only remove prefill work. Consequently, its best possible 5% endpoint reduction requires a measured prefill wall-time share of at least 39.3755%, even with perfect hit realization and no lookup, eviction, queueing, or capacity penalty. The conservative half-prefix sensitivity saves 6.4926% of prompt tokens and needs at least 77.01% exposed prefill time before overhead. This is a transfer bound, not a timing result.

The H100 0.90-utilization gross calculation leaves 13.744 GiB after 58.256 GiB weights; derived active-request KV is 0.712 GiB each, leaving 13.032 / 8.047 / 2.350 GiB at c1/c8/c16 before runtime reservations. These numbers only screen cache pressure. The future arm must use actual server cache, eviction, and allocation telemetry.

The exact source snapshot shows default 16-token blocks, hashes only full blocks, and records cache statistics only with runtime logging enabled. The single packet in `PREFIX_ARM_PACKET.json` is therefore gated on raw bytes/token IDs and actual cache-metric/timing capture from the same controller lineage. MTP, async scheduling, or changed batching requires a fresh matched pair because it changes the exposed prefill share.
