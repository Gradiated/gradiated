# Exact geometry and runtime opportunity rank

## Question

Which Gemma 4 31B model/runtime/hardware interaction offers the fastest credible path beyond the first stock control, and can the current MTP or async-scheduling arm be made executable before the paid owner needs a retained-session decision?

## Why this runs in parallel

The paid owner should not rediscover architecture or current runtime support while an H100 is live. The exact model is dense and prompt-heavy, with five local attention layers per global layer, a 1,024-token local window, unified global K/V, a large vocabulary/output head, and a supported native MTP path. These features interact differently with prefill, decode, KV capacity, scheduler occupancy, and memory bandwidth. A short `$0` reconstruction can rank interventions and prepare the adjacent arm without delaying the baseline.

## Scope

Use official repository bytes for `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, current official vLLM source/docs, the shared accelerator inventory, the fresh shared GPU-price inventory, and current exact-model market evidence. Download metadata and source only, not weight shards. Do not mutate a provider, spend money, or edit the paid project's files.

Produce content-addressed artifacts in this project that:

1. Reconstruct layer count and local/global pattern; hidden, intermediate, head, head-dimension, K/V, vocabulary/output-head, vision, precision, MTP-assistant, and KV-per-token geometry. Estimate BF16 residency and primary/10K workload KV state. Label every value measured from bytes, derived, or inferred.
2. Map the dominant tensors and primary workload onto H100 SM/tensor-core tile, register/shared-memory, L2, HBM, launch/grid, and occupancy constraints using `research/factory/data/accelerator_inventory.json`. Identify whether prefill, decode weight streaming, output head, attention/KV, launch, or scheduler underfill is the likely cost limiter; do not transfer peak FLOPS into a throughput claim.
3. Bind the current official vLLM Gemma 4 image/source revision and the exact 31B assistant checkpoint revision. Write a minimal launch-delta packet for stock versus native MTP (`num_speculative_tokens=1`) and, as the named fallback, stock versus `--async-scheduling`. Include expected output-equivalence checks and a ten-minute start-readiness test. Place the terminal packet where the paid owner can read it without modifying it.
4. Rank at most three next interventions by likely endpoint impact, information value, time, spend, runtime support, and quality risk. Search across representation/precision, MTP or other decode strategy, prefix/KV state, batching/load shape, output head, kernels, and cheaper production placement. A non-quality-preserving execution proxy may measure a cost mechanism but must be labeled non-deployable.
5. Refresh exact-model external evidence only where it changes the rank. Record the Artificial Analysis provider-comparison details (provider, cache/input/output prices, 7:2:1 blend, speed, latency, workload and recency) and use the repository's current OpenRouter evidence for the primary mix. Pricing inventory is fresh; do not duplicate GPU-price research.

Start with the official sources already identified by the director: the current vLLM Gemma 4 recipe documents one 80 GB NVIDIA GPU as the minimum BF16 placement, its Gemma 4 container, text-only multimodal disabling, async scheduling, and native 31B MTP support. Treat these as current vendor/runtime reports until the paid project measures them.

## Immediate and terminal decisions

Within the first 45 minutes, publish either a typed MTP/async arm packet that the paid owner can start in ten minutes or a negative compatibility result; do not turn it into another readiness project. Continue up to the wall-clock budget only to finish the exact geometry and top-three rank.

- If MTP is source-supported, identity-bound, and launch-ready, it remains the paid session's first candidate.
- If MTP cannot reach start-readiness, promote async scheduling as the conditional adjacent arm; do not delay the stock run.
- Nominate a later paid arm only when its conservative path is at least 5% endpoint cost or it unlocks a concrete cheaper placement/capacity discontinuity.
- Close mechanisms whose exact geometry or runtime support cannot reach that threshold, preserving the negative evidence.

## Budgets and ownership

- Provider spend and mutation: prohibited (`$0`).
- Wall clock: 2 hours.
- Compute: at most 4 local CPU-hours; no CUDA requirement and no model-weight materialization.
- Storage: 2 GiB maximum, with source/metadata caches outside committed artifacts when possible.
- Artifacts: `GEOMETRY.json`, `ADJACENT_ARM_PACKET.json`, and `OPPORTUNITY_RANK.md` (or one typed negative packet explaining why an item is absent).
