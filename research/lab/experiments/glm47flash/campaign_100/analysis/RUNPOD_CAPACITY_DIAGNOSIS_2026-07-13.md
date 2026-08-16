# RunPod capacity diagnosis — 2026-07-13

## Decision

RunPod is not globally out of GPU capacity. The live authenticated inventory at `2026-07-13T13:49Z` advertised at least one Secure H100 SXM pool as `High`, Secure A100 SXM as `Medium`, and multiple other relevant SKUs as `Low`. The account had zero active Pods at `2026-07-13T13:50:19Z`, and RunPod's public status page reported GPU Cloud operational.

The failed campaign placements are best explained by two concurrent causes:

1. **Measured capacity pressure and advisory/racy stock:** the exact A100 SXM datacenters used by the campaign were only `Low`/`Medium`, and a stock label did not guarantee that the subsequent allocation would succeed.
2. **Measured provider control-plane failure:** the `US-MD-1` create request returned an internal RunPod response-parsing error before a Pod existed. This is not a model, image, runtime, quality, or benchmark failure.

Therefore, “RunPod is simply at capacity” is too broad. Capacity is tight for the campaign's exact placement, but at least one failure crossed a provider control-plane defect and other GPU pools were advertised as obtainable.

## Question and scope

- Question: are RunPod's failed placements caused only by platform-wide GPU exhaustion, and which potentially relevant GPUs are currently advertised as obtainable?
- Scope: read-only authenticated RunPod GPU, datacenter, price, reservation, and Pod inventory; the public RunPod status page; prior campaign allocation evidence.
- Non-scope: no Pod creation, no spend, no workload execution, and no inference-performance or cost claim.
- Falsifier for the platform-wide-capacity hypothesis: any relevant SKU/datacenter with `Medium` or `High` stock, or evidence that a failed request reached a non-capacity control-plane error.

## Live observations

### GPUs that could fit native BF16 GLM-4.7-Flash

The model previously loaded at about 56.27 GB, so the relevant single-GPU native-BF16 floor is 80 GB. Prices below are provider-returned on-demand prices for the queried one-GPU pool and are not measured allocation costs.

| GPU | VRAM | Live aggregate stock | Datacenter evidence | Provider price | Campaign interpretation |
|---|---:|---|---|---:|---|
| H100 SXM | 80 GB | High | `AP-IN-1` High; several other pools Low | $2.99/h Secure | Best advertised chance of placement, but changes hardware and repeats the previously measured cold-image/SLO risk. |
| A100 SXM | 80 GB | Medium | `US-MD-1` Medium; `US-KS-2`, `US-MO-1`, `US-WA-1` Low | $1.49/h Secure | Closest stock control. Both exact campaign pools already rejected POSTs; `US-MD-1` exposed an internal parsing failure. |
| A100 PCIe | 80 GB | Low | `CA-MTL-3`, `US-KS-2` Low | $1.39/h Secure | Earlier Secure and Community placement lineage was exhausted. |
| H100 NVL | 94 GB | Low | `US-GA-2` Low | $3.19/h Secure | Fits, but is a different and more expensive hardware control. |
| H200 SXM | 141 GB | Low in CLI; exact constrained query had reported High | several datacenters Low | $4.39/h Secure | Apparently obtainable but expensive; conflicting advisory labels reinforce that stock is dynamic/query-dependent. |
| RTX PRO 6000 Blackwell Server | 96 GB | Low in CLI; exact constrained query had reported Medium | several datacenters Low | $1.99/h Secure | Attractive price, but changes architecture to unvalidated Blackwell and is not an admissible stock-control result. |
| H100 PCIe, H200 NVL, B200, B300, MI300X | 80–288 GB | None | no nonempty stock observed | not quoted | Not currently obtainable through the observed on-demand inventory. |

The authenticated GraphQL response returned `availableGpuCounts: null` and `maxUnreservedGpuCount: null` for the inspected offers. RunPod therefore exposed qualitative labels, not a count of allocatable machines. RunPod's documentation defines `Low` as very few GPUs and recommends another type or retrying later; it does not describe `High` as an allocation guarantee.

### 48 GB quantized-path candidates

These cannot hold the measured native-BF16 load, but could run the unresolved AWQ intervention if its loader path is fixed and GPU-validated.

| GPU | Live stock | Provider price | Limitation |
|---|---|---:|---|
| A40 | Low Secure | $0.44/h | Prior exact A40 placements failed; AWQ remains GPU-unverified. |
| L40S | Low Secure | $0.99/h | Prior Community request explicitly returned no instances; Secure stock is advisory. |
| RTX PRO 5000 Blackwell | Low Community in exact constrained query | $0.82/h | Different architecture; runtime and loader compatibility unvalidated. |
| L40, RTX 6000 Ada, RTX A6000 | no aggregate stock | not currently quoted in aggregate query | Not presently a credible placement target. |

## Evidence classification

### Measured directly in this audit

- Authenticated GPU and datacenter inventory returned nonempty `High`, `Medium`, and `Low` stock labels.
- `AP-IN-1` was the only datacenter observed with `High` stock for a native-BF16-capable SKU: H100 SXM.
- `US-MD-1` advertised A100 SXM `Medium`; the prior exact POST there returned HTTP 500 before allocation with a provider deployment-response parsing error.
- The account had zero active Pods after the audit. This audit allocated nothing and cost `$0`.

### Provider-documented or provider-reported

- RunPod documents `High`, `Medium`, `Low`, and `None` stock states and says `Low` means very few GPUs are available.
- RunPod documents preferred datacenter IDs and availability-prioritized GPU selection for Pod creation.
- The public status page reported all services online and GPU Cloud operational when checked; it did not report an active platform-wide Pod provisioning incident.

### Inferred

- Capacity contention is a material contributor for the exact A100/A40/L40S campaign pools.
- The `US-MD-1` error establishes that capacity is not a sufficient explanation for every rejection. It does not establish the prevalence or root cause of the internal parsing defect.
- H100 SXM in `AP-IN-1` is the best advertised placement opportunity, not proven allocatable capacity. A create request is the only decisive allocation test and was deliberately not issued in this read-only audit.

## Campaign consequence

The audit does not overturn `STOP_OR_PIVOT`. No stock label supplies the missing matched throughput, quality, TTFT/TPOT, queueing, or cost evidence. Reopening with H100/H200/Blackwell would change the hardware control and, for H100, repeat a failure mode already dominated by provider-side image readiness.

The highest-information next step remains an external placement-quality change: a documented reservation or API-visible deployment queue on an 80 GB NVIDIA host with the exact pinned image confirmed ready. If a best-effort allocation is nevertheless authorized as a new experiment, the live inventory suggests Secure H100 SXM in `AP-IN-1` is the least capacity-constrained target, with a newly preregistered hardware-control interpretation and a strict image-readiness timeout.

## Sources

| Source | Class | Supports | Limitation |
|---|---|---|---|
| Authenticated RunPod GraphQL `gpuTypes/lowestPrice`, `2026-07-13T13:49Z` | measured primary | constrained stock labels and prices | qualitative labels; counts were null |
| Authenticated `runpodctl gpu list --include-unavailable` and `datacenter list`, `2026-07-13T13:49–13:50Z` | measured primary | aggregate and datacenter stock | dynamic snapshot; no allocation guarantee |
| Campaign allocation artifacts and `REPORT.md` | measured primary | exact POST results, error hash, prior H100 image-readiness misses | specific to prior requests and times |
| [RunPod: Manage Pods with GraphQL](https://docs.runpod.io/sdks/graphql/manage-pods) | provider documentation | stock-state meanings and availability query | vendor-authored |
| [RunPod: datacenter CLI](https://docs.runpod.io/runpodctl/reference/runpodctl-datacenter) | provider documentation | datacenter inventory semantics | vendor-authored |
| [RunPod: Create a Pod](https://docs.runpod.io/api-reference/pods/POST/pods) | provider documentation | availability-priority and placement controls | does not promise availability |
| [RunPod status](https://uptime.runpod.io/) | provider status | no reported active platform-wide outage | component health does not prove individual placement health |

