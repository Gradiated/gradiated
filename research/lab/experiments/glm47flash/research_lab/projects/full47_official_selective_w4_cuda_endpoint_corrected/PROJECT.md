# Full47 official selective-W4 corrected CUDA endpoint

## Decision question

After correcting the one staged-binder basename mismatch, can the exact full-47 official head+shared group-32 W4 candidate pass its real SM89 consumer and serve the authoritative c16/c32 workload economically on L40S?

The current `glm47-official-w4-r2` allocation is a pre-science operational null: its already-staged remote script invokes a binder filename that was not copied. It must clean normally. This successor changes only that staging contract and proceeds directly to target-GPU science; it is not another validation ladder.

## Immutable execution

- Candidate root: `/root/.cache/glm47flash-awq-full47-official-head-shared-w4-7ab75a5258cc`, manifest `7ab75a5258cce406351790cefe1f3f8ba2c63aa4ad618f8d94c5ac3a65ec7778`, source revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`.
- Exact changed scope: `lm_head.weight` and serving shared-expert gate/up/down weights only; all routed experts, routing, MLA/KV, depth, tokenizer, and workload remain unchanged.
- Proven lifecycle: `campaign_100/nebius/vllm_smoke_control.py`; use the corrected packet hashes from `../official_w4_corrected_successor_packet/`, one user-systemd owner, independent watchdog, one-line public key, and authenticated zero inventory.
- Startup/workload: `max_num_seqs=32`, `max_num_batched_tokens=65536`, frontier `16,32`, `num_kv_splits=4`, cache off, exact 8,192 input / 1,024 output requests, all completions and semantic/histogram gates, 300-second envelope.

After the current owner is terminal, zero inventory is verified, and `CORRECTED_W4_PACKET_READY` exists, authorize one preemptible L40S create at most `$1.25` and 4,500 allocation seconds. First execute the official head plus representative shared gate/up/down CUDA registration/load/repack/consumer oracle. Require official WNA16/Marlin dispatch, no fallback/BF16 duplicate, finite dequant agreement, logits/sampler contracts, and exact shared-expert sum. Only then load full47 and run c16 then c32, recording resident/repack/workspace/graph/KV bytes, peak memory, throughput/latency, request semantics, useful GPU seconds, telemetry, exposure, artifacts, and cleanup.

Return `ROBUST_THROUGHPUT_PASS` for valid c32 `>=606.355 tok/s`, `ECONOMIC_PASS` for `[594.466,606.355)`, `SCIENTIFIC_FAIL` below `594.466`, or one typed CUDA/representation/load/memory/request/operational close. The existing retained-session path has no named result evaluator that can be safely made ready within ten minutes, so preregister no adjacent arm and clean normally for every outcome. The unchanged-stock direct project follows after cleanup.

No retry, further binder gate, or component-only successor is allowed.

## Director launch rebind — Cycle 109

The predecessor is terminal with authenticated zero instance/disk inventory, and `CORRECTED_W4_PACKET_READY` passes. After that packet froze controller SHA-256 `07f5842b...`, shared safeguards added a durable-systemd invocation ownership guard and truthful remote-failure attribution/archive ordering; the current controller is `edaeb5cc81577ef410b704588918c7841f7d3d003e40c83e27618746adca5636`, its focused test is `ba5593a11997b9ec5187523ac5287966ba966a5cb3b2e98e688eacf08d1572a2`, and the corrected remote script remains `29766910f0b3252ef0dd2e42051dfb5ab0b6a3fbd3e736187184bb0e7dc1defa`. The frozen direct `systemd-run` command satisfies the new ownership guard and the 39-test suite passes. Accept this explicitly audited rebind and launch now. Do not open another packet or source gate.
