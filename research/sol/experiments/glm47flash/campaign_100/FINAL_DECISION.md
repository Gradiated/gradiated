# GLM inference co-design campaign decision

Decision: `STOP_OR_PIVOT`.

The resumed RunPod test did not produce a GPU allocation. Both exact Secure A100-SXM placements were rejected before pod creation, so they cost `$0`, required no teardown, and generated no model or performance sample. The second request's safely captured provider body identifies a RunPod internal deployment-response parsing failure rather than a model/runtime error. Final inventory is empty and billing remains 22 rows at `$4.944724685296023` provider-settled account lifetime spend.

## What is measured

- The pinned native-BF16 GLM/SGLang path had historical smoke compatibility, but this campaign still has no valid stock throughput or SLO result.
- Community and Secure A100 PCIe requests, followed by exact `US-KS-2` and `US-MD-1` A100-SXM requests, all failed before allocation and added `$0`.
- An exact `Low` or `Medium` RunPod availability label did not guarantee POST success.
- The account has no template or capacity reservation; the public Pod API has no machine/cache-host selector.
- Campaign-additional spend is `$0.273464527`, entirely the conservative charge for the earlier interrupted L40S allocation. `$99.726535473` remains unspent.

## What is not known

There is no matched evidence for TTFT, TPOT/ITL, throughput, queueing, quality, SLO-goodput, GPU dollars per token, tuned SGLang, AWQ, a model-specific intervention, provider performance, memory hierarchy, or hardware co-design. The prospective A100-SXM prediction is unscored because no pod ran. Vendor prices and feature descriptions remain vendor evidence, not measured economics.

## Why the campaign stops here

The two changed A100-SXM placement pools are exhausted. Another cold H100 or best-effort A100 request would repeat the provisioning failure mode without a documented reservation or image-ready selector. Later campaign phases cannot answer the business question until the frozen stock and tuned controls both run on matched hardware.

The only admissible next experiment requires an external state change: a documented RunPod reservation or API-visible deploy queue on an 80 GB NVIDIA host with the exact image confirmed ready. Then run the frozen stock harness once and, only if it passes, the matched tuned control on that same machine. Do not build the gateway and do not infer cost improvements from public prices.

The machine-readable record is `DECISION_RESUMED_2026-07-13.json`; the prior 13:00 decision remains preserved as historical lineage.
