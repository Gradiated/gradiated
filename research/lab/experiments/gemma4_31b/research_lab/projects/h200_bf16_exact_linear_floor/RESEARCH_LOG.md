# Research log

## 2026-07-17 — director admission

Activated after checkpoint-backed H200 endpoint lines repeatedly ended before model science. The admitted primary is checkpoint-free exact-shape H200 BF16 transformer-linear measurement; its only conditional same-session arm is the already proven actual vLLM `ParallelLMHead`. One durable owner, one allocation, no paid repair.

## 2026-07-17T12:01:11Z — live owner handoff

- Question: can the exact-shape CUDA-event transformer-linear floor falsify one-H200 economics, with the actual head run only when it can change the decision?
- Action: launched one H200 under durable unit `gemma-h200-linear-20260717t115654z.service`; pre-create passed before one provider create. An adversarial audit arrived after create but before scientific staging, so the same owner retained the allocation while local staged bytes were corrected in place. No restart, second create, or paid repair occurred.
- Evidence: `artifacts/POST_CREATE_CORRECTION_AUDIT.json` passes 11/11 and binds the corrected CUDA-event lower-bound classification, lenient head trigger, telemetry coverage, owner, and transitive lifecycle bytes. `artifacts/LIVE_OWNER_SNAPSHOT.json` binds PID/cgroup/invocation, instance, watchdog, deadline, and phase.
- Interpretation: the owner is live in host bootstrap; only its typed primary/conditional artifacts may determine the result. Isolated synchronized wall timings are diagnostic and must not be used as an economic lower bound.

## 2026-07-17T12:06:42.562310Z — H200 exact BF16 linear terminal

- Question: do exact architecture-weighted BF16 transformer linears alone falsify one-H200 economics, and does the conditional actual head change the classification?
- Action: ran one retained H200 session through the shared lifecycle; the head was controlled by the preregistered typed trigger.
- Evidence: `/root/workspace/research/lab/experiments/gemma4_31b/research_lab/projects/h200_bf16_exact_linear_floor/artifacts/SUMMARY.json`; classification `combined_linear_head_floor_preserves_at_least_one_high_batch_point`; exposure `586.894` s; derived spend `$0.400998937`; cleanup `True`.
- Interpretation: component lower bound only; omitted attention, KV, scheduler, sampling, prefill, quality, and endpoint reliability remain unmeasured.

## 2026-07-17T12:12:04Z — terminal reconciliation

- Question: what does the raw CUDA-event transformer-plus-head component floor establish after resolving the global-QKV layout caveat?
- Action: treated wall-derived combined labels as non-authoritative; recomputed matching-M sums from raw `economic_lower_bound_seconds_358_steps` and exact H200 `ParallelLMHead` per-request rows. Independent source reconciliation confirmed pinned stock vLLM clones K as V and executes full-attention QKV width 20,480; width 18,432 would be a distinct K=V-specialized intervention.
- Evidence: `artifacts/RECONCILED_TERMINAL.json`. Combined floors are c1 `6.625177`, c4 `1.691650`, c8 `0.879517`, c16 `0.442462`, and c32 `0.224770` seconds/request against the `0.472012-0.477514` planning-base ceilings. Exposure was `586.894` s, useful GPU time `1.068793` s, derived spend `$0.400998937`; authenticated cleanup found zero instances and disks.
- Interpretation: c1/c4/c8 are falsified by the component floor; c16/c32 are preserved, not proven. No endpoint throughput, prefill/attention/KV/scheduler/sampling/reliability, or quality claim was measured. Project closed with no successor/provider authorization.
