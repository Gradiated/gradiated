# Research log

## 2026-07-16 — Director opening handoff

- Test only channelwise scale coarsening of the existing W4 majority tensors; preserve depth, expert geometry, MLA/KV, scheduler, and workload.
- Fail first on exact standard-linear plus fused-MoE SM89 dispatch, then on reconstruction, capacity, and the `606.355` endpoint bound.
- This is a `$0` representation falsifier; do not materialize a checkpoint, build a runtime, or prepare provider work.

## 2026-07-16 — Terminal result: CHANNELWISE_W4_CLOSE

- Question/action: bound the exact channelwise payload and reconstruction on real checkpoint data, audit both ordinary-linear and fused-MoE dispatch, then carry exact scale savings through robust memory and endpoint gates.
- Measured artifact: [`CHANNELWISE_W4_GATE.json`](CHANNELWISE_W4_GATE.json). Header scan found 9,259 packed W4 tensors. Replacing BF16 group-32 scales with one BF16 scale per output channel saves 1,805,660,288 bytes (1,722.012 MiB; 8.954% of the checkpoint).
- Measured fixture: streamed `model.layers.1.mlp.experts.0.gate_proj.weight` with shape `[1536,2048]`, native INT32 packed payload and BF16 scales. Channelwise payload shape is `[1536,256]` plus `[1536]` scales and `[2]` shape metadata. Reconstruction is deterministic but semantics-changing: channelwise MSE `0.10756256044922104`, max absolute error `0.6188616071428568` against the groupwise reconstruction.
- Dispatch result: pinned config remains `strategy=group`, `group_size=32`; retained source-bound methods are `MarlinLinearKernel_CompressedTensorsWNA16` and `CompressedTensorsWNA16MarlinMoE`. No exact channelwise loader/method is bound for either path, so a synthetic payload cannot be promoted to runtime support.
- Economics: linear projection moves full-model c32 from `46,875.7` to `45,153.688` MiB, which is nominally below the `46,068` MiB device view but `621.688` MiB above the `44,532` MiB robust limit. The required c16 endpoint improvement remains `9.813%` (`552.171` to `606.355` tok/s), with no scope-matched evidence identifying metadata-byte savings as wall-time transfer. The fresh inventory confirms L40S planning rate `$1.10/hour`; no spend was used.
- Decision/next move: `CHANNELWISE_W4_CLOSE`. No successor under this project contract; reopening requires an exact channelwise loader/kernel implementation and target-GPU measurement.
