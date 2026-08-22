# Research log

## 2026-07-28T16:36Z — admitted

Admitted as an independent deep, zero-GPU mechanism lane while the M32
recovery-5 owner holds the B200. The immediate result is one source- and
geometry-bound cross-operator implementation or typed rejection; no bench or
provider operation is authorized.

## 2026-07-28T17:02Z — exact-consumer discriminator complete

Question: can a recurring post-attention residual/RMSNorm/FP8-quantize/gate-up
block explain endpoint-scale residual latency without overlapping the active
M32 scaled-MM dispatcher work?

Action: traced the hash-bound Gemma4 decoder, RMSNorm, online-FP8 quantizer,
scaled-MM consumer, compilation defaults, endpoint terminal, and residual
discriminator. Implemented `b200_cross_operator_consumer.py`, which fails
closed on the pinned vLLM version and source hashes and compares the stock
compiled expression with the existing residual-aware
`rms_norm_dynamic_per_token_quant` primitive before the unchanged exact
Cutlass gate-up consumer. The offline describe and artifact hash checks pass.
No GPU, endpoint, provider, or dispatcher operation was performed.

Evidence: this block occurs once per layer, or 60 times per M32 decode step and
21,480 times across the bound 358-step endpoint batch. Only the residual-add
prologue can be credited independently: 0--1 launch and 0--344,064 logical
activation bytes per call (0--21,480 launches and 0--7,390,494,720 bytes per
batch). The lower bound is zero because the retained endpoint has no generated
Inductor code or kernel trace proving the add was separate. Gate-up accounts
for an unchanged 231,211,008 weight bytes and 14,797,504,512 useful FLOPs per
call, and no scaled-MM dispatch byte or launch is credited here. Closing the
endpoint gap solely through this block would require 199.443 microseconds per
call; ideal eliminated HBM traffic is only 28.869 microseconds per request.

Interpretation: reject RMSNorm+dynamic-FP8 fusion as a primary mechanism. The
pinned default O2 path already delegates that fusion to Inductor, and vLLM
already exposes the exact residual-aware fused primitive. Retain the
hash-bound consumer only as a stackable discriminator for whether the
preceding residual add remains outside that generated prologue.

Next move: director review
`B200_FP8_CROSS_OPERATOR_DISCRIMINATOR.json` (SHA-256
`777e1e54f10a2a26a6b4dcf08518a2a994bce35edb8988d2906d992fba592506`).
Keep the primary lane rejected. Run the component-only B200 discriminator only
if a stackable projected improvement of at least 0.002 seconds/request is
decision-relevant; otherwise close without claiming a bench.

## 2026-07-28T20:30Z — exact B200 component negative

Question: does the residual-aware pinned FP8 primitive preserve the exact
stock residual/RMSNorm/quant/gate-up consumer contract while delivering a
stackable component saving?

Action: claimed the director-bound B200 at 20:20:37Z and ran one fresh-process
stock/candidate generation after bounded same-claim repairs for remote output
generation, container UID, vLLM config context, and the exact Cutlass weight
layout. The final packet is hash-bound by
`PRECLAIM_B200_CROSS_OPERATOR_TERMINAL.json`; the component terminal is
`artifacts/b200-cross-operator-component-20260728t2016z/FINAL_TERMINAL.json`
(SHA-256 `aa341657553da2499c37aa18cd9aa2af4f735db86d84d84deddd446ca9249405`).
No model was loaded, endpoint request submitted, or M32 dispatcher changed.

Evidence: the B200 SM100 / CUDA 12.9 / pinned vLLM program completed both
first-call markers and all five finite correctness cases, then measured 8
warmups plus 40 CUDA-event samples per arm. Stock p50 was 0.101216 ms and
candidate p50 was 0.065824 ms, a 35.392 us/call apparent component advantage
that projects to 0.0237569 s/request. It is not promotable: all activation and
gate-up cases violate the required numerical envelope (relative L2
0.0143–0.0170 vs 0.005, max absolute up to 0.3278), despite finite outputs and
exact residual equality. The binding required paired timing for this finite
negative, which was retained.

Interpretation: reject this residual-aware primitive as a semantics-preserving
runtime promotion under the bound stock `QuantFP8.forward_native` contract.
The apparent timing improvement cannot offset the correctness failure. The
bench was released available at 20:30:32Z with its image and caches intact;
the conservative director-assigned project exposure is $3.7782.

## 2026-07-29T02:46Z — stock-semantics task graph closes as typed none

Question: can an exact M32 task graph preserve every stock RMSNorm,
per-token-E4M3/FP32-scale, residual, scaled-MM, cast, and rounding byte while
removing non-overlapping dispatch work from the bound endpoint?

Action: verified the two scheduled inputs once, traced 11 files at pinned vLLM
commit `6d4a8e6d...`, and inspected the exact endpoint launcher. Implemented
`b200_semantics_preserving_taskgraph.py`: its offline describe/export path and
target-SM100 run path capture only the compiled stock boundary plus unchanged
`cutlass_scaled_mm`, fail closed on all source hashes, and require `torch.equal`
for E4M3 activation, FP32 scale, BF16 residual, and BF16 consumer output across
five cases before timing. No GPU, endpoint, provider, or consumed component was
touched.

Evidence: the launcher has no eager, compilation-config, or optimization-level
override (SHA-256 `ffb96e2e...`); pinned O2 selects
`FULL_AND_PIECEWISE`, and `GPUModelRunner` wraps decode in
`CUDAGraphWrapper(FULL)`. The exact local graph would retain both stock device
kernel nodes and all tensor bytes. In the bound endpoint it removes zero graph
launches, zero CUDA API calls per selected block, zero synchronizations, and
zero DRAM/L2 bytes because the outer decode graph already owns the same
submission boundary. Offline validation and DevEx checks pass.

Interpretation: typed none,
`typed_none_no_non_overlapping_runtime_boundary`. The implemented graph is a
working standalone oracle/discriminator path, not a deployable endpoint
intervention; nesting or replacing it inside the full-model graph adds no
non-generic boundary and risks fixed-address copies or illegal nested capture.

Next move: director review
`B200_SEMANTICS_PRESERVING_TASKGRAPH_OFFLINE_RESULT.json` (SHA-256
`407d2a4f...`). Do not spend B200 time on this endpoint. Reopen the provided
bitwise component runner only if an exact endpoint trace first proves M32
decode is outside both full and piecewise CUDA graph capture.
