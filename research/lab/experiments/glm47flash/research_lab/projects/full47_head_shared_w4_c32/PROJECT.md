# Full-47 selective head/shared W4 c32

## Question

Can the full 47-layer model reach an economically useful c32 point on L40S by quantizing only its BF16 output head and 46 serving shared experts to the checkpoint's existing symmetric group-32 W4 format?

## Why this matters

This is the smallest current full-depth representation change. The exact scope is 139 BF16 tensors: `lm_head.weight` plus gate/up/down projections for shared experts in serving layers 1–46. Source payload is `1,502,609,408 B` (`1,433 MiB`); exact W4 payload is `422,611,120 B` (`403.033371 MiB`), saving `1,079,998,288 B` (`1,029.966629 MiB`). Layer 0, all routed experts, routing/top-k, MLA/KV, embeddings, depth, and layer-47 MTP remain unchanged.

The saving moves the stock c32 projection from `46,875.7` to `45,845.733 MiB`: only `222.267 MiB` below the `46,068-MiB` visible envelope and still `1,313.733 MiB` above the `44,532-MiB` robust convention. This is nominal fit with high fragmentation/repack risk, not robust memory admission. Direct load, resident-byte, and endpoint evidence must decide it.

## Fixed evidence

- Exact checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, with the campaign-bound config/index identities.
- Exact ledger and shared shapes: `../residual_w4_completion/residual_w4_completion_bound.json`.
- Real head pack/oracle: `../lm_head_w4_bridge/lm_head_w4_bridge.json` and its fixture. The former `../parallel_lm_head_w4_runtime_gate/` invariants are folded into this project.
- Proven runtime/lifecycle: pinned vLLM `0.15.0`, `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, and retained path `vllm_recover_existing.py` under one external-systemd owner plus watchdog.
- Workload/economics: cache off, 8,192 input/1,024 output, `num_kv_splits=4`, c16/c32, 300-second envelope, L40S `$1.10/hour`, absolute `594.466` and robust-throughput `606.355` tok/s gates.

## Execution contract

This is the sole provider-mutation/spend owner: one clean r3 create after authenticated zero inventory and a complete local admission packet, at most `$1.25` and 4,500 allocation seconds. r1 and r2 were pre-provider operational nulls; r3 must preserve the same scientific identity and absolute shared controller. Permit no new implementation correction or controller lineage after the admission packet.

Before create, materialize and content-address both the combined checkpoint and the conditional shared-W4/BF16-head ablation locally. Replace the 139 BF16 tensors with exactly 417 packed/scale/shape tensors, hash all changed payloads, prove state-dict/index closure and byte identity for every unrelated tensor, and record actual derived-file bytes. Remove only the head and serving shared-expert targets from the ignore set. The remote binder alone is not this admission proof.

Fold the output-head binding into this implementation. Use the existing SM89 Marlin WNA16 operation while preserving `ParallelLMHead` vocabulary partitioning, logits shape/dtype/device, bias, sampler behavior, and unquantized embeddings. Prove each shared expert resolves to an exact W4 path and preserves the shared-expert sum. Silent BF16 fallback, duplicate BF16 residency, missing-key tolerance, broad loader rewrites, or unrelated tensor changes close the project.

Reuse the head oracle and retain deterministic shared-expert error/saturation summaries plus bounded semantic smoke. Distinguish packed bytes from runtime repack duplication, workspace, graphs, allocator reservation, and KV bytes. If local admission passes, use only the absolute proven shared launcher for one combined candidate server and complete c16 then c32 batches with a 300-second background envelope. Require actual W4 dispatch, memory decomposition, complete rows/histograms, throughput/latency, finite diagnostics, utilization/power/clocks, useful GPU seconds, exposure, authenticated archives, and cleanup.

The adjacent shared-W4/BF16-head c16 ablation is preregistered for a valid combined c32 in `[594.466,606.355)` and is already content-addressed. Before create, minimally extend the proven smoke controller—not a new launcher lineage—so the same systemd owner/watchdog evaluates the authenticated c32 result, retains only on that named trigger, and then calls `vllm_recover_existing.py --reuse-staged-runtime` with a fresh ablation checkpoint stage/verification. It must otherwise clean immediately; cleanup follows the ablation. Fail closed before provider if this conditional path cannot be bound within the ten-minute preparation window.

The byte admission packet is necessary but not runtime admission. Add exactly one narrow pinned-runtime adapter so `lm_head`'s actual `ParallelLMHead` matches the existing symmetric group-32 W4 scheme while the embeddings remain BF16. Prove the exact head and all 138 shared tensors select WNA16, register/load packed/scale/shape state without missing/unexpected keys or BF16 duplicates, preserve TP vocabulary/logits/bias/sampler and shared-expert sum contracts, and pass deterministic head plus shared-MLP pack/dequantization error and saturation fixtures. Any broad matcher/loader rewrite or failed oracle closes before create.

Return `ROBUST_THROUGHPUT_PASS` for valid c32 `>=606.355`, `ECONOMIC_PASS` for `[594.466,606.355)`, `SCIENTIFIC_FAIL` below `594.466`, or typed `IMPLEMENTATION_CLOSE`, `LOAD_CLOSE`, `MEMORY_CLOSE`, or operational-null evidence. Report capacity margin separately; this is architecture-cost evidence and full quality remains mandatory.

## Available resources

Use the fixed evidence above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
