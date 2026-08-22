# Gemma 4 gated-activation to FP8 hot block

## Question

In the exact current SGLang Gemma 4 dynamic-FP8 decode path, can the pinned
gated MLP activation producer be fused with the adjacent per-token E4M3
activation quantizer feeding the down projection, eliminating one launch and
the BF16 activated-state round trip without changing model semantics?

## Why this matters

The exact campaign denominator is `0.625149101968745 s/request` and the target
is `0.500119281574996 s/request`. The source-complete pre-attention norm/FP8
candidate predicts a stackable 0.868% gain. This lane targets a distinct,
larger intermediate at every text layer: for decode M=32 and intermediate
width 21,504, eliminating one BF16 producer/quantizer boundary removes one
launch and up to `2,752,512` logical intermediate bytes per layer call.

## Authoritative identities

Read `../gemma4_h200_current_norm_fp8_hotblock/NORM_FP8_HOTBLOCK_RESULT.json`
once for the exact checkpoint, SGLang image/commit, workload, H200, numerical
convention, denominator, and target. Mechanically confirm the exact Gemma 4
activation class, tensor orientation, down-projection consumer, and scale
contract from the pinned source snapshot named there; do not assume that a
generic SwiGLU or GELU implementation matches.

The production scope is decode M<=32 for the exact c32 workload. Prefill,
attention, checkpoint, weights, residual semantics, FP8 convention, and the
down-projection consumer remain unchanged.

## Immediate evidence path

Work for at most 50 wall-clock minutes with zero GPU, zero CUDA, zero provider
or pool calls, and at most 2 GiB of new storage.

Trace the exact gate/up output through the production gated activation and
dynamic activation quantizer into the first `fp8_scaled_mm` down-projection
consumer. Establish shapes, strides, dtypes, ownership/reuse, stream and graph
behavior, and whether fusion can preserve the pinned finite FP8 semantics.
Then produce one of:

1. source-complete exact-shape CUDA/Triton plus a runtime adapter, CPU oracle,
   and H200 runner that consumes the real layer-0 down-projection weight; or
2. a typed causal falsification showing that the intermediate is reused,
   consumer semantics prevent fusion, numerical error is structurally outside
   the accepted envelope, or the launch/byte upper bound is uncompetitive.

The runner must compare the strongest current activation+quantization control
with the fused candidate at M=1/16/32, fully consume the down-projection
output, and include a CUDA-graph path. Predict the removed launches and
logical/HBM or L2 traffic. A future director—not this project turn—decides
whether a source-complete survivor receives H200 execution.

## Scope boundaries

Do not touch the claimed H200, streamed-global-KV project, or queued norm/FP8
component. Do not perform a generic fusion survey, prefill optimization,
attention work, flag sweep, model change, quality run, or provider
preparation. Publish `GATED_ACTIVATION_FP8_HOTBLOCK_RESULT.json` and update
`STATUS.json` last.

## Portfolio consequence

A source-complete positive becomes an independent exact-H200 component
candidate that can stack with streamed global KV and norm/FP8 fusion. A typed
negative closes only this gated-activation-to-quantizer boundary.
