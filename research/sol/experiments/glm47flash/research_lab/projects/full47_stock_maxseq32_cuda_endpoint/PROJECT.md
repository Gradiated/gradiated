# Full47 unchanged-stock maxseq32 CUDA endpoint

## Decision question

Does the exact unchanged full47 checkpoint serve the authoritative c32 workload economically on one L40S when vLLM is started with `max_num_seqs=32`, given that its measured fixed KV pool already admits all 32 complete requests and the inherited c32 HBM projection has been invalidated as a synthetic temporal extrapolation?

This is a direct execution-equivalence endpoint, not another allocator or readiness gate. It is queued below the corrected direct W4 successor, whose predecessor is now terminal. No W4 owner has an executable trigger-aware retained comparator, so this standalone endpoint should launch after the corrected successor terminates and authenticated inventory returns to zero.

## Immutable scope

- Checkpoint: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`; no derived checkpoint.
- Runtime/container: pinned vLLM 0.15.0 and the proven lifecycle, bound at this handoff to `vllm_smoke_control.py` SHA-256 `edaeb5cc81577ef410b704588918c7841f7d3d003e40c83e27618746adca5636`, `vllm_recover_existing.py` `9dfa0187188fb4d4c0a216487b77c2c6cc2b22691c4e3cf783a6348778acaeda`, and `vllm_batched_runner.py` `0db2de2bd749c18bcd2ca45c16e7b3617daf5307665456b1dac039c81f90fa72`; rehash and fail on unexplained change at launch. Use one-line public-key cloud-init, one user-systemd owner, and an independent cleanup watchdog.
- Startup: `max_num_seqs=32`, `max_num_batched_tokens=65536`, frontier `16,32`, `num_kv_splits=4`, automatic KV sizing, prefix cache off.
- Workload: exact 8,192 input / 1,024 output campaign requests, all 32 completions, cache off, 300-second background-arm envelope, existing semantic and histogram gates.
- The declared maxseq32 startup and c16/c32 load shape are the sole runtime/scheduler variables. No model, runtime implementation, capture, KV dtype, tokenizer, prompt, or quality intervention is permitted. Do not transfer depth42/43 performance as the answer.

## Sole-owner execution

Do not mutate a provider while the higher-priority corrected W4 owner is live or eligible to continue. After it is terminal and provider inventory is authenticated zero, authorize exactly one preemptible L40S create, at most `$1.10` and 4,200 allocation seconds. In the same server, run stock c16 then stock c32. Treat the retained `333,488`-token startup pool as a measured prior, not a guarantee under maxseq32: record the new startup model/repack/workspace/graph memory; available KV bytes, tokens, and blocks; input/capture allocations; peak HBM; per-request completion and latency histograms; throughput; semantic gates; useful GPU seconds; power/clocks/utilization; exposure; archives; and authenticated cleanup.

Classify a valid c32 endpoint as `ROBUST_THROUGHPUT_PASS` at `>=606.355 tok/s`, `ECONOMIC_PASS` in `[594.466,606.355)`, or `SCIENTIFIC_FAIL` below `594.466`. Otherwise return one typed initialization/admission OOM, runtime/load, request, semantic, or operational close. A valid subeconomic result is terminal.

## Retention decision

Disable the proposed `STOCK_C32_TYPED_ADMISSION_OOM_C24` arm before launch. The existing recovery parser and frontier validator do not accept c24, and the current controller has no post-result typed-admission-OOM evaluator: its keep path would retain after any artifact-bearing result. A parser-only edit therefore cannot make the arm compliant inside ten minutes. Launch with no keep flag and a zero repair window, then clean normally after c16/c32 or any typed failure. Do not delay the endpoint for another retention implementation, retry, or successor controller.

## Immediate offline launch binding

While the corrected-W4 owner remains live, finish the one missing launch packet at `$0`; this is successor planning and must not inspect or mutate that owner or any provider resource. Content-bind a stock-specific `EXPERIMENT_SPEC.json` for the exact checkpoint and tokenizer, `max_num_seqs=32`, `max_num_batched_tokens=65536`, frontier `16,32`, automatic KV dtype, four KV splits, cache off, and the 300-second background-arm envelope. Do not reuse the near-stock `99dd...` spec because it declares maxseq16 and c1/c8/c16.

Freeze a unique unit/name, artifact root, spec hash, current launcher hashes, and fully absolute `systemd-run` command in a project-local launch-packet artifact. Use `glm47-full47-stock-maxseq32-r1.service`, `artifacts/l40s_stock_maxseq32_20260716_r1`, no `--keep-instance-after-result`, and `--repair-window-seconds 0`. The packet must retain the existing 4,200-second deadline and `$1.10` cap; at the measured `$0.8581222/hour` VM-plus-disk rate the maximum derived exposure is about `$1.00114`. Stop after the packet and a bounded no-mutation parser/identity check are content-bound. Do not add a controller edit, support project, provider preflight, retention path, or another scientific gate. Launch remains prohibited until corrected W4 is terminal and inventory is authenticated zero.

## Starting evidence

- `../full47_stock_c32_kv_preallocation_reaudit/`
- `../nebius_current_awq_c16_direct/`
- `../minimal_depth42_v2_l40s_direct/`
- `../minimal_depth43_v2_l40s_direct/`
- `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/`
