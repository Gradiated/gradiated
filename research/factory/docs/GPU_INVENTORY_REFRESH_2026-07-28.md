# GPU inventory refresh — 2026-07-28

## Decision question

Is the lab's accelerator, provider, availability, and planning-price inventory current enough to choose credible inference co-design targets and place experiments without repeating market research?

Scope: commercially relevant inference accelerators already in the catalog, newly released 2026 accelerators, public experiment rates, medium-term production planning rates, and authenticated availability in providers already configured for the lab. This is not a measured performance ranking or an availability guarantee.

## Conclusion

The catalog is current enough for research selection after this refresh. It now covers 37 accelerator targets and 15 price-planning entries. Four material 2026 omissions were added: NVIDIA Rubin, AMD MI455X/CDNA5, Google TPU7x Ironwood, and AWS Trainium3.

The highest-impact correction is Nebius B200 pricing. The prior inventory selected the page's historical “before June 1, 2026” rates of $2.90 preemptible and $5.50 on-demand. The current effective rates are $3.95 and $7.15. The placement selector now returns the current $3.95 rate for the available 8-GPU preemptible B200 candidate.

## Method

- Re-read all catalog source URLs. Thirty of 38 existing URLs returned HTTP 200 to a direct reachability check. Eight AMD pages rejected the non-browser request, so their current product pages were inspected through browser retrieval instead.
- Preferred official architecture documentation and product specifications over aggregators.
- Treated public on-demand and preemptible rates as experiment references, not production rates.
- Kept production values as explicitly labeled 12–24 month, 8–64 GPU planning estimates. A matching written quote supersedes them.
- Queried Nebius capacity advice and Gcore's authenticated read-only inventory. No resources were created or destroyed.

## Material hardware additions

| Accelerator | Vendor-reported facts added | Research significance |
| --- | --- | --- |
| NVIDIA Rubin | 224 SMs, 896 Tensor Cores, 288 GB HBM4, 22 TB/s, 50 PFLOPS NVFP4, NVLink 6 at 3.6 TB/s | New TMA descriptor handling, 3-bit LUT weights, activation sparsity, and tile-level dependent execution create non-transferable inference opportunities. |
| AMD MI455X | CDNA5, 256 WGPs with Wave32, 432 GB HBM4, 23.3 TB/s, 192 MB L2, 40.3 PFLOPS MXFP4 | L2 multicast, direct global-to-LDS movement, WGP clustering, and Wave32 materially change AMD kernel design. |
| Google TPU7x | 192 GB HBM, 7.38 TB/s, 2.307 PFLOPS BF16, 4.614 PFLOPS FP8, two chiplets and four SparseCores | Chiplet-local sharding and VMEM-sized Pallas kernels are first-class constraints. |
| AWS Trainium3 | 144 GB HBM3e, 4.9 TB/s, 2.52 PFLOPS MXFP8, up to 144 chips with 2 TB/s NeuronLink per chip | NKI, MXFP4, and all-to-all NeuronSwitch make model/compiler co-design plausible. |

Evidence for these rows is vendor-reported or official documentation. Public toolchain target IDs, per-SM/WGP resource limits, power envelopes, and broad rentable capacity are not yet established for Rubin and MI455X, so those fields remain null or explicitly marked pre-broad-availability.

## Current planning-price inventory

Planning values below are derived medium-term production estimates, not quotes.

| Accelerator | Planning USD/GPU-hour | Current public anchors |
| --- | ---: | --- |
| L40S | 1.10 | Nebius $0.65 preemptible / $1.35 on-demand; RunPod $0.99 |
| H100 SXM | 2.80 | Nebius $2.15 / $3.85; RunPod $2.99 |
| H100 PCIe | 2.50 | RunPod $2.89 |
| H200 SXM | 3.25 | Nebius $2.45 / $4.50; RunPod $4.39 |
| B200 SXM | 5.15 | Nebius $3.95 / $7.15; RunPod $5.89 |
| B300 SXM | 5.80 | Nebius $4.30 / $7.85; RunPod $7.39 |
| RTX PRO 6000 Blackwell | 1.55 | Nebius $0.95 / $1.80; RunPod $1.99 |
| A100 80 GB PCIe / SXM | 1.20 / 1.30 | RunPod $1.39 / $1.49 |
| L4 | 0.34 | RunPod $0.39 |
| A40 | 0.38 | RunPod $0.44 |
| RTX 6000 Ada | 0.73 | RunPod $0.84 |
| RTX 4090 / 5090 | 0.60 / 0.86 | RunPod $0.69 / $0.99 |
| MI355X | 2.60 | TensorWave market listing $2.95 |

Consumer-card prices require a separate reliability, density, networking, and operations adjustment before production decisions.

## Authenticated provider state

- Nebius: projects exist in `eu-north1`, `eu-west1`, `uk-south1`, `me-west1`, and `us-central1`. Capacity advice returned an 8-GPU preemptible B200 candidate in `us-central1` and an 8-GPU preemptible H200 candidate in `eu-west1`. It returned no matching 8-GPU B300, H100, L40S, or RTX PRO 6000 candidate during this check.
- Gcore: the authenticated catalog returned one on-demand 8x H100 node in Sines-2 at EUR 21.816/hour. All other cataloged GPU flavors reported zero capacity. The lab project has a zero one-server H100 quota, so the visible node is not allocatable without a quota change.
- RunPod: current public Pod and cluster pricing was refreshed. Reserved prices are quote-only and no dependable authenticated capacity snapshot was obtained.
- Scaleway: credentials remain unavailable, so live capacity was not verified.

## Sources

| Source | Type | Used for |
| --- | --- | --- |
| [NVIDIA Rubin architecture](https://developer.nvidia.com/blog/inside-nvidia-rubin-gpu-architecture-powering-the-era-of-agentic-ai/) | Official technical documentation | Rubin architecture and co-design levers |
| [AMD MI455X specifications](https://www.amd.com/en/products/accelerators/instinct/mi400/mi455x.html) and [CDNA architecture](https://www.amd.com/en/technologies/cdna.html) | Vendor specification / official architecture | MI455X and CDNA5 |
| [Google TPU7x documentation](https://docs.cloud.google.com/tpu/docs/tpu7x) | Official documentation | Ironwood architecture |
| [AWS Trn3 UltraServers](https://aws.amazon.com/ec2/instance-types/trn3/) | Vendor specification | Trainium3 |
| [Nebius Compute pricing](https://docs.nebius.com/compute/resources/pricing) | Vendor pricing | Current effective Nebius rates |
| [RunPod pricing](https://www.runpod.io/pricing) | Vendor pricing | Current public Pod and cluster anchors |
| [MI355X market listing](https://gpus.io/en/gpus/mi355x) | Independent market listing | Current TensorWave public rate |
| [Authenticated Gcore snapshot](GCORE.md) | Vendor API output | Catalog, rates, capacity, quota |

## Uncertainty and refresh contract

- Confidence is high in architecture fields directly stated by vendors and in public prices with explicit effective dates.
- Confidence is medium in production planning rates because reserved prices are mostly quote-only.
- Confidence is low in future availability and price for Rubin, MI455X, TPU7x, and Trainium3 until the lab has account-level capacity and quotes.
- Price evidence expires after three days. Hardware review expires after seven days. Capacity must always be re-queried immediately before allocation.
