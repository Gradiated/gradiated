# Research log

## 2026-07-15 — Zero-cost c24/c32 saturation falsifier

**Question.** Can one c24/c32 arm credibly clear the 562.050 output tok/s promotion hurdle over measured c16 at 535.286 tok/s?

**Action.** Replayed the retained c16 bundle and wrote/run [saturation_bound.py](saturation_bound.py), producing [SATURATION_BOUND.json](SATURATION_BOUND.json). The calculator uses the exact 8,192/1,024 geometry, cache-off vLLM 0.15.0 settings, c16 server queue/latency, and the 206 retained 1-Hz science-window telemetry samples. Summed queue time was not converted into wall-time share.

**Evidence.** Measured c16 science telemetry averaged 98.36% GPU utilization (p95/max 100%), 252.79 W, and 42,716.65 MiB VRAM, peaking at 44,103 of 46,068 MiB. All 32 requests completed; c16 mean server queue was 2.072 s, p95 TTFT 10.061 s, and worst completion 30.641 s inside the 300 s background envelope. An intentionally optimistic ceiling that converts every sampled mean GPU-idle fraction into useful work is only 544.211 tok/s (+1.667%), below 562.050.

**Interpretation and decision.** Close higher concurrency. Linearizing the observed c16 memory increment gives c24 45,489 MiB (578.65 MiB nominal headroom) but no credible throughput path; c32 46,876 MiB, over the 46,068 MiB device envelope before fragmentation. No c24/c32 arm is nominated. This is a zero-provider derived bound, not a sustainable or quality-adjusted economic claim; the inherited absolute-quality limitation remains.

**Next move.** Retain c16 as the useful current-AWQ L40S scheduling frontier and spend future work on a materially different representation, kernel, hardware, or serving mechanism.
