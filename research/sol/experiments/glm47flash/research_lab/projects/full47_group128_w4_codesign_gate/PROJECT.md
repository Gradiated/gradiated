# Full47 group-128 W4 co-design gate

## Decision question

Can the exact full-47 checkpoint move its existing group-32 W4 majority—and the tile-legal BF16 head/shared scope—to official symmetric group-128 W4 while staying on pinned SM89 standard and fused-MoE Marlin paths, creating meaningful robust c32 headroom?

The prior selective-W4 lineage closed because its custom nibble encoding was not Marlin `uint4b8`; it produced no scientific result. This is a materially new representation candidate: use the official compressed-tensors compressor, coarsen scales across the already-W4 majority, and require native runtime binding before any checkpoint or provider work.

## Fixed opportunity

The current checkpoint contains `1,838,104,576` bytes of group-32 scale payload. Group 128 removes 75%, or `1,378,578,432 B` (`1,314.715 MiB`). Adding the analytically valid `1,029.967-MiB` head/shared W4 saving projects c32 to about `44,531.019 MiB` before also coarsening the newly added scales—only an arithmetic crossing of the `44,532-MiB` robust limit. Exact metadata, scale, runtime, and newly quantized-scope accounting must produce a real margin.

## Immediate `$0` contract

Within 1,200 seconds, use the immutable checkpoint and pinned vLLM/compressed-tensors image. Do not materialize a checkpoint, use a GPU/provider, install another stack, or build a controller.

- Use only pinned official `compressed_tensors.pack_to_int32`/`uint4b8` representation. For existing W4 tensors, dequantize group 32 then requantize group 128; for head/shared BF16 tensors, quantize directly. No custom nibble packer or self-referential oracle.
- Bind exact group-128 config, native weight registration/load/process, and existing SM89 WNA16 dispatch for ordinary `Linear`, the exact `ParallelLMHead`, and fused routed-MoE. Any fallback, duplicate BF16 residency, missing/unexpected key, broad loader patch, or unsupported target closes.
- Hash and sample real tensors across routed gate/up/down, ordinary attention/MLP, head, and shared-expert families. Record relative L2, max error, saturation, code/scale shapes, and runtime-format pack/depack agreement against group-32 reconstruction or BF16 source. Require finite results, no saturation, and relative L2 `<=0.10` for every preregistered sample.
- Compute exact full-checkpoint payload and c32 projection, including newly added group-128 head/shared scales, metadata, and any mandatory duplicate/repack bytes. Require at least `64 MiB` below the `44,532-MiB` robust peak convention; a one-MiB arithmetic crossing is not nomination.

Return `NOMINATE_GROUP128_COMBINED` only if all representation, native dispatch/load, numerical, and robust-memory gates pass. That result nominates one later full47 c16/c32 endpoint against `594.466/606.355 tok/s`; it is not throughput or deployable-quality evidence. Otherwise return a typed representation, runtime, numerical, or memory close.

## Starting evidence

- `../awq_channelwise_scale_coarsening_gate/` for exact current scale accounting, not channelwise dispatch conclusions
- `../full47_head_shared_w4_c32/` invalid custom-packer evidence and exact tensor scope
- `../residual_w4_completion/`
- `../../hardware/L40S.md`
