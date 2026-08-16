# Direct Nebius current-AWQ c8/c16 measurement

## Question

Does increasing the current GLM-4.7-Flash AWQ/vLLM background-serving concurrency from c8 to c16 on one Nebius L40S improve sustained output-token throughput by at least 5%, or reach the $0.60/M output-token gate?

## Why it matters

The lab has spent multiple turns on launch paths that failed before a model workload ran. Nebius itself is available, and `campaign_100/nebius/vllm_smoke_control.py` previously produced the valid V24-V28 L40S measurements. Reusing that launcher directly gives a current adjacent control and candidate without another controller lineage. At the measured $0.8581222/hour L40S-plus-disk rate, $0.60/M requires 397.279 output tok/s.

## Experiment

Use the proven launcher directly with the complete local AWQ revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, content-addressed tokenizer inputs, pinned vLLM 0.15.0 runtime, `num_kv_splits=4`, `max_num_seqs=16`, and frontier concurrencies `1,8,16`. The workload is 8,192 input and 1,024 output tokens per request. c8 is the matched stock control; c16 changes only admitted concurrency and sequence capacity.

Run as soon as direct inventory is empty. Do not build a wrapper, durable-service proof, identity-repair project, or new provider adapter. The existing launcher owns create, watchdog, model transfer, execution, artifact retrieval, teardown, and absence verification. If a mutable launch input fails, retain the diagnostic and use judgment to make at most one safe material correction in the same turn.

Correctness requires complete requests, exact geometry, semantic pass, no typed harness error, and retained quality/logprob diagnostics. Latency is reported but may trade against cost within the 300-second background arm envelope. Promote c16 at at least 5% throughput/cost improvement over adjacent c8; report the $0.60/M threshold separately. This run does not by itself repair the absolute quality gate or support a matched provider claim.

Maximum session exposure is 3,600 seconds and $1.00, including cleanup margin. Retrieve the runner summary, raw request rows, server metrics, GPU telemetry, cost accounting, manifest hashes, and verified zero inventory.

## Portfolio-changing result

A valid c8/c16 result updates the current L40S cost frontier immediately. A sub-5% c16 result closes this batching geometry and the next provider lane should test a materially different software or model intervention on the same proven path. A pre-GPU operational failure does not close Nebius or batching scientifically.
