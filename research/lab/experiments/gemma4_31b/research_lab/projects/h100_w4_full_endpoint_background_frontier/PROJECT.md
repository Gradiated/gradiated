# H100 W4 full-request background frontier

## Decision question

Can an exact-revision Gemma 4 31B W4-Machete endpoint on one H100 serve the 4,214-prompt/358-output OpenRouter workload at c96/c128 below the `0.5479752315195353 s/request` planning ceiling with usable background completion time and reliability?

The checkpoint-free frontier measured W4 linears plus the actual tied head at only `0.07381828800945853 s/request` for c96 and `0.057100911377696316 s/request` for c128, leaving `0.47415694351007676` and `0.490874320141839` seconds respectively. This margin is large enough to leave component proxies and measure the complete request. c32 is already closed and must not be retried.

## Bound identities and evidence

`BINDINGS.json` mechanically binds:

- exact model `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`;
- the verified local 62,546,338,248-byte BF16 checkpoint and tokenizer under `../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint`;
- exact image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`;
- the measured c48/c64/c96/c128 actual-consumer frontier terminal; and
- the c32 economic closure.

The W4 checkpoint produced here is explicitly a performance proxy, not a deployable quality result. A simple deterministic group-128 AWQ-compatible quantizer is allowed to measure runtime cost mechanics; no endpoint becomes production-eligible until representative quality and feature evaluation later passes.

## Stage A — durable local checkpoint owner

Within this same project, launch one bounded durable local owner to stream the verified BF16 safetensors into a vLLM-loadable AWQ W4 checkpoint without duplicating the source checkpoint. Preserve exact non-linear, embedding, normalization, tokenizer, config, and tied-head semantics; quantize only supported linear tensors using the representation already exercised by the measured Machete consumer. The owner may repair ordinary naming, packing, safetensors, quant-config, and manifest defects in place.

Write `W4_CHECKPOINT_TERMINAL.json` atomically only after all source hashes match, every expected tensor is accounted for exactly once, output files are content-hashed, quantization config is explicit, sample dequantization oracles are finite/nontrivial, and the exact image's loader can parse the checkpoint metadata with no missing or unexpected tensors. A typed failure is also terminal. Provider creation is forbidden until this terminal passes; do not force materialization into one researcher response or restart correct deterministic work for cadence.

## Stage B — retained H100 endpoint

After the typed checkpoint terminal passes, use the proven Nebius lifecycle for one H100 SXM retained development session with a 250-GiB disk and the exact pinned image. Stage the W4 checkpoint, assert that the loaded linear consumer is `MacheteLinearKernel.apply_weights`, and run the first c96 request batch as the discovery audit. Repair ordinary load, path, API, scheduler, request-harness, telemetry, and packaging defects in place under the same owner and a 600-second repair window.

Primary arm: W4 with engine-native FP8-E4M3 KV at c96 and c128. Drive a reproducible background request distribution around 4,214 prompt and 358 output tokens, including 12.7% prompt-cache reads, until steady-state rows exist or memory/correctness closes the point. Capture completed requests/s, complete batch duration, TTFT, ITL/decode rate, output tokens/s, queueing, failures/reloads, allocator peak, NVML power/utilization, provider exposure, and raw nonempty outputs. Separate setup, checkpoint staging, model load, warmup, and scored GPU time.

Because staging and model load dominate, prepare a matched BF16-KV configuration offline during the primary. If the FP8-KV arm is valid and at least 20 provider minutes remain, run the BF16-KV arm sequentially against the resident checkpoint/runtime at the best valid concurrency. Never delay the primary or retain an idle GPU waiting for this follow-up.

## Decision and budgets

Promote only if a complete-request point has service time below `0.5479752315195353 s/request`, planning economics below the matched market target, nonempty structurally valid outputs, usable reported batch completion time, and no disqualifying OOM/failure behavior. A performance pass promotes representative quality and feature validation; it does not itself establish deployability. If c96 and c128 both fail economics, memory, or runtime validity, close the H100 W4 endpoint line.

Execution profile. Total budget: 180 wall minutes; 6 local CPU-hours; source checkpoint read-only; at most 25 GiB retained W4 bytes plus 40 GiB local temporary; after Stage A passes, 75 provider minutes / 1.25 H100-hours, one 250-GiB disk, 8 GiB retrieved artifacts, and `$3.50` maximum spend. Stop on the typed endpoint decision, unsafe/unintelligible state, hardware/image change, or any exhausted limit. Always authenticate zero-resource cleanup. No c32 retry, separate checkpoint/audit/repair project, or quality claim is authorized.

## 2026-07-18 reactivation amendment

The H200 matched component terminal passes every actual consumer and oracle but fails its `1.160714286×` price hurdle: c128 is `0.05696907804079819 s/request` versus H100 `0.057100911377696316`, and c96 is `0.07436745774513111` versus H100 `0.07381828800945853`. H200 therefore provides no price-normalized component advantage, while the H100 c128 endpoint question remains unanswered only because the old owner used one opaque, non-retryable remote stage.

Reactivate this same scientific project at execution profile. Mechanically bind the passing 19.22-GB W4 terminal/manifest, exact image/workload, current program bytes, H200 comparison terminal, and shared `run_repairable_operation` controller. Implement one phased retained H100 owner with durable transfer, image, server, readiness, request, diagnostics, retrieval, and cleanup boundaries. Preserve the already-discovered runtime contract: image-supplied `vllm serve`, AWQ `float16`, `fp8_e4m3` KV, `max_num_batched_tokens=8192`, and staged `text_config.vocab_size` fallback. A retained fault may consume `action: retry` and rerun the failed stage on the same resource.

Run c128 first against the strict `0.5479752315195353 s/request` complete-request ceiling, with raw nonempty outputs and the original telemetry contract. Run c96 sequentially only when c128 is valid and at least ten provider minutes remain. Do not run BF16-KV, c32/c48/c64, another component sweep, or another H200 placement. The amended cumulative limits are 300 wall minutes, 130 provider minutes / 2.1667 H100-hours, one 250-GiB disk at a time, 8 GiB retrieved artifacts, and `$6.00`; the reactivation owner itself has a 60-wall-minute deadline and all prior exposure/spend remains charged.
