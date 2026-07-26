# Gemma 4 MI355X lossless FP8 weight-stream co-design

## Question

Can one decode-friendly blockwise lossless code compress the exact runtime
E4M3FN transformer weights enough that a real MI355X/gfx950 decode-to-GEMM
dataflow improves price-normalized service cost, while reproducing every FP8
weight bit and preserving all model capacity? Return a checkpoint-measured,
source-complete physical candidate or typed `none`.

This changes model-chip dataflow rather than placement, precision, rank,
sparsity, or capacity. It must not alter or delay the preserved MI355X FP8
next-dollar lifecycle.

## Authoritative bindings

- Model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only,
  non-reasoning mode.
- Primary workload: background c32 around 4,214 prompt and 358 output tokens
  per request, with 12.7% of prompt tokens served from cache.
- Exact checkpoint bytes already exist as read-only hardlinks under
  `projects/gemma4_current_runtime_frontier/inputs/checkpoint/`; do not
  download, copy, rewrite, or relink them. Mechanically bind the config,
  index, both shard identities, and tensor map before analysis.
- The bound config SHA-256 is
  `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`;
  the safetensors index SHA-256 is
  `d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2`.
- The preserved MI355X FP8 placement uses the current vLLM
  `Fp8PerTensorOnlineLinearMethod` and `ROCmFP8ScaledMMLinearKernel`, FP8 KV,
  and a BF16 tied head. Its analytical service bound is
  `0.6000950932112802 s/request`, consisting of
  `0.363906344068055` transformer-linear seconds plus
  `0.23618874914322519` fixed non-transformer seconds.
- At the `$2.60/hour` planning rate its hurdle is
  `0.625149101968745 s/request`. Clearing the high end of the production
  range, `$2.75/hour`, requires at most `0.5910500600431771 s/request`, hence
  no more than `0.3548613108999519` transformer-linear seconds after every
  compression/decompression cost.
- The existing MI355X FP8 exact-shape falsifier remains the sole funded
  lifecycle at `$0.9833333333333333`. This project has no authority to amend,
  prepare, execute, or stack onto it.

## Scope

1. Reproduce the current runtime's deterministic per-tensor OCP E4M3FN weight
   quantization for every transformer Q/K/V/O and gate/up/down tensor from the
   exact checkpoint. Exclude the BF16 tied embedding/head and keep FP8 KV
   unchanged.
2. Stream the two safetensors shards without copying them. Measure exact byte
   frequencies, block entropy, incompressible-tail behavior, alignment, and
   metadata for all 29,396,828,160 transformer parameters. Persist shard and
   encoded-stream hashes plus aggregate and worst-layer results.
3. Preregister one fixed, independently decodable block code before the full
   pass. It must support bounded random tile access and deterministic offsets;
   do not benchmark a compressor family or select the best result after a
   sweep.
4. Implement an exact CPU reference encoder/decoder and require bitwise
   equality with every source FP8 byte. Any lossy reconstruction, changed
   scale, dropped value, pruning, sparsity, low rank, dictionary approximation,
   or capacity reduction is invalid.
5. Use `$kernel-research` to bind a concrete gfx950 producer/consumer path from
   compressed HBM bytes through offset/metadata load, decode, staging, and the
   first decision-bearing matrix-core GEMM tile. Charge instructions, branches,
   metadata, alignment, worst-case blocks, registers, LDS, occupancy, cache
   pollution, synchronization, and fallback. A standalone decoder or nominal
   entropy result is not a source-complete consumer.
6. Reconstruct the whole request from the preserved non-overlapping MI355X
   accounting. Credit only bytes demonstrably avoided on the exact
   transformer-linear path. Vendor peaks, ideal entropy, CPU codec throughput,
   another accelerator, or another model cannot supply target timing.
7. Emit `LOSSLESS_FP8_WEIGHT_STREAM_SCREEN.json` as either:
   - `exact_weight_lossless_stream_candidate`: full exact-checkpoint
     compression is measured, decode is bitwise exact, the gfx950
     decode-to-GEMM path is source-complete without fallback, all costs are
     charged, and the conservative service bound is at most
     `0.5910500600431771 s/request`, with one finite target-MI355X
     discriminator; or
   - `typed_none`: identify the first decisive entropy, worst-block, metadata,
     random-access, source-consumer, resource, overhead, or economic gate.

## Invalid shortcuts

- Do not download or duplicate the checkpoint, claim hardware, contact a
  provider, use paid APIs, or create resources.
- Do not use gzip/zstd file compression, whole-file averages, synthetic
  weights, or BF16 entropy as proof of runtime FP8 tile compressibility.
- Do not sweep codecs, block sizes, quantization formats, layers, or hardware.
- Do not change FP8 values or scales, quantize the tied head, prune, sparsify,
  factorize, delete capacity, or rely on later training.
- Do not stack prompt-state, global-KV, recurrent-local, speculation,
  scheduling, placement, or other gains.
- Do not promote a physical candidate as target-hardware measured,
  quality-certified, or production-eligible.

## Resource envelope

- Wall clock: at most 4 hours.
- Local compute: at most 16 CPU-hours.
- Storage: at most 4 GiB of new code, compact fixtures, and results; do not
  persist a second full checkpoint or full compressed-weight image.
- Provider/API spend: `$0`.
- If the exact streaming pass outlives one response, start at most one bounded
  durable local owner in this same project with a four-hour deadline and
  atomic terminal output. Do not create a support project.

## Portfolio consequence

A qualifying result becomes a distinct lossless dataflow candidate for later
director ranking; it does not displace or amend the preserved FP8 lifecycle in
this turn. A typed negative closes only this exact blockwise lossless
FP8-weight stream mechanism.
