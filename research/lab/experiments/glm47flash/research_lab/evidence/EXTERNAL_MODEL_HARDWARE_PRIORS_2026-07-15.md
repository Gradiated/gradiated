# External GLM-4.7-Flash benchmark and hardware priors — 2026-07-15

## Decision

Use current online model-specific benchmarks and cross-provider hardware prices to widen the candidate set. Nebius remains a convenient experiment venue; it is not the assumed production host. External evidence selects experiments but does not replace a scope-matched measured cost result.

## Claim scope and falsification

These are measured or vendor-reported external priors plus transparent derived economics. They do not establish our workload quality, reliability, availability, or sustainable cost. A candidate is falsified for the campaign if a matched 8,192-input/1,024-output run cannot meet the quality contract or improve the current V21 `$0.670/M` output-token incumbent after material lifecycle costs.

## Decision-relevant evidence

### Exact-geometry public benchmark

Lambda reports GLM-4.7-Flash on the campaign's exact 8:1 geometry—8,192 input and 1,024 output tokens—with 256 prompts and concurrency 32 under SGLang:

- B200: `902.74` output tok/s.
- H100: `660.67` output tok/s.

This is valuable evidence that c32 and a different runtime/hardware stack can materially exceed V21's c8 `355.772` output tok/s. It is not an A/B against V21: checkpoint representation, SGLang revision, GPU SKU, concurrency, request content, and quality evidence differ.

At current public on-demand prices, high throughput does not by itself beat V21:

| Benchmark and price pairing | Derived compute-only $/M output tokens | Scope |
| --- | ---: | --- |
| Lambda B200 throughput + RunPod B200 `$5.89/h` | `$1.812` | Cross-provider analytical pairing |
| Lambda H100 throughput + RunPod H100 SXM `$2.99/h` | `$1.257` | Cross-provider/SKU analytical pairing |
| Lambda B200 throughput + Lambda B200 `$6.99/h` | `$2.151` | Same provider, lifecycle costs excluded |
| Lambda H100 throughput + Lambda H100 SXM `$4.29/h` | `$1.804` | Same provider, lifecycle costs excluded |

The useful conclusion is not "buy Hopper/Blackwell". It is to sweep higher concurrency and runtime choices while pricing every placement independently.

### Low-price hardware

RunPod currently lists A40 48 GB at `$0.44/h` and RTX A6000 48 GB at `$0.49/h`; its storage is separately priced. An A40 needs `192.022` output tok/s to beat V21 by 5% (`$0.6365/M`) and `203.704` output tok/s to reach `$0.60/M`, before lifecycle overhead. This makes A40 the best current fixed-price single-GPU falsifier. Vast.ai may be cheaper, but its official documentation says prices are market-driven and must be queried live through its dashboard, CLI, or API; compute, storage, and bandwidth must be combined.

### Exact-model software and model opportunities

- Vortex reports a RoPE-aware sparse-attention design for GLM-4.7-Flash on one B200. On AIME26 with a 32K generation budget, full attention sustains `1,031` tok/s at mean@16 `0.765`; the RoPE-aware design is roughly `4x` faster at mean@16 `0.752`, with up to `4.7x` at a tighter block budget. This is high-impact measured prior art with available code, but its 32K generation workload and B200 backend do not transfer directly to the campaign's 1,024-output workload. The cheapest next evidence is a source/config audit and an 8K/1K attention-share bound before any port or paid run.
- Unsloth reports approximately `13,000 tok/s` throughput on one B200 without GLM-4.7-Flash MTP and `1,300 tok/s` with MTP—an observed 10x regression in that configuration. The workload and quality contract are not campaign-matched, so this is a runtime-selection warning and reproduction lead, not an economic claim.
- The official Z.ai model card identifies GLM-4.7-Flash as a 30B-A3B MoE model. Runtime and representation results must preserve the exact model behavior; third-party quantizations require fresh quality evidence.

## Candidate ranking from this sweep

1. **Run the already authorized A40 matched falsifier** if live capacity/rate and exact identity preflight pass. It has the shortest route to a cheaper measured point.
2. **Audit the Lambda SGLang c32 configuration against V21** to isolate which differences are testable on retained hardware: concurrency, scheduler, runtime, and representation. Promote only one high-information bridge.
3. **Bound Vortex sparse attention at the 8K/1K workload** using retained traces and source/config inspection. Promote a component or server experiment only if the prospective end-to-end effect remains at least 5% with a quality-preserving path.
4. **Continuously query global spot/marketplace prices** after measuring a hardware/runtime point. Production placement is a separate optimization over rate, availability, interruption, storage, transfer, and orchestration.

## Sources

| Source | Date/revision | Retrieved | Evidence type | URL |
| --- | --- | --- | --- | --- |
| Lambda, “How to deploy GLM-4.7-Flash on Lambda” | Current page | 2026-07-15 | Provider-measured benchmark | https://lambda.ai/inference-models/zai-org/glm-4.7-flash |
| Lambda AI cloud pricing | Current page | 2026-07-15 | Vendor-reported price | https://lambda.ai/pricing |
| RunPod GPU Cloud Pricing | Current page | 2026-07-15 | Vendor-reported price and storage terms | https://www.runpod.io/pricing |
| Vast.ai pricing documentation | Current docs | 2026-07-15 | Official marketplace/cost methodology | https://docs.vast.ai/guides/instances/pricing |
| Vortex paper, arXiv:2606.06453v1 | 2026-06-04 | 2026-07-15 | Measured research result | https://arxiv.org/abs/2606.06453 |
| Vortex project page and code links | Current page | 2026-07-15 | Author-reported result/code | https://infini-ai-lab.github.io/vortex_torch/ |
| Unsloth GLM-4.7-Flash guide | Current page | 2026-07-15 | Vendor/community measured runtime result | https://unsloth.ai/docs/models/glm-4.7-flash |
| Z.ai GLM-4.7-Flash model card | Current revision | 2026-07-15 | Primary model identity/quality description | https://huggingface.co/zai-org/GLM-4.7-Flash |

## Limitations and next update

Prices and availability are unstable and must be refreshed at dispatch and production-decision time. External benchmark request content, model/checkpoint bytes, runtime commits, sampling, and quality evidence are incomplete or mismatched. Update this brief when a new exact-model benchmark changes candidate ordering; do not accumulate a catalog for its own sake.
