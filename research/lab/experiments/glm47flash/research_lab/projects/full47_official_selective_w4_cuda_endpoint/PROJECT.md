# Full47 official selective-W4 CUDA endpoint

## Decision question

Can the exact full-47 model serve the campaign workload economically at c32 on L40S after quantizing only `lm_head.weight` and the 46 serving shared experts with the pinned official group-32 `uint4b8` producer and a narrow `ParallelLMHead` adapter?

This is one direct candidate-to-endpoint experiment, not another readiness ladder. The `$0` predecessor reached the actual `ParallelLMHead -> CompressedTensorsWNA16.create_weights -> choose_mp_linear_kernel` path and stopped only because local device capability was `-1`. CUDA registration/load/post-load, logits/shared semantics, capacity, and endpoint performance must now be decided in the same allocation.

## Immutable identity and forbidden inputs

- Source checkpoint: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`.
- Exact changed scope: `lm_head.weight` plus gate/up/down weights for shared experts in layers 1–46. Layer 47 MTP, layer 0, embeddings, routed experts, routing/top-k, MLA/KV, depth, tokenizer, and workload remain unchanged.
- Never stage or read either quarantined derived root `1bd3249b...` / `6cd4cde5...` as candidate input. Do not invoke the current `--head-shared-w4` hook unchanged: it still points at the invalid custom `q & 15` binder.
- Proven lifecycle baseline: `campaign_100/nebius/vllm_smoke_control.py` at opening SHA-256 `09ede4bc...`, `remote_vllm_awq_smoke.sh` `cf4e2f87...`, and `vllm_batched_runner.py` `0db2de2b...`. Any project-local change is limited to the new official binder pointer/mode and trigger-aware retention, with focused fail-closed tests and before/after hashes.

## Before provider mutation

Resume the interrupted local packet rather than rematerializing by default. Finalize and content-address the combined official head+shared-W4 root, then emit `OFFICIAL_LOCAL_ADMISSION.json` binding the source and derived roots, exact 139-to-417 tensor closure, unrelated tensor-byte identity, index/config closure, official pack/unpack agreement, declared observer/calibration behavior, no BF16 duplicate, actual derived bytes, bounded numerical/saturation evidence, and hashes. The existing combined root `/root/.cache/glm47flash-awq-full47-official-head-shared-w4-7ab75a5258cc` is only a candidate until that admission artifact passes; the incomplete shared-only temporary root is neither required nor admitted. Bind the immutable stock source root as the sole adjacent input. Reuse the narrow pre-import selector expansion from the predecessor; do not broaden matching or rewrite the loader.

Before create, add and locally exercise a fail-closed CUDA-oracle command/artifact contract plus the named conditional-retention evaluator. Bind the one-line OpenSSH public key input, authenticated zero provider inventory, the exact source/runtime/checkpoint hashes, one user-systemd owner, and an independent cleanup watchdog. Unconditional `--keep-instance-after-result` is prohibited. Once these bounded omissions pass, launch immediately; do not insert another `$0` readiness project.

## One L40S execution

Authorize exactly one preemptible L40S create, at most `$1.25` and 4,500 allocation seconds. In the same owner and allocation:

1. On CUDA, exercise exact head and representative shared gate/up/down registration, official payload load, Marlin repack/post-load, and actual consumer execution. Require WNA16/Marlin dispatch, no fallback or BF16 duplicate, finite official-dequant agreement, correct vocabulary/logits/bias/sampler contracts, and exact shared-expert sum semantics.
2. If and only if that passes, immediately load the official combined full47 root and run candidate c16 then c32 with cache off, 8,192 input / 1,024 output, `max_num_seqs=32`, frontier `16,32`, `num_kv_splits=4`, complete request/histogram and semantic gates, and a 300-second background-arm envelope.
3. Record actual resident/repack/workspace/graph/KV bytes, peak memory, throughput/latency, useful GPU seconds, power/clocks/utilization, exposure, exact archives, and authenticated cleanup.

The `1,029.966629-MiB` payload saving projects c32 only `222.267 MiB` below the visible envelope and remains above the inherited robust convention. Report actual capacity; never relabel this as robust fit. Return `ROBUST_THROUGHPUT_PASS` for valid c32 `>=606.355 tok/s`, `ECONOMIC_PASS` for `[594.466,606.355)`, `SCIENTIFIC_FAIL` below `594.466`, or a typed representation/CUDA/load/memory/request/operational close. There is no retry, component-only return, or further adapter ladder.

## Adjacent conditional follow-up

Setup and checkpoint staging are expected to dominate scored GPU time. Preregister exactly one adjacent arm under trigger `VALID_SELECTIVE_W4_C32_STOCK_COMPARATOR`: any valid combined-W4 c32 result, with the immutable stock source root and exact maxseq32 c16/c32 command packet content-bound and ready inside ten minutes. Only then may the same sequential owner/watchdog use the existing `vllm_recover_existing.py --reuse-staged-runtime` path to restage and verify the stock checkpoint, run stock c16 and then c32, and clean. Runtime state may be reused; candidate checkpoint state may not. If combined-W4 c32 is invalid, the stock packet is not ready within ten minutes, or the trigger-aware retained path is unavailable, tear down immediately. This is the sole adjacent follow-up and supersedes the lower-information shared-only attribution ablation.

## Starting evidence

- `../official_group32_head_shared_w4_adapter_gate/`
- `../full47_head_shared_w4_c32/` (negative implementation evidence only)
- `../residual_w4_completion/`
- `../near_stock_c32_memory_frontier/`
- `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/`
