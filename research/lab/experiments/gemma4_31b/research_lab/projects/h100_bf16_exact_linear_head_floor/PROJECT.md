# H100 BF16 exact linear plus tied-head component floor

## Decision question

Do actual BF16 transformer linears at Gemma 4 31B's exact stock-vLLM shapes already falsify H100 production economics at c8/c16/c32, and if not, does the actual pinned `ParallelLMHead` close the surviving points?

This is a materially different stock-BF16 hardware-placement result, not a repair of FP8, W4, or paged-KV. Reuse the scientifically successful final H200 BF16 linear/head programs and the proven user-systemd H100 lifecycle; change only accelerator identity and H100 economic boundary. No checkpoint, quantization, model endpoint, or quality claim.

## Identity and primary

`assert_identity.py` mechanically binds campaign bytes, the reconciled H200 source result/program, the H100 economic mechanism, verified-empty W4 cleanup, and this brief before provider create. Required identity: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, vLLM `0.19.1.dev6+g6d4a8e6d2`, `NVIDIA H100 80GB HBM3` capability 9.0, workload 4,214 prompt / 358 output / 12.7% cache, and H100 ceiling `0.5479752315195353 s/request`.

Primary uses actual BF16 CUDA matmul at six exact stock-vLLM text-linear shapes: sliding QKV 5376→16384 ×50, global QKV 5376→20480 ×10, sliding output 8192→5376 ×50, global output 16384→5376 ×10, merged gate/up 5376→43008 ×60, and down 21504→5376 ×60. Measure M8/M16/M32 decode and M3679 prefill with warmups, repeated CUDA-event p50/p95, synchronized wall diagnostics, output consumption, allocator/telemetry, and finite nonzero varied-sign oracle. Aggregate prefill once plus 358 decode steps divided by concurrency exactly once. Atomically retrieve a sliding-QKV M8 sentinel before the full 24-row sweep.

## Adjacent conditional head

Before the owner ends, prepare for at most ten wall minutes the actual pinned-image BF16 `ParallelLMHead` from the proven H200 program. It must be content-bound and staged without checkpoint/compilation, with actual consumer identity, varied-sign nonzero tensors, output oracle, M8/M16/M32 timing, allocator and telemetry.

Run it sequentially on the same retained H100 only under `H100_BF16_LINEAR_SURVIVES_AND_SETUP_DOMINATES_AND_HEAD_READY`: all 24 primary rows pass; at least one of c8/c16/c32 remains below `0.5479752315195353`; measured bootstrap/image setup exceeds total scored primary CUDA time; head is start-ready; and at least seven provider minutes remain. Combine matching head and linear floors as a component lower bound. False trigger cleans immediately. No other adjacent arm.

## Budgets and terminal

- Wall clock: 28 minutes.
- Provider exposure: 20 minutes.
- Compute: 0.34 H100 GPU-hours plus 2 local CPU-hours.
- Storage: one 100-GiB provider disk; 1 GiB retained plus 512 MiB temporary.
- Spend: `$1.30` maximum; one allocation; zero repair/restart.

Use one sequential durable owner and independent watchdog. Fail closed before create on any identity/final-program mismatch. Stop and clean on sentinel/shape/oracle/timing/telemetry/trigger/deadline failure. Report setup, scored CUDA, provider exposure, derived cost, archive hashes, and authenticated zero instances/disks separately.
