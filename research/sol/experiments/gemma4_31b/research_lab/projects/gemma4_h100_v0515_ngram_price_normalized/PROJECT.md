# H100 price-normalized v0.5.15 NGRAM placement

## Question

Can one H100 SXM run the exact official SGLang v0.5.15 Gemma 4 31B
dynamic-FP8, E5M2 page-1 KV, native depth-12 NGRAM stack cheaply enough to
beat the campaign's `$0.14/M` sustainable planning target?

This is a hardware-placement hypothesis independent of the H200 runtime
semantic discriminator. It must not change the selected runtime, checkpoint,
workload, NGRAM geometry, or output semantics.

## Why this matters

The calibrated immutable-corpus H200 discriminator measured long accepted
drafts, zero queue, and `$0.10553298850106702/M` at the experimental
`$2.46/GPU-hour` rate, but one request-790 semantic mismatch prevents
promotion. The official v0.5.15 H200 lane tests a source-level semantic repair.
Separately, the fresh shared price inventory puts H100 planning cost at
`$2.80/GPU-hour` versus H200 at `$3.25/GPU-hour`, so H100 can be slower and
still improve production economics if the exact stack fits and remains
saturated.

## Scope and immediate experiment

Mechanically verify `DIRECTOR_BINDING.json`. Using the shared accelerator and
price inventories plus official v0.5.15 source/image evidence:

1. derive exact H100 memory fit for model weights, runtime state, CUDA graphs,
   and the bound workload's KV/cache geometry;
2. derive the maximum H100 elapsed/service-time hurdle for `$0.14/M` using the
   bound 759/791-request token denominator and current planning rate;
3. trace H100 support for every bound runtime feature and identify only
   hardware-specific launch, kernel, capacity, or topology risks;
4. return one execution-ready matched H100 packet with a smallest
   activation/fit discriminator and conditional endpoint, or typed `none`.

This phase has `$0` provider authority. Do not claim a GPU, create a provider
resource, pull an image on a paid guest, or transfer a checkpoint. A later
paid extension remains in this project and requires separate director
authorization. Do not perform a runtime, representation, flag, or hardware
sweep.

## Decision gate and budget

Nominate H100 only if the exact stack fits with safe runtime headroom, official
v0.5.15 supports the required path, and the measured service-time hurdle is
plausible without transferring H200 throughput as evidence. Bind the exact
checkpoint, image, requests, semantics, price source, launcher, provider need,
deadline, and first scientific arm.

- Provider/GPU spend: `$0`.
- Wall clock: 60 minutes.
- Local compute: at most 1 CPU-hour.
- Storage: at most 2 GiB; no model weights or container layers.
- Required artifacts: concise causal fit/hurdle analysis, one immutable
  execution packet or typed `none`, `RESEARCH_LOG.md`, and `STATUS.json`.
