# Full-47 stock maxseq36 and conditional split-8 frontier

## Question

Can the exact unchanged full-47 stock checkpoint use the measured L40S KV pool to raise background concurrency from 32 to 36 and clear the robust `606.355` output-tok/s boundary? If c36 nearly clears, can the already-measured split-8 MLA scheduling change close the remaining gap in the same retained session?

## Why this matters

The verified stock archive is already an economic pass at c32: `596.851973` tok/s versus `594.466`, but only `0.401%` above that gate and `1.592%` below the robust boundary. Its startup allocated `333,488` KV tokens (`20,843` 16-token blocks). Exact c36 demand is `36 * (8,192 + 1,024) = 331,776` tokens (`20,736` blocks), leaving `1,712` tokens or `107` blocks without changing model bytes or KV precision. This is the smallest directly executable background-scheduling step and does not preserve an interactive SLO.

## Fixed evidence and identity

- Source endpoint: `../full47_stock_maxseq32_cuda_endpoint/artifacts/l40s_stock_maxseq32_20260716_r1/vllm-awq-batch.tar.gz`, SHA-256 `ff873b597b33775787eada26ded437d1da91f326a47a8beb3ab8c994cc27cb4c`.
- Exact checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, model manifest `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`, and the same tokenizer/runtime image `sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`.
- Stock c32 is `596.851973` tok/s with 64/64 complete requests in `109.802770 s`; c16 is `550.908084` tok/s. The outer return code reflects the inherited interactive TTFT gate, while all requests pass the authoritative 300-second background envelope.
- Planning economics are `$1.10/L40S-hour`; the economic and robust gates are `594.466/606.355` tok/s. Experimental accounting uses the actual metered VM-plus-disk rate.
- Prior scope-matched split-count experiments bracketed a `1.0447%` server uplift from four to eight MLA KV splits. This is a prior and trigger bound, not a transferred c36 result.

## Execution contract

Use the proven shared `vllm_smoke_control.py` lifecycle, exact resident inputs, one external-systemd owner, and one independent absolute cleanup watchdog. Before create, extend only the existing AWQ frontier validation/tests needed for literal `(32,36)` and `(36,)`; the batched runner already accepts arbitrary positive concurrency. Do not create a project-specific controller or add a readiness project. Rehash changed launcher inputs and fail before mutation on unexplained drift.

Authorize one preemptible Nebius L40S create, at most `$0.60` and `2,400` allocation seconds including cleanup. Start one unchanged maxseq36 server with `max_num_batched_tokens=65,536`, cache off, automatic BF16 KV, four KV splits, and the exact 8,192-input/1,024-output workload. Run c32 as the within-server control and c36 as the primary arm. Require complete requests, exact token geometry, prefix-cache zero deltas, semantic/histogram gates, KV blocks/tokens, peak and steady HBM, TTFT/TPOT/queue, throughput, power/clocks/utilization, useful GPU seconds, exposure, archive integrity, and authenticated cleanup. A capacity or request failure is scientific evidence, not a retry trigger.

## One conditional retained follow-up

Measured setup and staging dominate scored GPU time, so bind one adjacent follow-up before provider creation. Use the existing retained-session recovery path and the same sequential owner/watchdog. Retain only if four-split c36 is valid, all diagnostics pass, c32 control is not materially drifted, and c36 lands in `[600.086,606.355)` tok/s. That interval is the range where the lower measured `1.0447%` split-8 uplift could cross the robust boundary.

On that named trigger only, reuse the content-bound runtime and verified checkpoint staging, restart with `num_kv_splits=8`, and run c36 once. Do not reuse mutable server/model state or create a second instance. If c36 is `>=606.355`, below `600.086`, invalid, semantically broken, operationally null, or the trigger/recovery command is not ready within ten minutes, tear down immediately. No c35/c40, retry, repair arm, or unconditional keep is allowed.

### Cycle 118 live-contract correction

Disable the split-8 follow-up for the already-running r1 owner. Read-only audit found that r1 launched the base controller with unconditional `--keep-instance-after-result`, no threshold evaluator is bound, and its watchdog is a child of the original `KillMode=control-group` unit, so it will not survive into recovery. The documented threshold and recovery CLI are not a compliant sequential owner/watchdog. Do not mutate or restart the live four-split experiment. When it terminates, do not run split-8; if the controller retained the allocation, the first and only provider action is immediate cleanup and authenticated zero inventory. This correction supersedes the retained-follow-up paragraphs for r1.

## Decision

Return `ROBUST_FRONTIER_PASS` for a valid c36 result at `>=606.355` (four or triggered eight splits), `ECONOMIC_ONLY_FRONTIER` for a valid best result in `[594.466,606.355)`, `FRONTIER_CLOSE` below the economic gate or on typed capacity/request failure, or a typed operational null. Full quality remains mandatory; this unchanged-checkpoint measurement inherits the stock archive's quality claim limit and is not a deployable quality claim.

## Available resources

Use the stock project, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.
