# Corrected-key full-model forced exit-35 c16 measurement

## Question

With the provider request bound to the already proven one-line OpenSSH key pair, does full-depth prefill followed by forced decode exit after serving layer 35 clear the campaign's `594.466` output tok/s L40S gate?

## Why this is a fresh scientific arm

`full_model_exit35_c16_direct` is an operational null: Nebius rejected cloud-init before allocation, so exit-35 has no GPU, model-load, phase, request, throughput, or quality evidence. The failure is isolated to invocation input. That launch used a 14-line PEM public-key file; the immediately preceding successful MoE allocation used the matching one-line Ed25519 pair. Read-only validation confirms the latter pair matches, and the exact generated cloud-init parses locally.

The mechanism remains the strongest immediately executable performance candidate. Its source-bound fixture proves 47-layer prefill, layers 0–34 for decode, no tail decode/KV writes, stock final norm/head, stable shapes, and fail-closed mixed-phase behavior. Its `669.459` tok/s all-exit ceiling is synthetic nomination evidence only. The current-identity full-model c16 context is `552.171055` tok/s, requiring `1.07660x` uplift to reach the gate.

## One correction, then direct execution

Use the existing launcher `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, initial SHA-256 `0eae6092708c66b54d570dec667bf0979fefa8faa9c18b8f4957262c7f2aa93d`, and remote script initial SHA-256 `bec5e3615b9b16d9018b78154a27e43361612be9829f11dac2f2d473ef779d03`. Select existing `--exit35-mode`; do not edit the shared launcher or create a wrapper/controller.

Bind exactly these existing external credential paths without copying, printing, hashing, or committing their contents:

- private key `/root/.config/nebius/glm-campaign/ssh_ed25519`;
- public key `/root/.config/nebius/glm-campaign/ssh_ed25519.pub`.

Before create, fail closed unless the public key is exactly one OpenSSH line, `ssh-keygen -y` confirms the pair, and the launcher's exact generated cloud-init parses locally with exactly that authorized key. This check and the paid arm are one researcher return; a readiness artifact is not a result.

Bind `../sequence_early_exit_architecture/exit35_vllm_source_patch.py` at SHA-256 `eae5a80f77a5029ebc22f33ab21dbb2e80762fcc497cec103fe874b5cef0fdf0`, with pinned runtime source SHA-256 `6a984f701d46dfa05389a45d7aedde6a10ef45a6f59e73d3bbfa1e82f556b4a9`. Use checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, manifest SHA-256 `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`, pinned vLLM 0.15.0 image/runtime, and tokenizer files from that checkpoint root.

Run one direct external-systemd-owned L40S arm with no retention: cache off, 8,192 input / 1,024 output, c16 only, `max_num_seqs=16`, `frontier_concurrencies=16`, `max_num_batched_tokens=65536`, `num_kv_splits=4`, `kv_cache_dtype=auto`, and a 300-second background envelope. The r3 summary at `../near_stock_c32_memory_frontier/artifacts/near_stock_c32_memory_frontier_r3_control/summary.json`, SHA-256 `23bce62e7a9f10c4d5708630a5351146f0c785ef2bc1281c6757459fb31c8218`, is contextual rather than adjacent.

## Result and stop rules

Retain provider request identity without credential bytes, emitted server command, launcher/patch hashes, patch and phase evidence, all 32 request rows, compact semantic-divergence diagnostics, server/GPU telemetry, useful GPU seconds, archive hashes, measured spend, and verified zero final instance/disk inventory.

- `PASS`: all 32 exact requests complete with finite outputs and no typed error inside 300 seconds, with conservative throughput at least `594.466` output tok/s.
- `SCIENTIFIC_FAIL`: the exact mechanism reaches GPU execution but load, phase behavior, requests, or throughput fail. Close exit-35.
- `OPERATIONAL_NULL`: any remaining pre-mechanism external failure. Close without another key, wrapper, controller, or retry.

Maximum allocation time is `3,300` seconds and maximum derived exposure is `$0.80`, including cleanup. Do not run an adjacent control, other concurrency, FP8 KV, MoE changes, training, confidence-head work, or broad quality. This proxy changes semantics; full quality is deferred but mandatory before promotion.
