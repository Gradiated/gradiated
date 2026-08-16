# Research log

## 2026-07-26T13:32Z — preregister exact tile code

Question: can one independently decodable lossless code reduce the exact
runtime OCP E4M3FN transformer-weight stream enough to repay a fused gfx950
decode-to-MFMA path and reach `0.5910500600431771 s/request`?

Action: preregistered `tensor_top31_u5_escape_v1`: one per-runtime-tensor
top-31 dictionary, fixed 5-bit indices, escape literals, uint32 block
directory, and 4,096-byte blocks mapped bijectively to `32x128` tiles in the
post-transpose `KxN` consumer layout. No codec, size, format, layer, or
hardware sweep was admitted.

The first launcher exited before module quantization because its mechanical
map counted only checkpoint tensors. Inspection localized the missing
`110,100,480` logical weights exactly to the ten global layers whose
checkpoint binds `K=V`; the pinned runtime materializes V by duplicating K.
This was a pre-science mapping defect. The raw traceback is preserved in
`artifacts/full-checkpoint-pass.stdout.log`; only that mapping was amended.

## 2026-07-26T13:56Z — typed none at entropy/economic gate

Action: streamed and SHA-256 verified both read-only safetensors shards,
reproduced all 240 fused runtime tensors with FP32
`max(abs(BF16))/448` OCP-E4M3FN scaling, transposed to the exact `KxN`
consumer order, tiled, encoded, and immediately decoded every block. Each
completed module and its full-block entropy arrays were persisted atomically
under `artifacts/full-checkpoint-pass/`.

Evidence:

- Measured: `29,396,828,160/29,396,828,160` logical FP8 bytes decoded
  bitwise equal with zero mismatches; both shard hashes matched their frozen
  bindings.
- Measured: all `7,176,960` blocks expanded. Aggregate encoded size was
  `31,385,103,914` bytes versus `29,396,828,160` raw bytes, ratio
  `1.0676357239351908`. Mean block entropy was `6.480647886729036`
  bits/byte, but the fixed token-plus-escape realization averaged
  `4,373.010243055555` bytes per 4,096-byte block including its directory
  entry.
- Derived optimistic lower bound: granting zero gfx950 unpack, dictionary,
  directory, literal, branch, LDS, synchronization, register, occupancy,
  cache, MFMA-integration, and fallback cost gives
  `0.6247081622369317 s/request`, already
  `0.033658102193754647` above the `$2.75/hour` target.
- Source-backed/analytical: blocks bind one exact `32x128` B tile feeding
  gfx950 wave64 `16x16x32` OCP-FP8 MFMA fragments. Because compressed HBM
  bytes already exceed stock bytes, every real decode/resource charge is
  nonnegative and cannot reverse the gate.

Interpretation: `LOSSLESS_FP8_WEIGHT_STREAM_SCREEN.json` is typed `none` at
the entropy/economic gate for the consumed preregistered realization. A
target-GPU call would have no decision value and no compatible shared gfx950
bench exists. No checkpoint was copied or downloaded; no GPU was claimed,
provider contacted, resource created, paid API used, or preserved MI355X
lifecycle altered. Cumulative spend is `$0`.
