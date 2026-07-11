# Sartor calibration status (2026-07-11)

The sim is a structured per-op roofline. Its outputs are interpreted through
two explicit factors rather than hidden tuning:

**sim → reality: achieved = sim × realization × duty**

- **Realization factor ≈ 0.73** — achieved fraction of the structured roofline
  at saturation on well-tuned stacks. Calibrated from the GB200 peak anchor
  (sim 18,336 vs measured 13,386 decode tok/s/GPU, SGLang NVL72, lmsys
  2025-09-25). Covers: kernel-tail losses, real attention efficiency,
  scheduling gaps, fragmentation — everything a roofline can't see.
- **Duty factor ≈ 0.4–0.6** — production fleets average below peak (diurnal
  load). Cross-check: DeepSeek H800 disclosure is a DAILY AVERAGE of 1,850;
  sim peak 4,760 × 0.73 realization = 3,475 achievable peak → implied duty
  0.53. Consistent with their published day/night node fluctuation.

**Anchor table**

| Anchor | Type | Sim | Measured | Interpretation |
|---|---|---|---|---|
| SmolLM2-135M, M4 Metal (ours) | measured lab | 1,004 | 977 | +2.7% (direct fit) |
| Qwen2.5-0.5B, M4 Metal (ours) | measured lab | 1,062 | 966 | +10.0% |
| Qwen3-4B, M4 Metal (ours) | measured lab | 124 | 112 | +10.2% (predicts kernel-limited regime) |
| DSv3 GB200 NVL72 decode (lmsys) | public peak | 18,336 | 13,386 | realization 0.73 |
| DSv3 H800 decode (DeepSeek) | public daily avg | 4,760 | 1,850 | 0.73 realization × 0.53 duty ✓ |

**Usage discipline**
- RATIOS between configs sharing a stack class (all tiers of the moat study)
  are quoted directly — realization/duty largely cancel.
- ABSOLUTE $/Mtok quoted externally must be multiplied by realization (and
  duty if fleet-average economics are claimed). The cost crate's utilization
  parameter partially overlaps duty — do not double count: for peak-econ
  quotes use utilization=duty×0.9.
- Lab anchors validate op-level physics (occupancy curves, dispatch floors);
  datacenter anchors validate system-level composition (EP, MLA, MoE mix).

**Known gaps (in order of impact)**
1. No direct measurement on H100/H200-class hardware (rental campaign is the
   #1 de-risk item — converts realization from one-anchor to measured).
2. EP load imbalance as a scalar; real EPLB dynamics are workload-dependent.
3. Prefill modeled GPU-local (no EP sharding of prefill).
4. Quality effects of model surgery are evidence-tiered, not yet all measured
   (twin workstream running).
