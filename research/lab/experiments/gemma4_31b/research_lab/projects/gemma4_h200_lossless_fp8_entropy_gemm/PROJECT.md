# Lossless FP8 entropy-to-GEMM on H200

## Question

Can the exact runtime E4M3 transformer-weight stream be compressed with a
tile-random-access entropy representation and decoded directly into Hopper
tensor-core consumption quickly enough to reduce complete-request cost?

## Why this matters

The measured exact-weight screen covers all `29,396,828,160` runtime FP8
bytes and reports mean 32x128-tile entropy of `6.480648 bits/byte`. Its consumed
top-31/5-bit/escape codec expanded every block to a `1.067636` stream ratio,
but that rejects only that code, not the information-theoretic opportunity.
An implementation approaching the measured entropy could remove roughly 19%
of FP8 weight bytes before decoder cost. This is independent of the active
hybrid-attention endpoint.

## Immediate discriminator

Use `$kernel-research`, but remain zero-GPU in this phase:

1. Consume
   `../gemma4_mi355x_lossless_fp8_weight_stream_codesign/FULL_CHECKPOINT_STREAM_RESULT.json`
   (SHA-256
   `16950c9160918898b9f74f727335862a84c9a5f6f10ee3edad34fe2c2e6618f5`)
   and its exact 32x128 K-major/N-major tile contract.
2. Select one preregistered tile-random-access representation suited to SM90
   decode-to-WGMMA consumption, such as canonical tabled ANS or bounded
   canonical Huffman with escape-free 256-symbol coverage. Do not sweep codec
   families after observing full-checkpoint results.
3. Measure exact encoded size and bitwise decode across all runtime FP8 bytes,
   charging tables, offsets, alignment, padding, fallback, and tile random
   access. Reuse prior streamed statistics when sufficient; stream the named
   runtime tensors once only when exact encode/decode proof requires it.
4. Derive the minimum decoder throughput, registers, shared memory, tile
   staging, and overlap required to beat the contemporaneous H200 dense-FP8
   consumer and the locked `0.500119281574996 s/request` campaign target.
5. Implement a source-complete SM90 compressed-tile-to-first-WGMMA path and
   exact CPU reference, or return typed `none` if size plus a physically
   optimistic decoder cannot yield a positive complete bound.

This is lossless representation work: decoded FP8 bytes must be bitwise exact.
Nominal entropy, a standalone decoder without the first matrix-core consumer,
or a size result that ignores metadata cannot promote.

## Resources and budget

- At most 90 wall-clock minutes, 6 CPU-hours, 20 GiB RAM, 32 GiB
  project-local scratch, and `$0` provider spend.
- Exact model revision:
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- No GPU claim, SSH, provider mutation, endpoint, checkpoint mutation, format
  sweep, lossy fallback, or full checkpoint copy.

Expected terminal: `LOSSLESS_FP8_ENTROPY_GEMM_OFFLINE_TERMINAL.json`, containing
the bound codec, full encoded-size and bitwise-decode evidence, direct input
hashes, decoder resource/throughput threshold, complete analytical bound, and
the SM90 consumer source or typed `none`.

## Portfolio-changing result

- A bitwise-exact stream materially below one byte/weight whose conservative
  decoder threshold is physically credible admits one H200 exact-consumer
  component.
- Expansion, insufficient net byte reduction, or an impossible decoder
  throughput/resource bound closes this entropy realization without GPU
  spend.

