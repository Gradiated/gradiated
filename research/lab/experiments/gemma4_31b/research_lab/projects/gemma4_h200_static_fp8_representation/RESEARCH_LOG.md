# Research log

## 2026-07-22 — activated

Opened because neither the historical ModelOpt serialization failure nor the current vLLM BF16-weight result measures a deployable static-FP8 endpoint. Proceed to the shortest real producer/consumer path and H200 evidence.

## 2026-07-22 — serialized producer complete; ordered consumer waiting on failed higher-priority claim owner

Question: can fixed activation scaling remove the dynamic per-token reduction while the same pinned SGLang FP8 GEMM consumes an exact Gemma weight?

Action: extracted `model.language_model.layers.0.mlp.down_proj.weight` into a project-local BF16 safetensor, CPU-produced a fresh serialized E4M3 weight with per-output-channel scales and a calibrated per-tensor activation scale, and implemented a fresh-process H200 consumer for exact M32 decode and M2048 chunked-prefill shapes. The consumer compares dynamic-per-token and static-per-tensor activation quantization through the same `fp8_scaled_mm`, consumes outputs against BF16, records CUDA kernels, timing, saturation, numerical error, and peak allocation. A durable owner requires release events from both higher-priority lanes before atomically claiming the shared H200.

Evidence: the exact BF16 tensor is 231,211,096 bytes at `f7b5e5bd...8447a3`; the serialized static representation is 115,627,244 bytes at `2e0eff5d...7bd8a4`. The source shard was independently verified as `eeef8791...bbfa`. The producer used 256 deterministic calibration tokens (seed 2026072201), observed absmax 3.5261998, and froze activation scale 0.00826453045. These are measured producer facts; the calibration distribution is synthetic and does not establish endpoint quality. No project CUDA or provider spend occurred.

Interpretation: the producer/export boundary is working and the next operation is a real target-GPU consumer, not another compatibility audit. At 15:18:42Z the higher-priority `gemma4-current-sglang-h200-20260722t1456z.service` exited 1 after checkpoint transfer with a retrieved `retrieval_failure` terminal but left `h200-continuity-e00hzj9a8khp0fevy5` claimed. Pool rules forbid this project from releasing, reclaiming, or mutating that other project’s bench.

Next: the ordered `gemma4-static-fp8-h200-20260722t1500z.service` remains live at $0.00. It proceeds only after director repair/release of the current-runtime claim and a subsequent partitioned-attention release; otherwise it writes a typed no-capacity terminal at 17:25Z while preserving all producer bytes.

## 2026-07-22 — same-claim scales_a ABI repair reached typed integration boundary

Question: can the existing fixed scalar activation scale be passed through the pinned SGLang FP8 consumer without changing the serialized FP8 representation?

Action: inspected the retained owner's first diagnostic once. The pinned dynamic quantizer creates `scales_a` with shape `[M, 1]`; patched only `static_fp8_consumer.py` to broadcast the unchanged scalar scale into contiguous `[32, 1]` and `[2048, 1]` tensors. `freeze_gpu_manifest.py` bound the revised 11,363-byte consumer (`89e252eb…bd362`) while the BF16 (`f7b5e5bd…8447a3`) and serialized FP8 (`2e0eff5d…7bd8a4`) hashes remained unchanged. Submitted `REPAIR_REQUEST.json` with `intervention_unchanged=true`; the retained owner matched both large artifacts and restaged only the consumer.

Evidence: attempt 2 began, then the remote launcher exited before a new run terminal could be written. All retrieved output remained attempt-1 data (`scales_a` scalar error), consistent with the launcher's cleanup encountering root-owned prior Docker output. The owner preserved the claim until its declared repair deadline, then wrote `artifacts/FINAL_TERMINAL.json`: `owner_or_integration_failure`, reason `repair handshake deadline expired`, 2,220.259 claimed seconds, and $1.517177 measured provider exposure. No M32 or M2048 row was persisted.

Interpretation: this does not measure static-FP8 performance or numerical quality. It is a typed remote retry/cleanup integration boundary after the permitted consumer-only repair; do not relaunch without a new director admission.

## 2026-07-22 — fresh-attempt static-FP8 component result

Question: after correcting the pinned `fp8_scaled_mm` scales_a ABI, does the frozen static activation scale improve the exact H200 down-projection component at M=32 or M=2048?

Action: claimed the warm H200 for 88.401 seconds, reused the resident pinned image and two immutable producer artifacts, and invoked the frozen consumer in new `/home/glmrunner/gemma4-static-fp8/attempt-20260722t164953z/run` output. No prior artifact was deleted or overwritten. The typed consumer terminal and rows were retrieved to `artifacts/attempt-20260722t164953z/` before release.

Evidence (measured): both rows completed. At M=32, static component median was 0.061760 ms vs dynamic 0.051232 ms (−20.55%); at M=2048, static was 0.405408 ms vs 0.414592 ms (+2.22%). Static relative L2 error was 0.03792 (M=32) and 0.03778 (M=2048), above the 0.03 gate, although cosine remained 0.99928 at both shapes. The result is `component_negative`; the terminal hash is `5c367462…6cfff`. This continuation cost $0.060408, bringing project exposure to $1.577585.

Interpretation: fixed scalar activation scaling does not survive the project's numerical gate and offers no robust exact-shape component win (it regresses decode materially). The admitted component question is answered negatively; no endpoint promotion is justified.
