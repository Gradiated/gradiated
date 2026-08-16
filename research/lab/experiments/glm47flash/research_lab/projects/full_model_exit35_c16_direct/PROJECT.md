# Full-model forced exit-35 c16 direct measurement

## Question

Does full-depth prefill followed by forced decode exit after serving layer 35 reduce exact full-model L40S c16 wall time enough to clear the campaign's `594.466` output tok/s economic gate?

## Why this arm now

The valid current-identity full-model BF16-KV control completes at `552.171055` output tok/s, so the next mechanism needs `1.07660x` absolute uplift. FP8 KV is closed by exact L40S MLA-backend incompatibility, and the fixed top-2/no-shared patch is closed after a model-initialization exception. Forced exit-35 is independent and immediately executable: its source-bound phase fixture proves 47-layer prefill, layers 0–34 for decode, no tail-layer decode/KV writes, stock final norm/head, stable shapes, and fail-closed mixed-phase handling. The current shared launcher already stages and enables the exact patch.

The synthetic all-exit ceiling is `669.459` output tok/s. That is nomination evidence only; the direct arm must measure endpoint wall time. This proxy intentionally changes semantics and is not a deployable-quality result.

## Exact execution contract

Use the existing shared launcher `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, initial SHA-256 `0eae6092708c66b54d570dec667bf0979fefa8faa9c18b8f4957262c7f2aa93d`, and remote script initial SHA-256 `bec5e3615b9b16d9018b78154a27e43361612be9829f11dac2f2d473ef779d03`. Select its existing `--exit35-mode`; do not add another launcher, wrapper, recovery sequence, adjacent control, or preparation phase.

Bind `../sequence_early_exit_architecture/exit35_vllm_source_patch.py` at SHA-256 `eae5a80f77a5029ebc22f33ab21dbb2e80762fcc497cec103fe874b5cef0fdf0`. It must match pinned `glm4_moe_lite.py` source SHA-256 `6a984f701d46dfa05389a45d7aedde6a10ef45a6f59e73d3bbfa1e82f556b4a9`, apply once, compile, and leave verifiable patch evidence. Use:

- checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, manifest SHA-256 `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`;
- image `vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543` and derived runtime `glm-vllm:0.15.0-transformers-1618d44`;
- one direct external-systemd-owned L40S allocation, no retention;
- cache off, 8,192 input / 1,024 output, c16 only, `max_num_seqs=16`, `frontier_concurrencies=16`, `max_num_batched_tokens=65536`, `num_kv_splits=4`, `kv_cache_dtype=auto`, and a 300-second background envelope.

The r3 control at `../near_stock_c32_memory_frontier/artifacts/near_stock_c32_memory_frontier_r3_control/summary.json`, SHA-256 `23bce62e7a9f10c4d5708630a5351146f0c785ef2bc1281c6757459fb31c8218`, is contextual rather than adjacent. Runtime/checkpoint/tokenizer/workload identity is unchanged, but do not claim a paired causal delta.

## Result and stop rules

Retain the emitted server command, launcher and patch hashes, patch evidence, all 32 request rows, proof of full-depth prefill and absent tail decode/KV writes, prefill/decode timing if available without delaying the arm, compact semantic-divergence diagnostics, server/GPU telemetry, useful GPU seconds, archive hashes, measured exposure/spend, and verified zero final instance/disk inventory.

- `PASS`: all 32 exact-geometry requests finish with finite outputs and no typed harness/performance error inside 300 seconds, and conservative throughput is at least `594.466` output tok/s.
- `SCIENTIFIC_FAIL`: source-bound patch/model/runtime execution reaches the GPU but load, phase behavior, request completion, or the absolute throughput gate fails. Close forced exit-35.
- `OPERATIONAL_NULL`: provider/bootstrap failure before the mechanism is exercised. Report once and close; no retry or successor wrapper.

Maximum allocation time is `3,300` seconds and maximum derived exposure is `$0.80`, including cleanup. Execute directly in the first researcher return; a readiness-only handoff is not a result. Do not run c1/c8/c24/c32, FP8 KV, MoE routing changes, training, confidence-head work, or broad quality.
