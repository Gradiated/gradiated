# Decision: typed none

## Superseded by 2026-07-17 correction: conditional component packet

The original typed-none result is preserved as evidence but is no longer branch-decisive. The correction separates prefill from decode, excludes vision/small inactive bytes from active text traffic, and uses the reconciled FP8-KV contract. W4 primary c16 is 31.158 GiB and 10K c16 is 34.717 GiB; 10K c32 is 44.091 GiB against the 44.704-GiB envelope. At c16, the phase-aware analytical service floor is 0.507631 s/request for W4 versus 0.873407 s/request for FP8, a 41.880% reduction. This changes the branch to the conditional synthetic packet in [W4_COMPONENT_PACKET.json](W4_COMPONENT_PACKET.json), while exact W4 producer provenance and quality remain absent.

See [W4_C16_BOUND_V2.json](W4_C16_BOUND_V2.json) for the authoritative corrected result. The packet is not executed, does not authorize provider/CUDA work, and remains gated on the live FP8 owner's typed terminal and cleanup plus later director admission.

The exact arithmetic is favorable but the project does not nominate a paid W4 arm. Group-128 AWQ-style W4 reduces the quantized language-linear payload to 15.273 GB and total retained weights to 20.343 GiB. With a 5 GiB reserve, primary c16 totals are 36.738 GiB with BF16 KV and 34.234 GiB with explicit per-token-head FP8 KV, below the 44.704 GiB conservative envelope. c32 requires explicit FP8 KV; BF16 KV is over the envelope.

At 864 GB/s, the optimistic primary 4,214+358 token weight-streaming bound at M=16 is 0.138421 requests/s for W4 versus 0.081979 requests/s for inherited conservative FP8: a derived 40.776% reduction, above the 25% screen. At the $1.10/GPU-hour planning rate this bound is $0.002207/request; it is not endpoint evidence and still exceeds the market target because it charges a full weight stream for every token.

First-party pinned vLLM source provides a real SM89 Marlin WNA16 consumer: AWQ uint4 or GPTQ uint4b8, group sizes -1/32/64/128, FP16/BF16 activations, and K/N tile constraints of 128/64. All Gemma fused linear shapes (`5376→16384`, `5376→20480`, `5376→43008`, both output projections, and down projection) are tile-exact with group 128. The tied 262144×5376 embedding/output remains BF16 and is not claimed as a W4 consumer.

The missing condition is an exact target-revision W4 producer/checkpoint route. The source audit only proves a synthetic checkpoint-free component proxy; no CUDA invocation or quality-preserving consumer run was authorized here. Therefore the terminal nomination is typed `none`. Any future arm must bind producer bytes and exact base revision, invoke this real Marlin consumer, and pass raw-output/feature validation.

Evidence labels: geometry and predecessor values are measured metadata; byte totals and bandwidth equations are derived; runtime support is first-party source inspection; quality and timing are unmeasured.
