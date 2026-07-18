# H200 W4 full-request background frontier

## Decision question

Can the exact-revision Gemma 4 31B AWQ-W4 performance proxy serve the 4,214-prompt/358-output workload on one H200 at c128 or c96 below `0.47201182295214134 s/request`, with nonempty outputs, usable batch completion time, and reliable cleanup?

This is a different hardware-placement hypothesis from the exhausted H100 endpoint project. Fresh shared planning rates are `$3.25/H200-hour` and `$2.80/H100-hour`, so H200 must provide `1.160714286x` price-normalized throughput. H100 checkpoint-free W4 plus actual-head components reached `0.057100911377696316 s/request` at c128, but no full-endpoint timing transfers across hardware. The exact W4 checkpoint is a performance proxy only.

## Bound inputs and lifecycle

`BINDINGS.json` binds the exact model revision, pinned vLLM image, W4 checkpoint terminal and transfer manifest, workload, H200 placement/rates, H200 lifecycle source, and component frontier. Before provider create, mechanically verify every referenced digest and require the existing flat transfer manifest to parse. Use the proven H200 lifecycle from `../h200_bf16_exact_linear_floor/h200_linear_owner.py` and the endpoint request semantics from `../h100_w4_full_endpoint_background_frontier/endpoint_runner.py`; implement the narrow H200 adapter inside this project.

Use one retained H200 development owner with an independent cleanup watchdog and a 600-second repair window. The exact-runtime c128 first request is the discovery audit. Repair ordinary transfer, image, load, API, request, telemetry, and packaging defects in place. Do not add a separate audit or readiness project.

## Observable endpoint program

Stage the existing 19.22-GB W4 checkpoint, assert the actual loaded linear consumer is Machete, and run engine-native FP8-E4M3 KV at c128 first, then c96 when it remains decision-relevant. Reproduce 4,214 prompt tokens, 358 output tokens, and 12.7% prompt-cache reads. Capture completed requests/s, service time, batch duration, TTFT, ITL/decode rate, output tokens/s, queueing, failures, allocator peak, power/utilization, provider exposure, and raw nonempty outputs.

Do not run the whole remote lifecycle inside one opaque SSH call. Persist typed phase transitions and bounded diagnostics for checkpoint transfer, image pull, server launch, model load, readiness, c128, c96, retrieval, and cleanup. Detect server exit separately from readiness timeout, retrieve container logs while the resource remains live, and leave enough absolute-deadline margin for the 600-second repair window and artifact retrieval. Setup, load, warmup, scored GPU time, and cleanup must be separated.

## Corrected-owner gate after the first H200 terminal

The first H200 allocation is operational evidence only. Its readiness diagnostic ran `docker logs` with output redirected to a remote file, while the controller saved only the SSH command's stdout and stderr; both local diagnostic files were therefore empty and the remote log was never retrieved. The owner also did not enter the promised retained-development context. Before another provider create, correct both defects in this project and emit a typed local gate proving that readiness timeout and server exit retrieve the container log plus inspect state, exit code, and OOM classification, and that the provider lifecycle is enclosed by the real 600-second repair context with an earlier repairable work deadline.

After that gate passes, launch one corrected retained H200 owner for c128 then c96. The first allocation used 1,846.914 provider seconds and `$1.261915171`, leaving 3,553.086 seconds (59.218 minutes) and `$2.988084829` under the original cumulative authority. Ordinary first-call defects remain in-place repairs on the same resource; do not create a repair, audit, or successor project.

## Lease-enabled reactivation after the model-load terminal

The second allocation corrected the launch arguments and reached exact-image Gemma4 AWQ float16 model loading with FP8-E4M3 KV, loading both shards and reporting 18.41 GiB model memory. It lost the endpoint opportunity only because the fixed 600-second repair timer cleaned the resource before readiness/c128. The shared repair protocol now supports a researcher-issued lease through the already-authorized absolute deadline and emits `repair_retention_extended`; `BINDINGS.json` binds that implementation and regression.

Before another create, adapt this project's owner to the bound lease protocol, retain the already-corrected `fp8_e4m3` spelling, image entrypoint invocation, AWQ `float16` dtype, retrievable log/state/exit/OOM/GPU diagnostics, and assert the lease behavior locally. Then launch one retained H200 development owner, stage the 19.22-GB checkpoint, run c128 first and c96 only when still decision-relevant, and repair ordinary failures in place. This is the same scientific project with additional cumulative authority, not a repair or successor project.

## Decision and limits

Promote representative quality and feature validation only if at least one complete-request point is below `0.472101737924523 s/request`, has valid nonempty outputs and usable completion time, and its planning economics beat the matched market target without disqualifying OOM or reliability behavior. A performance pass is not deployability. Close H200 W4 placement if both c128 and c96 fail economics, memory, or runtime validity.

Execution profile. Amended cumulative limits: 220 wall minutes, 135 provider minutes, 2.25 H200-hours, one 250-GiB disk at a time, 8 GiB retrieved artifacts, and `$6.50` maximum experiment spend. Prior measured exposure/spend remain cumulative. Use the actual `$2.45/H200-hour` provider rate plus disk charges for experiment accounting. Stop on a typed endpoint decision, hardware/image change, unsafe state, or exhausted limit; always authenticate zero-resource cleanup.
