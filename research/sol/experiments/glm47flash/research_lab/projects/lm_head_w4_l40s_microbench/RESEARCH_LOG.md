# Research log

No researcher result yet. Execute the single admitted component measurement under the shared durable L40S lifecycle; do not return with only controller or kernel preparation.

## 2026-07-15 — Exact-head Marlin session launched

Question: can an explicit Marlin W4 output layer beat the exact BF16 `[M,2048] x [2048,154880]` output projection by `3.4076x` at c16-relevant M=16 on L40S?

Action: generalized the admitted shared microbench controller only to accept explicit remote/benchmark scripts, compact staged inputs, an artifact basename, and the project timeout. Built the real-head group-32 W4 payload from the immutable checkpoint without transferring the full model: qweight `[256,154880]` (158,598,753 bytes, SHA-256 `0e943a76…b43e4b`) and BF16 scales `[64,154880]` (19,826,266 bytes, SHA-256 `279a41e4…e7108`). The payload preserves the bridge's `0.0926084` source-relative-L2 quantization error. After tests and authenticated zero instance/disk inventory, launched `glm47-lm-head-w4-l40s-r1` under systemd with one controller PID/cgroup, a 1,600-second absolute watchdog, and the compact inputs only. The controller emitted instance `computeinstance-e00dd9sxtj4cybsr0j`; one instance and its boot disk now belong solely to this controller.

Evidence/contract: the retained arm compares direct BF16 GEMM to vLLM's explicit `gptq_marlin_repack`/`apply_gptq_marlin_linear` path at M=1/8/16 using identical BF16 activations, CUDA-event p50/p95 timing, dequantized-W4 output diagnostics, peak VRAM, 1 Hz GPU telemetry, hashes, archive verification, and teardown. Its external artifact root is `artifacts/glm47-lm-head-w4-l40s-20260715-r1/`; successful retrieval must contain `vllm-head-microbench.tar.gz` and `summary.json`.

Interpretation/next move: no performance result is available yet. Do not infer support or speed from allocation existence. Reconcile the terminal archive, summary, typed remote diagnostics, and zero final inventory on the next turn; close this lineage if valid M=16 p50 speedup is below `3.4076x` or correctness fails.

## 2026-07-15 — L40S allocation closes before CUDA measurement

Question: can the sole admitted allocation reach the explicit W4-versus-BF16 Marlin sweep within its 1,600-second contract?

Action/evidence: the controller reached SSH in 95.346 seconds, but its pinned `vllm/vllm-openai:v0.15.0@sha256:97187…4543` Docker pull remained in the host bootstrap for 6m43s and never started a container, input transfer, CUDA allocation, or benchmark. The retained `host-bootstrap.stdout.log` records downloaded/pulled layers (SHA-256 `96664a01…2ccb0`); Docker's retained diagnostic says `reference for unknown type` for the tag-plus-digest reference. The single allowed in-place correction pulled the tag while requiring the same image ID, but it did not become ready during the controller's bounded repair window. `events.jsonl` (SHA-256 `a94c1635…0e68`) records `host bootstrap failed` and the accepted explicit teardown decision. No timing, output, utilization, power, or quality evidence exists.

Interpretation/next move: this is a typed image-bootstrap incompatibility/latency failure for this Nebius lifecycle, not evidence that Marlin is unsupported or slower. The project has spent its sole allocation and may not create a successor controller. Await the existing controller's verified teardown summary and zero inventory; then leave the M=16 `3.4076x` economic gate unresolved and return the slot. A future re-admission would need a prevalidated image reference or a retained base image before it can make a component-speed claim.

Final reconciliation: [`summary.json`](artifacts/glm47-lm-head-w4-l40s-20260715-r1/summary.json) records 683.431 seconds, `$0.144075245` derived exposure, `outcome=FAIL`, no result archive, and verified zero final instances/disks. The controller's final event also confirms cleanup. The compact staging payload was removed after teardown; the reproducible source packer remains in this project.
