# RTX 6000 Ada price-normalized Gemma placement

## Question

Is a commercially obtainable single-GPU RTX 6000 Ada placement a credible
lower-cost production venue for the exact Gemma 4 31B dual-KV path, with a
current rate and availability model that can deliver the campaign's fixed 20%
price-normalized improvement rather than merely transferring an L40S
component result?

## Why this matters

The current accelerator inventory identifies RTX 6000 Ada and L40S as the
same `sm_89` architecture profile with 142 SMs, 96 MiB L2, 48 GB ECC GDDR6,
broad CUDA/SGLang support, and no NVLink. RTX 6000 Ada is listed at 960 GB/s
and 300 W versus L40S at 864 GB/s and 350 W. That makes it a plausible
production placement for the fixed dual-KV representation, but it has no
joined rate in `gpu_prices.json` and only specialist-cloud availability.
Price, sustained server configuration, exact 48-GB exposure, and practical
access are therefore decision-bearing unknowns. Architecture similarity does
not transfer throughput or economics.

## Authoritative inputs

- `../../CAMPAIGN.md`, especially the fixed
  `0.625149101968745 s/request` qualified denominator,
  `0.500119281574996 s/request` H200 target, and requirement for an equivalent
  20% price-normalized improvement on another accelerator.
- `/root/workspace/research/factory/data/accelerator_inventory.json`, entries
  `nvidia-rtx-6000-ada` and `nvidia-l40s`.
- `/root/workspace/research/factory/data/gpu_prices.json`, whose RTX 6000 Ada price join is
  currently absent and whose L40S committed planning rate is `$1.10/hour`.
- `../gemma4_l40s_dual_kv4_allocator_0953_integration/L40S_DUAL_KV4_ALLOCATOR_0953_OFFLINE_TERMINAL.json`
  (`sha256 e98777580a46ef458e1ea704ceea6fc827030150fe4efa8e67ef380e99fd0090`)
  for the exact 48-GB representation and conditional request equation.

Mechanically resolve these paths and hashes. Treat inventory specifications as
vendor-reported priors and the dual-KV terminal as L40S-scoped until a matched
RTX result exists.

## Scope and method

Use `$evidence-research`. Within 90 wall-clock minutes:

1. Find current primary or direct-provider evidence for at least one
   actually purchasable RTX 6000 Ada server/cloud configuration, including
   whether the guest receives the full 48 GB device, ECC, sustained clocks,
   CPU/RAM/storage/network bundle, region, minimum term, capacity type, and
   single-GPU hourly or monthly rate. Prefer two independent venues when
   available; emit typed no-venue if none is source-complete.
2. Separate on-demand, spot/preemptible, and 12–24 month committed economics.
   Do not convert a consumer workstation purchase price into a cloud rate or
   use promotional credits as the base case.
3. Verify official runtime compatibility facts that could break transfer:
   compute capability, CUDA/driver requirements, container support, FP8/E5M2
   and INT4 execution, available memory, power/cooling, and whether the venue
   exposes a pass-through GPU suitable for custom CUDA extensions.
4. Derive the exact maximum sustainable RTX hourly rate and the required
   RTX/L40S service-time ratio as symbolic functions of the later measured
   dual-KV endpoint. Also evaluate each sourced venue across the campaign
   OpenRouter mix, 90% utilization, headroom, storage, orchestration, failure,
   and availability assumptions. Do not invent an RTX throughput value.
5. Name one authenticated experiment route only if an already configured
   controller or explicit access artifact exists. A market listing is not
   experimental authority.

## Budget and prohibitions

- Provider/GPU/SSH/endpoint spend: `$0`.
- Wall clock: 90 minutes.
- New artifacts: at most 256 MiB.
- Do not create accounts, contact sales, accept terms, reserve capacity,
  purchase hardware, use provider APIs, or expose credentials.
- Do not claim RTX performance from L40S, peak FLOPS, bandwidth, price, or
  shared SM89 identity.
- Do not reopen B200, MI355X, QServe/W4/AWQ, output-head, speculation, or
  scheduler mechanisms.

## Required terminal

Persist `RTX6000ADA_PRICE_NORMALIZED_PLACEMENT_TERMINAL.json` with direct
source citations and retrieval times; exact venue/SKU/capacity/rate terms;
hardware/runtime/access facts; the symbolic and venue-specific price-normalized
hurdles; uncertainty labels; and one of:

- `admit_matched_rtx_component_then_endpoint` with a real authenticated route
  and explicit experiment budget request;
- `preserve_production_lead_no_experiment_route`;
- `reject_current_placement` with the exact rate, access, or support reason.

The result changes the portfolio only by selecting or rejecting a real RTX
placement. It cannot promote the dual-KV mechanism or satisfy the campaign
objective without a matched measured endpoint.
