# Research log

## 2026-07-17 — telemetry-conditioned H200 packet

Question: can one quality-preserving BF16 H200 plausibly beat the H100 cost point without transferring a bandwidth specification into throughput?

Action: consumed the frozen exact geometry, the active H100 contract once, shared accelerator and pricing inventories, and the named shared Nebius lifecycle code. Performed one read-only Nebius platform-catalog query; no provider resource was mutated and the live H100 owner was not polled.

Evidence: H100 and H200 share 132 SMs, 989.5 BF16 TFLOPS, and 50 MB L2, while HBM changes from 3.35 to 4.80 TB/s (1.432836x) and capacity from 80 to 141 GB. The exact 62.546 GB weights exceed L2 by about 1251x. The production rate ratio is 1.160714x, requiring at least 45.8355% recoverable HBM endpoint time under the mixed Amdahl bound. H200's catalog entry exposes `gpu-h200-sxm`, `1gpu-16vcpu-200gb`, 141 GB GPU memory, and preemptible eligibility; its read-only response SHA-256 is recorded in `BOTTLENECK_BOUND.json`.

Interpretation: pure HBM streaming can theoretically clear the base hurdle; same Hopper compute, tile geometry, and scheduler behavior cannot. H200 has a real raw-memory discontinuity for c16 10K prompts, but no unmeasured capacity benefit is credited as economics.

Next move: after the H100 typed terminal and verified empty inventory, consume `H200_PACKET.json` only if the specified HBM-share or completed-work headroom gate passes; otherwise close the H200 line without a paid create.
