# Gemma 4 Gaudi3 runtime and placement co-design

## Question

Can a current purchasable Intel Gaudi3/SynapseAI placement execute the exact
pinned Gemma 4 31B serving graph and conservatively beat the campaign's
`$0.109725/M total tokens` sustainable-cost target? Return a source-bound,
costed target-hardware measurement candidate or typed `none`.

This is a materially different placement from the preserved GPU, TPU, and
Trainium2 frontiers. It must not stack their gains or weaken the exact-model
contract.

## Authoritative bindings

- Model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only,
  non-reasoning mode.
- Primary workload: background c32 around 4,214 prompt and 358 output tokens
  per request, with 12.7% of prompt tokens served from cache.
- Economic target: no more than `$0.109725/M total tokens`, including
  utilization, replicas/headroom, failures/reloads, storage, orchestration,
  and other material costs.
- Comparative H200 target: `0.500119281574996 s/request` from the locked
  `0.625149101968745 s/request` qualified denominator. Gaudi3 placement
  seconds must instead be tied to its complete purchasable topology rate and
  its own price-normalized hurdle.
- Shared accelerator inventory identifies Gaudi3 as a 128-GB HBM2e,
  3,700-GB/s, BF16/FP8 target with eight MMEs, 64 TPCs, 96 MB on-die SRAM,
  and SynapseAI/Optimum Habana/TGI/vLLM serving paths.
- The fresh shared GPU-price inventory has no Gaudi3 entry. Researching the
  missing exact topology, public availability, and current production rate is
  in scope; repeating priced GPU research is not.
- The completed MI355X exact-shape falsifier remains the sole next funded
  lifecycle. This project cannot reorder, prepare, or execute it.

## Scope

1. Bind current official runtime/compiler source for the first actual Gemma 4
   producer and decision-bearing Gaudi3 serving consumer. Consider SynapseAI,
   Optimum Habana, TGI, vLLM-HPU, or another current official path only where
   the exact Gemma 4 contract is present.
2. Verify the exact 60-layer hybrid five-local/one-global attention schedule,
   1,024-token local causal horizon, heterogeneous head geometry, KV layout
   and cache operations, tied 262,144-row vocabulary head, final softcap, and
   sampling path. Generic Gemma, Gemma 2, or dense-attention support is not
   transferable.
3. Derive the smallest purchasable Gaudi3 topology that fits the exact
   checkpoint representation, executable state, c32 KV/cache geometry,
   compiler buffers, and safe replica headroom. Bind tensor/data parallelism,
   precision, graph/static-shape constraints, and interconnect use.
4. Find current official or directly published price and availability
   evidence for that exact topology and purchasing basis. Separate
   experiment/on-demand rates from a credible 12–24 month production
   planning rate and show sensitivity.
5. Require scope-matched performance evidence: an exact-model public
   measurement, exact compiled graph result, or another source-bound result
   that supports a conservative service-time bound. Vendor peaks, nominal
   bandwidth, FLOP counts alone, and transferred GPU/TPU/Trainium throughput
   cannot qualify.
6. Normalize fresh input, cache read, and output costs separately, then the
   campaign workload blend. State the maximum service time allowed at every
   admitted topology rate and charge all-in utilization and reliability
   costs.
7. Emit `GAUDI3_RUNTIME_PLACEMENT_SCREEN.json` as either:
   - `source_bound_gaudi3_measurement_candidate`: exact producer/consumer,
     topology, availability, price, and a conservative path below
     `$0.109725/M` are all bound, with one finite target-Gaudi3 validation
     lifecycle; or
   - `typed_none`: identify the first decisive missing exact consumer,
     compile/runtime capability, capacity, performance, availability, or
     economic gate.

## Invalid shortcuts

- Do not download the checkpoint, use paid APIs, claim hardware, contact
  Intel or a provider, log in, or create provider resources.
- Do not infer performance from BF16/FP8 peaks, price, another Gemma version,
  another workload, another accelerator, or a generic HPU graph.
- Do not call source inspection, a configuration stub, or a self-authored
  simulator execution-ready without the real decision-bearing consumer.
- Do not stack prompt-state, global-KV, recurrent-local, MI355X, B200, H100,
  TPU, or Trainium2 gains.
- Do not repeat the exact-model retail market or existing GPU-price refresh.

## Resource envelope

- Wall clock: at most 90 minutes.
- Local compute: at most 4 CPU-hours; no local accelerator assumption.
- Storage: at most 2 GiB of new source and artifacts.
- Provider/API spend: `$0`.

## Portfolio consequence

A qualifying candidate becomes an independent next-funding option, ranked
against—not ahead of by assumption—the preserved MI355X lifecycle. A typed
negative closes only the current Gaudi3 source/runtime/placement path until
material new exact-model support, availability, pricing, or performance
evidence appears.
