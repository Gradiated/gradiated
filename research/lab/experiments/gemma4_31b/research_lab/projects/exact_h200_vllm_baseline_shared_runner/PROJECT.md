# Exact Gemma 4 vLLM H200 baseline through the shared runner

## Decision question

Can the exact pinned BF16 Gemma 4 31B checkpoint produce a valid, sustainable vLLM H200 baseline for the campaign's prompt-heavy background workload, and does its measured completed-request throughput clear the `$3.25/GPU-hour` planning-base market hurdle?

The matched SGLang/H200 lineage closed before provider creation after exhausting its single retry. The campaign still lacks one exact-model endpoint result. This project removes the second engine and uses the proven shared lifecycle plus simultaneous-load runner to obtain that missing direct measurement; it is not another controller or readiness project.

## Mechanically bound identities and inputs

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only non-reasoning.
- Verified local checkpoint: `../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint`; consume its passing `CHECKPOINT_TERMINAL.json` read-only. Its model index SHA-256 is `d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2`.
- Runtime image: `vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, BF16 weights and default BF16 KV.
- Workload: exact 4,214 input / 358 output tokens with 12.7% measured repeated-prefix cache reads under true simultaneous background concurrency; separate exact 10,000 input / 358 output single stream.
- Hardware: Nebius `gpu-h200-sxm`, preset `1gpu-16vcpu-200gb`, one H200 141 GB, one 250-GiB disk, preemptible experiment rate captured separately.
- Economic interpretation: `../h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json`; strict planning-base frontier is `2.094181-2.118591` completed primary requests/s. Production uses `$3.25/hour`; provider/preemptible rate is experiment accounting only.

Before create, mechanically compare this brief to the named checkpoint, start packet, and economic terminal and emit `artifacts/IDENTITY_ASSERTION.json`. Any mismatch closes locally.

## Proven execution path and first science

Use `VerifiedRetainedOwner`, diagnostic-bearing create reconciliation, lowercase RFC-1123 request inspection, SSH/transfer, one cleanup watchdog, typed retrieval, and authenticated cleanup from the shared Nebius tools. Adapt the existing `vllm_batched_runner.py` or `vllm_methodology_runner.py` for request generation and simultaneous timing; do not write another ad hoc synchronous client or general controller.

Render one vLLM server plus primary c1/c4/c8/c16 saturation ladder, adding c32 only on allocator/deadline headroom, then the separate 10K single stream. Capture exact submitted prompt bytes/token IDs/hashes, sampling/template/stop identity, serialized responses and retokenized output IDs with the boundary labeled, complete/failure/reload counts, request timestamps, TTFT/ITL/queueing, prefill/decode/cache metrics, HBM/allocator state, continuous GPU utilization/power, actual provider/disk rate, useful-GPU/provider seconds, and all-in cost surfaces. Atomically retrieve/hash the baseline stage before any follow-up.

The final-program audit must inspect the rendered files and real create argv. It must prove exact token counts, realized cache mix, simultaneous requests, raw/telemetry fields, lowercase name, atomic retrieval, and a distinct nonexistent owner output directory. Assertions deferred to later remote execution are a blocker, not a pass. On audit pass, launch immediately; if correct staging/science outlives the response, leave one bounded user-systemd owner with its unit/PID/cgroup/deadline/artifact root/typed terminal in `STATUS.json`.

## One conditional retained follow-up

Because checkpoint/image staging dominates scored work, prepare the existing vLLM prefix-cache on/off packet before the owner ends. It may run sequentially on the same allocation/runtime/checkpoint only if the baseline is healthy, measured exposed prefill share is at least `0.393755`, every packet raw metric is present, and the arm is start-ready within ten minutes without extending the absolute deadline. Otherwise record the trigger false and clean up immediately. No other retained arm is authorized.

## Decision and quality boundary

- A valid baseline establishes the new content-addressed endpoint control and reports whether planning-base throughput clears `2.118591` requests/s; it does not claim a SGLang delta.
- Failure to clear the market hurdle is a measured H200/BF16/vLLM negative, not a checkpoint or model-quality result.
- Raw output/reliability evidence must be retained. Broad feature and quality certification remains required before production eligibility.

## Budgets

- Wall clock: 110 minutes including staging and cleanup.
- Provider exposure: 80 minutes under one retained owner.
- Compute: 1.34 H200 GPU-hours and 2 local CPU-hours.
- Storage: reuse the verified checkpoint read-only; one 250-GiB provider disk and 10 GiB new project artifacts; no shared `/tmp`.
- Spend: `$4.00` maximum including disk/IPv4; one allocation.

