# Corrected full-model FP8-KV c32 measurement

## Question

Does the complete 47-layer current-AWQ GLM-4.7 Flash model fit and meet the campaign economic gate on one L40S at c32 when vLLM receives its actually accepted FP8 E4M3 KV-cache token, `fp8_e4m3`?

## Decision evidence

- The adjacent r3 full-model BF16-KV control is valid: c1/c8/c16 produced `56.611 / 360.608 / 552.171` conservative output tok/s, every request succeeded, and the c16 point completed inside the 300-second background envelope. Its summary SHA-256 is `23bce62e7a9f10c4d5708630a5351146f0c785ef2bc1281c6757459fb31c8218`.
- The r3 FP8 arm is an operational null. vLLM 0.15.0 rejected `fp8_e4m3fn` before model load and explicitly advertised `fp8_e4m3` among its accepted choices. The arm summary SHA-256 is `49d92311f72753633c5b3713cb49bb6d23bd9375bfb9443aa8a47dc777c7a6cd`; cleanup passed with zero instances and zero disks.
- Exact checkpoint revision is `ab31d120fbe79988fe2a0259993cf3c222aa8881`; local root is `/root/.cache/glm47flash-awq-ab31d120`; manifest SHA-256 is `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`.
- The campaign planning rate remains `$1.10/L40S-hour` and is fresh. The authoritative economic gate is at least `594.466` output tok/s, equivalent to at most `$0.514/M` output tokens. Experimental exposure must use the measured VM-plus-disk rate separately.

## Delegated work

Correct only the FP8 E4M3 token contract from `fp8_e4m3fn` to `fp8_e4m3` in the shared L40S smoke/recovery argument validation and focused tests. Preserve stock `auto` behavior and the remote command pass-through. Run the narrow focused tests, then continue in the same researcher return directly to one candidate-only full-model L40S measurement through the existing `vllm_smoke_control.py`; a passing local correction is not a handoff point.

Launch under one direct external-systemd owner with the proven `l40s-awq` profile, pinned runtime/checkpoint/tokenizer, cache off, 8,192 input / 1,024 output, `num_kv_splits=4`, `max_num_batched_tokens=65536`, `max_num_seqs=32`, `frontier_concurrencies=32`, `background_arm_envelope_seconds=300`, and `kv_cache_dtype=fp8_e4m3`. Do not retain the instance. Do not rerun c16, add a controller/recovery sequence, alter model tensors, enable prefix caching/MTP, run training, or perform broad quality work.

Record the exact pre/post launcher hashes, emitted server command, requested and resolved KV dtype/scales, model-load result, GPU memory decomposition and peak, all c32 request rows, conservative throughput, latency envelope, GPU utilization/power/clocks, useful GPU seconds, actual exposure/spend, artifact hashes, and verified zero final instance/disk inventory. Compact semantic/output diagnostics are required to reject broken execution; full quality remains deferred.

## Decision and stop rules

- `PASS`: all c32 requests complete within 300 seconds, conservative throughput is at least `594.466` output tok/s, compact diagnostics are intact, and cleanup is verified.
- `PARTIAL_MECHANISM`: valid c32 load and workload improve on the r3 c16 point but remain below `594.466` output tok/s.
- `SCIENTIFIC_FAIL`: a valid load/OOM, runtime incompatibility after the corrected token is accepted, incomplete c32 workload, or sub-c16/sub-gate endpoint closes this exact FP8-KV mechanism.
- `OPERATIONAL_NULL`: provider/bootstrap/artifact failure before a valid model decision. Report it and stop; no second provider attempt or successor wrapper is authorized.

Maximum provider exposure is 3,300 seconds and `$0.90`, including cleanup. Any local failure must be corrected before create; after provider creation there is one arm and no retry. The terminal artifact must bind the result to the two r3 summaries above and distinguish measured, derived, and deferred-quality claims.
