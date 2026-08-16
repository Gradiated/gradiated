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

The offline phase nominated one exact packet and is complete. The director
authorizes a paid extension under `DIRECTOR_EXECUTION_BINDING.json`. First
materialize and hash-verify the manifest-bound checkpoint under the expanded
project storage contract and emit `PRECREATE_TERMINAL.json`. Do not create or
claim a provider resource before both that terminal and the durable `$5`
reservation exist. Provider creation remains director-owned. After a
registered H100 bench exists, execute only the packet's 171-request
discriminator and its strictly conditional fresh-container endpoint. Do not
perform a runtime, representation, flag, or hardware sweep.

## Decision gate and budget

Nominate H100 only if the exact stack fits with safe runtime headroom, official
v0.5.15 supports the required path, and the measured service-time hurdle is
plausible without transferring H200 throughput as evidence. Bind the exact
checkpoint, image, requests, semantics, price source, launcher, provider need,
deadline, and first scientific arm.

- Provider/GPU spend: at most `$5`, only after durable reservation.
- GPU claim: at most 45 H100 minutes.
- Pre-create wall clock: at most 90 minutes under one durable local owner.
- Local compute: at most 2 CPU-hours.
- Storage: at most 70 GiB project-local, including the immutable checkpoint.
- Required additional artifacts: `PRECREATE_TERMINAL.json`, one measured
  discriminator, and a conditional endpoint or typed boundary.

## Director endpoint recovery

Repair 5 produced the valid canonical discriminator: 171/171 requests,
normalized semantics, native depth-12 activation, zero failures, queue peak
14, final queue zero, and `0.7073339939 s/request`. At the campaign's
`$2.80/hour` H100 planning rate this is approximately `$0.133700/M` total
tokens at 90% utilization, below the `$0.14/M` target.

The conditional endpoint then lost SSH when the lifecycle watchdog deleted
the provider resource. That is an invalid external-cleanup attempt, not an
endpoint sample or scientific rejection. Preserve the discriminator and never
replay it.

`DIRECTOR_ENDPOINT_RECOVERY_BINDING.json` admits one replacement H100 after
the cumulative `$9.00` project reservation is durable. Use one bounded durable
owner for exact checkpoint and packet staging, server startup, the unconsumed
791-request endpoint, retrieval, and release. Allow at most 70 additional H100
minutes, release by `09:10Z`, and protect the bench through `09:15Z`.
