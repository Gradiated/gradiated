# W4 output-head L40S microbenchmark

## Question

Does an exact-shape Marlin W4 implementation of GLM-4.7 Flash's output head run at least `3.408x` faster than the pinned BF16 output-head path at c16-relevant decode shapes on L40S?

## Why it matters

`lm_head_w4_bridge` packed and unpacked the real `[154880, 2048]` head at zero spend. The actual symmetric group-32 W4 payload is 170.156 MiB versus 605.0 MiB BF16, with relative-L2 weight error 0.09261; SM89 shape legality passes. The pinned compressed-tensors selector cannot attach that scheme to `ParallelLMHead`, so a full checkpoint arm is premature, but this is now an exact and inexpensive runtime-kernel question rather than a representation question.

The retained head interval ceiling is 14.09% and the campaign needs a 9.9551% wall-time reduction. Therefore candidate head time must be no more than 29.346% of BF16, or `3.4077x` faster, before any loader/integration overhead. The ideal payload ratio is only `3.5556x`, leaving almost no endpoint headroom. A target-GPU component measurement can close this line faster and more credibly than another full model session.

## Scope and experiment contract

This project is the sole provider owner for one L40S component session after authenticated zero-instance/zero-disk inventory. Use the proven shared lifecycle in `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py`, the digest-pinned image `vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`, and one external systemd owner plus absolute cleanup watchdog. If needed, minimally generalize that shared controller to accept explicit remote-script and benchmark-script inputs while preserving its existing defaults and tests; integration, durable preflight, measurement, retrieval, and cleanup must complete in this turn rather than returning another readiness artifact.

The maximum provider exposure is 1,600 seconds and `$0.40`, including cleanup reserve. Stage only the compact inputs required to reproduce the real-head pack manifest from `../lm_head_w4_bridge/`; do not transfer or load the full model. On one retained allocation, compare the exact runtime BF16 output projection with an explicit Marlin W4 output-layer implementation at `M=1,8,16`, identical `[M,2048] x [2048,154880]` geometry, fixed seeds, adequate warmup, repeated CUDA-event timing, and synchronization outside timed regions. Record p50/p95 latency, speedup, outputs/error diagnostics from identical activations, peak VRAM, GPU clocks/utilization/power, setup versus useful GPU seconds, image/source/input hashes, provider spend, archive hash, and verified zero final inventory.

Do not claim that compressed-tensors can load a quantized `ParallelLMHead`, run a full server, change the model workload, repair native MTP, or evaluate broad quality. One material in-place benchmark correction is allowed while the allocation remains retained. A source/kernel incompatibility, invalid output, timing failure, or sub-threshold result is a scientific closure, not a reason for a successor controller.

## Resources

- Real pack/error/loader evidence: `../lm_head_w4_bridge/`.
- Residual and head attribution: `../residual_w4_completion/` and `../output_head_architecture/`.
- Current c16 denominator: `../nebius_current_awq_c16_direct/`.
- Shared lifecycle and benchmark tools: `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/`.

## Portfolio-changing result

Close the W4-head lineage if the valid `M=16` speedup is below `3.408x`; report `M=1/8` as workload-shape sensitivity. Nominate a later full-runtime output-layer integration only if `M=16` clears `3.408x`, all correctness/error and lifecycle gates pass, and the result has enough margin to survive the distinction between the 14.09% interval ceiling and endpoint wall time. Even a pass is architecture-cost evidence only; production quality remains deferred.
