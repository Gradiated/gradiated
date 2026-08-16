# Marlin MoE block-4 specialization on SM89

## Decision question

Can a block-4 specialization of the existing expert-sorted W4 Marlin path materially reduce tiny-M padding at c16/c32 while preserving the exact 64-expert/top-4 computation and SM89 Tensor-Core legality?

Pinned vLLM already sorts expert assignments and globally schedules two routed Marlin GEMMs per MoE invocation, so another persistent scheduler is duplicate work. The concrete remaining discontinuity is its minimum `moe_block_size=8`; c16/c32 average only one/two assignments per expert.

## `$0` contract

Within 1,200 seconds, use the pinned vLLM source and cached nvcc 12.9 image. Use no provider, GPU, install, or new framework.

- Bind the exact stock `moe_align_block_size` and `moe_wna16_marlin_gemm` contracts, packed group-32 weights, route weights, reduction, and current block-8 c16/c32 descriptors.
- Derive padded-row counts for balanced, skewed, and any recovered exact route geometry at block 8 versus block 4. Preserve the same gate/up and down launch count; do not claim routing elimination or weight-memory saving.
- Implement at most one block-4 Tensor-Core specialization around the stock sorted path. Compile for SM89 and record cubin/PTX identity, ptxas registers/shared memory/spills, grid, occupancy constraints, and source-bound descriptor/reduction fixtures.
- Close on scalar fallback, changed semantics, illegal resources, unchanged padded work, or lack of a credible conditional endpoint path.

Block 4 can reduce padded expert rows by at most 2x versus block 8. Against the retained `12.374%` fused-MoE wall share, perfect transfer would move the `552.171 tok/s` full-model c16 reference only to about `588.6 tok/s`, below both campaign gates. Therefore source readiness alone does not nominate GPU. A later component A/B is admissible only if selective-W4 r3 supplies a valid scope-compatible baseline of at least about `557.7 tok/s` for the `594.466` economic gate or `568.8 tok/s` for the `606.355` robust gate, and the compiled specialization still has a plausible near-2x fused-MoE path.

Return `CONDITIONAL_SOURCE_READY`, `ECONOMIC_CLOSE`, `MECHANISM_CLOSE`, or a typed SM89 compile/resource close.

## Starting evidence

- `../expert_sorted_marlin_moe_sm89/` duplicate-mechanism close
- retained L40S V24R2/V25R1 traces
- `../expert_count_geometry/`
- `../../hardware/L40S.md`

## Cycle 125 direct reopen

The old conditional close is superseded by new scope-compatible exact-stock evidence: `full47_stock_maxseq36_split8_frontier` measured c32 at `609.606365` output tok/s with all 64 requests complete under the 300-second background envelope. This clears both preregistered reopen thresholds (`557.7/568.8`) and makes the perfect block-4 transfer ceiling approximately `649.8 tok/s`. To improve the current frontier by a decision-relevant 5%, the component must deliver about `1.63x` fused-MoE speedup; merely clearing the old `594.466/606.355` campaign floors is no longer enough.

This project is now a direct execution project, not another source/readiness gate. Use the proven durable launcher `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, its existing retained-session path, and exact current-AWQ root `/root/.cache/glm47flash-awq-ab31d120` at revision `ab31d120fbe79988fe2a0259993cf3c222aa8881` and manifest `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`. Hold the checkpoint, routing/top-k/shared expert, group-32 W4 weights, runtime, cache-off 8,192/1,024 workload, `max_num_seqs=32`, `max_num_batched_tokens=65,536`, four KV splits, and background envelope fixed.

Before create, group exact input/source hashes, current block-8 descriptor/reduction fixtures, local SM89 compile command, matching SSH pair, fresh L40S price/orderability, unique names, direct zero instance/disk inventory, one external sequential systemd owner, and its independent instance/disk watchdog. Authorize one preemptible L40S create, no retry, at most 4,200 allocation seconds and `$1.10` experiment spend.

On the target GPU, compile the narrow block-4 specialization and first run a matched block-8 versus block-4 WNA16 component A/B over exact routed-expert shapes drawn from the c32 geometry. Predeclare numerical equivalence, p50/p95 timing, padding-row, grid, registers/shared-memory/spill, occupancy, and route/reduction checks. `BLOCK4_COMPONENT_PASS` requires at least `1.63x` p50 fused-MoE speedup, legal resources, the numerical/semantic gates, and p95 behavior consistent with a credible 5% endpoint path.

Setup, bootstrap, and checkpoint staging will materially exceed this component science, so preregister exactly one adjacent conditional follow-up now. If and only if `BLOCK4_COMPONENT_PASS` fires, retain the same allocation through the existing path and run one paired full47 c32 stock-block8 versus candidate-block4 A/B under the same content-bound checkpoint/runtime state and the same owner/watchdog. Nominate only if the candidate preserves every request/semantic/background gate and improves the contemporaneous stock endpoint by at least 5%; report planning-rate `$ / M output` separately from measured experiment cost. If the trigger fails, tear down immediately. After the paired endpoint—or any typed compile, numerical, load, request, timeout, or preemption failure—clean and authenticate zero resources. No readiness-only return, second create, retry, or further retained arm is admissible.
