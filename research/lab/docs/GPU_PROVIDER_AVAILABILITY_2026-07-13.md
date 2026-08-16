# GPU provider availability decision — 2026-07-13

## Question and decision

Which single API-accessible service should the GLM-4.7-Flash campaign add after RunPod rejected pod placement, when the immediate requirement is one on-demand NVIDIA GPU with at least 80 GB VRAM?

Decision: use Nebius as the primary signup. Shadeform is a legitimate-looking, useful discovery/control-plane option, but it is not yet supported as the campaign's primary billing counterparty: independent placement/SLA evidence is sparse, every API key has administrator permissions, its current terms make marketplace fees non-refundable and state that refunds below $500 will not be issued, and a third-party availability history showed weaker one-GPU H100 availability than Nebius during the latest seven-day window. Keep Shadeform as an optional low-balance aggregation fallback. Do not make Lambda the primary fallback during the current capacity crunch.

## Claim scope and falsification

This is an availability-routing decision, not a performance, reliability, security, or cost claim. The hypothesis is that an aggregated inventory and launch API is more likely to place one admissible 80 GB GPU than another single-provider account. It is falsified if Shadeform's authenticated inventory has no admissible offer, or if two materially distinct launch attempts against offers marked available fail before allocation.

## Method

Reviewed recent Reddit and Hacker News reports returned by provider-specific searches, then checked official API and billing documentation. Community reports were treated as anecdotal; vendor documentation was used only to establish API behavior and product capability. Retrieval date: 2026-07-13.

## Evidence

| Source | Date | Type | Decision-relevant result |
| --- | --- | --- | --- |
| [RunPod GPU supply megathread](https://www.reddit.com/r/RunPod/comments/1ttfe7h/gpu_supply_and_availability_megathread_with/) | 2026-06-01, updated | community/vendor-moderated | Reports an industry-wide high-end GPU crunch and rapidly consumed H100/H200/B200 additions. |
| [Google Cloud H100 stock-out discussion](https://www.reddit.com/r/googlecloud/comments/1uf3b6k/total_stock_out_of_h100_vms_in_north_america/) | 2026-06-25 | community anecdote | One user found no H100 placement across usual US regions; a commenter reported most Lambda inventory out of capacity. |
| [Recent GPU rental discussion](https://www.reddit.com/r/deeplearning/comments/1usbezt/where_do_you_actually_rent_gpus_these_days_h100/) | 2026-07-10 | community anecdote | Describes Lambda/on-demand RunPod as stable when available and Vast/community supply as cheaper but more failure-prone. Very small sample. |
| [DigitalOcean GPU unavailability report](https://www.reddit.com/r/digital_ocean/comments/1u8v7p1/why_is_this_problem_always_happening/) | 2026-06-18 | community anecdote | Reports a GPU droplet unavailable for two days; reply says stock was exhausted. |
| [Shadeform introduction](https://docs.shadeform.ai/getting-started/introduction) | current at retrieval | vendor documentation | Documents one API for pricing, availability, and lifecycle operations across 15+ providers. |
| [Shadeform quickstart](https://docs.shadeform.ai/getting-started/quickstart) | current at retrieval | vendor documentation | Documents `available=true` inventory queries, wallet-backed launch, polling, and capacity-race handling. |
| [Shadeform instance/cluster types API](https://docs.shadeform.ai/api-reference/clusters/clusters-types) | current at retrieval | vendor documentation | Returns provider, region, GPU geometry, price, and current availability. |
| [Shadeform authentication](https://docs.shadeform.ai/api-reference/authentication) | current at retrieval | vendor documentation | States that all API keys have administrator permission; keys are hashed and can be rotated/revoked. |
| [Shadeform Terms of Service](https://shadeform.com/terms-of-service) | 2026-06-29 | legal terms | Marketplace fees are non-refundable and the terms state that refunds below $500 will not be issued. Services are provided as-is and as-available. |
| [Y Combinator company record](https://www.ycombinator.com/companies/shadeform) | current at retrieval | independent company directory | Lists Shadeform as an active S23 company founded in 2023 with 11 team members. This supports legitimacy, not service reliability. |
| [GPU Finder H100 availability history](https://gpufinder.dev/gpu/h100) | verified 2026-07-12 | third-party derived tracker | Hourly API-derived history reports 51% seven-day availability for one-GPU H100 through Shadeform versus 100% for Nebius; it explicitly warns that reported stock does not guarantee placement. |
| [Nebius compute pricing](https://docs.nebius.com/compute/resources/pricing) | current at retrieval | vendor documentation | Confirms on-demand H100/H200-class VM products; it does not prove current allocatable capacity. |

## Result and uncertainty

Measured campaign evidence shows RunPod placement failure for this account. Community evidence suggests the shortage is broader than RunPod and specifically weakens Lambda and DigitalOcean as availability-first choices. Shadeform has reasonable legitimacy signals—an active YC listing, documented credential handling, a trust center, and a vendor-reported SOC 2 Type II attestation—but there is insufficient independent evidence to call its control plane or underlying machines production-reliable. Its unfavorable small-refund language and full-admin API keys materially increase bounded-campaign risk. A current third-party tracker favors Nebius for recent one-GPU H100 availability, although that is API-stock history rather than measured successful placement.

Vast.ai may expose more low-cost individual offers, but heterogeneous hosts and community reports of instability make it a weaker choice for clean matched benchmark evidence. It remains a useful last-mile falsification venue with strict host filters.

## Published on-demand price comparison

Retrieved 2026-07-13. These are vendor-published compute prices, not measured allocation costs or cost-per-token evidence. Nebius's unified rates include the preset's GPU, vCPU, and RAM; both providers bill running compute per second. Persistent disk and ancillary resources remain additional.

| One-GPU regular/on-demand VM | Nebius | RunPod Secure | Nebius difference |
| --- | ---: | ---: | ---: |
| H100 SXM/NVLink, 80 GB | $2.95/h | $2.99/h | $0.04/h or 1.34% lower |
| H200 SXM/NVLink, 141 GB | $3.50/h | $4.39/h | $0.89/h or 20.27% lower |

Nebius also publishes preemptible H100 at $1.25/h and H200 at $1.45/h. Those rates are not controls for regular RunPod Pods because interruption risk changes the service contract. Nebius documents `1gpu-16vcpu-200gb` presets for both H100 and H200, so its per-GPU prices do not require renting an eight-GPU node. H100 is limited to Nebius `eu-north1`; H200 is offered in multiple regions.

Sources: [Nebius compute pricing](https://docs.nebius.com/compute/resources/pricing), [Nebius GPU VM presets](https://docs.nebius.com/compute/virtual-machines/types), [RunPod GPU pricing](https://www.runpod.io/pricing), and the campaign's authenticated RunPod H100 observation in `experiments/glm47flash/REPORT.md`.

## Next action and kill condition

After receiving a Nebius API credential, query authenticated inventory and quotas without allocating. Select the cheapest available one-GPU H100, H200, or A100-80GB VM that satisfies the experiment contract. Pre-register a small placement/load smoke test, allocate once, retrieve and hash evidence, delete the instance, and verify deletion. If Nebius cannot allocate two materially distinct admissible placements, use Shadeform only with the minimum wallet balance the user is willing to lose, a dedicated key, an automatic time/spend deletion threshold, and immediate post-experiment key revocation.

### Credential smoke — 2026-07-13

The Nebius CLI `0.12.242` was installed from the current official installer. Before the role change, authenticated IAM reached Nebius but Compute returned `PermissionDenied`; no resource was created and cost was `$0`. After the user added the dedicated service account to the tenant's `editors` group, read-only instance, disk, project, subnet, platform, quota, and capacity-advice calls succeeded. Fresh advice reported allocatable regular one-GPU H100 capacity in multiple `eu-north1` fabrics and one-GPU H200 capacity in `eu-north1`, `eu-west1`, and `us-central1`.

The first bounded regular H100 smoke then measured an instance in `RUNNING` state with public and private IP allocations, proving that this account can place the SKU. A local observer bug rejected the public address's `/32` suffix before SSH; the instance and managed disk were subsequently absent in fresh inventories. The conservative allocation upper bound is `$0.171193495`; provider invoice evidence is pending. This upgrades Nebius from vendor/third-party availability evidence to measured campaign placement evidence, while admitting no inference or SLO-goodput result yet.
