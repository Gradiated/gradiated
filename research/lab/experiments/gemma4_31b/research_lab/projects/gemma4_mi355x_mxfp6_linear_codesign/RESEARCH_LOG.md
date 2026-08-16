# Research log

## 2026-07-26T13:16:18Z — exact-shape MI355X MXFP6 physical screen

**Decision.** Emit typed `none` with type
`native_mxfp6_activation_producer_and_runtime_dispatch_missing_with_no_scope_matched_target_timing`.
Current dense vLLM cannot bind the admitted native MXFP6 mechanism: every
MXFP6 activation/weight combination is forced through Quark dequantization,
activation QDQ emulation, and high-precision `F.linear`. A maintained direct
hipBLASLt/RocRoller E3M2 block-scale consumer exists, but current vLLM has no
native dynamic MXFP6 activation producer or dispatch to it, and no exact
MI355X timing exists in the zero-spend scope. Candidate whole-request time
therefore remains null rather than being inferred from nominal bytes.

**Source and shape evidence.** All 31 content and behavioral source checks pass
against vLLM `0da6e7f3d6ed50fe1262cc2cf44066989a6b4cdd`, ROCm/rocm-libraries
`1eb022d06b7e2a1b0031d74e96d85a2e9e150c99`, and Quark
`1b229f781a1974cc742884e42d8eefc1eebb4f0a`. Quark supplies the E3M2 six-bit
packing layout, while hipBLASLt binds `bf6_r`, 32-element E8M0 block scales,
FP32 accumulation, BF16 output, packed deterministic MX input generation,
and RocRoller dispatch. The six actual fused consumer families
(sliding/global QKV and O, gate/up, and down) cover both M32 and M384. All K
and N dimensions are multiples of 128; data packing, 32-element scale blocks,
and the documented scale-swizzle geometry require zero padding.

**Physical accounting.** All 60 layers, widths, and 29,396,828,160
transformer-linear parameters are retained. Packed E3M2 weights require
22,047,621,120 data bytes plus 918,650,880 scale bytes, or 22,966,272,000
bytes total. That is a nominal 21.875% reduction from one-byte FP8 weights,
explicitly not timing credit. The preserved FP8 screen assigns
`0.363906344068055 s/request` to transformer linears and
`0.23618874914322519 s/request` to fixed attention, KV, tied-head, launch,
and service work. A qualifying MXFP6 path must therefore put native dynamic
packing, scales/layout, GEMMs, outputs, dispatch, padding, and fallback below
`0.363906344068055 s/request`; no admissible target sample provides that
number.

**Runnable discriminator and limit.** `mi355x_mxfp6_exact_runner.py` binds the
official hipBLASLt synthetic MX producer and RocRoller consumer for all 12
exact M/shape calls, with a bounded tiny layout correctness check and durable
raw/stage artifacts. It is intentionally not promoted: hipBLASLt prepares
packed inputs outside its steady-state timer, so this runner alone does not
charge production activation packing or prove vLLM dispatch/full-shape
correctness. Reopen only after maintained source supplies the native producer
and dense dispatch, then run a target-MI355X paired discriminator that charges
that whole boundary without fallback.

**Attempt amendment.** The first offline generator invocation fetched and
validated all pinned source, then stopped before emitting a result because the
shared accelerator inventory was parsed as an ID-keyed object rather than its
actual list schema. This was an ordinary local observer defect. The parser was
corrected and only the invalidated zero-cost generator was rerun; no GPU or
scientific sample was consumed.

**Resources.** Spend was `$0`. No checkpoint was downloaded, no shared bench
or GPU was claimed, no provider was contacted, no paid API was used, no
resource was created, and the preserved MI355X FP8 lifecycle was unchanged.
The source-complete typed terminal is
`MI355X_MXFP6_PHYSICAL_SCREEN.json`.
