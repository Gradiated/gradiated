# N-gram speculative c16 direct measurement

## Question

Can target-verified prompt-lookup/n-gram speculative decoding raise the exact current-AWQ L40S c16 workload from the contextual `552.171055` endpoint to at least `594.466` output tok/s without changing model quality or the 300-second background envelope?

## Why this matters

The checkpoint's native MTP layer loaded but had near-zero acceptance, low draft throughput, and excessive residency. N-gram speculation is a materially different decode mechanism: it proposes from already available request tokens, requires no draft model or training, and retains target-model verification. The target workload has long 8K prompts and 1K outputs, so repeated code, prose, or prompt-local sequences may supply acceptance that MTP did not. Existing archives discarded token order, so another offline acceptance estimate cannot decide this; one bounded endpoint arm is the shortest honest falsifier.

## Fixed inputs and proven path

- Exact model/checkpoint: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, manifest SHA-256 `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`.
- Tokenizer: the content-addressed tokenizer root paired with the valid r3 result; do not reconstruct or replace it.
- Runtime: pinned `vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543` plus the existing Transformers-derived runtime.
- Proven launcher: `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, current SHA-256 `2c6685288bb4c79b558696eb9621060eb4886d0f95264bdf1e5df5b3ab0ce164`; remote script SHA-256 `9ba66342b64a749ec961354399030496bcb482277cb2a80df138c37481968139`.
- Proven SSH pair: `/root/.config/nebius/glm-campaign/ssh_ed25519` and `.pub`.
- Contextual control: `../near_stock_c32_memory_frontier/artifacts/near_stock_c32_memory_frontier_r3_control/summary.json`, SHA-256 `23bce62e7a9f10c4d5708630a5351146f0c785ef2bc1281c6757459fb31c8218`, `552.1710554232396` tok/s. It is not an adjacent control.
- Economics: `$1.10/L40S-hour`, `$0.514/M`, absolute gate `594.466` tok/s. Actual experiment accounting uses the measured Nebius VM-plus-disk rate `$0.8581222/hour`.

## Scope and immediate experiment

First, in the pinned image/source, bind exactly one source-defined prompt-lookup/n-gram `SpeculativeConfig` accepted by this runtime, including proposal length and lookup bounds. Add only one explicit launcher boolean/environment value and the corresponding remote server argument; preserve stock mode byte-for-byte. Focused tests and the execution-equivalent no-mutation terminal must prove that the option selects the L40S-AWQ profile, exact inputs, candidate config, `$0.8581222/hour` rate, methodology-off path, and cannot select MTP, exit-35, MoE patches, H100, or BF16. If the pinned runtime has no exact n-gram/prompt-lookup method, close `RUNTIME_CLOSE` at `$0`; do not upgrade runtime or build a proposer.

If the source gate passes, continue in the same researcher return through one direct external-systemd-owned candidate-only session:

- `--profile l40s-awq`, `--scientific-mode awq`;
- cache off, 8,192 input / 1,024 output, `num_kv_splits=4`;
- `max_num_seqs=16`, `frontier_concurrencies=16`, `max_num_batched_tokens=65536`;
- exact 32-request c16 arm, 300-second background envelope;
- `VLLM_RUN_METHODOLOGY=0`; no methodology or profiler tail;
- one source-defined n-gram configuration, fixed before create; do not sweep proposal lengths.

Retain all request rows, the new per-request output-token histograms/completeness flags, stream hashes, proposal/acceptance counters by position, accepted tokens per round, proposer/verify timing where exposed, server/KV metrics, peak/steady memory, GPU telemetry, semantic-determinism diagnostics, useful GPU seconds, provider exposure/spend, archive manifest, and authenticated zero inventory. N-gram verification must preserve target-model semantics; any typed divergence or incomplete histogram is a correctness failure. Compare economics to the absolute gate, not a claimed causal delta from r3.

## Budget and stop rule

This is the sole provider-mutation/spend project. Maximum exposure is 3,300 seconds and `$0.80`, including cleanup. Hand off immediately after the durable service owns one instance/disk and shows forward progress; do not poll. One material in-allocation correction is allowed only after a genuine provider/runtime external failure and before the deadline. No second create, adjacent stock arm, runtime upgrade, wrapper, or successor is authorized.

Terminal outcomes:

- `ECONOMIC_PASS`: all 32 requests complete inside 300 seconds, correctness evidence passes, and throughput is at least `594.466` tok/s;
- `SCIENTIFIC_FAIL`: a valid candidate endpoint is below the gate or has negligible/negative proposal economics;
- `RUNTIME_CLOSE`: exact prompt-lookup support fails before create; or
- typed external/operational terminal with spend and verified cleanup, without throughput inference.

## Artifact contract

Produce one project spec, focused shared-launcher tests and no-mutation result, candidate archive/summary when launched, exact acceptance and economics evidence, spend/useful-GPU accounting, zero-cleanup receipt, and a concise research-log handoff.

