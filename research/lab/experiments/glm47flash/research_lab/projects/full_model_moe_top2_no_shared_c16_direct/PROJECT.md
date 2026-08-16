# Full-model top-2/no-shared MoE c16 direct measurement

## Question

Does the source-bound fixed top-2 routed plus no-shared-expert proxy make the complete current-AWQ GLM-4.7 Flash model meet the campaign's L40S economic gate at the exact cache-off c16 workload?

## Why this arm now

The exact adjacent full-model BF16-KV c16 control is valid at `552.171055` output tok/s, below the authoritative `594.466` tok/s (`$0.514/M` at `$1.10/L40S-hour`) gate. Corrected full-model FP8 KV is scientifically closed because vLLM 0.15.0 has no compatible MLA attention backend for this model on L40S. The existing MoE proxy is the next highest-information mechanism: its synthetic ideal ceiling is `13.288%`, while top-2 or no-shared alone do not clear the gate. This proxy intentionally changes model semantics and is not a quality result.

This is a fresh direct-measurement project. Do not reopen or repeat the exhausted `adaptive_moe_architecture` launcher-integration lineage.

## Bound implementation

Use the current shared launcher `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py` at initial SHA-256 `1ea632fc88f36ffba357ed12dd4ffe99a26e0fa81a265a33a3be7682df284745`. The remote script at initial SHA-256 `49f340c8411f53bb8d8d5f71f6ee87e6d217b3831158c38d8bb24df8bf0fb895` already contains the dormant `GLM_MOE_TOP2_NO_SHARED=1` patch hook; do not edit it unless a focused test exposes a concrete defect.

Add only the narrow missing mode to the shared launcher and focused tests:

- one `--moe-top2-no-shared` candidate flag, valid only for `scientific_mode=awq` and `profile=l40s-awq`;
- require and stage `../adaptive_moe_architecture/moe_top2_no_shared_patch.py` only for that flag, pinned to SHA-256 `69f34087f816038a8ba7e9c3874b42fb6837d4f4df794a11f0d8c797820dfa7e`;
- set `GLM_MOE_TOP2_NO_SHARED=1` only in the candidate container and record mode/patch identity in the provider and artifact records;
- allow only candidate frontier `(16,)` while preserving stock behavior.

Run the focused tests, then continue in the same researcher return to the paid arm. A passing test or readiness artifact is not a terminal handoff. Do not create a project-local controller, wrapper, recovery sequence, no-mutation terminal, launcher-history audit, general profiler, or adjacent stock orchestration.

## Exact paid arm

- One direct external-systemd-owned L40S allocation; no retention and no retry.
- Checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, manifest SHA-256 `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`.
- Pinned image `vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543` and derived runtime `glm-vllm:0.15.0-transformers-1618d44`.
- Cache off; 8,192 input / 1,024 output; c16 only; `max_num_seqs=16`; `frontier_concurrencies=16`; `max_num_batched_tokens=65536`; `num_kv_splits=4`; `kv_cache_dtype=auto`; 300-second background envelope.

Use c16, not c32: the proxy was derived from c16 compute traces and does not reduce KV residency. Compare contextually, not as a paired causal estimate, with the current-identity r3 c16 summary at `../near_stock_c32_memory_frontier/artifacts/near_stock_c32_memory_frontier_r3_control/summary.json`, SHA-256 `23bce62e7a9f10c4d5708630a5351146f0c785ef2bc1281c6757459fb31c8218`.

## Result contract and stop rules

Retain the emitted server command, pre/post launcher hashes, patch application evidence and source hashes, all 32 raw request rows, exact geometry, compact semantic-divergence diagnostics, server/GPU telemetry, useful GPU seconds, archive and artifact hashes, measured exposure/spend, and verified zero final instance/disk inventory.

- `PASS`: all 32 requests complete with finite outputs and no typed performance/harness error within 300 seconds, and conservative throughput is at least `594.466` output tok/s.
- `SCIENTIFIC_FAIL`: the exact patch reaches model initialization/GPU execution but model load, runtime, request completion, or the absolute throughput gate fails. Close this fixed proxy.
- `OPERATIONAL_NULL`: provider/bootstrap failure before the source-bound mechanism is exercised. Report once and close; no retry or successor integration project.

Maximum allocation time is `3,300` seconds and maximum derived exposure is `$0.80`, including cleanup. Do not run c1/c8/c32, FP8 KV, training, broad quality, an adjacent control, or another preparation turn. Forced exit-35 remains second in the campaign queue and is outside this project.
