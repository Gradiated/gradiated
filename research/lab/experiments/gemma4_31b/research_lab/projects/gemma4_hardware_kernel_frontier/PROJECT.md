# Gemma 4 hardware/kernel frontier

## Decision question

Which hardware-placement plus kernel/precision combination has the best credible path to beating the current Artificial Analysis price frontier by a material margin, and what single direct experiment should the lab run next?

This project runs in parallel with `l40s_online_fp8_actual_consumer_floor`. It must use that live project as a pending branch, not poll it or duplicate its FP8/W4 measurements. Its output is one executable experiment nomination or typed none, not a general hardware report or another readiness project.

## Evidence and scope

Use the exact Gemma 4 31B revision, 4,214-input/358-output campaign mix, 12.7% prompt-cache fraction, AA 10K sensitivity, current market gate, measured H200 BF16 linear/head floors, prefill/KV bounds, valid L40S component results, and the fresh shared accelerator and committed-price inventories.

Compare only candidates whose capacity, precision, runtime, and economics can be made explicit:

- L40S and materially cheaper Ada 48-GiB placements under online FP8 or W4, conditional on the live actual-consumer mechanism;
- H100, H200, GH200, and B200 where BF16/FP8 fit, tensor formats, HBM/L2 hierarchy, and committed cost imply a credible whole-request advantage;
- MI300X, MI325X, and MI355X where exact Gemma runtime support and an accessible measurement venue exist or can be named precisely.

Map exact hot shapes and the prompt-heavy workload to chip capacity, bandwidth, dense/low-precision tensor throughput, L2/shared-memory limits, occupancy, and price-normalized required completed requests/s. Do not transfer measured throughput across chips. Use the shared inventories while fresh; browse only for a missing runtime-support fact, venue, or matching committed-rate input.

Evaluate kernel opportunities against the measured bottleneck and a prospective 5% whole-request threshold. Include actual online FP8/W4 consumers as pending evidence, correct paged hybrid local/global attention, KV read/write and paging, prefill/decode specialization, and fusion of normalization/rotary/activation with adjacent operations. Treat the K=V global-QKV shrink as already low-priority unless new arithmetic overturns its measured sub-1% service effect. Do not nominate the large vocabulary head without new evidence that it is again critical at the selected concurrency.

## Terminal contract

Rank at most three combinations by expected sustainable $/token impact, uncertainty, time to evidence, software work, provider access, and quality risk. Nominate exactly one first experiment with:

- hardware and venue;
- stock comparator and kernel/representation intervention;
- exact shapes/workload and telemetry;
- expected effect and falsification threshold;
- wall, compute, storage, provider-exposure, and spend budget;
- the shortest proven launcher or a precise external-access dependency.

Prefer a checkpoint-free target-GPU component or retained-session experiment. A full endpoint is admissible only when prior mechanism evidence justifies its setup cost. Write `FRONTIER.json`, a concise research log, and terminal status.

## Budget

- Wall clock: 40 minutes.
- Compute: 2 local CPU-hours; no GPU and no provider mutation.
- Storage: 512 MiB retained plus 256 MiB project-local temporary.
- Spend: `$0`.
