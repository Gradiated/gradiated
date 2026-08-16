# H200 BF16 decision

The direct H200 BF16 stock packet is conditionally nominated, not launched. The read-only Nebius catalog supports the matched one-GPU `gpu-h200-sxm` / `1gpu-16vcpu-200gb` shape, while the current H100 owner remains the sole provider-mutating resource.

H100 and H200 have the same 132 SMs, BF16 peak, 50 MB L2, and Hopper kernel environment. Their only relevant stock-model hardware change is HBM: 3.35 to 4.80 TB/s (1.432836x), with 80 to 141 GB capacity. Therefore compute-, SM-grid-, and scheduler/launch-limited endpoint time has a maximum H200 gain of 1.0x. Pure weight streaming has a 1.432836x upper bound; a mixed endpoint must have at least 45.8355% recoverable HBM time to clear the 1.160714x production planning hurdle.

The exact 62.546 GB weights cannot reside in 50 MB L2. The primary c16 prompt KV state is 12.234 GB, which fits H100 before runtime overhead; c16 at 10K is 19.818 GB and exceeds H100's 17.454 GB post-weight raw headroom but fits H200. This is a concrete headroom discontinuity, not an endpoint economics result.

After the H100 terminal, use the packet only if its matched telemetry conservatively supports the HBM-share gate or shows that the headroom discontinuity improves completed-work economics. Otherwise close H200 without a paid create. The adverse shared-rate ratio is 1.44x, above the raw bandwidth bound, so a fresh matched quote is mandatory for any production claim.
